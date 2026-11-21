# Code Audit — bugs, loopholes and gaps found during the Phase 3 deep-dive

Severity: 🔴 critical · 🟠 high · 🟡 medium · 🔵 low
Status: ✅ fixed in this pass · 🛠 partially addressed · ⏳ documented, not fixed

## Security

| # | Sev | Where | Problem | Status |
|---|-----|-------|---------|--------|
| S1 | 🔴 | `apps/api/app/dependencies.py` | `jwt.decode(..., options={"verify_signature": False, "verify_aud": False, "verify_exp": False})`. **Any** token is accepted; an attacker can mint a JWT with an arbitrary `sub` and read/sync another creator's data. Verified: a token signed with `ATTACKER-KEY` was accepted as `sub=victim-user-id`. Also `print("JWT Header", ...)` leaks headers to logs. | ✅ Signature, `exp` and `aud` are verified with `SUPABASE_JWT_SECRET`; explicit 500 if the secret is missing in non-mock mode. |
| S2 | 🔴 | `apps/web/src/app/explore/page.tsx` + migrations | The browser reads/updates `content_suggestions` directly through Supabase with the anon key. No RLS policy is created in any migration and the query is not filtered by `creator_id`, so every logged-in user sees and can mutate every creator's suggestions. | 🛠 New migration adds RLS policies (`creator_id = auth.uid()`) for the planning tables and `content_suggestions`; Explore now goes through the authenticated API for reads/actions. |
| S3 | 🟠 | `apps/api/app/routers/content.py::sync_content` | Raw exception text is returned to the client (`detail=str(e)`) — may leak tokens/URLs from Google/Meta errors. | ✅ Generic message, full error logged. |
| S4 | 🟡 | `apps/api/app/main.py` | `allow_origins` includes `settings.frontend_url` *and* `allow_credentials=True`; fine, but `allow_methods/headers=["*"]` is broader than needed. | ⏳ |
| S5 | 🟡 | `docker-compose.yml` | `DEBUG` is passed but SQLAlchemy `echo=settings.debug` default is `True` → full SQL (with params) in logs when `.env` omits it. | ✅ `debug` defaults to `False`. |

## Correctness / runtime bugs

