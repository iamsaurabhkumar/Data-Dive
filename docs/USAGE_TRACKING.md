# Usage Tracking, Telemetry & Feature Feedback

Goal: know **which features creators actually use**, **how they flow through the product**
(ideas → board → published → reviewed), and **what they think** of each feature — without
building a surveillance system. Everything is first-party, opt-out-able, and exportable to
whatever telemetry backend you already run.

## 1. What gets tracked

### Event schema (one row / one log line per event)

| field | example | notes |
|---|---|---|
| `name` | `feature_used`, `page_view`, `api_call`, `feedback_submitted`, `survey_dismissed` | small fixed vocabulary |
| `feature` | `ideas`, `board`, `review`, `analytics`, `dashboard`, `insights`, `trend_feed`, `sync`, `feedback` | stable taxonomy (`app/services/telemetry/taxonomy.py`) |
| `action` | `generate`, `to_board`, `move`, `link_post`, `review`, `filter`, `sort` | free-form but lower-case snake |
| `properties` | `{"count": 6, "from": "idea", "to": "planning"}` | JSON, **no free text from users**, no titles |
| `page` | `/board` | route, not full URL |
| `session_id` | uuid | per browser tab session (sessionStorage) |
| `client` | `web` / `api` | web = sent by the browser, api = recorded by middleware |
| `duration_ms` | `184` | API latency or time-on-page |
| `status` | `200` | API calls only |
| `creator_id` | uuid | raw in our DB; **hashed** (salted SHA-256) when exported |
| `ts` | ISO-8601 | client timestamp, clamped to server time ± 5 min |

### Sources
1. **Server middleware** (`app/middleware/usage.py`) — every authenticated API call becomes an
   `api_call` event with the *route template* (`/api/kanban/cards/{card_id}/move`, never raw ids),
   status and latency. Health, docs and telemetry endpoints are excluded. This works even if the
   frontend never sends anything.
2. **Browser SDK** (`apps/web/src/lib/telemetry.ts`) — `track(feature, action, props)` and automatic
   `page_view` with time-on-page. Events are queued, batched (≤25 / 5 s), flushed with
   `navigator.sendBeacon` on unload, and retried once on failure.

### Privacy / consent
* `creator_profiles.telemetry_opt_out` — when true, events are **dropped at ingestion** (not stored,
  not exported). Toggle: `PATCH /api/telemetry/preferences`.
* Exported payloads replace `creator_id` with `sha256(salt + creator_id)`; `TELEMETRY_HASH_SALT`.
* Properties are validated against an allow-list of JSON scalar types, capped at 2 KB; free text is
  only accepted through the explicit feedback form.

## 2. Where it goes (sinks)

`TELEMETRY_SINKS=db,log` (comma-separated, default). Sinks run from an in-process buffer flushed every
`TELEMETRY_FLUSH_SECONDS` (5) or when 200 events accumulate; failures are logged and never affect
the request path.

| sink | config | format |
|---|---|---|
| `db` | — | `usage_events` table (queryable by the summary endpoint) |
| `log` | — | JSON lines on logger `datadive.telemetry` (`{"type":"usage_event",...}`) — any log shipper (Loki, Datadog, CloudWatch) picks it up |
| `webhook` | `TELEMETRY_WEBHOOK_URL`, `TELEMETRY_WEBHOOK_TOKEN` | `POST {"source":"data-dive","events":[...]}` batches (Segment/PostHog-style collectors, your own lambda) |
| `otlp` | `TELEMETRY_OTLP_ENDPOINT` (e.g. `http://otel-collector:4318/v1/logs`), `TELEMETRY_OTLP_HEADERS` | OpenTelemetry log records, attributes = event fields; requires `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` |

## 3. Feedback & surveys

Two channels, same table (`feature_feedback`):

1. **Contextual micro-survey** — after a *feature moment* (idea added to board, review completed,
   ideas generated, …) the UI asks the API `GET /api/feedback/prompt?feature=review`. The server
   decides whether to ask, using frequency rules so the creator is never nagged:
   * feature used ≥ `FEEDBACK_MIN_USES` times (3)
   * no feedback for that feature in the last `FEEDBACK_COOLDOWN_DAYS` (30)
   * no dismissal of that feature's survey in the last 7 days
   * at most one prompt per creator per day
   The widget asks three things: **rating 1–5**, **“Was it worth using?”** (yes / somewhat / no),
   **“What should we improve?”** (optional free text, 1000 chars), plus a hidden `context`
   (e.g. the verdict of the review that triggered it).
2. **Always-available feedback** — a “Feedback” button in the sidebar opens the same form for any
   feature.

Submissions emit a `feedback_submitted` usage event (rating/worth only, no text) so the export
stream shows sentiment next to usage.

## 4. Reading the results

`GET /api/telemetry/summary?days=30` (own data) — `?scope=all` for admins (`ADMIN_USER_IDS`):

* totals: events, active days, sessions, creators
* per feature: uses, sessions, last used, avg/p95 API latency, error rate
* funnel: ideas generated → added to board → published → reviewed (counts + conversion)
* feedback: avg rating, worth-it split, response count per feature, recent comments
* daily series for charts

The `/usage` page in the web app renders this.

## 5. Verification done

* 15 unit/API tests (`tests/test_telemetry.py`) — validation/sanitization, clock clamping, anonymized export,
  buffer/flush, opt-out, webhook sink (mock transport) incl. failure containment, OTLP sink construction,
  prompt frequency rules, feedback validation, summary maths, middleware + endpoints, admin scope.
* DB integration (`tests/test_sql_repo.py::test_sql_telemetry_repository`) on Postgres 16, migration
  `c4d5e6f7a8b9` up/down/up.
* Headless-browser run of the built app: survey appears after the configured number of uses, submit →
  stored + visible on `/usage`; manual survey from the sidebar; page_view with time-on-page on both
  client-side and full navigations.

## 6. Files

```
apps/api/app/services/telemetry/{taxonomy,models,sinks,service,summary}.py
apps/api/app/middleware/usage.py
apps/api/app/routers/telemetry.py            /api/telemetry/*, /api/feedback/*
apps/api/app/repositories/telemetry.py       memory + SQL stores
apps/api/alembic/versions/c4d5e6f7a8b9_usage_tracking.py
apps/web/src/lib/telemetry.ts                browser SDK
apps/web/src/components/FeedbackWidget.tsx   micro-survey + sidebar button
apps/web/src/app/usage/page.tsx              usage & feedback dashboard
```
