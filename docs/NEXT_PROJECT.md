# "Generate Next Project"

One-click, trend-driven content generation from the Insights page.

## Flow

```
Insights ── click ──▶ POST /api/projects/next ──▶ 201 (≈50 ms, no external calls)
                         │  load trends (platform_trends, last 7 days; mock set in demo)
                         │  score vs creator analytics → best trend (or analytics fallback)
                         │  build project + kit + forecast, persist as content_suggestions row
                         └─ enqueue enrich_idea (worker, optional) ──▶ LLM polish → enrichment_status=done
UI modal ── polls GET /api/ideas/{id} every 3 s (≤ 1 min) while enrichment_status == "queued"
        ── Send to Kanban → POST /api/ideas/{id}/to-board → card in "Ideas", kit rendered into notes
        ── Regenerate → rejects the shown draft, excludes its trend, generates the next best
        ── Not this one → rejects;  Close/Esc → stays pending (visible in Explore)
```

## Trend scoring (`services/analytics/trends.py`)

`score = 0.55·relevance + 0.30·momentum + 0.15·freshness`

* **relevance** — creator topics (stems + bigrams from their own titles, redundant fragments collapsed) that
  appear in the trend's title/description/tags, weighted by how those topics perform for this creator.
  The platform *category* is deliberately ignored (too coarse; produced false matches).
* **momentum** — log views/hour normalised across the candidates.
* **freshness** — `exp(-age_h / 72)`; trends older than 7 days are dropped.
* A trend needs score ≥ 0.25 **and** at least one topic match to be used; viral but off-niche trends
  (e.g. a recipe for a camera channel) are shown as "also considered" but never chosen.
* The server never proposes a trend the creator already has an idea for.

## Project (`services/analytics/next_project.py`)

* Platform/format: YouTube trends → YouTube + the creator's best YouTube format; Instagram/TikTok → Reel;
  news → the creator's leading platform.
* Title/hook templates combine a cleaned trend subject ("The 'invisible cut' transition everyone is copying" →
  "The 'Invisible Cut' Transition") with the creator's best matching topic; brand casing is preserved.
* Outline = the format outline with an explicit "why now / trend context" beat.
* Forecast = the normal explainable model × `trend` lift `1 + 0.2·momentum·relevance`, clamped to ≤ 1.25 and
  reported in `factors.extra_lifts` so the prediction review later shows whether the trend bet paid off.
* Kit: shot list, thumbnail text + concept, caption, hashtags, checklist keyed by Kanban column
  (`idea, scripting, filming, editing, published`) and the trend window (publish within N hours).

## Failure modes

| Situation | Behaviour |
|---|---|
| No trends in the DB | analytics fallback, `fallback_reason=no_trends`, `trend_refresh=queued` |
| Trends exist but none fit | analytics fallback, `no_relevant_trends`, off-niche trends listed as alternatives |
| Redis down | project still returned, `enrichment=unavailable`, status cleared |
| Worker has no OpenAI key | `enrichment_status=skipped` (UI stops polling) |
| OpenAI errors | 3 attempts with backoff, then `failed` (UI stops polling, keeps the engine's version) |

## Tests

* `apps/api/tests/test_next_project.py` — scoring, subject cleaning/casing, bounded extra lifts, project
  completeness, regenerate/platform filter, fallbacks, API flow, telemetry.
* `apps/api/tests/test_sql_repo.py` — DB mode with a real `platform_trends` row, enrichment queued/unavailable.
* `apps/worker/tests/test_enrich.py` — worker task against Postgres with a fake OpenAI client
  (success with trend context in the prompt, retry → failed, no key → skipped).
