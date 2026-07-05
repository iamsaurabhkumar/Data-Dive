"use client";

import { useEffect, useState } from "react";
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

interface ContentSuggestion {
  id: string;
  title: string;
  description: string;
  reasoning: string;
  confidence_score: number;
  status: string;
  created_at: string;
}

export default function ExplorePage() {
  const supabase = createClient();
  const [suggestions, setSuggestions] = useState<ContentSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch initial pending suggestions
  useEffect(() => {
    async function fetchInitialSuggestions() {
      try {
        setLoading(true);
        const { data, error: fetchErr } = await supabase
          .from("content_suggestions")
          .select("*")
          .eq("status", "pending")
          .order("created_at", { ascending: false });

        if (fetchErr) throw fetchErr;
        setSuggestions(data || []);
      } catch (err) {
        console.error("Error fetching suggestions:", err);
        setError("Failed to load content suggestions.");
      } finally {
        setLoading(false);
      }
    }

    fetchInitialSuggestions();
  }, [supabase]);

  // Realtime subscription setup
  useEffect(() => {
    const channel = supabase
      .channel("realtime-suggestions")
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "content_suggestions",
        },
        (payload) => {
          const newSuggestion = payload.new as ContentSuggestion;
          if (newSuggestion.status === "pending") {
            setSuggestions((prev) => [newSuggestion, ...prev]);
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [supabase]);

  // Optimistic action handler
  const handleAction = async (id: string, action: "converted_to_kanban" | "rejected") => {
    const previousSuggestions = [...suggestions];

    // Optimistic UI Update: remove card instantly from local state
    setSuggestions((prev) => prev.filter((item) => item.id !== id));
    setError(null);

    try {
      const { error: updateErr } = await supabase
        .from("content_suggestions")
        .update({ status: action })
        .eq("id", id);

      if (updateErr) throw updateErr;
    } catch (err) {
      console.error(`Failed to update suggestion state:`, err);
      // Revert UI state on failure
      setSuggestions(previousSuggestions);
      setError("Network error: Failed to save action. Please try again.");
    }
  };

  return (
    <main className="min-h-screen bg-[#06080f] text-[#f1f5f9] p-6 md:p-12">
      {/* Header bar */}
      <div className="max-w-5xl mx-auto mb-10 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link 
            href="/dashboard" 
            className="p-2 bg-slate-900/50 hover:bg-slate-800/80 border border-slate-800 rounded-lg transition"
          >
            <ArrowLeft className="h-5 w-5 text-[#94a3b8]" />
          </Link>
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">
              Explore Ideas
            </h1>
            <p className="text-sm text-[#94a3b8] mt-1">
              AI-generated strategy recommendations derived from real-time global platform trends.
            </p>
          </div>
        </div>
      </div>

      {/* Main viewport container */}
      <div className="max-w-5xl mx-auto">
        {/* Error notification banner */}
        {error && (
          <div className="mb-6 p-4 bg-rose-950/30 border border-rose-800/50 rounded-xl flex items-center gap-3 text-rose-200">
            <AlertTriangle className="h-5 w-5 flex-shrink-0 text-rose-400" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {/* Loading fallback */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            <p className="text-[#94a3b8] text-sm font-mono">Curating global insights...</p>
          </div>
        ) : suggestions.length === 0 ? (
          /* Empty State */
          <div className="flex flex-col items-center justify-center text-center py-20 border border-dashed border-slate-800 rounded-2xl bg-[#0c1220]/20 max-w-2xl mx-auto">
            <div className="p-4 bg-blue-500/10 rounded-full mb-4">
              <Lightbulb className="h-10 w-10 text-blue-400" />
            </div>
            <h3 className="text-lg font-semibold mb-2">No pending suggestions</h3>
            <p className="text-sm text-[#94a3b8] max-w-sm">
              Our background processors are actively scraping trends. Keep this page open; new suggestions arrive in real-time.
            </p>
          </div>
        ) : (
          /* Ideas Grid */
          <div className="grid grid-cols-1 gap-6 max-w-3xl mx-auto">
            {suggestions.map((item) => (
              <div 
                key={item.id}
                className="group relative bg-[#0c1220]/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-2xl p-6 transition-all duration-300 shadow-lg hover:shadow-xl"
              >
                {/* Confidence Metric Pin */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2 px-3 py-1 bg-slate-900 border border-slate-800 rounded-full">
                    <Target className="h-4 w-4 text-emerald-400" />
                    <span className="text-xs font-mono text-[#94a3b8]">
                      {(item.confidence_score * 100).toFixed(0)}% Match
                    </span>
                  </div>
                  
                  {/* Quick Action buttons */}
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleAction(item.id, "converted_to_kanban")}
                      className="p-2 bg-slate-900 border border-slate-800 hover:bg-emerald-950/30 hover:border-emerald-700/50 rounded-xl text-[#94a3b8] hover:text-emerald-400 transition cursor-pointer"
                      title="Send to Board"
                    >
                      <Check className="h-4.5 w-4.5" />
                    </button>
                    <button
                      onClick={() => handleAction(item.id, "rejected")}
                      className="p-2 bg-slate-900 border border-slate-800 hover:bg-rose-950/30 hover:border-rose-700/50 rounded-xl text-[#94a3b8] hover:text-rose-400 transition cursor-pointer"
                      title="Dismiss"
                    >
                      <X className="h-4.5 w-4.5" />
                    </button>
                  </div>
                </div>

                {/* Content Header & Body */}
                <h2 className="text-xl font-bold mb-2 group-hover:text-blue-400 transition duration-300">
                  {item.title}
                </h2>
                
                <p className="text-sm text-[#94a3b8] leading-relaxed mb-6">
                  {item.description}
                </p>

                {/* AI Reasoning Block */}
                <div className="mt-4 p-4 bg-slate-900/40 rounded-xl border border-slate-800/40">
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="h-4 w-4 text-blue-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-blue-400/80">AI Strategy Directive</span>
                  </div>
                  <p className="text-xs text-[#94a3b8] leading-normal italic">
                    {item.reasoning}
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
