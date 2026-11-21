"use client";

import { useCallback, useEffect, useMemo, useState, DragEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Plus, Loader2, X, Trash2, Link2, Target, CheckCircle2, ArrowRight, Quote, History, Wand2, TrendingUp, TrendingDown, Minus,
  Lightbulb, PenLine, Clapperboard, Scissors, Rocket, CalendarClock,
} from "lucide-react";
import { api, formatNumber, kanbanApi, PIPELINE, STAGE_LABELS, type Card, type ContentPost, type Stage } from "@/lib/api";
import { useSession } from "@/hooks/useSession";
import { useAsyncLoad } from "@/hooks/useAsyncLoad";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useFeedback } from "@/components/FeedbackWidget";
import { track as trackEvent } from "@/lib/telemetry";
import AppShell from "@/components/AppShell";
import { ErrorBanner, Lift, PlatformBadge, PredictionBar, SlotChip, TypeBadge } from "@/components/ui";

const FORMATS: Record<string, string[]> = { YouTube: ["Short", "Long-form"], Instagram: ["Reel", "Post"] };

const COLUMN_META: Record<Exclude<Stage, "reviewed">, { icon: React.ReactNode; color: string; hint: string; empty: string }> = {
  idea: { icon: <Lightbulb size={14} />, color: "var(--accent-amber)", hint: "Backlog — picked from Explore or the Idea generator", empty: "Send ideas here from Explore or Ideas" },
  scripting: { icon: <PenLine size={14} />, color: "var(--accent-violet)", hint: "Write the hook and outline", empty: "Drag an idea here to start the script" },
  filming: { icon: <Clapperboard size={14} />, color: "var(--accent-cyan)", hint: "Shoot / record", empty: "Nothing being filmed" },
  editing: { icon: <Scissors size={14} />, color: "var(--accent-blue)", hint: "Cut, thumbnail, schedule the publish slot", empty: "Nothing in the edit" },
  published: { icon: <Rocket size={14} />, color: "var(--accent-emerald)", hint: "Link the live post, then compare with the forecast", empty: "Nothing published yet" },
};

/** Stage used for drag/drop and API calls; reviewed cards sit in the Published column. */
const columnOf = (stage: Stage): Exclude<Stage, "reviewed"> => (stage === "reviewed" ? "published" : stage);

function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  return new Date(s).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function VerdictIcon({ verdict }: { verdict: string }) {
  if (verdict === "outperformed") return <TrendingUp size={14} color="var(--accent-emerald)" />;
  if (verdict === "underperformed") return <TrendingDown size={14} color="var(--accent-rose)" />;
  return <Minus size={14} color="var(--accent-amber)" />;
}

