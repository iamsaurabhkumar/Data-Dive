/**
 * API client for communicating with the FastAPI backend.
 */

// Always use relative path on client to trigger Next.js rewrites, absolute internal URL on server
const API_BASE = typeof window !== "undefined"
  ? ""
  : (process.env.INTERNAL_API_URL || "http://127.0.0.1:8000");

interface FetchOptions extends RequestInit {
  token?: string;
}

async function apiFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { token, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (typeof window !== "undefined") {
    try {
      const sid = window.sessionStorage.getItem("dd.telemetry.session");
      if (sid) headers["X-Session-Id"] = sid;
    } catch { /* storage unavailable */ }
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "API Error" }));
    const detail = typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail ?? `API error: ${response.status}`);
    throw new Error(detail);
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

// Content Feed
export interface Metrics {
  views: number;
  likes: number;
  comments: number;
  watch_time_hours: number;
  shares: number;
  saves: number;
}

export interface ContentPost {
  id: string;
  platform: string;
  external_post_id: string;
  title: string;
  content_type: string;
  thumbnail_url: string | null;
  published_at: string | null;
  metrics: Metrics;
}

export interface FeedResponse {
  posts: ContentPost[];
  total: number;
  page: number;
  per_page: number;
}

export interface SummaryResponse {
  total_views: number;
  total_likes: number;
  total_comments: number;
  total_posts: number;
  avg_views_per_post: number;
  avg_engagement_rate: number;
  top_platform: string;
  top_content_type: string;
  platform_breakdown: {
    youtube: { posts: number; views: number };
    instagram: { posts: number; views: number };
  };
}

export interface CreatorProfile {
  id: string;
  user_id: string;
  email: string | null;
  youtube_connected: boolean;
  youtube_channel_id: string | null;
  instagram_connected: boolean;
  instagram_user_id: string | null;
}

export interface WhatWorks {
  top_content_type: string;
  top_platform: string;
  recommendation_text: string;
}

export interface PerformanceData {
  date: string;
  youtube_views: number;
  instagram_views: number;
}

export interface InsightsResponse {
  what_works: WhatWorks;
  performance_data: PerformanceData[];
}

export const api = {
  // Health check
  health: () => apiFetch<{ status: string }>("/api/health"),

  // Content
  getFeed: (token: string, params?: {
    platform?: string;
    content_type?: string;
    sort_by?: string;
    sort_order?: string;
    page?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.platform) searchParams.set("platform", params.platform);
    if (params?.content_type) searchParams.set("content_type", params.content_type);
    if (params?.sort_by) searchParams.set("sort_by", params.sort_by);
    if (params?.sort_order) searchParams.set("sort_order", params.sort_order);
    if (params?.page) searchParams.set("page", String(params.page));
    const qs = searchParams.toString();
    return apiFetch<FeedResponse>(`/api/content/feed${qs ? `?${qs}` : ""}`, { token });
  },

  getSummary: (token: string) =>
    apiFetch<SummaryResponse>("/api/content/summary", { token }),

  syncContent: (token: string, providerToken?: string, provider?: string) =>
    apiFetch<{ success: boolean; posts_synced: number; message: string }>(
      "/api/content/sync",
      { 
        token, 
        method: "POST",
        body: JSON.stringify({ provider_token: providerToken, provider: provider })
      }
    ),

  // Metrics
  getInsights: (token: string) =>
    apiFetch<InsightsResponse>("/api/metrics/insights", { token }),

  // Auth
  getProfile: (token: string) =>
    apiFetch<CreatorProfile>("/api/auth/profile", { token }),
};

// ──────────────────────────────────────────────
// Phase 3: Analytics, Ideas, Kanban
// ──────────────────────────────────────────────
export interface GroupStat {
  key: string;
  label: string;
  posts: number;
  avg_views: number;
  median_views: number;
  avg_engagement_rate: number;
  lift: number;
  raw_lift: number;
  confidence: "low" | "medium" | "high";
  platforms: string[];
  example_titles: string[];
}

