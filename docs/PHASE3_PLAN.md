# Phase 3 Plan — Analytics & Recommendation System ("Planning Bridge")

## 0. Where the codebase is today (deep-dive summary)

| Layer | State | Notes |
|---|---|---|
| `apps/api` (FastAPI) | Feed / summary / sync / naive insights | All analytics is done in-route with N+1 queries; `MOCK_MODE=true` by default but **crashes on import without `DATABASE_URL`** |
| `apps/worker` (ARQ) | One real task: `fetch_and_analyze_trends` | Pulls top-1 YouTube trending video → OpenAI embed → GPT suggestion → `content_suggestions`. Embedding is never used for similarity; persona prompt is hard-coded; `process_sync_task` is a stub; no 12h cron |
| `apps/web` (Next 16) | `/dashboard`, `/insights`, `/explore` | Explore reads `content_suggestions` straight from Supabase (no creator scoping, no RLS in migrations). "Send to Board" flips status to `converted_to_kanban` but **no board exists** — the idea disappears |
| DB | `creator_profiles`, `content_posts`, `metric_snapshots`, `platform_trends`(pgvector), `content_suggestions` | Alembic migrations exist, but `init_db()` also runs `create_all` in non-mock mode |

The data model is already good enough to build on: `content_posts` + time-series `metric_snapshots` give everything needed for pattern analysis, and `content_suggestions` is the natural "idea" entity.

## 1. Target capabilities

1. **Analyze performance across YouTube and Instagram** — comparable, normalized metrics (a 50k-view Short and a 5k-view carousel cannot be compared on raw views).
2. **Find patterns in topics, formats, posting times** — with sample-size-aware confidence.
3. **Generate tailored ideas** — title, hook, outline, recommended platform/format/time, **and a prediction** of expected performance (so it can be checked later).
4. **Kanban production plan** — turn ideas into cards, drag through stages.
5. **Track each idea** — planning → creation → publishing, with an event log.
6. **Compare published results with the prediction and learn** — link the card to the real post, score the prediction, and feed the error back into a per-creator calibration that improves the next predictions.

## 2. Architecture decisions

* **Analytics engine is pure Python over a normalized `PostRecord` list** (`apps/api/app/services/analytics/`). It does not know about SQLAlchemy or mock data, so it runs identically in mock mode, DB mode, tests, and (later) the worker.
* **Ideas are rules-based and deterministic by default** (template engine driven by the detected patterns). An LLM pass is an *optional enhancement* (worker task, same context payload) — the product must work without an OpenAI key, and predictions must be reproducible to be evaluated.
* **Prediction model** — intentionally simple and explainable:
  `expected_views = platform_median_views × format_lift × topic_lift × time_lift × calibration_factor`, with a range derived from the dispersion of the creator's own history and a confidence derived from sample sizes. Every factor is returned so the UI can show "why".
* **Learning loop** — `prediction_reviews` store predicted vs actual; `creator_calibrations` keep an exponentially-weighted ratio (actual/predicted) per `(platform, content_type)` that scales future predictions. Accuracy (MAPE, hit-rate inside range) is exposed so the creator can see the system getting better.
* **Persistence via a small repository interface** with two implementations: in-memory (mock mode, seeded) and SQLAlchemy (DB mode). Routers and services never branch on `mock_mode` for business logic.
* **Reuse `content_suggestions` as the idea table** (add nullable columns: `hook`, `outline`, `platform`, `content_type`, `recommended_post_time`, `prediction`, `source`, `topics`) so the existing Explore/Realtime flow and the worker keep working.
* **Frontend**: a shared `AppShell` (sidebar + session) replaces the three copy-pasted sidebars; new pages `/analytics`, `/ideas`, `/kanban` (`/board` redirects). Kanban uses native HTML5 drag-and-drop (no new dependency); columns are the production pipeline Ideas → Scripting → Filming → Editing → Published, and Explore sends cards into Ideas.

## 3. Data model additions (Alembic `b3c4d5e6f7a8`)

```
content_suggestions (+ columns)
  hook TEXT, outline JSONB, platform VARCHAR(20), content_type VARCHAR(20),
  recommended_post_time JSONB, prediction JSONB, topics JSONB,
  source VARCHAR(30) DEFAULT 'analytics'   -- analytics | trend | manual

production_cards
  id, creator_id FK(cascade), suggestion_id FK(set null), post_id FK(set null)
  title, hook, outline JSONB, platform, content_type, topics JSONB
  stage VARCHAR(20)  -- idea | scripting | filming | editing | published | reviewed (terminal, shown inside Published)
  position INT, scheduled_for TIMESTAMPTZ, published_at TIMESTAMPTZ
  prediction JSONB, notes TEXT, created_at, updated_at

production_events
  id, card_id FK(cascade), from_stage, to_stage, note, created_at

prediction_reviews
  id, card_id FK(cascade), post_id FK(set null), creator_id
  predicted JSONB, actual JSONB, views_ratio FLOAT, er_delta FLOAT
  verdict VARCHAR(20)  -- outperformed | on_target | underperformed
  lessons JSONB, reviewed_at

creator_calibrations
  creator_id, platform, content_type, factor FLOAT, samples INT, updated_at
  UNIQUE(creator_id, platform, content_type)
```

