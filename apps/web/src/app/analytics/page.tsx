"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import {
  TrendingUp, TrendingDown, Layers, Hash, Clock, Flame, CalendarDays, Target, Sparkles, Loader2, RefreshCw, Brain,
} from "lucide-react";
import { analyticsApi, formatNumber, type Finding, type GroupStat, type LearningResponse, type OverviewResponse, type PatternsResponse } from "@/lib/api";
import { useSession } from "@/hooks/useSession";
import { useAsyncLoad } from "@/hooks/useAsyncLoad";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useFeedback } from "@/components/FeedbackWidget";
import AppShell from "@/components/AppShell";
import { ConfidencePill, Empty, ErrorBanner, Lift, PlatformBadge, Section, SlotChip } from "@/components/ui";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const BUCKETS = ["morning", "midday", "evening", "night"];

function findingIcon(kind: Finding["kind"]) {
  const map = {
    platform: { icon: <Layers size={18} />, color: "var(--accent-blue)" },
    format: { icon: <Flame size={18} />, color: "var(--accent-violet)" },
    topic: { icon: <Hash size={18} />, color: "var(--accent-emerald)" },
    timing: { icon: <Clock size={18} />, color: "var(--accent-amber)" },
    momentum: { icon: <TrendingUp size={18} />, color: "var(--accent-cyan)" },
    cadence: { icon: <CalendarDays size={18} />, color: "var(--accent-rose)" },
  } as const;
  return map[kind] ?? map.platform;
}

function StatTable({ rows, labelHeader }: { rows: GroupStat[]; labelHeader: string }) {
  if (!rows.length) return <Empty text="Not enough recurring data yet." />;
  return (
    <div>
      <div className="stat-row stat-row-header">
        <div>{labelHeader}</div><div>Posts</div><div>Median views</div><div>Eng. rate</div><div>Lift</div>
      </div>
      {rows.map((r) => (
        <div className="stat-row" key={r.key}>
          <div>
            <div style={{ fontWeight: 500 }}>{r.label}</div>
            {r.example_titles[0] && <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>e.g. {r.example_titles[0]}</div>}
          </div>
          <div className="font-mono">{r.posts}</div>
          <div className="font-mono">{formatNumber(r.median_views)}</div>
          <div className="font-mono">{r.avg_engagement_rate}%</div>
          <div><Lift value={r.lift} /> <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{r.confidence}</span></div>
        </div>
      ))}
    </div>
  );
}

