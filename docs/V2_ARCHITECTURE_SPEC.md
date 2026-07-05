# Antigravity Manager Specification: Data-Dive V2 (Event-Driven & AI-Native)

## 1. Objective
Evolve the existing Data-Dive monorepo from a synchronous data sync pipeline into an asynchronous, event-driven architecture that continuously monitors platform trends (YouTube, TikTok, Instagram, News) and uses semantic vector search and an LLM reasoning engine to deliver proactive content recommendations via a real-time UI feed.

## 2. Core Constraints & System Boundary
- Frameworks: Next.js (apps/web), FastAPI (apps/api), Python ARQ async worker (apps/worker).
- Decision Record: ARQ selected over Celery — all tasks are I/O-bound (HTTP/DB), native async/await, 3x lower memory on NAS hardware.
- Infrastructure: Monorepo containerization ready for local CasaOS NAS deployment.
- State & Queues: Redis 7.x (Message Broker), Supabase PostgreSQL with 'pgvector' extension enabled.
- External Dependencies: YouTube Data API v3, Meta Graph API, Apify Scraper API, NewsAPI, and OpenAI API. All heavy external network calls must occur strictly within the background worker context.

## 3. Architecture Component Map

### Service 1: Next.js Client Gateway (`apps/web`)
- Primary View Layer.
- Must listen to real-time database modifications via Supabase WebSockets to stream newly generated AI recommendations seamlessly without pulling or reloading.
- Includes the interactive Kanban implementation and Recharts analytical layouts.

### Service 2: FastAPI Routing Engine (`apps/api`)
- Acts strictly as a lightweight, stateless API gateway.
- Intercepts incoming client requests, executes JWT verification against the Supabase signing secret, and immediately pushes long-running execution requests to the Redis message queue.
- Must maintain a sub-50ms execution window before returning HTTP 202 Accepted status responses.

### Service 3: Redis In-Memory Broker (`docker/redis`)
- Operates as the messaging transport medium between FastAPI and the background execution framework.

### Service 4: ARQ Async Processing Worker (`apps/worker`)
- A decoupled Python environment running ARQ against Redis.
- Owns its own asyncpg connection pool (pool_size=3, max_overflow=5) — independent from FastAPI.
- Responsible for executing scheduled 12-hour automated polling cycles across the external network adapters.
- Interacts directly with Supabase to perform analytical writes, vector generation, and execution logic.
- Retry policy: exponential backoff (2s base), max 3 tries, 5-minute job timeout.

## 4. Agent Execution Tasks & Verifiable Artifacts

### Task Group A: Core Orchestration Configuration
- Update the root `docker-compose.yml` to include a Redis instance and the independent `worker` build container context.
- Ensure all services map to the existing isolated internal application network bridge.
- **Artifact Required:** A verified root Docker Compose structure with distinct configuration keys for the Redis healthcheck.

### Task Group B: Data Model Migration & Vector Initialization
- Define the SQLModel structure for the `PlatformTrend` and `ContentSuggestion` tables.
- Write an independent migration pattern executing the setup of `pgvector` hooks.
- **Artifact Required:** A verified SQL migration script or python initialization script mapping high-dimensional embedding dimensions (1536 vector length).

### Task Group C: Async Task Core Architecture (COMPLETED)
- **Producer Integration**: Replaced raw `LPUSH` enqueueing with ARQ's native `ArqRedis.enqueue_job()` in FastAPI (`apps/api/app/core/redis.py`) to ensure jobs are correctly serialized for the worker.
- **Worker Configuration**: Initialized a dedicated DB connection pool (`asyncpg`) and a global `httpx.AsyncClient` inside `apps/worker/main.py` via `startup`/`shutdown` lifecycle hooks. No per-task clients.
- **Resiliency**: Implemented strict per-task constraints (`func(max_tries=4, timeout=120)`) and programmatic exponential backoff using `arq.Retry(defer=...)`.
- **Idempotency**: Prevented duplicate API ingestion on retry by implementing a partial unique index in Supabase: `(source, external_url, date)` paired with `ON CONFLICT DO NOTHING`.

### Task Group D: Feature Engineering (COMPLETED)
- **External Ingestion (Token Optimization):** Built `fetch_youtube_trends` in `apps/worker/tasks.py`. Hard-truncated YouTube Data API payloads to extract strictly `id`, `title`, and `tags` (max 5) to minimize LLM token bloat.
- **Structured RAG Inference:** Integrated `openai.AsyncClient` (`gpt-4o-mini`) using `client.beta.chat.completions.parse` with a Pydantic `LLMSuggestion` schema to strictly enforce valid JSON returns mapping our database columns.
- **Context Injection:** Programmed a specialized system prompt anchoring the AI as a creative director for the "Keyboard on Clouds" channel persona.
- **Transaction Safety:** Enclosed the `PlatformTrend` vector upsert and `ContentSuggestion` generation inside a single SQLAlchemy `session` context manager for secure rollbacks upon API failure.

Do not write downstream logical routines before generating and presenting structural artifacts for each Task Group.

---

# Comprehensive System Architecture Document

This document explains the conceptual mapping, data pathways, and technical justifications for each architectural shift in the V2 upgrade.

## 1. High-Level Architectural Blueprint

