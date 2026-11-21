"use client";

import { useEffect } from "react";

/**
 * Runs an async loader once `ready` flips to true (e.g. session resolved).
 * The call is scheduled on the next tick and cancelled on cleanup, so the
 * effect body itself never sets state synchronously.
 */
export function useAsyncLoad(load: () => Promise<void>, ready: boolean) {
  useEffect(() => {
    if (!ready) return;
    const handle = setTimeout(() => { void load(); }, 0);
    return () => clearTimeout(handle);
  }, [ready, load]);
}
