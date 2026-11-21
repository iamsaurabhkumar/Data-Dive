"use client";

import { ReactNode } from "react";
import { Video, Camera } from "lucide-react";
import type { Prediction, Slot } from "@/lib/api";
import { formatNumber } from "@/lib/api";

export function PlatformBadge({ platform }: { platform: string }) {
  const yt = platform === "YouTube";
  return (
    <span className={`badge ${yt ? "badge-youtube" : "badge-instagram"}`} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      {yt ? <Video size={11} /> : <Camera size={11} />} {yt ? "YT" : "IG"}
    </span>
  );
}

export function TypeBadge({ type }: { type: string }) {
  const cls = { short: "badge-short", "long-form": "badge-longform", reel: "badge-reel", post: "badge-post" }[type.toLowerCase()] || "";
  return <span className={`badge ${cls}`}>{type}</span>;
}

export function ConfidencePill({ level }: { level: string }) {
  const color = level === "high" ? "var(--accent-emerald)" : level === "medium" ? "var(--accent-amber)" : "var(--text-muted)";
  return <span className="pill" style={{ color, borderColor: color }}>{level} confidence</span>;
}

export function Lift({ value, suffix = "x" }: { value: number; suffix?: string }) {
  const color = value >= 1.15 ? "var(--accent-emerald)" : value <= 0.85 ? "var(--accent-rose)" : "var(--text-secondary)";
  return <span className="font-mono" style={{ color, fontWeight: 600 }}>{value.toFixed(2)}{suffix}</span>;
}

export function SlotChip({ slot }: { slot: Slot | null }) {
  if (!slot) return <span style={{ color: "var(--text-muted)", fontSize: 12 }}>no slot data</span>;
  return (
    <span className="pill" title={`${slot.posts} posts in this slot · ${slot.confidence} confidence`}>
      {slot.weekday_label} {slot.hour_bucket} · {slot.hour_range} · <Lift value={slot.lift} />
    </span>
  );
}

export function PredictionBar({ prediction, actual }: { prediction: Prediction; actual?: number }) {
  const max = Math.max(prediction.views_high, actual ?? 0) * 1.1;
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
        <span>Forecast <b className="font-mono" style={{ color: "var(--text-primary)" }}>{formatNumber(prediction.expected_views)}</b> views</span>
        <span className="font-mono">{formatNumber(prediction.views_low)} – {formatNumber(prediction.views_high)}</span>
      </div>
      <div style={{ position: "relative", height: 10, borderRadius: 5, background: "var(--bg-tertiary)" }}>
        <div style={{ position: "absolute", left: pct(prediction.views_low), width: `calc(${pct(prediction.views_high)} - ${pct(prediction.views_low)})`, top: 0, bottom: 0, background: "rgba(59,130,246,0.35)", borderRadius: 5 }} />
        <div style={{ position: "absolute", left: pct(prediction.expected_views), top: -2, width: 2, height: 14, background: "var(--accent-blue)" }} />
        {actual !== undefined && (
          <div title={`Actual ${actual.toLocaleString()}`} style={{ position: "absolute", left: `calc(${pct(actual)} - 5px)`, top: -1, width: 12, height: 12, borderRadius: "50%", background: actual > prediction.views_high ? "var(--accent-emerald)" : actual < prediction.views_low ? "var(--accent-rose)" : "var(--accent-amber)", border: "2px solid var(--bg-primary)" }} />
        )}
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11, color: "var(--text-muted)", flexWrap: "wrap" }}>
        <span>baseline {formatNumber(prediction.factors.format_baseline_views)}</span>
        <span>× topic <Lift value={prediction.factors.topic_lift} /></span>
        <span>× timing <Lift value={prediction.factors.time_lift} /></span>
        {prediction.factors.calibration !== 1 && <span>× calibration <Lift value={prediction.factors.calibration} /></span>}
        <span>· ER {prediction.expected_engagement_rate}%</span>
        <span>· {(prediction.confidence * 100).toFixed(0)}% confidence</span>
      </div>
    </div>
  );
}

export function Section({ title, icon, right, children }: { title: string; icon?: ReactNode; right?: ReactNode; children: ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>{icon}{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>{text}</div>;
}

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div style={{ padding: "12px 16px", marginBottom: 16, background: "rgba(244,63,94,0.1)", border: "1px solid rgba(244,63,94,0.4)", borderRadius: "var(--radius-md)", color: "var(--accent-rose)", fontSize: 13 }}>
      {error}
    </div>
  );
}