export interface Finding {
  kind: "platform" | "format" | "topic" | "timing" | "momentum" | "cadence";
  headline: string;
  detail: string;
  confidence: "low" | "medium" | "high";
  evidence: Record<string, unknown>;
}

export interface Slot {
  weekday: number;
  weekday_label: string;
  hour_bucket: string;
  hour_range: string;
  lift: number;
  posts: number;
  confidence: string;
}

export interface PatternsResponse {
  timezone: string;
  sample_size: number;
  topics: GroupStat[];
  formats: GroupStat[];
  weekdays: GroupStat[];
  hour_buckets: GroupStat[];
  slots: GroupStat[];
  best_slots: Record<string, Slot[]>;
  findings: Finding[];
}

export interface PlatformSummary {
  platform: string;
  posts: number;
  total_views: number;
  total_engagement: number;
  avg_views: number;
  median_views: number;
  avg_engagement_rate: number;
  watch_time_hours: number;
  best_format: string | null;
  best_format_lift: number;
  posts_last_30d: number;
  posts_per_week: number;
  momentum: number;
  top_posts: { id: string; title: string; content_type: string; views: number; relative_performance: number; engagement_rate: number; published_at: string | null }[];
}

export interface OverviewResponse {
  total_posts: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  total_engagement: number;
  avg_views_per_post: number;
  avg_engagement_rate: number;
  top_platform: string;
  top_content_type: string;
  platforms: PlatformSummary[];
  content_type_counts: Record<string, number>;
}

export interface Prediction {
  platform: string;
  content_type: string;
  expected_views: number;
  views_low: number;
  views_high: number;
  expected_engagement_rate: number;
  expected_engagement: number;
  confidence: number;
  confidence_label: string;
  factors: {
    format_baseline_views: number;
    format_samples: number;
    topic_lift: number;
    topic_samples: number;
    time_lift: number;
    calibration: number;
    calibration_samples: number;
    sigma: number;
    topics: string[];
    extra_lifts?: Record<string, number>;
  };
  recommended_slot: Slot | null;
  model_version: string;
}

export interface Idea {
  id: string;
  title: string;
  hook: string;
  outline: string[];
  platform: string;
  content_type: string;
  topics: string[];
  strategy: string;
  rationale: string;
  recommended_slot: Slot | null;
  prediction: Prediction;
  confidence_score: number;
  description: string;
  source: string;
  status: string;
  created_at: string;
  trend_id?: string | null;
  kit?: ProjectKit;
  enrichment_status?: "queued" | "done" | "failed" | "skipped" | null;
}

export interface ProjectKit {
  shot_list?: string[];
  thumbnail?: { text: string; concept: string };
  caption?: string;
  hashtags?: string[];
  checklist?: Partial<Record<"idea" | "scripting" | "filming" | "editing" | "published", string[]>>;
  trend_window?: { publish_within_hours: number; reason: string } | null;
}

export interface ScoredTrend {
  trend: { id: string; source: string; category: string; title: string; tags: string[]; url: string | null; fetched_at: string | null; views: number; views_per_hour: number };
  score: number;
  relevance: number;
  momentum: number;
  freshness: number;
  matched_topics: string[];
  topic_fit: number;
  age_hours: number;
}

export interface NextProjectResponse {
  idea: Idea;
  trend: ScoredTrend | null;
  alternatives: ScoredTrend[];
  trends_considered: number;
  fallback_reason: "no_trends" | "no_relevant_trends" | null;
  enrichment: "queued" | "unavailable" | "disabled";
  trend_refresh: "queued" | null;
}

export const projectsApi = {
  next: (token: string, body: { exclude_trend_ids?: string[]; platform?: "YouTube" | "Instagram"; enrich?: boolean } = {}) =>
    apiFetch<NextProjectResponse>("/api/projects/next", { token, method: "POST", body: JSON.stringify(body) }),
};

export interface ReviewResult {
  verdict: "outperformed" | "on_target" | "underperformed";
  views_ratio: number;
  abs_pct_error: number;
  within_range: boolean;
  er_delta: number;
  predicted: { views: number; views_low: number; views_high: number; engagement_rate: number; confidence: number | null; slot: Slot | null };
  actual: { post_id: string; title: string; views: number; likes: number; comments: number; shares: number; saves: number; engagement_rate: number; published_at: string | null; weekday: string | null; hour_bucket: string | null; age_days: number };
  lessons: string[];
  calibration_before: number;
  calibration_after: number;
  reviewed_at?: string;
}

