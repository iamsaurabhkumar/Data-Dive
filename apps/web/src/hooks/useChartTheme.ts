"use client";

import { useEffect, useState } from "react";
import { onThemeChange } from "@/hooks/useTheme";

export interface ChartTheme {
  grid: string; axis: string; tick: string;
  tooltip: { backgroundColor: string; borderColor: string; borderRadius: number; color: string };
  accents: string[];
}

const VARS = ["--chart-grid", "--chart-axis", "--chart-tick", "--chart-tooltip-bg", "--chart-tooltip-border", "--chart-tooltip-text",
  "--accent-blue", "--accent-violet", "--accent-emerald", "--accent-amber", "--accent-rose", "--accent-cyan", "--text-muted"];

function read(): ChartTheme {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string) => cs.getPropertyValue(name).trim();
  return {
    grid: v("--chart-grid"), axis: v("--chart-axis"), tick: v("--chart-tick"),
    tooltip: { backgroundColor: v("--chart-tooltip-bg"), borderColor: v("--chart-tooltip-border"), borderRadius: 8, color: v("--chart-tooltip-text") },
    accents: [v("--accent-blue"), v("--accent-violet"), v("--accent-emerald"), v("--accent-amber"), v("--accent-rose"), v("--accent-cyan"), "#a3e635", "#f97316", v("--text-muted")],
  };
}

const FALLBACK: ChartTheme = {
  grid: "#2d3748", axis: "#4a5568", tick: "#a0aec0",
  tooltip: { backgroundColor: "#1a202c", borderColor: "#4a5568", borderRadius: 8, color: "#f1f5f9" },
  accents: ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#f43f5e", "#06b6d4", "#a3e635", "#f97316", "#64748b"],
};

/**
 * Recharts paints SVG presentation attributes, where CSS var() is not reliable,
 * so chart colours are resolved from the active palette and refreshed on theme change.
 */
export function useChartTheme(): ChartTheme {
  const [t, setT] = useState<ChartTheme>(FALLBACK);
  useEffect(() => {
    const h = setTimeout(() => setT(read()), 0);
    const off = onThemeChange(() => setT(read()));
    return () => { clearTimeout(h); off(); };
  }, []);
  void VARS;
  return t;
}
