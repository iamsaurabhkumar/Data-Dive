"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Eye,
  Heart,
  MessageCircle,
  TrendingUp,
  RefreshCw,
  LogOut,
  LayoutDashboard,
  Zap,
  Clock,
  Crown,
  ChevronDown,
  ArrowUpDown,
  Video,
  Camera,
  Loader2,
  Lightbulb,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import {
  api,
  type ContentPost,
  type SummaryResponse,
} from "@/lib/api";

type PlatformFilter = "all" | "YouTube" | "Instagram";
type ContentTypeFilter = "all" | "Short" | "Long-form" | "Reel" | "Post";
type SortField = "published_at" | "views" | "likes";

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString();
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function getContentTypeBadgeClass(type: string): string {
  switch (type.toLowerCase()) {
    case "short": return "badge-short";
    case "long-form": return "badge-longform";
    case "reel": return "badge-reel";
    case "post": return "badge-post";
    default: return "";
  }
}

export default function DashboardPage() {
  const router = useRouter();
  const supabase = createClient();

  const [posts, setPosts] = useState<ContentPost[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>("all");
  const [contentTypeFilter, setContentTypeFilter] = useState<ContentTypeFilter>("all");
  const [sortBy, setSortBy] = useState<SortField>("published_at");
  const [sortOrder, setSortOrder] = useState<"desc" | "asc">("desc");

  // User
  const [userEmail, setUserEmail] = useState<string>("Demo User");
  const [isDemo, setIsDemo] = useState(true);

  const fetchData = useCallback(async (token: string) => {
    try {
      setLoading(true);
      setError(null);

      const [feedRes, summaryRes] = await Promise.all([
        api.getFeed(token, {
          platform: platformFilter !== "all" ? platformFilter : undefined,
          content_type: contentTypeFilter !== "all" ? contentTypeFilter : undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
        }),
        api.getSummary(token),
      ]);

      setPosts(feedRes.posts);
      setSummary(summaryRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [platformFilter, contentTypeFilter, sortBy, sortOrder]);

  useEffect(() => {
    const init = async () => {
      // Check for authenticated session
      const { data: { session } } = await supabase.auth.getSession();

      if (session?.user) {
        setUserEmail(session.user.email || "Creator");
        setIsDemo(false);
        fetchData(session.access_token);
      } else {
        // Demo mode with mock token
        setIsDemo(true);
        fetchData("demo-token");
      }
    };

    init();
  }, [fetchData, supabase.auth]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token || "demo-token";
      const providerToken = session?.provider_token ?? undefined;
      const provider = session?.user?.app_metadata?.provider;
      await api.syncContent(token, providerToken, provider);
      await fetchData(token);
    } catch (err) {
      console.error("Sync failed:", err);
    } finally {
      setSyncing(false);
    }
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/");
  };

  const toggleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "desc" ? "asc" : "desc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };

  return (
    <div className="dashboard-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div style={{ padding: "24px", borderBottom: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "var(--radius-sm)",
                background: "var(--gradient-brand)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <BarChart3 size={20} color="white" />
            </div>
            <span style={{ fontSize: "18px", fontWeight: 700, letterSpacing: "-0.3px" }}>
              Data<span className="text-gradient">Dive</span>
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ padding: "16px 12px", flex: 1 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 12px",
              borderRadius: "var(--radius-sm)",
              background: "rgba(59, 130, 246, 0.08)",
              color: "var(--accent-blue)",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: 500,
            }}
            onClick={() => router.push("/dashboard")}
          >
            <LayoutDashboard size={18} />
            Dashboard
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 12px",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-secondary)",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: 500,
              transition: "all 0.2s",
            }}
            onClick={() => router.push("/insights")}
            onMouseOver={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseOut={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          >
            <TrendingUp size={18} />
            Insights
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 12px",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-secondary)",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: 500,
              transition: "all 0.2s",
            }}
            onClick={() => router.push("/explore")}
            onMouseOver={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseOut={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          >
            <Lightbulb size={18} />
            Explore Ideas
          </div>

          <div style={{ margin: "24px 12px 8px", fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Connected Platforms
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", borderRadius: "var(--radius-sm)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "14px", color: "var(--text-secondary)" }}>
                <Video size={16} style={{ color: "var(--youtube-red)" }} />
                YouTube
              </div>
              <span className="badge badge-connected" style={{ fontSize: "10px", padding: "2px 8px" }}>Live</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", borderRadius: "var(--radius-sm)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "14px", color: "var(--text-secondary)" }}>
                <Camera size={16} style={{ color: "var(--instagram-pink)" }} />
                Instagram
              </div>
              <span className="badge badge-connected" style={{ fontSize: "10px", padding: "2px 8px" }}>Live</span>
            </div>
          </div>
        </nav>

        {/* User info */}
        <div style={{ padding: "16px", borderTop: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary)" }}>{userEmail}</div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                {isDemo ? "Demo Mode" : "Creator"}
              </div>
            </div>
            <button onClick={handleLogout} className="btn btn-ghost btn-sm" title="Sign out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        {/* Header */}
        <header className="header">
          <div>
            <h1 style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-0.3px" }}>
              Analytics Dashboard
            </h1>
            <p style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "2px" }}>
              {isDemo ? "Viewing mock data — connect platforms for real analytics" : "Real-time cross-platform metrics"}
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {isDemo && (
              <span className="badge" style={{ background: "rgba(245, 158, 11, 0.1)", color: "var(--accent-amber)", border: "1px solid rgba(245, 158, 11, 0.2)", padding: "4px 12px", fontSize: "11px" }}>
                <Zap size={12} />
                DEMO
              </span>
            )}
            <button onClick={handleSync} className="btn btn-primary btn-sm" disabled={syncing}>
              {syncing ? (
                <Loader2 size={14} className="animate-spin" style={{ animation: "spin 1s linear infinite" }} />
              ) : (
                <RefreshCw size={14} />
              )}
              {syncing ? "Syncing..." : "Refresh"}
            </button>
          </div>
        </header>

        <div className="page-content">
          {error && (
            <div
              className="card animate-fade-in-up"
              style={{
                marginBottom: "24px",
                borderColor: "rgba(244, 63, 94, 0.3)",
                background: "rgba(244, 63, 94, 0.05)",
              }}
            >
              <p style={{ color: "var(--accent-rose)", fontSize: "14px" }}>⚠️ {error}</p>
              <p style={{ color: "var(--text-muted)", fontSize: "13px", marginTop: "4px" }}>
                Make sure the FastAPI backend is running on port 8000.
              </p>
            </div>
          )}

          {/* KPI Cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "16px",
              marginBottom: "32px",
            }}
          >
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="metric-card">
                  <div className="skeleton" style={{ width: "60%", height: "14px", marginBottom: "12px" }} />
                  <div className="skeleton" style={{ width: "40%", height: "28px", marginBottom: "8px" }} />
                  <div className="skeleton" style={{ width: "80%", height: "12px" }} />
                </div>
              ))
            ) : summary ? (
              <>
                <div className="metric-card animate-fade-in-up animate-delay-1">
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
                    <span style={{ fontSize: "13px", color: "var(--text-secondary)", fontWeight: 500 }}>Total Views</span>
                    <Eye size={18} style={{ color: "var(--accent-blue)" }} />
                  </div>
                  <div className="font-mono" style={{ fontSize: "28px", fontWeight: 700, letterSpacing: "-1px" }}>
                    {formatNumber(summary.total_views)}
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                    Across {summary.total_posts} posts
                  </div>
                </div>

                <div className="metric-card animate-fade-in-up animate-delay-2">
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
                    <span style={{ fontSize: "13px", color: "var(--text-secondary)", fontWeight: 500 }}>Engagement Rate</span>
                    <TrendingUp size={18} style={{ color: "var(--accent-emerald)" }} />
                  </div>
                  <div className="font-mono" style={{ fontSize: "28px", fontWeight: 700, letterSpacing: "-1px", color: "var(--accent-emerald)" }}>
                    {summary.avg_engagement_rate}%
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                    Likes + comments / views
                  </div>
                </div>

                <div className="metric-card animate-fade-in-up animate-delay-3">
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
                    <span style={{ fontSize: "13px", color: "var(--text-secondary)", fontWeight: 500 }}>Avg Views/Post</span>
                    <Crown size={18} style={{ color: "var(--accent-amber)" }} />
                  </div>
                  <div className="font-mono" style={{ fontSize: "28px", fontWeight: 700, letterSpacing: "-1px" }}>
                    {formatNumber(summary.avg_views_per_post)}
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                    Top type: <span style={{ color: "var(--text-secondary)" }}>{summary.top_content_type}</span>
                  </div>
                </div>

                <div className="metric-card animate-fade-in-up animate-delay-4">
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
                    <span style={{ fontSize: "13px", color: "var(--text-secondary)", fontWeight: 500 }}>Top Platform</span>
                    {summary.top_platform === "YouTube" ? (
                      <Video size={18} style={{ color: "var(--youtube-red)" }} />
                    ) : (
                      <Camera size={18} style={{ color: "var(--instagram-pink)" }} />
                    )}
                  </div>
                  <div style={{ fontSize: "28px", fontWeight: 700, letterSpacing: "-1px" }}>
                    {summary.top_platform}
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                    YT: {formatNumber(summary.platform_breakdown.youtube.views)} · IG: {formatNumber(summary.platform_breakdown.instagram.views)}
                  </div>
                </div>
              </>
            ) : null}
          </div>

          {/* Filters Section */}
          <div
            className="card animate-fade-in-up"
            style={{
              marginBottom: "24px",
              padding: "16px 20px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Platform
                </div>
                <div className="filter-group">
                  {(["all", "YouTube", "Instagram"] as PlatformFilter[]).map((p) => (
                    <button
                      key={p}
                      className={`filter-btn ${platformFilter === p ? "active" : ""}`}
                      onClick={() => setPlatformFilter(p)}
                    >
                      {p === "all" ? "All" : p}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Content Type
                </div>
                <div className="filter-group">
                  {(["all", "Short", "Long-form", "Reel", "Post"] as ContentTypeFilter[]).map((t) => (
                    <button
                      key={t}
                      className={`filter-btn ${contentTypeFilter === t ? "active" : ""}`}
                      onClick={() => setContentTypeFilter(t)}
                    >
                      {t === "all" ? "All" : t}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Sort:</span>
              <button className="btn btn-secondary btn-sm" onClick={() => toggleSort("published_at")}>
                <Clock size={12} />
                Date
                {sortBy === "published_at" && <ChevronDown size={12} style={{ transform: sortOrder === "asc" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => toggleSort("views")}>
                <Eye size={12} />
                Views
                {sortBy === "views" && <ChevronDown size={12} style={{ transform: sortOrder === "asc" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => toggleSort("likes")}>
                <Heart size={12} />
                Likes
                {sortBy === "likes" && <ChevronDown size={12} style={{ transform: sortOrder === "asc" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
              </button>
            </div>
          </div>

          {/* Content Feed */}
          <div className="card animate-fade-in-up" style={{ padding: 0, overflow: "hidden" }}>
            {/* Table header */}
            <div className="content-row content-row-header">
              <div></div>
              <div>Content</div>
              <div style={{ textAlign: "right" }}>Platform</div>
              <div style={{ textAlign: "right" }}>Type</div>
              <div style={{ textAlign: "right" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "4px", cursor: "pointer" }} onClick={() => toggleSort("views")}>
                  Views <ArrowUpDown size={10} />
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "4px", cursor: "pointer" }} onClick={() => toggleSort("likes")}>
                  Likes <ArrowUpDown size={10} />
                </div>
              </div>
              <div style={{ textAlign: "right" }}>Published</div>
            </div>

            {/* Loading skeleton */}
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="content-row">
                  <div className="skeleton" style={{ width: "48px", height: "48px" }} />
                  <div className="skeleton" style={{ height: "14px", width: "70%" }} />
                  <div className="skeleton" style={{ height: "20px", width: "60px", marginLeft: "auto" }} />
                  <div className="skeleton" style={{ height: "20px", width: "60px", marginLeft: "auto" }} />
                  <div className="skeleton" style={{ height: "14px", width: "50px", marginLeft: "auto" }} />
                  <div className="skeleton" style={{ height: "14px", width: "40px", marginLeft: "auto" }} />
                  <div className="skeleton" style={{ height: "14px", width: "60px", marginLeft: "auto" }} />
                </div>
              ))
            ) : posts.length === 0 ? (
              <div style={{ padding: "60px 20px", textAlign: "center" }}>
                <BarChart3 size={48} style={{ color: "var(--text-muted)", marginBottom: "16px" }} />
                <p style={{ fontSize: "15px", fontWeight: 500, marginBottom: "4px" }}>No content found</p>
                <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                  Try adjusting your filters or sync your platforms.
                </p>
              </div>
            ) : (
              posts.map((post, index) => (
                <div
                  key={post.external_post_id}
                  className="content-row"
                  style={{
                    animation: `fadeInUp 0.3s ease-out ${index * 0.02}s both`,
                  }}
                >
                  {/* Thumbnail */}
                  <div
                    className="content-thumbnail"
                    style={{
                      backgroundImage: post.thumbnail_url ? `url(${post.thumbnail_url})` : undefined,
                      backgroundSize: "cover",
                      backgroundPosition: "center",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {!post.thumbnail_url && (
                      post.platform === "YouTube" ? (
                        <Video size={20} style={{ color: "var(--youtube-red)" }} />
                      ) : (
                        <Camera size={20} style={{ color: "var(--instagram-pink)" }} />
                      )
                    )}
                  </div>

                  {/* Title */}
                  <div className="content-title" title={post.title}>
                    {post.title}
                  </div>

                  {/* Platform */}
                  <div style={{ textAlign: "right" }}>
                    <span className={`badge ${post.platform === "YouTube" ? "badge-youtube" : "badge-instagram"}`}>
                      {post.platform === "YouTube" ? "YT" : "IG"}
                    </span>
                  </div>

                  {/* Content Type */}
                  <div style={{ textAlign: "right" }}>
                    <span className={`badge ${getContentTypeBadgeClass(post.content_type)}`}>
                      {post.content_type}
                    </span>
                  </div>

                  {/* Views */}
                  <div style={{ textAlign: "right" }}>
                    <div className="metric-value">{formatNumber(post.metrics.views)}</div>
                  </div>

                  {/* Likes */}
                  <div style={{ textAlign: "right" }}>
                    <div className="metric-value">{formatNumber(post.metrics.likes)}</div>
                  </div>

                  {/* Published date */}
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
                      {formatDate(post.published_at)}
                    </div>
                  </div>
                </div>
              ))
            )}

            {/* Feed footer */}
            {!loading && posts.length > 0 && (
              <div
                style={{
                  padding: "16px 20px",
                  borderTop: "1px solid var(--border-subtle)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                  Showing {posts.length} of {summary?.total_posts || posts.length} posts
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                    <span className="font-mono" style={{ color: "var(--text-secondary)" }}>
                      {summary?.platform_breakdown.youtube.posts || 0}
                    </span> YouTube
                    {" · "}
                    <span className="font-mono" style={{ color: "var(--text-secondary)" }}>
                      {summary?.platform_breakdown.instagram.posts || 0}
                    </span> Instagram
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
