/**
 * API client for communicating with the FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "API Error" }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

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

  syncContent: (token: string) =>
    apiFetch<{ success: boolean; posts_synced: number; message: string }>(
      "/api/content/sync",
      { token, method: "POST" }
    ),

  // Metrics
  getInsights: (token: string) =>
    apiFetch<InsightsResponse>("/api/metrics/insights", { token }),

  // Auth
  getProfile: (token: string) =>
    apiFetch<CreatorProfile>("/api/auth/profile", { token }),
};
