"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Rocket, X, Loader2, RefreshCw, KanbanSquare, Flame, Quote, ListOrdered, Clapperboard, Image as ImageIcon,
  Hash, CheckSquare, Sparkles, Timer, AlertTriangle, Check,
} from "lucide-react";
import { formatNumber, ideasApi, projectsApi, type Idea, type NextProjectResponse, type ScoredTrend } from "@/lib/api";
import { track } from "@/lib/telemetry";
import { askAfter } from "@/components/FeedbackWidget";
import { PlatformBadge, PredictionBar, SlotChip, TypeBadge } from "@/components/ui";

const POLL_MS = 3000;
const POLL_MAX = 20;            // ~1 minute of waiting for the worker's LLM pass
const STAGE_ORDER = ["idea", "scripting", "filming", "editing", "published"] as const;
const STAGE_NAME: Record<string, string> = { idea: "Ideas", scripting: "Scripting", filming: "Filming", editing: "Editing", published: "Published" };

type Tab = "outline" | "shots" | "package" | "checklist";

function TrendPill({ s }: { s: ScoredTrend }) {
  return (
    <span className="pill" title={`score ${s.score} · relevance ${s.relevance} · momentum ${s.momentum} · freshness ${s.freshness}`}>
      {s.trend.source} · {formatNumber(s.trend.views)} views · {Math.round(s.age_hours)}h old
    </span>
  );
}

