"use client";

import { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3, LayoutDashboard, TrendingUp, Lightbulb, KanbanSquare, Sparkles, LogOut, Video, Camera, Activity, MessageSquareHeart,
} from "lucide-react";
import { FeedbackProvider, useFeedback } from "@/components/FeedbackWidget";
import ThemeToggle from "@/components/ThemeToggle";
import type { FeatureId } from "@/lib/telemetry";

const NAV: { href: string; label: string; icon: typeof LayoutDashboard; feature: FeatureId }[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, feature: "dashboard" },
  { href: "/analytics", label: "Analytics", icon: TrendingUp, feature: "analytics" },
  { href: "/ideas", label: "Ideas", icon: Sparkles, feature: "ideas" },
  { href: "/kanban", label: "Kanban", icon: KanbanSquare, feature: "board" },
  { href: "/explore", label: "Explore", icon: Lightbulb, feature: "trend_feed" },
  { href: "/usage", label: "Usage & Feedback", icon: Activity, feature: "usage" },
];

function FeedbackButton({ feature }: { feature: FeatureId }) {
  const { open } = useFeedback();
  return (
    <button className="btn btn-secondary btn-sm" style={{ width: "100%", justifyContent: "center", marginBottom: 8 }} onClick={() => open(feature)}>
      <MessageSquareHeart size={14} /> Give feedback
    </button>
  );
}

interface Props {
  title: string;
  subtitle?: string;
  email: string;
  isDemo: boolean;
  onSignOut: () => void;
  actions?: ReactNode;
  children: ReactNode;
  /** Session token for telemetry/feedback (optional: pages without a session still render). */
  token?: string;
}

export default function AppShell({ title, subtitle, email, isDemo, onSignOut, actions, children, token = "" }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const feature: FeatureId = NAV.find((n) => pathname === n.href || pathname.startsWith(n.href + "/"))?.feature ?? "other";

  return (
    <FeedbackProvider token={token} currentFeature={feature}>
    <div className="dashboard-layout">
      <aside className="sidebar">
        <div style={{ padding: "24px", borderBottom: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: 36, height: 36, borderRadius: "var(--radius-sm)", background: "var(--gradient-brand)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <BarChart3 size={20} color="white" />
            </div>
            <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.3px" }}>
              Data<span className="text-gradient">Dive</span>
            </span>
          </div>
        </div>

        <nav style={{ padding: "16px 12px", flex: 1 }}>
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <button
                key={href}
                onClick={() => router.push(href)}
                className={`nav-item ${active ? "nav-item-active" : ""}`}
              >
                <Icon size={18} />
                {label}
              </button>
            );
          })}

          <div style={{ margin: "24px 12px 8px", fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Connected Platforms
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div className="platform-row"><span><Video size={16} style={{ color: "var(--youtube-red)" }} /> YouTube</span><span className="badge badge-connected">{isDemo ? "Demo" : "Live"}</span></div>
            <div className="platform-row"><span><Camera size={16} style={{ color: "var(--instagram-pink)" }} /> Instagram</span><span className="badge badge-connected">{isDemo ? "Demo" : "Live"}</span></div>
          </div>
        </nav>

        <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border-subtle)" }}>
          {token && <FeedbackButton feature={feature} />}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <div style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--bg-tertiary)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: "var(--accent-violet)" }}>
              {email.charAt(0).toUpperCase()}
            </div>
            <div style={{ overflow: "hidden" }}>
              <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{email}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{isDemo ? "Demo mode" : "Creator plan"}</div>
            </div>
          </div>
          <button className="btn btn-secondary btn-sm" style={{ width: "100%", justifyContent: "center" }} onClick={onSignOut}>
            <LogOut size={14} /> {isDemo ? "Exit demo" : "Sign out"}
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="header">
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.3px" }}>{title}</h1>
            {subtitle && <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{subtitle}</p>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>{actions}<ThemeToggle compact /></div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
    </FeedbackProvider>
  );
}
