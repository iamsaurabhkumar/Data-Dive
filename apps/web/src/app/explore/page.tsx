"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Sparkles,
  Target,
  Check,
  X,
  Loader2,
  AlertTriangle,
  Lightbulb,
  ArrowLeft
} from "lucide-react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useSession } from "@/hooks/useSession";
import { useAsyncLoad } from "@/hooks/useAsyncLoad";
import { ideasApi, type Idea } from "@/lib/api";
import { useTelemetry } from "@/hooks/useTelemetry";
import ThemeToggle from "@/components/ThemeToggle";

/**
 * Trend feed: suggestions produced by the background worker from platform trends.
 *
 * Reads and actions go through the authenticated API (creator-scoped); Supabase
 * Realtime is only used as a wake-up signal to refetch, so the browser never
 * needs row-level access to the table.
 */
export default function ExplorePage() {
  const supabase = useMemo(() => createClient(), []);
  const { token, ready, isDemo } = useSession();
  const [suggestions, setSuggestions] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const { track } = useTelemetry("trend_feed", token, ready);

  const fetchSuggestions = useCallback(async () => {
    if (!token) return;
    try {
      const res = await ideasApi.list(token, "pending");
      // Trend suggestions (worker) first, then analytics-driven ideas — both can be sent to the Kanban.
      setSuggestions([...res.ideas].sort((a, b) => (a.source === "trend" ? 0 : 1) - (b.source === "trend" ? 0 : 1)));
      setError(null);
    } catch (err) {
      console.error("Error fetching suggestions:", err);
      setError("Failed to load content suggestions.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useAsyncLoad(fetchSuggestions, ready);

  // Realtime: refetch (through the API) whenever the worker inserts/updates a suggestion
  useEffect(() => {
    if (!ready || isDemo) return;
    const channel = supabase
      .channel("realtime-suggestions")
      .on("postgres_changes", { event: "*", schema: "public", table: "content_suggestions" }, () => { fetchSuggestions(); })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [supabase, ready, isDemo, fetchSuggestions]);

  // Optimistic action handler
  const handleAction = async (id: string, action: "converted_to_kanban" | "rejected") => {
    const previousSuggestions = [...suggestions];
    setSuggestions((prev) => prev.filter((item) => item.id !== id));
    setError(null);
    try {
      track(action === "converted_to_kanban" ? "to_board" : "dismiss");
      if (action === "converted_to_kanban") {
        const card = await ideasApi.toBoard(token, id);
        setToast(`“${card.title}” is now in the Ideas column of your Kanban, with a forecast attached.`);
        setTimeout(() => setToast(null), 4000);
      } else {
        await ideasApi.dismiss(token, id);
      }
    } catch (err) {
      console.error("Failed to update suggestion state:", err);
      setSuggestions(previousSuggestions);
      setError("Failed to save action. Please try again.");
    }
  };

  return (
    <main className="min-h-screen bg-[var(--bg-primary)] text-[var(--text-primary)] p-6 md:p-12">
      {/* Header bar */}
      <div className="max-w-5xl mx-auto mb-10 flex items-center justify-between">
        <div className="flex items-center gap-4 flex-1">
          <Link
            href="/dashboard" 
            className="p-2 bg-[var(--bg-tertiary)] hover:bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-lg transition"
          >
            <ArrowLeft className="h-5 w-5 text-[var(--text-secondary)]" />
          </Link>
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-gradient">
              Explore Ideas
            </h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Pick what to make next: trend-driven suggestions and ideas from your own analytics. Send one to the Kanban to start production.
            </p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle compact />
            <Link href="/kanban" className="px-4 py-2 text-sm font-medium bg-[var(--accent-blue)] text-white hover:opacity-90 rounded-lg transition">
              Open Kanban →
            </Link>
          </div>
        </div>
      </div>

      {/* Main viewport container */}
      <div className="max-w-5xl mx-auto">
        {toast && (
          <div className="mb-6 p-4 bg-[rgba(16,185,129,0.1)] border border-[var(--accent-emerald)] rounded-xl flex items-center gap-3 text-[var(--accent-emerald)]">
            <Check className="h-5 w-5 flex-shrink-0 text-[var(--accent-emerald)]" />
            <p className="text-sm font-medium">{toast} <Link href="/kanban" className="underline">Open Kanban →</Link></p>
          </div>
        )}

        {/* Error notification banner */}
        {error && (
          <div className="mb-6 p-4 bg-[rgba(244,63,94,0.1)] border border-[var(--accent-rose)] rounded-xl flex items-center gap-3 text-[var(--accent-rose)]">
            <AlertTriangle className="h-5 w-5 flex-shrink-0 text-[var(--accent-rose)]" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {/* Loading fallback */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--accent-blue)]" />
            <p className="text-[var(--text-secondary)] text-sm font-mono">Curating global insights...</p>
          </div>
        ) : suggestions.length === 0 ? (
          /* Empty State */
          <div className="flex flex-col items-center justify-center text-center py-20 border border-dashed border-[var(--border-medium)] rounded-2xl bg-[var(--bg-glass)] max-w-2xl mx-auto">
            <div className="p-4 bg-[var(--tint-blue)] rounded-full mb-4">
              <Lightbulb className="h-10 w-10 text-[var(--accent-blue)]" />
            </div>
            <h3 className="text-lg font-semibold mb-2">Nothing to explore yet</h3>
            <p className="text-sm text-[var(--text-secondary)] max-w-sm">
              {isDemo
                ? "Trend suggestions come from the background worker (not available in demo mode). Generate analytics-driven ideas and they will show up here, ready to send to the Kanban."
                : "Our background processors are actively scraping trends. Keep this page open; new suggestions arrive in real-time — or generate ideas from your own analytics."}
            </p>
            <Link href="/ideas" className="mt-4 text-sm text-[var(--accent-blue)] underline">Generate ideas →</Link>
          </div>
        ) : (
          /* Ideas Grid */
          <div className="grid grid-cols-1 gap-6 max-w-3xl mx-auto">
            {suggestions.map((item) => (
              <div 
                key={item.id}
                className="group relative bg-[var(--bg-card)] backdrop-blur-md border border-[var(--border-medium)] hover:border-[var(--border-accent)] rounded-2xl p-6 transition-all duration-300 shadow-lg hover:shadow-xl"
              >
                {/* Confidence Metric Pin */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-2 px-3 py-1 bg-[var(--bg-tertiary)] border border-[var(--border-medium)] rounded-full">
                      <Target className="h-4 w-4 text-[var(--accent-emerald)]" />
                      <span className="text-xs font-mono text-[var(--text-secondary)]">
                        {(item.confidence_score * 100).toFixed(0)}% {item.source === "trend" ? "match" : "confidence"}
                      </span>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs border ${item.source === "trend" ? "border-[var(--accent-amber)] text-[var(--accent-amber)] bg-[rgba(245,158,11,0.1)]" : "border-[var(--accent-violet)] text-[var(--accent-violet)] bg-[rgba(139,92,246,0.1)]"}`}>
                      {item.source === "trend" ? "from platform trends" : "from your analytics"}
                    </span>
                    <span className="px-3 py-1 rounded-full text-xs border border-[var(--border-medium)] text-[var(--text-secondary)]">{item.platform} · {item.content_type}</span>
                  </div>
                  
                  {/* Quick Action buttons */}
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleAction(item.id, "converted_to_kanban")}
                      className="p-2 bg-[var(--bg-tertiary)] border border-[var(--border-medium)] hover:bg-[rgba(16,185,129,0.1)] hover:border-[var(--accent-emerald)] rounded-xl text-[var(--text-secondary)] hover:text-[var(--accent-emerald)] transition cursor-pointer"
                      title="Send to Kanban"
                    >
                      <Check className="h-4.5 w-4.5" />
                    </button>
                    <button
                      onClick={() => handleAction(item.id, "rejected")}
                      className="p-2 bg-[var(--bg-tertiary)] border border-[var(--border-medium)] hover:bg-[rgba(244,63,94,0.1)] hover:border-[var(--accent-rose)] rounded-xl text-[var(--text-secondary)] hover:text-[var(--accent-rose)] transition cursor-pointer"
                      title="Dismiss"
                    >
                      <X className="h-4.5 w-4.5" />
                    </button>
                  </div>
                </div>

                {/* Content Header & Body */}
                <h2 className="text-xl font-bold mb-2 group-hover:text-[var(--accent-blue)] transition duration-300">
                  {item.title}
                </h2>
                
                {item.hook && <p className="text-sm italic text-[var(--text-secondary)] mb-3">“{item.hook}”</p>}
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-6">
                  {item.description}
                </p>

                {/* AI Reasoning Block */}
                <div className="mt-4 p-4 bg-[var(--bg-glass)] rounded-xl border border-[var(--border-subtle)]">
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="h-4 w-4 text-[var(--accent-blue)]" />
                    <span className="text-xs font-bold uppercase tracking-wider text-[var(--accent-blue)]">AI Strategy Directive</span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] leading-normal italic">
                    {item.rationale}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