## 4. API surface

```
GET  /api/analytics/overview            cross-platform comparison + normalized KPIs
GET  /api/analytics/patterns            topics / formats / posting-time patterns + findings
GET  /api/analytics/learning            calibration factors, prediction accuracy, review history

POST /api/ideas/generate                generate N tailored ideas (persisted as suggestions, source=analytics)
GET  /api/ideas                         list ideas (status filter)
POST /api/ideas/{id}/to-board           create Kanban card from idea (status → converted_to_kanban)
POST /api/ideas/{id}/dismiss

GET  /api/kanban/board                  columns + cards
POST /api/kanban/cards                  manual card
PATCH/api/kanban/cards/{id}             edit fields
POST /api/kanban/cards/{id}/move        {stage, position}  (validated transitions, event logged)
DELETE /api/kanban/cards/{id}
GET  /api/kanban/cards/{id}/events
POST /api/kanban/cards/{id}/link-post   {post_id} | {auto: true}
POST /api/kanban/cards/{id}/review      compare predicted vs actual, store review, update calibration
GET  /api/kanban/cards/{id}/review
```

## 5. Work breakdown

| # | Item | Files |
|---|---|---|
| A | Fix blocking bugs that the new work depends on (lazy DB engine, deterministic mock data, JWT verification, tz-aware `onupdate`) | `db/session.py`, `services/mock_data.py`, `dependencies.py`, models |
| B | Analytics engine: normalization, baselines, topic/format/time patterns, findings | `services/analytics/engine.py`, `topics.py` |
| C | Prediction + idea generator (templates, hooks, outlines, recommended slots) | `services/analytics/ideas.py`, `prediction.py` |
| D | Review & learning (compare, verdict, lessons, calibration update) | `services/analytics/learning.py` |
| E | Repositories (memory + SQL), models, migration | `repositories/`, `models/planning.py`, `alembic/versions/b3c4…` |
| F | Routers + schemas | `routers/analytics.py`, `ideas.py`, `kanban.py`, `schemas/planning.py` |
| G | Tests (engine, ideas, learning, kanban transitions, API in mock mode) | `apps/api/tests/` |
| H | Frontend: AppShell, `/analytics`, `/ideas`, `/board` (+ card drawer, review panel), Explore "Send to Board" → real card | `apps/web/src/…` |
| I | Worker: optional LLM enrichment task, creator-aware persona, 12 h trend cron | `apps/worker/tasks.py`, `main.py` |
| J | Docs/README, docker env fixes | root |

## 6. Status after this pass

| Item | Status |
|---|---|
| A Foundation fixes | ✅ lazy engine, deterministic mock data, JWT verification, server-side timestamps |
| B Analytics engine | ✅ `services/analytics/{records,topics,engine}.py` — normalized relative performance, shrunk lifts, findings |
| C Prediction + ideas | ✅ `prediction.py`, `ideas.py` — 6 strategies, angle library, format-specific outlines |
| D Review & learning | ✅ `learning.py` — verdicts, lessons, EWMA calibration, accuracy summary, auto-match |
| E Persistence | ✅ memory + SQL repositories, models, migration `b3c4d5e6f7a8` (validated up/down/up on Postgres 16) |
| F API | ✅ `/api/analytics/*`, `/api/ideas/*`, `/api/kanban/*`; legacy `/feed`, `/summary`, `/insights` now share the engine |
| G Tests | ✅ 33 unit/API tests (mock mode) + 2 DB integration tests (`TEST_DATABASE_URL`) |
| H Frontend | ✅ `AppShell`, `/analytics`, `/ideas`, `/board` (DnD + drawer + review), Explore via API, runtime API proxy |
| I Worker | 🛠 `enrich_idea`, creator-aware prompt, 12 h cron. Sync-in-worker and nightly auto-review remain on the roadmap |
| J Docs / Docker | ✅ README, `.env.example`, Node 20 image, env passthrough, audit doc |

### Known limitations / next steps
* Topic extraction is lexical (stems + bigrams over titles). It finds recurring themes but not semantics; the stored trend embeddings could be reused for clustering later.
* Predictions are point-in-time: a review compares against the *latest* snapshot, so reviewing a 2-day-old post under-counts. `min_age_days` exists on the review endpoint; the UI currently passes 0.
* Calibration is per (platform, format). With few reviews it moves half-way towards the first observation and then by EWMA (α = 0.35); bounds 0.25–4.0.
* The worker cannot import the API's analytics package (separate build contexts), which is why auto-review is not a cron yet. Extracting `services/analytics` into a shared package is the clean fix.