export default function NextProjectModal({ token, onClose }: { token: string; onClose: () => void }) {
  const [data, setData] = useState<NextProjectResponse | null>(null);
  const [idea, setIdea] = useState<Idea | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("outline");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState<"board" | "dismiss" | null>(null);
  const seen = useRef<string[]>([]);
  const started = useRef(false);

  const current = useRef<{ id: string; sent: boolean } | null>(null);

  const generate = useCallback(async (regenerate: boolean) => {
    // "Regenerate" means "not this one": reject the unsent draft so Explore doesn't fill up with discards
    const prev = current.current;
    if (regenerate && prev && !prev.sent) await ideasApi.dismiss(token, prev.id).catch(() => undefined);
    setLoading(true); setError(null); setSent(false); setTab("outline");
    const t0 = performance.now();
    try {
      const res = await projectsApi.next(token, { exclude_trend_ids: seen.current });
      if (res.trend) seen.current = [...seen.current, res.trend.trend.id];
      setData(res); setIdea(res.idea);
      current.current = { id: res.idea.id, sent: false };
      track("next_project", regenerate ? "regenerate" : "generate", {
        ok: true, duration_ms: Math.round(performance.now() - t0), fallback: res.fallback_reason ?? "none",
        enrichment: res.enrichment, platform: res.idea.platform, content_type: res.idea.content_type,
        trend_score: res.trend?.score ?? null,
      });
      askAfter("next_project", "generate");
    } catch (e) {
      track("next_project", regenerate ? "regenerate" : "generate", { ok: false });
      setError(e instanceof Error ? e.message : "Could not generate a project");
    } finally { setLoading(false); }
  }, [token]);

  // First generation on open (scheduled, so the effect never sets state synchronously)
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const h = setTimeout(() => { void generate(false); }, 0);
    return () => clearTimeout(h);
  }, [generate]);

  // Poll for the worker's LLM polish
  useEffect(() => {
    if (!idea || idea.enrichment_status !== "queued") return;
    let n = 0;
    const id = setInterval(async () => {
      n += 1;
      try {
        const fresh = await ideasApi.get(token, idea.id);
        if (fresh.enrichment_status !== "queued" || n >= POLL_MAX) {
          clearInterval(id);
          setIdea(fresh.enrichment_status === "queued" ? { ...fresh, enrichment_status: "failed" } : fresh);
        }
      } catch { clearInterval(id); }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [idea, token]);

  const sendToKanban = async () => {
    if (!idea) return;
    setBusy("board");
    try {
      await ideasApi.toBoard(token, idea.id);
      setSent(true);
      if (current.current) current.current.sent = true;
      track("next_project", "to_board", { platform: idea.platform, content_type: idea.content_type, from_trend: !!idea.trend_id });
      askAfter("next_project", "to_board");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not add to Kanban"); }
    finally { setBusy(null); }
  };

  /** "Not this one": reject the idea. */
  const dismiss = async () => {
    if (idea && !sent) {
      setBusy("dismiss");
      await ideasApi.dismiss(token, idea.id).catch(() => undefined);
      track("next_project", "dismiss", { from_trend: !!idea.trend_id });
    }
    onClose();
  };

  /** Close (X / backdrop / Esc): keep the idea pending — it stays available in Explore. */
  const close = () => {
    if (idea && !sent) track("next_project", "close", { kept_pending: true });
    onClose();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const kit = idea?.kit ?? {};
  const trend = data?.trend;

  return (
    <>
      <div className="drawer-backdrop" onClick={close} />
      <div className="modal" role="dialog" aria-label="Your next project">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div className="modal-icon"><Rocket size={18} /></div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>Your next project</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {data ? `Built from ${data.trends_considered} current trend${data.trends_considered === 1 ? "" : "s"} × your own performance data` : "Scanning current trends against your analytics…"}
              </div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={close} aria-label="Close"><X size={16} /></button>
        </div>

        {error && <div style={{ padding: "10px 12px", borderRadius: 8, background: "rgba(244,63,94,0.1)", color: "var(--accent-rose)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        {loading || !idea ? (
          <div style={{ padding: "70px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 12, color: "var(--text-muted)", fontSize: 13 }}>
            <Loader2 size={28} className="animate-spin" />
            Matching trends to your best topics, formats and posting slots…
          </div>
        ) : (
          <>
            {/* Trend that inspired it */}
            {trend ? (
              <div className="finding" style={{ marginBottom: 14 }}>
                <div className="finding-icon" style={{ background: "rgba(245,158,11,0.15)", color: "var(--accent-amber)" }}><Flame size={18} /></div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>Trending now</div>
                  <div style={{ fontWeight: 600, fontSize: 13, margin: "2px 0 6px" }}>{trend.trend.title}</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <TrendPill s={trend} />
                    {trend.matched_topics.map((t) => <span key={t} className="pill">matches #{t}</span>)}
                    <span className="pill">fit {trend.topic_fit.toFixed(2)}x</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="finding" style={{ marginBottom: 14 }}>
                <div className="finding-icon" style={{ background: "rgba(148,163,184,0.15)", color: "var(--text-secondary)" }}><AlertTriangle size={18} /></div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  {data?.fallback_reason === "no_trends" ? "No fresh trend data yet" : "None of the current trends fit your niche"} — this project doubles down on your own strongest pattern instead.
                  {data?.trend_refresh === "queued" && " A trend refresh has been queued."}
                </div>
              </div>
            )}

            {/* Title + hook */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
              <PlatformBadge platform={idea.platform} /><TypeBadge type={idea.content_type} />
              {idea.enrichment_status === "queued" && <span className="pill" style={{ color: "var(--accent-violet)", borderColor: "var(--accent-violet)" }}><Loader2 size={11} className="animate-spin" /> AI polishing…</span>}
              {idea.enrichment_status === "done" && <span className="pill" style={{ color: "var(--accent-emerald)", borderColor: "var(--accent-emerald)" }}><Sparkles size={11} /> AI-polished</span>}
              {kit.trend_window && <span className="pill" style={{ color: "var(--accent-amber)", borderColor: "var(--accent-amber)" }}><Timer size={11} /> publish within {kit.trend_window.publish_within_hours}h</span>}
            </div>
            <h2 style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.3, marginBottom: 10 }}>{idea.title}</h2>
            <div style={{ display: "flex", gap: 8, fontSize: 14, color: "var(--text-secondary)", fontStyle: "italic", marginBottom: 14, lineHeight: 1.5 }}>
              <Quote size={15} style={{ flexShrink: 0, marginTop: 3, color: "var(--accent-violet)" }} /> {idea.hook}
            </div>

            {idea.prediction?.expected_views !== undefined && (
              <div style={{ marginBottom: 10 }}>
                <PredictionBar prediction={idea.prediction} />
                {idea.prediction.factors.extra_lifts?.trend && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>includes a trend lift of ×{idea.prediction.factors.extra_lifts.trend} (capped) — the review will show if the bet paid off</div>
                )}
              </div>
            )}
            <div style={{ marginBottom: 14 }}><SlotChip slot={idea.recommended_slot} /></div>

            {/* Tabs */}
            <div className="filter-group" style={{ marginBottom: 12 }}>
              {([["outline", "Outline", ListOrdered], ["shots", "Shot list", Clapperboard], ["package", "Thumbnail & caption", ImageIcon], ["checklist", "Checklist", CheckSquare]] as const).map(([k, label, Icon]) => (
                <button key={k} className={`filter-btn ${tab === k ? "active" : ""}`} onClick={() => { setTab(k); track("next_project", "view_tab", { tab: k }); }}>
                  <Icon size={12} style={{ display: "inline", marginRight: 4 }} />{label}
                </button>
              ))}
            </div>
            <div className="modal-tab">
              {tab === "outline" && <ol className="outline-list">{idea.outline.map((b, i) => <li key={i}>{b}</li>)}</ol>}
              {tab === "shots" && <ol className="outline-list">{(kit.shot_list ?? []).map((b, i) => <li key={i}>{b}</li>)}</ol>}
              {tab === "package" && (
                <div style={{ fontSize: 13, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 10 }}>
                  {kit.thumbnail && <div><b style={{ color: "var(--text-primary)" }}>Thumbnail text:</b> <span className="font-mono">{kit.thumbnail.text}</span><div>{kit.thumbnail.concept}</div></div>}
                  {kit.caption && <div><b style={{ color: "var(--text-primary)" }}>Caption:</b> {kit.caption}</div>}
                  {kit.hashtags && <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><Hash size={13} />{kit.hashtags.map((h) => <span key={h} className="pill">{h}</span>)}</div>}
                </div>
              )}
              {tab === "checklist" && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
                  {STAGE_ORDER.map((st) => (
                    <div key={st}>
                      <div className="metric-label" style={{ marginBottom: 4 }}>{STAGE_NAME[st]}</div>
                      <ul style={{ paddingLeft: 16, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                        {(kit.checklist?.[st] ?? []).map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <details style={{ marginTop: 12 }}>
              <summary style={{ fontSize: 12, color: "var(--text-muted)", cursor: "pointer" }}>Why this project?</summary>
              <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, marginTop: 6 }}>{idea.rationale}</p>
              {data && data.alternatives.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}>
                  Also considered: {data.alternatives.map((a) => `“${a.trend.title.slice(0, 40)}” (${a.score.toFixed(2)})`).join(" · ")}
                </div>
              )}
            </details>

            {/* Actions */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 18, gap: 8, flexWrap: "wrap" }}>
              <button className="btn btn-secondary btn-sm" onClick={() => generate(true)} disabled={loading || !!busy}>
                <RefreshCw size={14} /> Regenerate
              </button>
              {sent ? (
                <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "var(--accent-emerald)" }}>
                  <Check size={16} /> In your Kanban’s Ideas column, with the checklist in its notes.
                  <Link href="/kanban" className="btn btn-primary btn-sm">Open Kanban</Link>
                </div>
              ) : (
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-ghost btn-sm" onClick={dismiss} disabled={!!busy}>Not this one</button>
                  <button className="btn btn-primary btn-sm" onClick={sendToKanban} disabled={!!busy}>
                    {busy === "board" ? <Loader2 size={14} className="animate-spin" /> : <KanbanSquare size={14} />} Send to Kanban
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