```text
  +-----------------------------------------------------------------------+
  |                          PRESENTATION LAYER                           |
  |  [Next.js Client Dashboard] <======= Real-time WS =====+             |
  +-------------------+------------------------------------+-------------+
                      |                                    |
                      | HTTP Requests                      | Real-time Updates
                      v                                    |
  +-----------------------------------+                    |
  |         APPLICATION GATEWAY       |                    |
  |  [FastAPI Stateless Router]        |                    |
  +-------------------+---------------+                    |
                      |                                    |
                      | Push Task                          |
                      v                                    |
  +-----------------------------------+                    |
  |          TRANSPORT LAYER          |                    |
  |  [Redis Message Broker]           |                    |
  +-------------------+---------------+                    |
                      |                                    |
                      | Pull Task                          |
                      v                                    |
  +-----------------------------------+                    |
  |          PROCESSING LAYER         |                    |
  |  [Python Async Worker (Celery)]   |                    |
  +--------+-----------------+--------+                    |
           |                 |                             |
           | HTTPS Calls     | DB Writes / Vector Search   |
           v                 v                             v
  +-----------------+  +-------------------------------------------------+
  |  EXTERNAL APIS  |  |                 DATA STORAGE LAYER              |
  | - YouTube/Meta  |  |  [Supabase Managed PostgreSQL + pgvector]       |
  | - Apify Scrape  |  +-------------------------------------------------+
  | - OpenAI/News   |
  +-----------------+

```

## 2. In-Depth Component Breakdown

### A. Next.js Client Dashboard

* **WHAT:** The client application interface handling user analytics visualization, production pipelines, and target suggestions.
* **HOW:** Built inside the monorepo framework, the UI connects to the Supabase client wrapper. It subscribes to the `ContentSuggestions` database schema using persistent WebSockets. When a background service generates an item, the row insertion fires a client callback, instantly injecting the card into the user's viewport without forcing page refreshes.
* **WHY:** Creators expect real-time response speeds. Moving the application layer away from poll-based queries prevents server congestion and maximizes client-side performance during long analytics jobs.

### B. FastAPI Stateless Router

* **WHAT:** An ultra-lightweight entry gateway responsible for traffic control, request verification, and structural validation.
* **HOW:** It processes route targets, handles incoming webhooks, and decrypts the Supabase authorization token via the `SUPABASE_JWT_SECRET` keys. When a creator triggers a sync operation, FastAPI converts the request into a JSON string payload and executes a non-blocking push command to the Redis messaging space, returning an immediate HTTP 202 status code back to the client UI.
* **WHY:** Heavy platform scraping tasks and LLM inferences take a long time to resolve. Keeping the gateway stateless and fast ensures it handles high numbers of concurrent users smoothly while protecting your server resources from timing out.

### C. Redis Message Broker

* **WHAT:** A high-throughput, in-memory data store functioning explicitly as a secure messaging pipeline.
* **HOW:** It holds structured task messages (e.g., `{"task": "fetch_trends", "creator_id": "123"}`) in a volatile first-in, first-out memory queue, waiting for processing instances to claim the payload.
* **WHY:** It acts as a protective shock absorber between the API layer and the worker. If third-party APIs slow down, Redis safely holds incoming operations in a queue so no data drops, keeping the frontend stable and decoupled.

### D. ARQ Async Worker

* **WHAT:** The heavy engine running on an independent background process, isolated from client web routines. Uses ARQ (native Python async task queue) instead of Celery.
* **HOW:** It continuously listens to the Redis stream via ARQ's built-in consumer loop. Upon processing an ingestion message, it executes sequential execution cycles: calling scraping networks, executing database reads, transforming unstructured tracking models, and making calls to the OpenAI completion endpoints. Cron jobs run heartbeats (60s) and trend fetches (12h).
* **WHY:** Isolating blocking I/O and computing operations ensures the system scales easily. ARQ's native async/await integration eliminates the sync-async impedance mismatch that Celery introduces. If analytics processing demands grow, you can simply spin up extra worker containers on your CasaOS NAS without modifying the API codebase.

### E. Supabase PostgreSQL with `pgvector`

* **WHAT:** A highly capable hybrid database storing standard relation profiles side-by-side with high-dimensional vector embeddings.
* **HOW:** It holds relational workspace maps while using the `pgvector` extension to process cosine similarity equations directly inside native database tables:

$$\text{Cosine Similarity} = \frac{A \cdot B}{\|A\| \|B\|}$$

Trending phrases are passed through an embedding algorithm, converted into multidimensional arrays, and compared against historical creator tags to find optimal contextual matches.

* **WHY:** It removes the operational complexity of hosting and paying for a separate vector database. Keeping relational creator logs and performance vector blocks under a unified Postgres database engine ensures clean transaction controls and high data consistency.

### F. External Data Connectors & APIs

* **WHAT:** A modular system of network integration adapters feeding external real-world trends into the system.
* **HOW:**
* *YouTube Data API:* Queries the `mostPopular` chart parameters categorized strictly by niche.
* *Apify Scraper Infrastructure:* Programmatically bypasses platform locks via rotating proxy endpoints to ingest current trending media objects, audios, and tag metrics from Instagram and TikTok.
* *NewsAPI:* Aggregates raw textual summaries from leading domain-specific feeds to flag breaking current events.


* **WHY:** Combining deep personal account statistics with real-time global market trends is the exact combination needed to generate automated, highly accurate creator content strategies.
