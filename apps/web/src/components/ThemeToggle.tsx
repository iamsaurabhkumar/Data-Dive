"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { track } from "@/lib/telemetry";

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggle } = useTheme();
  const next = theme === "light" ? "dark" : "light";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => { toggle(); track("other", "theme_toggle", { theme: next }); }}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      aria-pressed={theme === "light"}
    >
      {theme === "light" ? <Sun size={14} /> : <Moon size={14} />}
      {!compact && <span>{theme === "light" ? "Light" : "Dark"}</span>}
      <span className="theme-toggle-track" aria-hidden><span className="theme-toggle-knob" /></span>
    </button>
  );
}
