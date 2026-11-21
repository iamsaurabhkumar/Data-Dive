# 📊 Data-Dive — Content Creator Analytics Dashboard

A data-first analytics engine for content creators. Aggregate YouTube & Instagram metrics into one unified dashboard.

## License

This repository is licensed under the [MIT License](LICENSE).

## 🏗️ Architecture

```
Data-Dive/
├── apps/
│   ├── web/          # Next.js 16 (App Router) — Frontend Dashboard
│   ├── api/          # FastAPI — REST API, analytics engine, planning bridge
│   └── worker/       # ARQ worker — trend ingestion, optional LLM enrichment
└── docs/             # Architecture spec, Phase 3 plan, code audit
```

| Layer | Technology | Purpose |
|:------|:-----------|:--------|
| Frontend | Next.js 16 + TypeScript | Dashboard, analytics, ideas, Kanban board |
| Backend | FastAPI (Python) | REST API, analytics engine, prediction + learning loop |
| Worker | ARQ + Redis | Background trend polling, LLM enrichment |
| Auth | Supabase Auth | OAuth 2.0 (Google, Meta); HS256 JWT verified by the API |
| Database | PostgreSQL (Supabase) + pgvector | Content, metrics, ideas, production cards, reviews |

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- Python 3.11+
- Supabase project (for auth & database)

### 1. Start the Backend (FastAPI)

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Start the Frontend (Next.js)

```bash
cd apps/web
npm install
npm run dev
```

### 3. (Optional) Background worker

```bash
cd apps/worker && pip install -r requirements.txt && arq main.WorkerSettings
```

### 4. Open the Dashboard

- Frontend: [http://localhost:3000](http://localhost:3000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

## 🎭 Mock Mode

The app starts in **mock mode** by default — no database, Redis or API credentials needed. You'll see a
*deterministic* dataset of 30 YouTube and 30 Instagram posts (seeded, stable ids) plus a pre-populated
production board, so analytics, ideas, forecasts and reviews are consistent between requests.

To switch to live data, copy `apps/api/.env.example` to `apps/api/.env`, set `MOCK_MODE=false`, fill in the
Supabase values and run the migrations:

```bash
cd apps/api && alembic upgrade head
```

### Docker

```bash
docker network create data-dive_datadive_net   # the compose file expects this external network
docker compose up --build
```

## 📋 Phase 1 Features (MVP)

- [x] Supabase authentication (Google OAuth)
- [x] Mock data engine with realistic content
- [x] KPI summary cards (views, engagement, top platform)
- [x] Unified content feed from YouTube & Instagram
- [x] Platform filter (All / YouTube / Instagram)
- [x] Content type filter (Short / Long-form / Reel / Post)
- [x] Multi-column sorting (date, views, likes)
- [x] Skeleton loading states
- [x] Responsive dark-mode UI

## 📈 Phase 2 Features (Insights Engine)

- [x] Real API Integration (YouTube Data API v3 & Meta Graph API)
- [x] Database Sync & Aggregation (Supabase PostgreSQL)
- [x] Insights Engine UI (Recharts data visualization)
- [x] "What Works" Algorithmic Recommendations
- [x] Multi-platform performance comparison charts

## 🧭 Phase 3 Features (Planning Bridge)

- [x] **Cross-platform analytics** — YouTube vs Instagram on normalized metrics (relative performance per format, engagement rate, momentum, cadence)
- [x] **Pattern detection** — topics (from titles), formats and posting times (weekday × time-of-day) with sample-size-aware confidence
- [x] **Idea generation** — tailored titles, hooks, outlines, recommended platform/format/slot, each with an explainable forecast (`baseline × topic lift × timing lift × calibration`)
- [x] **Kanban production board** (`/kanban`) — Ideas → Scripting → Filming → Editing → Published, drag & drop (between and within columns), event history; reviewed cards stay in Published as a terminal state
- [x] **Explore → Kanban** — trend suggestions and analytics ideas on `/explore`, one click sends them to the Ideas column with a forecast attached
- [x] **Prediction review & learning** — link the published post, compare with the forecast, get lessons; per-creator calibration improves the next forecasts
- [x] Optional LLM enrichment of ideas in the worker (`POST /api/ideas/generate {"enrich": true}`), 12-hour trend cron

See [`docs/PHASE3_PLAN.md`](docs/PHASE3_PLAN.md) for the design and [`docs/CODE_AUDIT.md`](docs/CODE_AUDIT.md) for the bugs found and fixed along the way.

### API surface

```
GET  /api/analytics/overview | /patterns | /learning
GET  /api/ideas?status=pending      POST /api/ideas/generate
POST /api/ideas/{id}/to-board       POST /api/ideas/{id}/dismiss
GET  /api/kanban/board              POST /api/kanban/cards
GET|PATCH|DELETE /api/kanban/cards/{id}
POST /api/kanban/cards/{id}/move | /link-post | /review
```

### Tests

```bash
cd apps/api && pip install pytest pytest-asyncio && pytest            # mock mode, no DB needed
TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/test_sql_repo.py   # DB-mode integration
```

## 🚀 Generate Next Project

One click on **Insights** turns today's trends into a production-ready project for *this* creator:
trends are scored by topic fit with the creator's own winners × momentum × freshness, the best one becomes
a title, hook, outline, platform/format, posting slot and a forecast (with an explicit, capped trend lift),
plus a production kit (shot list, thumbnail, caption/hashtags, a checklist per Kanban column, trend window).
The response is immediate; an optional LLM polish runs in the worker and the UI picks it up by polling.
No relevant trends → it falls back to the creator's strongest analytics idea and queues a trend refresh.
See [`docs/NEXT_PROJECT.md`](docs/NEXT_PROJECT.md).

```
POST /api/projects/next   {"exclude_trend_ids": [], "platform": "YouTube|Instagram", "enrich": true}
GET  /api/ideas/{id}      (poll enrichment_status: queued → done | failed | skipped)
```

## 🌗 Light / dark mode

Toggle in the app header (and on the landing/Explore pages). Saved per browser, follows the OS preference
until chosen explicitly, applied before first paint (no flash), and charts re-theme live. All colours are CSS
variables — see [`docs/THEMING.md`](docs/THEMING.md) for how to add new ones.

## 📡 Usage tracking & feedback

Every feature use is recorded (API middleware + browser SDK), exportable to your telemetry stack
(`TELEMETRY_SINKS=db,log,webhook,otlp`), and creators are asked a 3-question micro-survey after
they have actually used a feature (rating, “was it worth using?”, “what should we improve?”).
Results live on the **Usage & Feedback** page; creators can opt out per account.
See [`docs/USAGE_TRACKING.md`](docs/USAGE_TRACKING.md).

```
POST /api/telemetry/events      GET /api/telemetry/summary?days=30&scope=me|all
GET|PATCH /api/telemetry/preferences
GET  /api/feedback/prompt?feature=ideas&moment=generate
POST /api/feedback              POST /api/feedback/prompt/{feature}/dismiss
```

## 🔮 Roadmap

- Move platform sync into the worker (`process_sync_task`) and store provider tokens server-side
- Nightly auto-review of published cards once metrics settle
- Real vector similarity between trends and the creator's catalogue (embeddings are stored but unused)