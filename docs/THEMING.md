# Light / dark theme

## How it works

1. **One source of truth: CSS variables.** `globals.css` defines the dark palette on `:root` and a light
   palette on `:root[data-theme="light"]`. Components only ever reference `var(--…)`; no page knows
   which theme is active.
2. **The theme is an attribute on `<html>`**: `data-theme="dark" | "light"`, plus `color-scheme` so native
   controls (selects, date pickers, scrollbars) follow.
3. **No flash of the wrong theme.** A tiny inline script in `layout.tsx` runs *before* React hydrates,
   reads `localStorage["dd.theme"]` (falls back to `prefers-color-scheme`) and sets the attribute.
4. **`useTheme()` hook** (`hooks/useTheme.ts`) reads/sets the attribute, persists to `localStorage`,
   syncs across tabs (`storage` event) and follows the OS while the user has not chosen explicitly.
5. **`ThemeToggle`** component: in the `AppShell` header (every app page) and on the landing page and
   Explore page (which render outside the shell).
6. **Charts** (Recharts renders SVG attributes, where `var()` is not reliable): `useChartTheme()` reads
   the computed CSS variables and re-reads them when the theme changes, so grid/axis/tooltip colours
   switch with the theme.
7. **Theme-specific tokens** that had been hard-coded were promoted to variables: header/backdrop
   backgrounds, skeleton shimmer, chart grid/axis/tooltip colours, social-button surfaces, overlay
   scrim, glow/shadow strength, heat-map tints.

## Steps that were taken (all screens)

| Step | Where |
|---|---|
| Light palette + `color-scheme` + promoted tokens | `globals.css` |
| Pre-hydration theme script, `suppressHydrationWarning` | `app/layout.tsx` |
| `useTheme` hook, `ThemeToggle` component | `hooks/useTheme.ts`, `components/ThemeToggle.tsx` |
| `useChartTheme` hook for Recharts colours | `hooks/useChartTheme.ts` |
| Toggle in shell header | `components/AppShell.tsx` |
| Landing page: toggle + variable-based surfaces | `app/page.tsx`, `globals.css` (`.social-btn-*`) |
| Explore: Tailwind colour literals → variable-based classes; toggle | `app/explore/page.tsx` |
| Insights & Usage charts → `useChartTheme()` | `app/insights/page.tsx`, `app/usage/page.tsx` |
| Dashboard / Analytics / Ideas / Kanban / Usage / modals: remaining hard-coded dark surfaces → variables | respective pages, `components/ui.tsx`, `NextProjectModal.tsx`, `FeedbackWidget.tsx` |
| Telemetry: `feature_used(other, theme_toggle, {theme})` | `ThemeToggle` |

## Adding a colour later

Add it to **both** palettes in `globals.css` (`:root` and `:root[data-theme="light"]`) and use `var(--name)`.
Accent tints like `rgba(59,130,246,0.1)` are fine on both themes; solid dark/light surfaces are not —
those must be variables.