// ──────────────────────────────────────────────────────────────────────────
// Card drawer
// ──────────────────────────────────────────────────────────────────────────
function CardDrawer({ card, token, onClose, onChange }: { card: Card; token: string; onClose: () => void; onChange: (c: Card | null) => void }) {
  const [detail, setDetail] = useState<Card>(card);
  const [form, setForm] = useState({ title: card.title, hook: card.hook, notes: card.notes, outline: card.outline.join("\n"), scheduled_for: card.scheduled_for ?? "", published_at: card.published_at ?? "" });
  const [posts, setPosts] = useState<ContentPost[]>([]);
  const [pick, setPick] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    kanbanApi.card(token, card.id).then(setDetail).catch(() => undefined);
  }, [token, card.id]);

  useEffect(() => {
    if (detail.stage === "published" && !detail.post_id) {
      api.getFeed(token, { platform: detail.platform, sort_by: "published_at" }).then((r) => setPosts(r.posts)).catch(() => undefined);
    }
  }, [token, detail.stage, detail.post_id, detail.platform]);

  const { askAfter } = useFeedback();
  const run = async (key: string, fn: () => Promise<Card | void>) => {
    setBusy(key); setError(null);
    try {
      const res = await fn();
      if (res) { setDetail(res); onChange(res); }
      const feature = key === "review" || key === "link" || key === "auto" ? "review" : "board";
      trackEvent(feature, key, { stage: res?.stage ?? detail.stage, platform: detail.platform, content_type: detail.content_type,
        ...(key === "review" && res?.review ? { verdict: res.review.verdict, views_ratio: res.review.views_ratio } : {}) });
      if (key === "review" && res?.review) askAfter("review", "review", { verdict: res.review.verdict });
      if (key === "advance" && res?.stage === "published") trackEvent("board", "published", { platform: detail.platform, content_type: detail.content_type });
    } catch (e) {
      trackEvent("board", `${key}_failed`, { stage: detail.stage });
      setError(e instanceof Error ? e.message : "Action failed");
    }
    finally { setBusy(null); }
  };

  const save = () => run("save", () => kanbanApi.update(token, card.id, {
    title: form.title, hook: form.hook, notes: form.notes,
    outline: form.outline.split("\n").map((s) => s.trim()).filter(Boolean),
    scheduled_for: form.scheduled_for || undefined,
    published_at: form.published_at || undefined,
  }));

  const next = PIPELINE[PIPELINE.indexOf(columnOf(detail.stage)) + 1];
  const canAdvance = detail.stage !== "reviewed" && !!next;
  const review = detail.review;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <PlatformBadge platform={detail.platform} /><TypeBadge type={detail.content_type} />
            <span className="pill">{STAGE_LABELS[detail.stage]}</span>
            {detail.strategy && <span className="pill">{detail.strategy.replace("_", " ")}</span>}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={16} /></button>
        </div>
        <h2 style={{ marginTop: 12 }}>{detail.title}</h2>
        <ErrorBanner error={error} />

        {/* Review result */}
        {review && (
          <div className="card" style={{ marginTop: 16, borderColor: review.verdict === "outperformed" ? "rgba(16,185,129,0.4)" : review.verdict === "underperformed" ? "rgba(244,63,94,0.4)" : "rgba(245,158,11,0.4)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, marginBottom: 10 }}>
              <VerdictIcon verdict={review.verdict} /> {review.verdict.replace("_", " ")} · actual <Lift value={review.views_ratio} /> of forecast
            </div>
            {detail.prediction && <PredictionBar prediction={detail.prediction} actual={review.actual.views} />}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, margin: "14px 0" }}>
              <div><div className="metric-label">Predicted</div><div className="metric-value" style={{ fontSize: 16 }}>{formatNumber(review.predicted.views)}</div></div>
              <div><div className="metric-label">Actual</div><div className="metric-value" style={{ fontSize: 16 }}>{formatNumber(review.actual.views)}</div></div>
              <div><div className="metric-label">Eng. rate</div><div className="metric-value" style={{ fontSize: 16 }}>{review.actual.engagement_rate}% <span style={{ fontSize: 11, color: review.er_delta >= 0 ? "var(--accent-emerald)" : "var(--accent-rose)" }}>({review.er_delta >= 0 ? "+" : ""}{review.er_delta} pt)</span></div></div>
            </div>
            <div className="metric-label" style={{ marginBottom: 6 }}>What we learned</div>
            {review.lessons.map((l, i) => <div className="lesson" key={i}>{l}</div>)}
          </div>
        )}

        {/* Forecast */}
        {detail.prediction && !review && (
          <div style={{ marginTop: 16 }}>
            <label>Forecast</label>
            <PredictionBar prediction={detail.prediction} />
            <div style={{ marginTop: 8 }}><SlotChip slot={detail.recommended_slot} /></div>
          </div>
        )}

        {/* Linked post */}
        {detail.linked_post && (
          <div style={{ marginTop: 16 }}>
            <label>Linked post</label>
            <div className="finding" style={{ alignItems: "center" }}>
              <Link2 size={16} color="var(--accent-blue)" />
              <div style={{ fontSize: 13 }}>
                <div style={{ fontWeight: 500 }}>{detail.linked_post.title}</div>
                <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{formatNumber(detail.linked_post.metrics.views)} views · {fmtDate(detail.linked_post.published_at)}</div>
              </div>
            </div>
          </div>
        )}

        {/* Publish → link → review workflow */}
        {detail.stage === "published" && (
          <div className="card" style={{ marginTop: 16, background: "rgba(59,130,246,0.05)" }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, display: "flex", gap: 6, alignItems: "center" }}><Target size={14} /> Close the loop</div>
            {!detail.post_id ? (
              <>
                <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>Link the published post so the forecast can be checked against real numbers.</p>
                <div style={{ display: "flex", gap: 8 }}>
                  <select value={pick} onChange={(e) => setPick(e.target.value)} style={{ flex: 1 }}>
                    <option value="">Pick the published post…</option>
                    {posts.map((p) => <option key={p.id} value={p.id}>{p.title.slice(0, 60)} · {formatNumber(p.metrics.views)}</option>)}
                  </select>
                  <button className="btn btn-primary btn-sm" disabled={!pick || busy === "link"} onClick={() => run("link", () => kanbanApi.linkPost(token, card.id, { post_id: pick }))}>Link</button>
                  <button className="btn btn-secondary btn-sm" disabled={busy === "auto"} onClick={() => run("auto", () => kanbanApi.linkPost(token, card.id, { auto: true }))}><Wand2 size={14} /> Auto</button>
                </div>
              </>
            ) : (
              <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={busy === "review"} onClick={() => run("review", () => kanbanApi.review(token, card.id))}>
                {busy === "review" ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />} Compare with forecast & learn
              </button>
            )}
          </div>
        )}

        {/* Editable fields */}
        {detail.stage !== "reviewed" && (
          <>
            <label>Title</label>
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <label>Hook</label>
            <textarea value={form.hook} onChange={(e) => setForm({ ...form, hook: e.target.value })} />
            <label>Outline (one beat per line)</label>
            <textarea value={form.outline} onChange={(e) => setForm({ ...form, outline: e.target.value })} style={{ minHeight: 140 }} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div><label><CalendarClock size={11} style={{ display: "inline", marginRight: 4 }} />Publish slot</label><input type="datetime-local" value={form.scheduled_for ? form.scheduled_for.slice(0, 16) : ""} onChange={(e) => setForm({ ...form, scheduled_for: e.target.value ? new Date(e.target.value).toISOString() : "" })} /></div>
              <div><label>Published at</label><input type="datetime-local" value={form.published_at ? form.published_at.slice(0, 16) : ""} onChange={(e) => setForm({ ...form, published_at: e.target.value ? new Date(e.target.value).toISOString() : "" })} /></div>
            </div>
            <label>Notes</label>
            <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
              <button className="btn btn-primary btn-sm" onClick={save} disabled={busy === "save"}>Save</button>
              {canAdvance && (
                <button className="btn btn-secondary btn-sm" disabled={busy === "advance"} onClick={() => run("advance", () => kanbanApi.move(token, card.id, next as Stage))}>
                  <ArrowRight size={14} /> Move to {STAGE_LABELS[next as Stage]}
                </button>
              )}
            </div>
          </>
        )}

        {detail.stage === "reviewed" && (
          <>
            <label>Hook</label>
            <div style={{ display: "flex", gap: 8, fontSize: 13, color: "var(--text-secondary)", fontStyle: "italic" }}><Quote size={14} /> {detail.hook || "—"}</div>
            <label>Outline</label>
            <ol className="outline-list">{detail.outline.map((s, i) => <li key={i}>{s}</li>)}</ol>
          </>
        )}

        {detail.rationale && (<><label>Why this idea</label><p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>{detail.rationale}</p></>)}

        {detail.events && detail.events.length > 0 && (
          <>
            <label><History size={11} style={{ display: "inline", marginRight: 4 }} />History</label>
            {detail.events.map((e) => (
              <div key={e.id} style={{ fontSize: 12, color: "var(--text-secondary)", padding: "4px 0", display: "flex", gap: 8 }}>
                <span className="font-mono" style={{ color: "var(--text-muted)", flexShrink: 0 }}>{fmtDate(e.created_at)}</span>
                <span>{e.from_stage ? `${STAGE_LABELS[e.from_stage as Stage]} → ` : ""}{STAGE_LABELS[e.to_stage as Stage]}{e.note ? ` · ${e.note}` : ""}</span>
              </div>
            ))}
          </>
        )}

        <div style={{ marginTop: 24, borderTop: "1px solid var(--border-subtle)", paddingTop: 14 }}>
          <button className="btn btn-ghost btn-sm" style={{ color: "var(--accent-rose)" }} disabled={busy === "delete"}
            onClick={() => { if (confirm("Delete this card?")) run("delete", async () => { await kanbanApi.remove(token, card.id); onChange(null); onClose(); }); }}>
            <Trash2 size={14} /> Delete card
          </button>
        </div>
      </div>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// New card modal
