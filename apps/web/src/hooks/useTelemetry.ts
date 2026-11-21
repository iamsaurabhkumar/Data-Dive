"use client";

import { useCallback, useEffect, useRef } from "react";
import { configureTelemetry, flush, track as rawTrack, trackPageView, type FeatureId, type TelemetryEvent } from "@/lib/telemetry";

/**
 * Configures the SDK with the session token, emits a page_view with time-on-page
 * when the page unmounts/hides, and returns a bound `track`.
 */
export function useTelemetry(feature: FeatureId, token: string, ready: boolean) {
  const started = useRef<number | null>(null);

  useEffect(() => {
    if (!ready || !token) return;
    configureTelemetry(token);
    started.current = performance.now();
    const page = window.location.pathname;
    const emit = () => {
      if (started.current === null) return;
      trackPageView(feature, page, Math.round(performance.now() - started.current));
      started.current = null;
    };
    // Full page unloads never run React cleanup, so emit + flush (keepalive) on pagehide/hidden too.
    const onHide = () => { if (document.visibilityState === "hidden") { emit(); void flush(true); } };
    const onPageHide = () => { emit(); void flush(true); };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onPageHide);
      emit();  // client-side navigation
    };
  }, [feature, token, ready]);

  const track = useCallback((action: string, properties?: TelemetryEvent["properties"]) => rawTrack(feature, action, properties), [feature]);
  return { track };
}