| # | Sev | Where | Problem | Status |
|---|-----|-------|---------|--------|
| B1 | 🔴 | `apps/api/app/db/session.py` | Engine is created at **import time** with `settings.database_url`. With the documented default (`MOCK_MODE=true`, no `.env`) the API fails to start: `ArgumentError: Could not parse SQLAlchemy URL`. README's "no credentials needed" is false. | ✅ Lazy engine; mock mode never touches the DB. |
| B2 | 🟠 | `apps/api/app/services/mock_data.py` | Mock feed is regenerated with unseeded `random` and fresh `uuid4()` ids on **every request**. `/feed` and `/summary` disagree, sorting/pagination is unstable, React keys change, and nothing can be linked/predicted/reviewed against a stable post. | ✅ Deterministic seeded generator, cached per process, stable ids. |
| B3 | 🟠 | `apps/web/Dockerfile` | Base image `node:18-alpine`, but `next@16.2.9` requires Node `>=20.9.0` (`node_modules/next/package.json#engines`). Docker build fails. | ✅ `node:20-alpine`. |
| B4 | 🟠 | `docker-compose.yml` / `apps/worker/config.py` | Worker reads `youtube_api_key`, compose only injects `GOOGLE_CLIENT_ID`. `fetch_youtube_trends` always logs "YOUTUBE_API_KEY is not set" and returns `[]` → every trend job ends `no_trends`. | ✅ `YOUTUBE_API_KEY` passed through. |
| B5 | 🟠 | `apps/api/app/routers/content.py::sync_content` | `YouTubeService` uses the **synchronous** `googleapiclient` inside an `async` route → blocks the event loop for the whole sync. Violates the V2 spec ("all heavy external network calls must occur strictly within the worker"). Worker's `process_sync_task` is a stub. | 🛠 Sync wrapped in `asyncio.to_thread`; moving to the worker is tracked in the plan. |
| B6 | 🟡 | `apps/api/app/services/youtube.py::_normalize_videos` | Duration heuristic: the `elif` branch can never be true (`int("1") == 0`), `PT1M` / `PT1M0S` (exactly 60 s) are classified Long-form, and Shorts up to 3 min are all Long-form. | ✅ Proper ISO-8601 duration parser, `<= 180s` + vertical hint → Short. |
| B7 | 🟡 | `routers/content.py`, `routers/metrics.py` | N+1: one `MetricSnapshot` query per post on every feed/summary/insights call. | ✅ Single `DISTINCT ON (post_id)` query via shared `services/posts.py` loader. |
| B8 | 🟡 | `routers/metrics.py` | "Weekly Performance Comparison" sums **lifetime** views by publish weekday — it is not a weekly time series. Mock returns fixed numbers, real returns weekday buckets; labels mismatch the intent. | ✅ Replaced by the analytics engine's posting-time analysis (explicitly "views by publish weekday"). |
| B9 | 🟡 | `services/mock_data.py` vs `routers/content.py` | Engagement-rate definition differs: mock = `(likes+comments)/views`, DB = `(likes+comments+shares+saves)/views`. Mock insights hard-code "Reel on Instagram" regardless of data. | ✅ One definition in `analytics/engine.py`, used by both paths. |
| B10 | 🟡 | `models/creator.py`, `models/suggestion.py` | `onupdate=datetime.utcnow` writes a **naive** datetime into `timestamptz`; asyncpg interprets it as local time → wrong offset on non-UTC hosts. | ✅ `func.now()` server-side. |
| B11 | 🟡 | `apps/web/src/app/insights/page.tsx` | Uses CSS vars that don't exist (`--accent-primary`, `--accent-secondary`, `--border-color`, `--bg-hover`) and an undefined `glass-card` class → invisible borders/backgrounds. | ✅ Vars/aliases added to `globals.css`. |
| B12 | 🟡 | `apps/web/src/app/dashboard/page.tsx::handleSync` | Supabase only exposes `provider_token` right after the OAuth redirect. After a refresh it is `undefined`, the API receives no token, `AggregatorService` silently syncs 0 posts, and the UI reports success. | 🛠 API now returns `success=false` + explanatory message when no provider token is present; UI surfaces it. |
| B13 | 🟡 | `apps/worker/tasks.py` | "Structured RAG" is not RAG: the embedding is stored but never compared against creator content; `confidence_score` is LLM self-reported, not cosine similarity as the model docstring claims; persona ("Keyboard on Clouds") is hard-coded for every creator. | ⏳ Documented; Phase 3 ideas are driven by the creator's own analytics instead. Hook provided for LLM enrichment with real creator context. |
| B14 | 🟡 | `apps/worker/main.py` | Spec promises a 12-hour trend cron; only a 60 s heartbeat exists. | 🛠 12-hour trend cron added (`fetch_trends_for_all_creators`). Nightly auto-review of published cards is on the roadmap (needs the analytics package shared with the worker). |
| B15 | 🔵 | `alembic/versions/a1b2c3d4e5f6` | `sa.Column(..., default=sa.text('gen_random_uuid()'))` in a migration is a client-side default → no `DEFAULT` in the DB. Inserts from Supabase client/SQL without an explicit id fail. | ✅ `server_default=gen_random_uuid()` added in the new migration for all new tables + backfilled for `content_suggestions`/`platform_trends`. |
| B16 | 🔵 | `apps/api/app/main.py` | `init_db()` runs `create_all` in non-mock mode alongside Alembic — schema drift risk (e.g. HNSW index created twice with different names). | ⏳ Documented; recommend `alembic upgrade head` only. |
| B17 | 🔵 | `apps/web/src/app/auth/callback/route.ts` | Falls back to the hard-coded production domain `https://divesocialdata.com` when `NEXT_PUBLIC_SITE_URL` is unset (it is not set in compose) → local logins redirect to prod. | ✅ Falls back to request origin. |
| B18 | 🔵 | `apps/web/src/app/explore/page.tsx` | Realtime subscription handles only `INSERT`; accept/dismiss in another tab leaves stale cards. "Send to Board" sets `converted_to_kanban` and the idea vanishes (no board). | ✅ Now creates a real Kanban card via API; list refreshes. |
| B19 | 🔵 | `docker-compose.yml` | Network is `external: true` but README never says to `docker network create data-dive_datadive_net`. Web image's `NEXT_PUBLIC_API_URL` is unused by the code. | ✅ README updated. |
| B20 | 🔵 | `apps/api/app/models/content.py` | `UniqueConstraint(platform, external_post_id)` is global, not per creator — if two creators ever sync the same media id, the second creator's metrics attach to the first creator's post. | ⏳ Documented. |
| B21 | 🔵 | `routers/content.py::get_feed` | `sort_by=comments` supported in mock path but not DB path; `published_at` sorted as `str(...)` ("None" sorts between values). | ✅ Unified sorting in `services/posts.py`. |
| B22 | 🔵 | `apps/web` lint | `no-explicit-any` error in `insights/page.tsx`, unused imports. README says Next 14; project is Next 16. | ✅ |
| B23 | 🟠 | `apps/web/next.config.ts` | `rewrites()` resolves `INTERNAL_API_URL` at **build** time. The Docker build stage never receives it, so the value injected by docker-compose at run time is ignored; it only works because the default `http://api:8000` happens to match the compose service name. Found while running the standalone build locally (`getaddrinfo ENOTFOUND api`). | ✅ Replaced by a runtime proxy route handler `src/app/api/[...path]/route.ts`. |
| B24 | 🔵 | `apps/web/src/lib/api.ts` | `apiFetch` always calls `response.json()`, so any `204 No Content` endpoint throws. | ✅ |
| B25 | 🔵 | `apps/web/src/app/explore/page.tsx` | `key`/ids aside, the page rendered outside the app shell with a different design system (Tailwind utility classes vs CSS variables), no sidebar. | 🛠 Kept its layout, now uses the authenticated API + session hook. |

## Design gaps that Phase 3 fills

* No comparable cross-platform metric (raw views only).
* No topic or posting-time analysis; "What works" picks the content type with the highest mean engagement rate even with n=1.
* Suggestions have no prediction attached, so nothing can ever be evaluated.
* No production workflow entity, no event history, no feedback loop.
* No tests at all (`apps/api/tests/` added: engine, ideas, learning, kanban, API).
