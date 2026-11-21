"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, Loader2, MessageSquareHeart, Star, Shield, Filter, Users, Clock, AlertTriangle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { telemetryApi, type UsageSummary } from "@/lib/api";
import { setTelemetryEnabled } from "@/lib/telemetry";
import { useSession } from "@/hooks/useSession";
import { useAsyncLoad } from "@/hooks/useAsyncLoad";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useChartTheme } from "@/hooks/useChartTheme";
import { useFeedback } from "@/components/FeedbackWidget";
import AppShell from "@/components/AppShell";
import { Empty, ErrorBanner, Section } from "@/components/ui";

function Stars({ value }: { value: number }) {
  return (
    <span style={{ display: "inline-flex", gap: 1 }} title={`${value} / 5`}>
      {[1, 2, 3, 4, 5].map((n) => <Star key={n} size={12} fill={value >= n - 0.25 ? "var(--accent-amber)" : "none"} color={value >= n - 0.25 ? "var(--accent-amber)" : "var(--text-muted)"} />)}
    </span>
  );
}

export default function UsagePage() {
  const router = useRouter();
  const { token, email, isDemo, ready, signOut } = useSession();
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [days, setDays] = useState(30);
  const [scope, setScope] = useState<"me" | "all">("me");
  const [optOut, setOptOut] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { track } = useTelemetry("usage", token, ready);
  const { open } = useFeedback();
  const chart = useChartTheme();
  const COLORS = chart.accents;

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [s, p] = await Promise.all([telemetryApi.summary(token, days, scope), telemetryApi.preferences(token)]);
      setSummary(s); setOptOut(p.telemetry_opt_out); setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load usage");
      if (scope === "all") setScope("me");
    } finally { setLoading(false); }
  }, [token, days, scope]);

  useAsyncLoad(load, ready);

  const toggleOptOut = async () => {
    if (optOut === null) return;
    const next = !optOut;
    try {
      const p = await telemetryApi.setPreferences(token, next);
      setOptOut(p.telemetry_opt_out);
      setTelemetryEnabled(!p.telemetry_opt_out);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update preference"); }
  };

  const featureKeys = summary ? Array.from(new Set(summary.daily.flatMap((d) => Object.keys(d).filter((k) => k !== "date" && k !== "total")))) : [];
  const maxFunnel = summary ? Math.max(1, ...summary.funnel.map((f) => f.count)) : 1;

  return (
    <AppShell token={token} title="Usage & Feedback" subtitle="Which features get used, how they convert, and what creators say about them" email={email} isDemo={isDemo}
      onSignOut={async () => { await signOut(); router.push("/"); }}
      actions={
        <>
          <select className="btn btn-secondary btn-sm" style={{ appearance: "auto" }} value={days} onChange={(e) => { setDays(Number(e.target.value)); track("change_range", { days: Number(e.target.value) }); setLoading(true); }}>
            {[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}
          </select>
          <select className="btn btn-secondary btn-sm" style={{ appearance: "auto" }} value={scope} onChange={(e) => { setScope(e.target.value as "me" | "all"); track("change_scope", { scope: e.target.value }); setLoading(true); }}>
            <option value="me">My usage</option>
            <option value="all">All creators (admin)</option>
          </select>
          <button className="btn btn-primary btn-sm" onClick={() => open("usage")}><MessageSquareHeart size={14} /> Give feedback</button>
        </>
      }>
      <ErrorBanner error={error} />
      {loading || !summary ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Loader2 className="animate-spin" size={28} /></div>
      ) : (
        <>
          {/* Totals */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 20 }}>
            {[
              ["Feature uses", summary.totals.uses, <Activity key="a" size={14} />],
              ["Sessions", summary.totals.sessions, <Users key="b" size={14} />],
              ["Active days", summary.totals.active_days, <Clock key="c" size={14} />],
              ["Creators", summary.totals.creators, <Users key="d" size={14} />],
              ["Feedback responses", summary.totals.feedback_responses, <MessageSquareHeart key="e" size={14} />],
              ["Avg rating", summary.totals.avg_rating ?? "—", <Star key="f" size={14} />],
            ].map(([label, value, icon]) => (
              <div className="metric-card" key={String(label)}>
                <div className="metric-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>{icon}{label}</div>
                <div className="metric-value">{value as number}</div>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(460px, 1fr))", gap: 20 }}>
            {/* Funnel */}
            <Section title="Idea → published → reviewed funnel" icon={<Filter size={16} color="var(--accent-blue)" />}>
              {summary.funnel.map((f) => (
                <div key={f.step} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                    <span>{f.step}</span>
                    <span className="font-mono">{f.count}{f.conversion !== null && <span style={{ color: "var(--text-muted)" }}> · {(f.conversion * 100).toFixed(0)}%</span>}</span>
                  </div>
                  <div style={{ background: "var(--bg-tertiary)", borderRadius: 5 }}><div className="funnel-bar" style={{ width: `${Math.max(2, (f.count / maxFunnel) * 100)}%` }} /></div>
                </div>
              ))}
              <p style={{ fontSize: 11, color: "var(--text-muted)" }}>Conversion is relative to the previous non-empty step. Counts come from both the browser SDK and the API middleware.</p>
            </Section>

            {/* Feedback per feature */}
            <Section title="How creators rate each feature" icon={<Star size={16} color="var(--accent-amber)" />}>
              {summary.feedback.length === 0 ? <Empty text="No survey responses yet. Surveys appear after a feature has been used a few times." /> : (
                <div>
                  <div className="stat-row stat-row-header"><div>Feature</div><div>Resp.</div><div>Rating</div><div>Worth it</div><div>Score</div></div>
                  {summary.feedback.map((f) => (
                    <div className="stat-row" key={f.feature}>
                      <div><div style={{ fontWeight: 500 }}>{f.label}</div></div>
                      <div className="font-mono">{f.responses}</div>
                      <div><Stars value={f.avg_rating} /> <span className="font-mono" style={{ fontSize: 11 }}>{f.avg_rating}</span></div>
                      <div style={{ fontSize: 11 }}><span style={{ color: "var(--accent-emerald)" }}>{f.worth_it.yes}y</span> / <span style={{ color: "var(--accent-amber)" }}>{f.worth_it.somewhat}s</span> / <span style={{ color: "var(--accent-rose)" }}>{f.worth_it.no}n</span></div>
                      <div className="font-mono" style={{ color: f.worth_score >= 0.7 ? "var(--accent-emerald)" : f.worth_score >= 0.4 ? "var(--accent-amber)" : "var(--accent-rose)" }}>{(f.worth_score * 100).toFixed(0)}%</div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          {/* Feature table */}
          <Section title="Feature usage" icon={<Activity size={16} color="var(--accent-violet)" />}
            right={summary.most_used && <span className="pill">most used: <b>{summary.most_used}</b></span>}>
            {summary.features.length === 0 ? <Empty text="No usage recorded in this period." /> : (
              <div>
                <div className="stat-row stat-row-header" style={{ gridTemplateColumns: "minmax(0,1.4fr) 60px 60px 90px 80px 120px" }}>
                  <div>Feature</div><div>Uses</div><div>Sess.</div><div>p95 latency</div><div>Errors</div><div>Top actions</div>
                </div>
                {summary.features.map((f) => (
                  <div className="stat-row" key={f.feature} style={{ gridTemplateColumns: "minmax(0,1.4fr) 60px 60px 90px 80px 120px" }}>
                    <div>
                      <div style={{ fontWeight: 500 }}>{f.label}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{f.page_views} views · {f.time_on_page_s}s on page · last {new Date(f.last_used).toLocaleDateString()}</div>
                    </div>
                    <div className="font-mono">{f.uses}</div>
                    <div className="font-mono">{f.sessions}</div>
                    <div className="font-mono">{f.p95_latency_ms !== null ? `${f.p95_latency_ms} ms` : "—"}</div>
                    <div className="font-mono" style={{ color: (f.error_rate ?? 0) > 0.05 ? "var(--accent-rose)" : undefined }}>
                      {f.error_rate !== null ? `${(f.error_rate * 100).toFixed(0)}%` : "—"}{(f.error_rate ?? 0) > 0.05 && <AlertTriangle size={11} style={{ marginLeft: 4 }} />}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {f.top_actions.map((a) => `${a.action} ${a.count}`).join(" · ") || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Daily chart */}
          <Section title="Daily activity by feature" icon={<Clock size={16} color="var(--accent-cyan)" />}>
            {summary.daily.length === 0 ? <Empty text="Nothing yet." /> : (
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={summary.daily} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                    <XAxis dataKey="date" stroke={chart.tick} tick={{ fill: chart.tick, fontSize: 11 }} />
                    <YAxis stroke={chart.tick} tick={{ fill: chart.tick, fontSize: 11 }} />
                    <Tooltip contentStyle={chart.tooltip} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {featureKeys.map((k, i) => <Bar key={k} dataKey={k} stackId="a" fill={COLORS[i % COLORS.length]} />)}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Section>

          {/* Comments */}
          <Section title="What creators asked for" icon={<MessageSquareHeart size={16} color="var(--accent-rose)" />}>
            {summary.comments.length === 0 ? <Empty text="No written feedback yet." /> : summary.comments.map((c, i) => (
              <div className="lesson" key={i} style={{ borderLeftColor: c.rating >= 4 ? "var(--accent-emerald)" : c.rating <= 2 ? "var(--accent-rose)" : "var(--accent-amber)" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, fontSize: 11, color: "var(--text-muted)" }}>
                  <span className="pill">{c.feature}</span> <Stars value={c.rating} /> · worth it: {c.worth_it} · {new Date(c.created_at).toLocaleDateString()} · {c.trigger}
                </div>
                {c.improvement}
              </div>
            ))}
          </Section>

          {/* Privacy */}
          <Section title="Privacy" icon={<Shield size={16} color="var(--accent-emerald)" />}>
            <label className="toggle">
              <input type="checkbox" checked={!!optOut} onChange={toggleOptOut} />
              Opt out of usage tracking for my account
            </label>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
              We record which features you use (never your titles, captions or metrics) to decide what to build next. Exported telemetry replaces your id with a salted hash. Opting out drops events at the server before they are stored or forwarded.
            </p>
          </Section>
        </>
      )}
    </AppShell>
  );
}
