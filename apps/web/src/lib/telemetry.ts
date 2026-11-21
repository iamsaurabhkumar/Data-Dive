/**
 * Browser usage-tracking SDK.
 *
 *   configureTelemetry(token)              once the session is known
 *   track("ideas", "generate", { count })  feature_used
 *   trackPageView("/board", durationMs)    emitted automatically by useTelemetry()
 *
 * Events are queued and sent in batches (≤25 or every 5 s) to POST /api/telemetry/events.
 * On tab hide/unload the queue is flushed with `fetch(..., { keepalive: true })` so the
 * Authorization header is preserved (sendBeacon cannot set headers). Never throws.
 */
export type FeatureId =
  | "dashboard" | "insights" | "analytics" | "ideas" | "board" | "review" | "trend_feed" | "sync" | "feedback" | "usage" | "next_project" | "auth" | "other";

export interface TelemetryEvent {
  name: "page_view" | "feature_used";
  feature: FeatureId;
  action?: string;
  properties?: Record<string, string | number | boolean | null>;
  page?: string;
  session_id: string;
  duration_ms?: number;
  ts: string;
}

const BATCH_SIZE = 25;
const FLUSH_MS = 5000;
const STORAGE_KEY = "dd.telemetry.session";

let token = "";
let enabled = true;
let queue: TelemetryEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let listenersBound = false;

export function getSessionId(): string {
  if (typeof window === "undefined") return "server";
  let id = sessionStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function configureTelemetry(authToken: string, isEnabled = true) {
  token = authToken;
  enabled = isEnabled;
  if (!listenersBound && typeof window !== "undefined") {
    listenersBound = true;
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") void flush(true); });
    window.addEventListener("pagehide", () => { void flush(true); });
  }
}

export function setTelemetryEnabled(value: boolean) {
  enabled = value;
  if (!value) queue = [];
}

function schedule() {
  if (timer) return;
  timer = setTimeout(() => { timer = null; void flush(); }, FLUSH_MS);
}

function enqueue(event: TelemetryEvent) {
  if (!enabled || typeof window === "undefined") return;
  queue.push(event);
  if (queue.length >= BATCH_SIZE) void flush();
  else schedule();
}

export function track(feature: FeatureId, action: string, properties?: TelemetryEvent["properties"]) {
  enqueue({
    name: "feature_used",
    feature,
    action,
    properties,
    page: typeof window !== "undefined" ? window.location.pathname : undefined,
    session_id: getSessionId(),
    ts: new Date().toISOString(),
  });
}

export function trackPageView(feature: FeatureId, page: string, durationMs?: number) {
  enqueue({ name: "page_view", feature, page, duration_ms: durationMs, session_id: getSessionId(), ts: new Date().toISOString() });
}

export async function flush(keepalive = false): Promise<void> {
  if (!queue.length || !token) return;
  const batch = queue.splice(0, BATCH_SIZE);
  try {
    const res = await fetch("/api/telemetry/events", {
      method: "POST",
      keepalive,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, "X-Session-Id": getSessionId() },
      body: JSON.stringify({ events: batch }),
    });
    if (!res.ok && res.status >= 500 && !keepalive) queue.unshift(...batch); // retry next flush once
  } catch {
    if (!keepalive) queue.unshift(...batch);
  }
  if (queue.length) schedule();
}

/** Wrap an async action so its duration and outcome are tracked. */
export async function timed<T>(feature: FeatureId, action: string, fn: () => Promise<T>, props?: TelemetryEvent["properties"]): Promise<T> {
  const start = performance.now();
  try {
    const out = await fn();
    track(feature, action, { ...props, ok: true, duration_ms: Math.round(performance.now() - start) });
    return out;
  } catch (e) {
    track(feature, action, { ...props, ok: false, duration_ms: Math.round(performance.now() - start) });
    throw e;
  }
}
