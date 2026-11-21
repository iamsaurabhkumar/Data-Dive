"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, TrendingUp, LogOut, Lightbulb, Loader2, Rocket } from "lucide-react";
import { api, type InsightsResponse } from "@/lib/api";
import { useSession } from "@/hooks/useSession";
import { useAsyncLoad } from "@/hooks/useAsyncLoad";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useChartTheme } from "@/hooks/useChartTheme";
import AppShell from "@/components/AppShell";
import NextProjectModal from "@/components/NextProjectModal";
import { track } from "@/lib/telemetry";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString();
}

export default function InsightsPage() {
  const router = useRouter();
  const { token, email: userEmail, isDemo, ready, signOut } = useSession();

  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNext, setShowNext] = useState(false);
  const chart = useChartTheme();
  useTelemetry("insights", token, ready);

  const openNextProject = (placement: "header" | "what_works") => {
    track("next_project", "open", { placement });
    setShowNext(true);
  };

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      setInsights(await api.getInsights(token));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load insights");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useAsyncLoad(fetchData, ready);

  const handleLogout = async () => {
    await signOut();
    router.push("/");
  };

  return (
    <AppShell token={token} title="Insights Engine" subtitle="Discover what works and optimize your strategy." email={userEmail} isDemo={isDemo}
      onSignOut={handleLogout}
      actions={
        <>
          <button className="btn btn-secondary btn-sm" onClick={() => router.push("/analytics")}><TrendingUp size={14} /> Full analytics</button>
          <button className="btn btn-hero btn-sm" onClick={() => openNextProject("header")} disabled={!token}><Rocket size={14} /> Generate Next Project</button>
        </>
      }>
      {showNext && token && <NextProjectModal token={token} onClose={() => setShowNext(false)} />}
      <div style={{ maxWidth: "1200px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "32px" }}>
        {loading && <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Loader2 className="animate-spin" size={28} /></div>}
            {error && (
              <div style={{ padding: "16px", backgroundColor: "rgba(244, 63, 94, 0.1)", border: "1px solid var(--accent-rose)", borderRadius: "var(--radius-md)", color: "var(--accent-rose)", fontSize: "14px", display: "flex", alignItems: "center", gap: "8px" }}>
                <LogOut size={16} />
                {error}
              </div>
            )}

            {insights && (
              <>
                {/* What Works Card */}
                <div className="glass-card" style={{ padding: "32px", borderRadius: "var(--radius-lg)", border: "1px solid rgba(139, 92, 246, 0.3)", position: "relative", overflow: "hidden" }}>
                  <div style={{ position: "absolute", top: "-50px", right: "-50px", width: "150px", height: "150px", background: "radial-gradient(circle, rgba(139, 92, 246, 0.2) 0%, transparent 70%)", borderRadius: "50%" }} />
                  
                  <div style={{ display: "flex", alignItems: "flex-start", gap: "24px" }}>
                    <div style={{ width: "56px", height: "56px", borderRadius: "16px", background: "linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))", display: "flex", alignItems: "center", justifyContent: "center", color: "white", flexShrink: 0, boxShadow: "0 8px 16px rgba(139, 92, 246, 0.3)" }}>
                      <Lightbulb size={28} />
                    </div>
                    
                    <div>
                      <h2 style={{ fontSize: "20px", fontWeight: 700, marginBottom: "8px", display: "flex", alignItems: "center", gap: "8px" }}>
                        What Works: 
                        <span style={{ color: "var(--accent-secondary)" }}>{insights.what_works.top_content_type}</span> on 
                        <span style={{ color: "var(--accent-primary)" }}>{insights.what_works.top_platform}</span>
                      </h2>
                      <p style={{ fontSize: "16px", color: "var(--text-secondary)", lineHeight: "1.6", margin: 0, maxWidth: "800px" }}>
                        {insights.what_works.recommendation_text}
                      </p>
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 20, flexWrap: "wrap" }}>
                        <button className="btn btn-hero" onClick={() => openNextProject("what_works")}>
                          <Rocket size={16} /> Generate Next Project
                        </button>
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          One click: today’s trends × what works for you → title, hook, outline, shot list and a forecast.
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Charts Grid */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "24px" }}>
                  
                  {/* Performance Chart */}
                  <div className="glass-card" style={{ padding: "24px", borderRadius: "var(--radius-lg)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
                      <div style={{ padding: "8px", borderRadius: "8px", backgroundColor: "rgba(59, 130, 246, 0.1)", color: "var(--accent-primary)" }}>
                        <BarChart3 size={20} />
                      </div>
                      <h3 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>Views by publish weekday</h3>
                    </div>
                    
                    <div style={{ height: "350px", width: "100%" }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={insights.performance_data}
                          margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                          <XAxis dataKey="date" stroke={chart.tick} tick={{ fill: chart.tick }} axisLine={{ stroke: chart.axis }} />
                          <YAxis stroke={chart.tick} tick={{ fill: chart.tick }} axisLine={{ stroke: chart.axis }} tickFormatter={formatNumber} />
                          <Tooltip
                            contentStyle={chart.tooltip}
                            itemStyle={{ color: chart.tooltip.color }}
                          />
                          <Legend wrapperStyle={{ paddingTop: '20px' }} />
                          <Bar dataKey="youtube_views" name="YouTube Views" fill="var(--youtube-red)" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="instagram_views" name="Instagram Views" fill="url(#colorInstagram)" radius={[4, 4, 0, 0]} />
                          
                          <defs>
                            <linearGradient id="colorInstagram" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#f77737" stopOpacity={0.9}/>
                              <stop offset="95%" stopColor="#c13584" stopOpacity={0.9}/>
                            </linearGradient>
                          </defs>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                </div>
              </>
            )}
      </div>
    </AppShell>
  );
}
