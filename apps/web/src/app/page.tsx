"use client";

import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  BarChart3,
  Zap,
  TrendingUp,
  Play,
  ArrowRight,
} from "lucide-react";

export default function LandingPage() {
  const router = useRouter();
  const supabase = createClient();

  const handleGoogleLogin = async () => {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
        scopes: "https://www.googleapis.com/auth/youtube.readonly",
      },
    });
  };

  const handleDemoMode = () => {
    // Navigate directly to dashboard in demo/mock mode
    router.push("/dashboard");
  };

  return (
    <div className="landing-container">
      {/* Background glows */}
      <div className="landing-glow landing-glow-blue animate-pulse-glow" />
      <div className="landing-glow landing-glow-violet animate-pulse-glow" style={{ animationDelay: "2s" }} />

      {/* Floating metric preview cards */}
      <div
        className="animate-fade-in-up animate-delay-1"
        style={{
          position: "absolute",
          top: "15%",
          left: "8%",
          opacity: 0,
        }}
      >
        <div className="card" style={{ padding: "16px 20px", transform: "rotate(-6deg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <TrendingUp size={16} style={{ color: "var(--accent-emerald)" }} />
            <span className="font-mono" style={{ color: "var(--accent-emerald)", fontSize: "14px", fontWeight: 600 }}>+247%</span>
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>Reel performance</div>
        </div>
      </div>

      <div
        className="animate-fade-in-up animate-delay-2"
        style={{
          position: "absolute",
          top: "20%",
          right: "10%",
          opacity: 0,
        }}
      >
        <div className="card" style={{ padding: "16px 20px", transform: "rotate(4deg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Play size={16} style={{ color: "var(--accent-blue)" }} />
            <span className="font-mono" style={{ fontSize: "14px", fontWeight: 600 }}>2.4M</span>
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>Total views</div>
        </div>
      </div>

      <div
        className="animate-fade-in-up animate-delay-3"
        style={{
          position: "absolute",
          bottom: "18%",
          right: "15%",
          opacity: 0,
        }}
      >
        <div className="card" style={{ padding: "16px 20px", transform: "rotate(3deg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Zap size={16} style={{ color: "var(--accent-amber)" }} />
            <span className="font-mono" style={{ fontSize: "14px", fontWeight: 600 }}>4.8%</span>
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>Engagement rate</div>
        </div>
      </div>

      {/* Main card */}
      <div className="landing-card animate-fade-in-up">
        {/* Logo */}
        <div style={{ marginBottom: "32px" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "24px",
            }}
          >
            <div
              style={{
                width: "44px",
                height: "44px",
                borderRadius: "var(--radius-md)",
                background: "var(--gradient-brand)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <BarChart3 size={24} color="white" />
            </div>
            <span
              style={{
                fontSize: "24px",
                fontWeight: 800,
                letterSpacing: "-0.5px",
              }}
            >
              Data<span className="text-gradient">Dive</span>
            </span>
          </div>

          <h1
            style={{
              fontSize: "28px",
              fontWeight: 700,
              lineHeight: 1.3,
              marginBottom: "12px",
              letterSpacing: "-0.5px",
            }}
          >
            Your content,{" "}
            <span className="text-gradient">one dashboard</span>
          </h1>
          <p
            style={{
              fontSize: "15px",
              color: "var(--text-secondary)",
              lineHeight: 1.6,
            }}
          >
            Aggregate YouTube & Instagram analytics. See what works, skip what doesn&apos;t.
          </p>
        </div>

        {/* Auth buttons */}
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <button onClick={handleGoogleLogin} className="social-btn social-btn-google">
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            Continue with Google
          </button>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "16px",
              margin: "4px 0",
            }}
          >
            <div style={{ flex: 1, height: "1px", background: "var(--border-medium)" }} />
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>or</span>
            <div style={{ flex: 1, height: "1px", background: "var(--border-medium)" }} />
          </div>

          <button onClick={handleDemoMode} className="social-btn social-btn-demo">
            <Zap size={18} />
            Try Demo Dashboard
            <ArrowRight size={16} />
          </button>
        </div>

        {/* Footer text */}
        <p
          style={{
            fontSize: "12px",
            color: "var(--text-muted)",
            marginTop: "24px",
            lineHeight: 1.5,
          }}
        >
          Connect YouTube & Instagram to see your real analytics.
          <br />
          Demo mode uses realistic mock data.
        </p>
      </div>
    </div>
  );
}
