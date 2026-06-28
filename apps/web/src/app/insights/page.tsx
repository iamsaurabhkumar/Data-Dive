"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  TrendingUp,
  LogOut,
  LayoutDashboard,
  Lightbulb,
  Video,
  Camera,
  Loader2,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { api, type InsightsResponse } from "@/lib/api";
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
  const supabase = createClient();

  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [userEmail, setUserEmail] = useState<string>("Demo User");

  const fetchData = useCallback(async (token: string) => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getInsights(token);
      setInsights(res);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to load insights");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.user) {
        setUserEmail(session.user.email || "Creator");
        fetchData(session.access_token);
      } else {
        // Demo mode with mock token
        fetchData("demo-token");
      }
    };

    init();
  }, [supabase.auth, fetchData]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/");
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", backgroundColor: "var(--bg-primary)" }}>
        <Loader2 className="animate-spin" size={32} color="var(--accent-primary)" />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}>
      {/* Sidebar */}
      <aside style={{ width: "260px", backgroundColor: "var(--bg-card)", borderRight: "1px solid var(--border-color)", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "24px", display: "flex", alignItems: "center", gap: "12px", borderBottom: "1px solid var(--border-color)" }}>
          <div style={{ width: "32px", height: "32px", borderRadius: "8px", background: "linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))", display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: "bold" }}>
            D
          </div>
          <span style={{ fontSize: "18px", fontWeight: "700", letterSpacing: "-0.5px" }}>Data-Dive</span>
        </div>

        <nav style={{ padding: "24px 16px", flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
          <button 
            onClick={() => router.push("/dashboard")}
            style={{ display: "flex", alignItems: "center", gap: "12px", padding: "10px 16px", borderRadius: "var(--radius-md)", width: "100%", textAlign: "left", background: "transparent", color: "var(--text-secondary)", transition: "all 0.2s", border: "none", cursor: "pointer" }}
            onMouseOver={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseOut={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          >
            <LayoutDashboard size={18} />
            <span style={{ fontSize: "14px", fontWeight: 500 }}>Dashboard</span>
          </button>

          <button 
            onClick={() => router.push("/insights")}
            style={{ display: "flex", alignItems: "center", gap: "12px", padding: "10px 16px", borderRadius: "var(--radius-md)", width: "100%", textAlign: "left", background: "var(--accent-primary)", color: "white", border: "none", cursor: "pointer", boxShadow: "0 4px 12px rgba(59, 130, 246, 0.25)" }}
          >
            <TrendingUp size={18} />
            <span style={{ fontSize: "14px", fontWeight: 500 }}>Insights</span>
          </button>

        </nav>

        <div style={{ padding: "24px", borderTop: "1px solid var(--border-color)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "50%", backgroundColor: "var(--bg-hover)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "14px", fontWeight: "bold", color: "var(--accent-secondary)" }}>
              {userEmail.charAt(0).toUpperCase()}
            </div>
            <div style={{ overflow: "hidden" }}>
              <div style={{ fontSize: "14px", fontWeight: 600, whiteSpace: "nowrap", textOverflow: "ellipsis" }}>{userEmail}</div>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Creator Plan</div>
            </div>
          </div>
          <button 
            onClick={handleLogout}
            style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", width: "100%", padding: "10px", borderRadius: "var(--radius-sm)", backgroundColor: "var(--bg-hover)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", transition: "all 0.2s" }}
            onMouseOver={(e) => { e.currentTarget.style.color = "var(--youtube-red)"; e.currentTarget.style.borderColor = "var(--youtube-red)"; }}
            onMouseOut={(e) => { e.currentTarget.style.color = "var(--text-secondary)"; e.currentTarget.style.borderColor = "var(--border-color)"; }}
          >
            <LogOut size={16} />
            <span style={{ fontSize: "13px", fontWeight: 500 }}>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
        
        {/* Header */}
        <header style={{ padding: "24px 40px", borderBottom: "1px solid var(--border-color)", display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "rgba(10, 15, 28, 0.8)", backdropFilter: "blur(12px)", zIndex: 10 }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: 700, letterSpacing: "-0.5px", margin: "0 0 4px 0", color: "var(--text-primary)" }}>Insights Engine</h1>
            <p style={{ fontSize: "14px", color: "var(--text-secondary)", margin: 0 }}>Discover what works and optimize your strategy.</p>
          </div>
        </header>

        {/* Scrollable Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "40px" }}>
          <div style={{ maxWidth: "1200px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "32px" }}>
            
            {error && (
              <div style={{ padding: "16px", backgroundColor: "rgba(244, 63, 94, 0.1)", border: "1px solid var(--youtube-red)", borderRadius: "var(--radius-md)", color: "var(--youtube-red)", fontSize: "14px", display: "flex", alignItems: "center", gap: "8px" }}>
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
                      <h3 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>Weekly Performance Comparison</h3>
                    </div>
                    
                    <div style={{ height: "350px", width: "100%" }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={insights.performance_data}
                          margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" vertical={false} />
                          <XAxis dataKey="date" stroke="#a0aec0" tick={{ fill: '#a0aec0' }} axisLine={{ stroke: '#4a5568' }} />
                          <YAxis stroke="#a0aec0" tick={{ fill: '#a0aec0' }} axisLine={{ stroke: '#4a5568' }} tickFormatter={formatNumber} />
                          <Tooltip 
                            contentStyle={{ backgroundColor: '#1a202c', borderColor: '#4a5568', borderRadius: '8px', color: '#fff' }}
                            itemStyle={{ color: '#e2e8f0' }}
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
        </div>
      </main>
    </div>
  );
}