export type Stage = "idea" | "scripting" | "filming" | "editing" | "published" | "reviewed";
/** Kanban columns, in pipeline order. "reviewed" is a terminal sub-state shown inside Published. */
export const PIPELINE: Exclude<Stage, "reviewed">[] = ["idea", "scripting", "filming", "editing", "published"];
export const STAGES: Stage[] = [...PIPELINE, "reviewed"];
export const STAGE_LABELS: Record<Stage, string> = {
  idea: "Ideas",
  scripting: "Scripting",
  filming: "Filming",
  editing: "Editing",
  published: "Published",
  reviewed: "Reviewed",
};

export interface CardEvent {
  id: string;
  card_id: string;
  from_stage: string | null;
  to_stage: string;
  note: string;
  created_at: string;
}

export interface Card {
  id: string;
  creator_id: string;
  title: string;
  hook: string;
  outline: string[];
  platform: string;
  content_type: string;
  topics: string[];
  stage: Stage;
  position: number;
  suggestion_id: string | null;
  post_id: string | null;
  scheduled_for: string | null;
  published_at: string | null;
  prediction: Prediction | null;
  recommended_slot: Slot | null;
  strategy: string | null;
  rationale: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  review: ReviewResult | null;
  linked_post: ContentPost | null;
  events?: CardEvent[];
}

export interface BoardResponse {
  columns: { stage: Stage; cards: Card[] }[];
  total: number;
  stages: Stage[];
  all_stages?: Stage[];
}

export interface Accuracy {
  count: number;
  mape: number | null;
  hit_rate: number | null;
  bias: number | null;
  trend: number | null;
}

export interface LearningResponse {
  accuracy: Accuracy;
  by_platform: Record<string, Accuracy>;
  calibrations: { creator_id: string; platform: string; content_type: string; factor: number; samples: number; updated_at: string }[];
  reviews: (ReviewResult & { card_id: string; post_id: string | null; reviewed_at: string })[];
}

export const analyticsApi = {
  overview: (token: string) => apiFetch<OverviewResponse>("/api/analytics/overview", { token }),
  patterns: (token: string) => apiFetch<PatternsResponse>("/api/analytics/patterns", { token }),
  learning: (token: string) => apiFetch<LearningResponse>("/api/analytics/learning", { token }),
};

export const ideasApi = {
  list: (token: string, status = "pending") =>
    apiFetch<{ ideas: Idea[]; total: number }>(`/api/ideas?status=${status}`, { token }),
  generate: (token: string, count = 6, seed?: number) =>
    apiFetch<{ ideas: Idea[]; total: number }>("/api/ideas/generate", {
      token, method: "POST", body: JSON.stringify({ count, seed }),
    }),
  get: (token: string, id: string) => apiFetch<Idea>(`/api/ideas/${id}`, { token }),
  toBoard: (token: string, id: string) =>
    apiFetch<Card>(`/api/ideas/${id}/to-board`, { token, method: "POST" }),
  dismiss: (token: string, id: string) =>
    apiFetch<Idea>(`/api/ideas/${id}/dismiss`, { token, method: "POST" }),
};