// ──────────────────────────────────────────────────────────────────────────
function NewCard({ token, onClose, onCreated }: { token: string; onClose: () => void; onCreated: (c: Card) => void }) {
  const [form, setForm] = useState({ title: "", platform: "YouTube", content_type: "Long-form", hook: "", topics: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      onCreated(await kanbanApi.create(token, { ...form, topics: form.topics.split(",").map((t) => t.trim()).filter(Boolean) }));
      trackEvent("board", "create", { platform: form.platform, content_type: form.content_type, has_topics: form.topics.trim().length > 0 });
      onClose();
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  };
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <div style={{ display: "flex", justifyContent: "space-between" }}><h2>New card</h2><button className="btn btn-ghost btn-sm" onClick={onClose}><X size={16} /></button></div>
        <ErrorBanner error={error} />
        <label>Title</label><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Working title" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div><label>Platform</label>
            <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value, content_type: FORMATS[e.target.value][0] })}>
              {Object.keys(FORMATS).map((p) => <option key={p}>{p}</option>)}
            </select></div>
          <div><label>Format</label>
            <select value={form.content_type} onChange={(e) => setForm({ ...form, content_type: e.target.value })}>
              {FORMATS[form.platform].map((f) => <option key={f}>{f}</option>)}
            </select></div>
        </div>
        <label>Hook</label><textarea value={form.hook} onChange={(e) => setForm({ ...form, hook: e.target.value })} />
        <label>Topics (comma separated — used for the forecast)</label><input value={form.topics} onChange={(e) => setForm({ ...form, topics: e.target.value })} placeholder="editing, camera" />
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>A forecast and recommended posting slot are computed from your analytics when the card is created.</p>
        <div style={{ marginTop: 16 }}><button className="btn btn-primary" disabled={!form.title || busy} onClick={submit}>{busy ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />} Create</button></div>
      </div>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Board
