"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
export const THEME_KEY = "dd.theme";
const EVENT = "dd:theme";

/** Inline script for <head>: applies the stored/system theme before React hydrates (no flash). */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark"){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","dark");}})();`;

export function getTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme, persist = true) {
  document.documentElement.setAttribute("data-theme", theme);
  if (persist) {
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode */ }
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: theme }));
}

/** Subscribe to theme changes (same tab + other tabs). Returns an unsubscribe function. */
export function onThemeChange(cb: (theme: Theme) => void): () => void {
  const onLocal = (e: Event) => cb((e as CustomEvent<Theme>).detail);
  const onStorage = (e: StorageEvent) => {
    if (e.key === THEME_KEY && (e.newValue === "light" || e.newValue === "dark")) {
      document.documentElement.setAttribute("data-theme", e.newValue);
      cb(e.newValue);
    }
  };
  window.addEventListener(EVENT, onLocal);
  window.addEventListener("storage", onStorage);
  return () => { window.removeEventListener(EVENT, onLocal); window.removeEventListener("storage", onStorage); };
}

export function useTheme() {
  // Server render + first client render must agree; the real value is read after mount.
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const sync = () => setThemeState(getTheme());
    const h = setTimeout(sync, 0);
    const off = onThemeChange(sync);
    // Follow the OS only while the user has not chosen explicitly
    const mq = window.matchMedia?.("(prefers-color-scheme: light)");
    const onMq = (e: MediaQueryListEvent) => {
      let stored: string | null = null;
      try { stored = localStorage.getItem(THEME_KEY); } catch { /* ignore */ }
      if (!stored) applyTheme(e.matches ? "light" : "dark", false);
    };
    mq?.addEventListener?.("change", onMq);
    return () => { clearTimeout(h); off(); mq?.removeEventListener?.("change", onMq); };
  }, []);

  const setTheme = useCallback((t: Theme) => { applyTheme(t); setThemeState(t); }, []);
  const toggle = useCallback(() => setTheme(getTheme() === "light" ? "dark" : "light"), [setTheme]);
  return { theme, setTheme, toggle };
}