export const kanbanApi = {
  board: (token: string) => apiFetch<BoardResponse>("/api/kanban/board", { token }),
  card: (token: string, id: string) => apiFetch<Card>(`/api/kanban/cards/${id}`, { token }),
  create: (token: string, body: { title: string; platform: string; content_type?: string; hook?: string; outline?: string[]; topics?: string[]; notes?: string }) =>
    apiFetch<Card>("/api/kanban/cards", { token, method: "POST", body: JSON.stringify(body) }),
  update: (token: string, id: string, body: Partial<Pick<Card, "title" | "hook" | "outline" | "topics" | "notes" | "scheduled_for" | "published_at" | "platform" | "content_type">>) =>
    apiFetch<Card>(`/api/kanban/cards/${id}`, { token, method: "PATCH", body: JSON.stringify(body) }),
  move: (token: string, id: string, stage: Stage, position?: number, note = "") =>
    apiFetch<Card>(`/api/kanban/cards/${id}/move`, { token, method: "POST", body: JSON.stringify({ stage, position, note }) }),
  remove: (token: string, id: string) =>
    apiFetch<void>(`/api/kanban/cards/${id}`, { token, method: "DELETE" }),
  linkPost: (token: string, id: string, body: { post_id?: string; auto?: boolean }) =>
    apiFetch<Card>(`/api/kanban/cards/${id}/link-post`, { token, method: "POST", body: JSON.stringify(body) }),
  review: (token: string, id: string, minAgeDays = 0) =>
    apiFetch<Card>(`/api/kanban/cards/${id}/review`, { token, method: "POST", body: JSON.stringify({ min_age_days: minAgeDays }) }),
};

export function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString();
}

// ──────────────────────────────────────────────
// Usage tracking & feedback
// ──────────────────────────────────────────────
export interface FeatureUsage {
  feature: string; label: string; uses: number; page_views: number; sessions: number; creators: number;
  last_used: string; avg_latency_ms: number | null; p95_latency_ms: number | null; error_rate: number | null;
  time_on_page_s: number; top_actions: { action: string; count: number }[];
}
export interface FeedbackSummary {
  feature: string; label: string; responses: number; avg_rating: number;
  worth_it: { yes: number; somewhat: number; no: number }; worth_score: number;
}
export interface UsageSummary {
  days: number; since: string; scope: "me" | "all";
  totals: { events: number; uses: number; sessions: number; creators: number; active_days: number; feedback_responses: number; avg_rating: number | null };
  features: FeatureUsage[]; most_used: string | null;
  funnel: { step: string; feature: string; action: string; count: number; conversion: number | null }[];
  daily: ({ date: string; total: number } & Record<string, number | string>)[];
  feedback: FeedbackSummary[];
  comments: { feature: string; rating: number; worth_it: string; improvement: string; created_at: string; trigger: string }[];
  hub: Record<string, number>;
}
export interface SurveyQuestion { id: "rating" | "worth_it" | "improvement"; type: string; text: string; options?: string[]; min?: number; max?: number; optional?: boolean; max_length?: number }
export interface PromptDecision { prompt: boolean; reason: string; feature: string; uses?: number; questions?: SurveyQuestion[] }

export const telemetryApi = {
  summary: (token: string, days = 30, scope: "me" | "all" = "me") =>
    apiFetch<UsageSummary>(`/api/telemetry/summary?days=${days}&scope=${scope}`, { token }),
  preferences: (token: string) => apiFetch<{ telemetry_opt_out: boolean; sinks: string[] }>("/api/telemetry/preferences", { token }),
  setPreferences: (token: string, optOut: boolean) =>
    apiFetch<{ telemetry_opt_out: boolean; sinks: string[] }>("/api/telemetry/preferences", { token, method: "PATCH", body: JSON.stringify({ telemetry_opt_out: optOut }) }),
  features: () => apiFetch<{ features: { id: string; label: string }[] }>("/api/telemetry/features"),
};

export const feedbackApi = {
  prompt: (token: string, feature: string, moment?: string) =>
    apiFetch<PromptDecision>(`/api/feedback/prompt?feature=${feature}${moment ? `&moment=${moment}` : ""}`, { token }),
  dismiss: (token: string, feature: string) => apiFetch<void>(`/api/feedback/prompt/${feature}/dismiss`, { token, method: "POST" }),
  questions: (token: string, feature: string) =>
    apiFetch<{ feature: string; label: string; questions: SurveyQuestion[] }>(`/api/feedback/questions/${feature}`, { token }),
  submit: (token: string, body: { feature: string; rating: number; worth_it: "yes" | "somewhat" | "no"; improvement?: string; context?: Record<string, string | number | boolean>; trigger: "prompt" | "manual" }) =>
    apiFetch<{ id: string }>("/api/feedback", { token, method: "POST", body: JSON.stringify(body) }),
};
