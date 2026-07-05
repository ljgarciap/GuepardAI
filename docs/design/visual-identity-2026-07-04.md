# Design: Visual Identity (Light/Dark Theming)

**Date**: 2026-07-04
**Source assets**: `Logos/GUEPARD.AI_logo.png`, `Logos/GUEPARD.AI_logo_white.png`

## Note on file naming

The two files are named by which *background* they're meant to sit on, not
by the color of the mark itself:
- `GUEPARD.AI_logo.png` → black background, orange cheetah outline, "GUEPARD"
  in white + "AI" in orange. **This is the dark-mode logo.**
- `GUEPARD.AI_logo_white.png` → white background, same orange cheetah, "GUEPARD"
  in dark charcoal + "AI" in orange. **This is the light-mode logo**, despite
  the filename suggesting otherwise. Frontend Dev should rename the asset
  references accordingly (`logo-dark-bg.png` / `logo-light-bg.png`) to avoid
  confusion — a literal read of "_white" as "the white-colored logo" would
  pick the wrong file for light mode.

## Extracted identity

- **Constant across modes — the true brand accent**: a warm orange
  (approx. `#E08A34`), used for the cheetah mark and the "AI" wordmark in
  both variants. This never changes between themes — it's the one thing
  that must survive any re-skin.
- **Flips per mode**:
  | | Light mode | Dark mode |
  |---|---|---|
  | Background | White (`#FFFFFF`) | Black (`#0A0A0A`, not pure `#000` for softer contrast) |
  | Primary wordmark ("GUEPARD") | Dark charcoal (`#262626`), not pure black | White (`#FFFFFF`) |
- **Tone**: geometric line-art mark, generous letter-spacing on the wordmark,
  all-caps tagline ("MAKE YOUR IDEAS COME TO LIFE") in the accent orange —
  reads as precise/technical, not playful. Supports a clean, high-contrast
  UI rather than soft pastels.

**Values above are inferred from a rasterized PNG, not a brand guideline
document — treat the exact hex as a starting point, confirm before treating
as final if a brand guideline exists elsewhere.**

## Proposed tokens

| Token | Light | Dark | Notes |
|---|---|---|---|
| `--brand-accent` | `#E08A34` | `#E08A34` | Never changes — the one constant from the logo |
| `--bg-app` | `#FFFFFF` | `#0A0A0A` | Was `#f8fafc` (generic slate) in light — now true white per logo |
| `--bg-card` / `--bg-sidebar` | `#FFFFFF` | `#171717` | Dark surfaces slightly lifted off pure black for depth |
| `--text-main` | `#262626` | `#F5F5F5` | Was `#334155` (slate) — now charcoal per logo |
| `--text-muted` | `#6B6B6B` | `#A3A3A3` | |
| `--border-light` | `#E5E5E5` | `#2E2E2E` | |
| `--primary-navy` / `--primary-blue` | *(current values, see Open questions)* | *(needs dark equivalent)* | |

## Rollout coverage audit

Current frontend has **no theming infrastructure at all** — one fixed light
palette (`src/styles.css`, "Proseguir Aesthetic" — unrelated to the actual
Guepard AI brand: navy `#0f172a` + blue `#2563eb`, no relation to the orange
identity in the logo). No dark mode exists today; this isn't a toggle to
add to an existing dual-theme system, it's greenfield.

Colors are **not consistently tokenized** — grepped for the current vars:
only 6 files (`app.component.css`, `sidebar.component.css`,
`brand-hub.component.css`, `brand-manager.component.css`,
`generator.component.css`, `template-merge.component.css`) reference the
CSS custom properties at all. `styles.css` itself hardcodes literal hex
values in several blocks (`.synthesis-console`, `.console-header`, etc. —
`#0f172a`, `#1e293b`, `#334155`, `#94a3b8`, `#cbd5e1`) instead of using
tokens. **A theme toggle applied only at the root will not fully re-skin
the app** — every hardcoded hex outside the token system will stay frozen
in its current color regardless of mode. Full coverage requires migrating
each component's CSS to reference tokens, not just adding the toggle
mechanism.

## Open questions for Luis

1. Keep `--primary-blue` (`#2563eb`) as a secondary accent alongside the new
   orange, or should orange fully replace blue as the interactive/CTA color?
   The logo has no blue at all — blue is a holdover from the borrowed
   "Proseguir" reference aesthetic, not the actual brand.
2. Scope of this pass: build the theming **infrastructure** (tokens +
   ThemeService + toggle + logo swap, applied to the app shell/sidebar) now,
   with per-component color migration tracked as explicit follow-up tasks —
   or attempt a full re-skin of every view in one pass?
