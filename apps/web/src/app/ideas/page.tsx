"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, KanbanSquare, X, Loader2, ChevronDown, ChevronUp, Wand2, Quote, ListOrdered } from "lucide-react";
import { ideasApi, type Idea } from "@/lib/api";
import { useSession } from "@/hooks/useSession";
import { useAsyncLoad } from "@/hooks/useAsyncLoad";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useFeedback } from "@/components/FeedbackWidget";
import { track as trackEvent } from "@/lib/telemetry";
import AppShell from "@/components/AppShell";
import { ConfidencePill, ErrorBanner, PlatformBadge, PredictionBar, SlotChip, TypeBadge } from "@/components/ui";

const STRATEGY_LABEL: Record<string, string> = {
  double_down: "Double down",
  cross_post: "Cross-post",
  remix: "Remix",
  revive: "Revive",
  series: "Series",
  evergreen: "Evergreen",
  trend: "Trend",
  manual: "Manual",
};

function IdeaCard({ idea, onBoard, onDismiss, busy }: { idea: Idea; onBoard: () => void; onDismiss: () => void; busy: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card idea-card animate-fade-in-up">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 10 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <PlatformBadge platform={idea.platform} />
          <TypeBadge type={idea.content_type} />
          <span className="pill">{STRATEGY_LABEL[idea.strategy] ?? idea.strategy}</span>
          {idea.source === "trend" && <span className="pill" style={{ color: "var(--accent-amber)", borderColor: "var(--accent-amber)" }}>from trend</span>}
        </div>
        <ConfidencePill level={idea.prediction?.confidence_label ?? "low"} />
      </div>

      <h3 style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.35, marginBottom: 10 }}>{idea.title}</h3>

      {idea.hook && (
        <div style={{ display: "flex", gap: 8, fontSize: 13, color: "var(--text-secondary)", fontStyle: "italic", marginBottom: 14, lineHeight: 1.5 }}>
          <Quote size={14} style={{ flexShrink: 0, marginTop: 3, color: "var(--accent-violet)" }} />
          <span>{idea.hook}</span>
        </div>
      )}

      {idea.prediction?.expected_views !== undefined && <PredictionBar prediction={idea.prediction} />}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
        <SlotChip slot={idea.recommended_slot} />
        {idea.topics.map((t) => <span className="pill" key={t}>#{t}</span>)}
      </div>

      <button className="btn btn-ghost btn-sm" style={{ marginTop: 10, paddingLeft: 0 }} onClick={() => { if (!open) trackEvent("ideas", "expand_outline", { strategy: idea.strategy }); setOpen(!open); }}>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />} {open ? "Hide" : "Show"} outline & reasoning
      </button>
      {open && (
        <div style={{ marginTop: 8 }}>
          <div className="metric-label" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}><ListOrdered size={12} /> Outline</div>
          <ol className="outline-list">{idea.outline.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <div className="metric-label" style={{ marginTop: 12, marginBottom: 6 }}>Why this idea</div>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>{idea.rationale}</p>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
        <button className="btn btn-secondary btn-sm" onClick={onDismiss} disabled={busy}><X size={14} /> Dismiss</button>
        <button className="btn btn-primary btn-sm" onClick={onBoard} disabled={busy}><KanbanSquare size={14} /> Send to Kanban</button>
      </div>
    </div>
  );
}

export default function IdeasPage() {
  const router = useRouter();
  const { token, email, isDemo, ready, signOut } = useSession();
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(6);
  const [toast, setToast] = useState<string | null>(null);
  const { track } = useTelemetry("ideas", token, ready);
  const { askAfter } = useFeedback();

  const load = useCallback(async () => {
    if (!token) return;
    try { setIdeas((await ideasApi.list(token, "pending")).ideas); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load ideas"); }
    finally { setLoading(false); }
  }, [token]);

  useAsyncLoad(load, ready);

  const generate = async () => {
    setGenerating(true); setError(null);
    try {
      const res = await ideasApi.generate(token, count);
      setIdeas((prev) => [...res.ideas, ...prev]);
      track("generate", { count, strategies: res.ideas.map((i) => i.strategy).join(",") });
      askAfter("ideas", "generate", { count });
    } catch (e) { setError(e instanceof Error ? e.message : "Generation failed"); }
    finally { setGenerating(false); }
  };

  const act = async (idea: Idea, action: "board" | "dismiss") => {
    setBusy(idea.id); setError(null);
    const prev = ideas;
    setIdeas((p) => p.filter((i) => i.id !== idea.id));
    try {
      if (action === "board") {
        await ideasApi.toBoard(token, idea.id);
        setToast(`“${idea.title}” is in the Ideas column of your Kanban`);
        track("to_board", { strategy: idea.strategy, platform: idea.platform, content_type: idea.content_type, confidence: idea.prediction?.confidence ?? null });
        askAfter("ideas", "to_board", { strategy: idea.strategy });
      } else {
        await ideasApi.dismiss(token, idea.id);
        track("dismiss", { strategy: idea.strategy, platform: idea.platform, content_type: idea.content_type });
      }
      setTimeout(() => setToast(null), 3000);
    } catch (e) {
      setIdeas(prev);
      setError(e instanceof Error ? e.message : "Action failed");
    } finally { setBusy(null); }
  };

  return (
    <AppShell token={token} title="Ideas" subtitle="Titles, hooks and outlines generated from your own patterns — each with a forecast you can hold it to" email={email} isDemo={isDemo}
      onSignOut={async () => { await signOut(); router.push("/"); }}
      actions={
        <>
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} className="btn btn-secondary btn-sm" style={{ appearance: "auto" }}>
            {[3, 6, 9, 12].map((n) => <option key={n} value={n}>{n} ideas</option>)}
          </select>
          <button className="btn btn-primary btn-sm" onClick={generate} disabled={generating}>
            {generating ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />} Generate
          </button>
        </>
      }>
      <ErrorBanner error={error} />
      {toast && <div style={{ padding: "10px 14px", marginBottom: 16, borderRadius: "var(--radius-md)", background: "rgba(16,185,129,0.12)", border: "1px solid rgba(16,185,129,0.4)", color: "var(--accent-emerald)", fontSize: 13 }}>{toast} · <a href="/kanban" style={{ color: "inherit", textDecoration: "underline" }}>open Kanban</a></div>}

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Loader2 className="animate-spin" size={28} /></div>
      ) : ideas.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 60 }}>
          <Sparkles size={40} style={{ color: "var(--accent-violet)", marginBottom: 12 }} />
          <h3 style={{ fontWeight: 600, marginBottom: 6 }}>No pending ideas</h3>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>Generate a batch from your analytics. Each idea comes with a title, hook, outline, best posting slot and a forecast.</p>
          <button className="btn btn-primary" onClick={generate} disabled={generating}>{generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />} Generate ideas</button>
        </div>
      ) : (
        <div className="idea-grid">
          {ideas.map((idea) => (
            <IdeaCard key={idea.id} idea={idea} busy={busy === idea.id} onBoard={() => act(idea, "board")} onDismiss={() => act(idea, "dismiss")} />
          ))}
        </div>
      )}
    </AppShell>
  );
}