// ──────────────────────────────────────────────────────────────────────────
export default function BoardPage() {
  const router = useRouter();
  const { token, email, isDemo, ready, signOut } = useSession();
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Card | null>(null);
  const [creating, setCreating] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<Stage | null>(null);
  const { track } = useTelemetry("board", token, ready);
  const { askAfter } = useFeedback();

  const load = useCallback(async () => {
    if (!token) return;
    try { setCards((await kanbanApi.board(token)).columns.flatMap((c) => c.cards)); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load board"); }
    finally { setLoading(false); }
  }, [token]);

  useAsyncLoad(load, ready);

  const byColumn = useMemo(() => {
    const m = Object.fromEntries(PIPELINE.map((s) => [s, [] as Card[]])) as Record<Exclude<Stage, "reviewed">, Card[]>;
    for (const c of cards) m[columnOf(c.stage)].push(c);
    for (const s of PIPELINE) {
      // reviewed cards are terminal: keep them after the live published ones
      m[s].sort((a, b) => (a.stage === "reviewed" ? 1 : 0) - (b.stage === "reviewed" ? 1 : 0) || a.position - b.position);
    }
    return m;
  }, [cards]);

  const upsert = (c: Card | null, id?: string) => {
    setCards((prev) => {
      if (!c) return prev.filter((x) => x.id !== id);
      const i = prev.findIndex((x) => x.id === c.id);
      if (i === -1) return [...prev, c];
      const copy = [...prev]; copy[i] = c; return copy;
    });
  };

  /** Drop on a column (append) or on a card (insert before it). */
  const onDrop = async (e: DragEvent, stage: Exclude<Stage, "reviewed">, beforeCardId?: string) => {
    e.preventDefault();
    e.stopPropagation();
    const id = dragId ?? e.dataTransfer.getData("text/plain");
    setOver(null); setDragId(null);
    const card = cards.find((c) => c.id === id);
    if (!card || card.stage === "reviewed" || id === beforeCardId) return;
    const siblings = byColumn[stage].filter((c) => c.id !== id && c.stage !== "reviewed");
    const position = beforeCardId ? Math.max(0, siblings.findIndex((c) => c.id === beforeCardId)) : siblings.length;
    if (card.stage === stage && card.position === position) return;
    const prev = cards;
    upsert({ ...card, stage, position: position - 0.5 });  // optimistic; server returns exact positions
    try {
      const moved = await kanbanApi.move(token, id, stage, position);
      const board = await kanbanApi.board(token);          // sibling positions were renumbered server-side
      setCards(board.columns.flatMap((c) => c.cards)); setError(null);
      track("move", { from: card.stage, to: stage, via: "drag", position, platform: card.platform, content_type: card.content_type });
      if (stage === "published" && card.stage !== "published") track("published", { platform: moved.platform, content_type: moved.content_type });
      if (card.stage !== stage) askAfter("board", "move", { to: stage });
    } catch (err) { setCards(prev); setError(err instanceof Error ? err.message : "Move failed"); }
  };

  const summary = useMemo(() => {
    const reviewed = cards.filter((c) => c.review);
    const hits = reviewed.filter((c) => c.review?.within_range).length;
    return { reviewed: reviewed.length, hits, live: cards.filter((c) => c.stage !== "reviewed").length };
  }, [cards]);

  return (
    <AppShell token={token} title="Kanban" subtitle="Ideas → Scripting → Filming → Editing → Published. Drag cards along the pipeline, then check published ones against their forecast." email={email} isDemo={isDemo}
      onSignOut={async () => { await signOut(); router.push("/"); }}
      actions={
        <>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{summary.live} in progress · {summary.reviewed} reviewed{summary.reviewed ? ` · ${summary.hits}/${summary.reviewed} inside forecast` : ""}</span>
          <button className="btn btn-secondary btn-sm" onClick={() => router.push("/explore")}><Lightbulb size={14} /> Explore</button>
          <button className="btn btn-secondary btn-sm" onClick={() => router.push("/ideas")}><Wand2 size={14} /> Get ideas</button>
          <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}><Plus size={14} /> New card</button>
        </>
      }>
      <ErrorBanner error={error} />
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Loader2 className="animate-spin" size={28} /></div>
      ) : (
        <div className="kanban kanban-5">
          {PIPELINE.map((stage) => {
            const meta = COLUMN_META[stage];
            const items = byColumn[stage];
            return (
              <div key={stage} className={`kanban-col ${over === stage ? "drag-over" : ""}`}
                onDragOver={(e) => { e.preventDefault(); if (over !== stage) setOver(stage); }}
                onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(null); }}
                onDrop={(e) => onDrop(e, stage)}>
                <div className="kanban-col-header" style={{ borderTop: `2px solid ${meta.color}` }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, color: meta.color }}>{meta.icon} {STAGE_LABELS[stage]}</span>
                  <span className="font-mono">{items.length}</span>
                </div>
                <div className="kanban-col-hint">{meta.hint}</div>
                <div className="kanban-cards">
                  {items.map((c) => {
                    const reviewed = c.stage === "reviewed";
                    return (
                      <div key={c.id} className={`kanban-card ${dragId === c.id ? "dragging" : ""} ${reviewed ? "kanban-card-reviewed" : ""}`} draggable={!reviewed}
                        onDragStart={(e) => { setDragId(c.id); e.dataTransfer.setData("text/plain", c.id); e.dataTransfer.effectAllowed = "move"; }}
                        onDragEnd={() => { setDragId(null); setOver(null); }}
                        onDragOver={(e) => { e.preventDefault(); }}
                        onDrop={(e) => onDrop(e, stage, reviewed ? undefined : c.id)}
                        onClick={() => { track("open_card", { stage: c.stage, has_review: !!c.review }); setSelected(c); }}>
                        <div className="kanban-card-title">{c.title}</div>
                        <div className="kanban-card-meta">
                          <PlatformBadge platform={c.platform} /><TypeBadge type={c.content_type} />
                          {c.prediction && <span>· {formatNumber(c.prediction.expected_views)} fc.</span>}
                          {c.strategy && c.strategy !== "manual" && <span className="pill" style={{ padding: "1px 6px" }}>{c.strategy.replace("_", " ")}</span>}
                        </div>
                        {stage === "scripting" && <div style={{ fontSize: 11, marginTop: 6, color: c.hook ? "var(--text-muted)" : "var(--accent-amber)" }}>{c.hook ? `“${c.hook.slice(0, 70)}${c.hook.length > 70 ? "…" : ""}”` : "no hook yet"}</div>}
                        {stage === "editing" && <div style={{ fontSize: 11, color: c.scheduled_for ? "var(--accent-amber)" : "var(--text-muted)", marginTop: 6 }}><CalendarClock size={11} style={{ display: "inline", marginRight: 4 }} />{c.scheduled_for ? fmtDate(c.scheduled_for) : "no publish slot"}</div>}
                        {stage === "published" && !reviewed && <div style={{ fontSize: 11, marginTop: 6, color: c.post_id ? "var(--accent-blue)" : "var(--accent-amber)" }}>{c.post_id ? "linked · ready to review" : "link the post to review"}</div>}
                        {c.review && (
                          <div style={{ fontSize: 11, marginTop: 6, display: "flex", alignItems: "center", gap: 4 }}>
                            <VerdictIcon verdict={c.review.verdict} /> {formatNumber(c.review.actual.views)} vs {formatNumber(c.review.predicted.views)} · <Lift value={c.review.views_ratio} />
                            <span className="pill" style={{ marginLeft: "auto", padding: "1px 6px", color: "var(--accent-emerald)", borderColor: "var(--accent-emerald)" }}>reviewed</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {items.length === 0 && <div className="kanban-empty">{meta.empty}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selected && <CardDrawer card={selected} token={token} onClose={() => setSelected(null)} onChange={(c) => upsert(c, selected.id)} />}
      {creating && <NewCard token={token} onClose={() => setCreating(false)} onCreated={(c) => upsert(c)} />}
    </AppShell>
  );
}
