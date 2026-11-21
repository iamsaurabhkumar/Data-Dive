import type { Metadata } from "next";
import "./globals.css";
import { THEME_INIT_SCRIPT } from "@/hooks/useTheme";

export const metadata: Metadata = {
  title: "Data-Dive — Creator Analytics Dashboard",
  description:
    "A data-first analytics engine for content creators. Aggregate YouTube & Instagram metrics in one unified dashboard.",
  keywords: ["analytics", "content creator", "youtube", "instagram", "dashboard"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* Apply the saved / system theme before paint — avoids a flash of the wrong theme */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
