# 📊 Data-Dive — Content Creator Analytics Dashboard

A data-first analytics engine for content creators. Aggregate YouTube & Instagram metrics into one unified dashboard.

## 🏗️ Architecture

```
Data-Dive/
├── apps/
│   ├── web/          # Next.js 14 (App Router) — Frontend Dashboard
│   └── api/          # FastAPI — Backend API & Platform Integrations
```

| Layer | Technology | Purpose |
|:------|:-----------|:--------|
| Frontend | Next.js 14 + TypeScript | Dashboard UI with SSR |
| Backend | FastAPI (Python) | REST API, platform integrations |
| Auth | Supabase Auth | OAuth 2.0 (Google, Meta) |
| Database | PostgreSQL (Supabase) | Content & metrics storage |

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

### 3. Open the Dashboard

- Frontend: [http://localhost:3000](http://localhost:3000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

## 🎭 Mock Mode

The app starts in **mock mode** by default — no API credentials needed. You'll see realistic fake data for 30 YouTube and 30 Instagram posts.

To switch to live data, set `MOCK_MODE=false` in `apps/api/.env` and configure your platform API credentials.

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

## 🔮 Roadmap

- **Phase 2**: Insights Engine — bar charts, performance comparison, "What Works" algorithm
- **Phase 3**: Planning Bridge — Kanban board, "Generate Next Project" from insights