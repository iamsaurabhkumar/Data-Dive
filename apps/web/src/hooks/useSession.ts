"use client";

import { useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export interface SessionInfo {
  token: string;          // Supabase access token, or "demo-token" in demo mode
  email: string;
  isDemo: boolean;
  ready: boolean;
}

/**
 * Resolves the Supabase session once and exposes the bearer token.
 * Falls back to demo mode (mock API) when there is no session.
 */
export function useSession(): SessionInfo & { signOut: () => Promise<void> } {
  const supabase = useMemo(() => createClient(), []);
  const [state, setState] = useState<SessionInfo>({ token: "", email: "Demo User", isDemo: true, ready: false });

  useEffect(() => {
    let cancelled = false;
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (cancelled) return;
      if (session?.user) {
        setState({ token: session.access_token, email: session.user.email || "Creator", isDemo: false, ready: true });
      } else {
        setState({ token: "demo-token", email: "Demo User", isDemo: true, ready: true });
      }
    });
    return () => { cancelled = true; };
  }, [supabase]);

  const signOut = async () => { await supabase.auth.signOut(); };
  return { ...state, signOut };
}
