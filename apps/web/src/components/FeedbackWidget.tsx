"use client";

import { useEffect, useState, type ReactNode } from "react";
import { MessageSquareHeart, Star, X, Loader2, Check } from "lucide-react";
import { feedbackApi, type SurveyQuestion } from "@/lib/api";
import { track, type FeatureId } from "@/lib/telemetry";

type Worth = "yes" | "somewhat" | "no";

interface Survey {
  feature: FeatureId;
  label: string;
  questions: SurveyQuestion[];
  trigger: "prompt" | "manual";
  context?: Record<string, string | number | boolean>;
}

/**
 * A tiny module-level bus instead of React context: pages call `useFeedback()` *above*
 * the AppShell that renders the survey host, so context would not reach them.
 */
const bus: { token: string; currentFeature: FeatureId; show: ((s: Survey) => void) | null } = { token: "", currentFeature: "other", show: null };

const FEATURE_LABELS: Record<string, string> = {
  dashboard: "the Dashboard", analytics: "Analytics", ideas: "the Idea generator", board: "the Production board",
  review: "Prediction review", trend_feed: "the Trend feed", next_project: "Generate Next Project", sync: "Platform sync", insights: "Insights", usage: "the Usage page", other: "Data-Dive",
};

const DEFAULT_QUESTIONS = (label: string): SurveyQuestion[] => [
  { id: "rating", type: "scale", min: 1, max: 5, text: `How would you rate ${label}?` },
  { id: "worth_it", type: "choice", options: ["yes", "somewhat", "no"], text: "Was it worth using?" },
  { id: "improvement", type: "text", optional: true, max_length: 1000, text: "What should we improve or add?" },
];

/** Ask the server whether to show the micro-survey after a feature moment. Silent if not eligible. */
export function askAfter(feature: FeatureId, moment: string, context?: Survey["context"]) {
  if (!bus.token || !bus.show) return;
  feedbackApi.prompt(bus.token, feature, moment).then((d) => {
    if (d.prompt && bus.show) {
      bus.show({ feature, label: FEATURE_LABELS[feature] ?? feature, questions: d.questions ?? DEFAULT_QUESTIONS(FEATURE_LABELS[feature] ?? feature), trigger: "prompt", context });
    }
  }).catch(() => undefined);
}

/** Open the survey unconditionally (sidebar button). */
export function openFeedback(feature: FeatureId = bus.currentFeature) {
  track("feedback", "open", { feature });
  bus.show?.({ feature, label: FEATURE_LABELS[feature] ?? feature, questions: DEFAULT_QUESTIONS(FEATURE_LABELS[feature] ?? feature), trigger: "manual" });
}

export function useFeedback() {
  return { askAfter, open: openFeedback };
}

/** Rendered once by AppShell; owns the visible survey and the current token. */
export function FeedbackProvider({ token, currentFeature, children }: { token: string; currentFeature: FeatureId; children: ReactNode }) {
  const [survey, setSurvey] = useState<Survey | null>(null);

  useEffect(() => {
    bus.token = token;
    bus.currentFeature = currentFeature;
    bus.show = (s) => setSurvey(s);
    return () => { bus.show = null; };
  }, [token, currentFeature]);

  return (
    <>
      {children}
      {survey && <SurveyCard token={token} survey={survey} onClose={() => setSurvey(null)} />}
    </>
  );
}

function SurveyCard({ token, survey, onClose }: { token: string; survey: Survey; onClose: () => void }) {
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [worth, setWorth] = useState<Worth | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const q = Object.fromEntries(survey.questions.map((x) => [x.id, x])) as Record<string, SurveyQuestion>;

  const dismiss = () => {
    if (survey.trigger === "prompt") feedbackApi.dismiss(token, survey.feature).catch(() => undefined);
    track("feedback", "dismiss", { feature: survey.feature, trigger: survey.trigger });
    onClose();
  };

  const submit = async () => {
    if (!rating || !worth) return;
    setBusy(true); setError(null);
    try {
      await feedbackApi.submit(token, { feature: survey.feature, rating, worth_it: worth, improvement: text, context: survey.context, trigger: survey.trigger });
      setDone(true);
      setTimeout(onClose, 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send feedback");
    } finally { setBusy(false); }
  };

  return (
    <div className="survey animate-fade-in-up" role="dialog" aria-label="Feature feedback">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: 14 }}>
          <MessageSquareHeart size={16} color="var(--accent-violet)" /> Quick feedback
        </div>
        <button className="btn btn-ghost btn-sm" onClick={dismiss} aria-label="Dismiss"><X size={14} /></button>
      </div>

      {done ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent-emerald)", fontSize: 13, padding: "12px 0" }}>
          <Check size={16} /> Thanks — this goes straight to the roadmap.
        </div>
      ) : (
        <>
          <div className="survey-q">{q.rating?.text ?? `How would you rate ${survey.label}?`}</div>
          <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className="star" onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(0)} onClick={() => setRating(n)} aria-label={`${n} star`}>
                <Star size={22} fill={(hover || rating) >= n ? "var(--accent-amber)" : "none"} color={(hover || rating) >= n ? "var(--accent-amber)" : "var(--text-muted)"} />
              </button>
            ))}
          </div>

          <div className="survey-q">{q.worth_it?.text ?? "Was it worth using?"}</div>
          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
            {(["yes", "somewhat", "no"] as Worth[]).map((w) => (
              <button key={w} className={`filter-btn ${worth === w ? "active" : ""}`} onClick={() => setWorth(w)}>{w}</button>
            ))}
          </div>

          <div className="survey-q">{q.improvement?.text ?? "What should we improve or add?"} <span style={{ color: "var(--text-muted)" }}>(optional)</span></div>
          <textarea value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Be blunt — what's missing, confusing or not worth your time?" />

          {error && <div style={{ color: "var(--accent-rose)", fontSize: 12, marginTop: 6 }}>{error}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
            <button className="btn btn-secondary btn-sm" onClick={dismiss}>Not now</button>
            <button className="btn btn-primary btn-sm" disabled={!rating || !worth || busy} onClick={submit}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Send
            </button>
          </div>
        </>
      )}
    </div>
  );
}