function Heatmap({ patterns }: { patterns: PatternsResponse }) {
  // Build weekday × bucket lifts from slots; fall back to weekday × bucket products for sparse cells
  const wd = Object.fromEntries(patterns.weekdays.map((w) => [w.key, w.lift]));
  const hb = Object.fromEntries(patterns.hour_buckets.map((h) => [h.key, h.lift]));
  const slots = Object.fromEntries(patterns.slots.map((s) => [s.key, s]));
  const cell = (d: number, b: string) => {
    const s = slots[`${d}:${b}`];
    if (s) return { lift: s.lift, n: s.posts };
    if (wd[String(d)] === undefined || hb[b] === undefined) return null;
    return { lift: wd[String(d)] * hb[b], n: 0 };
  };
  const color = (lift: number) => {
    const t = Math.max(-1, Math.min(1, Math.log(lift) / Math.log(2))); // -1..1 over 0.5x..2x
    return t >= 0 ? `rgba(16,185,129,${0.12 + t * 0.6})` : `rgba(244,63,94,${0.12 + -t * 0.6})`;
  };
  return (
    <div className="heat-grid">
      <div />
      {WEEKDAYS.map((d) => <div key={d} style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center" }}>{d}</div>)}
      {BUCKETS.map((b) => (
        <>
          <div key={`${b}-label`} style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center" }}>{b}</div>
          {WEEKDAYS.map((_, d) => {
            const c = cell(d, b);
            return (
              <div key={`${b}-${d}`} className="heat-cell" title={c ? `${c.lift.toFixed(2)}x${c.n ? ` · ${c.n} posts` : " (estimated)"}` : "no data"}
                style={{ background: c ? color(c.lift) : "var(--bg-tertiary)", opacity: c && c.n === 0 ? 0.6 : 1 }}>
                {c ? `${c.lift.toFixed(2)}x` : "–"}
              </div>
            );
          })}
        </>
      ))}
    </div>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
  const { token, email, isDemo, ready, signOut } = useSession();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [patterns, setPatterns] = useState<PatternsResponse | null>(null);
  const [learning, setLearning] = useState<LearningResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { track } = useTelemetry("analytics", token, ready);
  const { askAfter } = useFeedback();

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [o, p, l] = await Promise.all([analyticsApi.overview(token), analyticsApi.patterns(token), analyticsApi.learning(token)]);
      setOverview(o); setPatterns(p); setLearning(l); setError(null);
      track("view", { findings: p.findings.length, topics: p.topics.length, reviewed: l.accuracy.count });
      askAfter("analytics", "view");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally { setLoading(false); }
  }, [token, track, askAfter]);

  useAsyncLoad(load, ready);

  return (
    <AppShell token={token} title="Analytics" subtitle="Cross-platform performance and the patterns behind it" email={email} isDemo={isDemo}
      onSignOut={async () => { await signOut(); router.push("/"); }}
      actions={<button className="btn btn-secondary btn-sm" onClick={() => { setLoading(true); load(); }}><RefreshCw size={14} /> Refresh</button>}>
      <ErrorBanner error={error} />
      {loading || !overview || !patterns ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Loader2 className="animate-spin" size={28} /></div>
      ) : (
        <>
          {/* Platform comparison */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 16, marginBottom: 20 }}>
            {overview.platforms.map((p) => (
              <div className="card" key={p.platform}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}><PlatformBadge platform={p.platform} /><span style={{ fontWeight: 600 }}>{p.platform}</span></div>
                  {overview.top_platform === p.platform && <span className="pill" style={{ color: "var(--accent-emerald)", borderColor: "var(--accent-emerald)" }}>leading</span>}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                  {[
                    ["Posts", p.posts.toString()], ["Median views", formatNumber(p.median_views)], ["Eng. rate", `${p.avg_engagement_rate}%`],
                    ["Total views", formatNumber(p.total_views)], ["Posts / week", p.posts_per_week.toFixed(1)], ["Last 30d", p.posts_last_30d.toString()],
                  ].map(([l, v]) => (
                    <div key={l}><div className="metric-label">{l}</div><div className="metric-value" style={{ fontSize: 18 }}>{v}</div></div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
                  <span className="pill">best format: <b>{p.best_format ?? "—"}</b> <Lift value={p.best_format_lift} /></span>
                  <span className="pill">{p.momentum >= 1 ? <TrendingUp size={12} color="var(--accent-emerald)" /> : <TrendingDown size={12} color="var(--accent-rose)" />} momentum <Lift value={p.momentum} /></span>
                </div>
                {p.top_posts.length > 0 && (
                  <div style={{ marginTop: 14, borderTop: "1px solid var(--border-subtle)", paddingTop: 10 }}>
                    <div className="metric-label" style={{ marginBottom: 6 }}>Top relative performers</div>
                    {p.top_posts.map((t) => (
                      <div key={t.id} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 12, padding: "4px 0" }}>
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</span>
                        <span className="font-mono" style={{ flexShrink: 0 }}>{formatNumber(t.views)} · <Lift value={t.relative_performance} /></span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Findings */}
          <Section title="What the data says" icon={<Sparkles size={16} color="var(--accent-violet)" />}
            right={<span style={{ fontSize: 12, color: "var(--text-muted)" }}>{patterns.sample_size} posts analysed · {patterns.timezone}</span>}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 12 }}>
              {patterns.findings.map((f, i) => {
                const { icon, color } = findingIcon(f.kind);
                return (
                  <div className="finding" key={i}>
                    <div className="finding-icon" style={{ background: `color-mix(in srgb, ${color} 15%, transparent)`, color }}>{icon}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{f.headline}</div>
                      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>{f.detail}</div>
                      <div style={{ marginTop: 6 }}><ConfidencePill level={f.confidence} /></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(460px, 1fr))", gap: 20 }}>
            <Section title="Topics" icon={<Hash size={16} color="var(--accent-emerald)" />}>
              <StatTable rows={patterns.topics.slice(0, 12)} labelHeader="Topic (from titles)" />
            </Section>
            <Section title="Formats" icon={<Flame size={16} color="var(--accent-violet)" />}>
              <StatTable rows={patterns.formats} labelHeader="Format" />
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10 }}>Lift is relative to the platform median; topic and timing lifts are relative to the format median so they can be combined.</p>
            </Section>
          </div>

          <Section title="Posting times" icon={<Clock size={16} color="var(--accent-amber)" />}
            right={<div style={{ display: "flex", gap: 8 }}>{Object.entries(patterns.best_slots).map(([pl, slots]) => slots[0] && <span key={pl} style={{ fontSize: 12 }}><PlatformBadge platform={pl} /> <SlotChip slot={slots[0]} /></span>)}</div>}>
            <Heatmap patterns={patterns} />
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10 }}>Relative performance by publish weekday × time of day ({patterns.timezone}). Faded cells are estimated from row × column lifts (fewer than 2 posts).</p>
          </Section>

          {/* Learning */}
          <Section title="Prediction accuracy" icon={<Brain size={16} color="var(--accent-cyan)" />}
            right={<button className="btn btn-ghost btn-sm" onClick={() => router.push("/kanban")}><Target size={14} /> Review on Kanban</button>}>
            {learning && learning.accuracy.count > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
                <div><div className="metric-label">Reviewed</div><div className="metric-value">{learning.accuracy.count}</div></div>
                <div><div className="metric-label">Mean abs. error</div><div className="metric-value">{((learning.accuracy.mape ?? 0) * 100).toFixed(0)}%</div></div>
                <div><div className="metric-label">Inside range</div><div className="metric-value">{((learning.accuracy.hit_rate ?? 0) * 100).toFixed(0)}%</div></div>
                <div><div className="metric-label">Bias (actual ÷ forecast)</div><div className="metric-value"><Lift value={learning.accuracy.bias ?? 1} /></div></div>
                <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {learning.calibrations.map((c) => (
                    <span className="pill" key={`${c.platform}-${c.content_type}`}>{c.content_type} on {c.platform}: calibration <Lift value={c.factor} /> · {c.samples} sample{c.samples === 1 ? "" : "s"}</span>
                  ))}
                </div>
              </div>
            ) : <Empty text="No reviewed predictions yet. Publish a card from the board, link the post and review it — the system learns from every review." />}
          </Section>
        </>
      )}
    </AppShell>
  );
}
