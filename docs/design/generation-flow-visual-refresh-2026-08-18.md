# Design: Generation flow — visual refresh & guided UX

**Date**: 2026-08-18
**Source assets**: `Insumos/mock.html` ("Win Deck — Deck Studio" reference mock, provided by Luis)
**Compared against**: `frontend/src/app/pages/generator/` (current "Synthesis Studio"), `frontend/src/styles.css` (token system), `docs/design/visual-identity-2026-07-04.md` (canonical brand tokens)
**Requested by Luis**: (1) review the mock's visual suggestions, (2) explore making the generation process more intuitive / add visual aids.

---

## 1. What today's screen actually is

`generator.component.html` is a single dense toolbar — 6 dropdowns exposed at once
(IDENTITY, BLUEPRINT, KNOWLEDGE, TARGET REGION, DELIVERY FORMAT, ENGINE TIER), all
required before the input even accepts a prompt, labeled in ops/systems language
("SYNTHESIS STUDIO — OPERATIONAL CONTROL", "ENGINE TIER", "STANDBY/BUSY"). Nothing
guides a first-time user toward what to pick or why. This matches what you flagged
as needing help — it's built for someone who already knows what a "Blueprint" or
"Engine Tier" is, which is exactly what a pilot tester won't know on day one.

## 2. The mock's real contribution isn't color — it's sequencing

The mock's headline improvement is **progressive disclosure via an objective picker**:
pick "Sales Deck" / "Executive" / "Workshop" first (visual cards, not a dropdown) →
that single choice auto-sets blueprint, knowledge base and tone → the 5 technical
dropdowns collapse into an "Advanced settings" toggle most users never need to open.
A step rail (Objective → Brief → Generate) makes progress visible. Prompt history
and a filterable deck library (with win/lost/moved-up outcome tags) let the user
reuse or reference past work instead of writing every prompt from scratch.

**This is the answer to your second ask.** It's directly the shape of "more intuitive
with visual aids": fewer decisions up front, decisions made visual (icon cards vs.
text dropdowns), and prior work surfaced as reusable context instead of buried.

## 3. Visual tokens — what to take, what to flag

| Mock value | Our canonical token (`visual-identity-2026-07-04.md`) | Verdict |
|---|---|---|
| Accent `#E8963C` | `--brand-accent: #E08A34` | **Close but not identical** — use our existing token, don't adopt the mock's value. It reads as the same orange but isn't the extracted one; two near-identical oranges in the codebase is a bug waiting to happen. |
| Dark bg `#0A0A0B` / panel `#141416` / raised `#1B1B1E` | `--bg-app: #0a0a0a` / `--bg-surface: #171717` (single surface token, no raised tier) | Adoptable direction, needs a decision (see §5) — the mock's 3-tier surface system (void/panel/raised) gives more depth than our current flat 2-tier one. |
| Fonts: Sora (headings) + Inter (body) + IBM Plex Mono (labels/data) | Single family, Plus Jakarta Sans, for everything | **Not adoptable as-is.** This is a typography system change, not a mock detail — three new font families is a brand decision, not a UX/UI-agent call. Flagged for Luis, not silently taken. |
| Win/Lost/Moved-up state colors (green/red/blue) | No equivalent tokens exist today | New semantic tokens, needed regardless of font decision — see §5. |

## 4. Rollout coverage audit (don't skip this — it changes scope)

Checked `generator.component.css` (772 lines) before proposing anything: only 63
`var(--...)` references against **~20 distinct hardcoded hex colors** that aren't
brand tokens at all — `#6366f1` (indigo), `#a855f7` (purple), `#10b981` (green),
`#f59e0b`/`#d97706` (amber), plus the slate scale (`#0f172a`…`#94a3b8`) already
called out in the original identity doc as leftover "Proseguir" palette. **A
progressive-disclosure restyle on top of this page today would restyle a page
that's still ~90% off-token underneath.** Any visual work here should migrate this
page's hardcoded colors to tokens in the same pass, not after.

## 5. Proposed split of work (this is the actual deliverable)

**Constraint confirmed by Luis (2026-08-18): the existing process must not change.**
Same 6 fields (Identity, Blueprint, Knowledge, Region, Delivery Format, Engine Tier),
same order, same required-ness, same free-text prompt as the only thing that actually
triggers generation. Everything below is either (a) a visual-only pass over what
exists, or (b) a strictly additive, skippable element that never gates or reorders
the current form. Nothing here removes or blocks the prompt field — confirmed
explicitly after Luis asked directly whether it was being eliminated (it isn't).

This is bigger than a CSS pass — separating what's a contained Frontend Dev task
from what needs Architect + Analyst first, per how this team works:

**A — Contained visual/UX task (Frontend Dev, no new data model)**
- Keep all 6 controls, same order, same required-ness. Add inline helper text
  under each (what it affects) — replacing tribal knowledge with on-screen
  guidance, the cheapest "visual aid" win here.
- Migrate `generator.component.css` off hardcoded hex onto the token system (§4).
- Rename ops-speak labels to plain language ("OPERATIONAL CONTROL" → drop it;
  "ENGINE TIER" → "Rendering quality" or similar — needs a copy pass, not just CSS).
- *(Dropped from this pass)* Collapsing Region/Format/Tier behind an "Advanced"
  toggle — parked pending Luis's call on whether progressive disclosure counts as
  a structural change under the constraint above, or is acceptable as layout-only
  since no field is removed or reordered, just grouped.

**B — New feature, needs Architect design + Analyst spec (not a UX/UI-brief-only change)**
- Objective quick-picker: **optional, advisory only** — if used, it pre-fills
  suggested values for Identity/Blueprint/Knowledge and seeds the prompt's
  placeholder with a relevant example. It never disables or gates the Generate
  button, and a user who ignores it entirely gets today's exact flow. Still needs
  a spec because the objective→defaults mapping table doesn't exist as data yet —
  "optional" changes the risk profile (a wrong suggestion is just overridden by
  the user) but not the need for someone to define and own that mapping.
- Prompt history reuse and the deck library with win/lost/moved-up tagging are a
  **new outcome-tracking concept**, distinct from the existing star-rating
  `PresentationReview` schema (see `project-reviews-and-prompt-support` memory) —
  needs its own spec, not an assumption that it reuses ratings data. Renders as
  its own collapsible panel below the existing form, not inline with it.
- Reference-deck selection feeding into generation (the mock's "ref-tray") is a
  new generation input — needs an ADR if it touches LLM prompt construction
  (AI Architect gate, per workspace rules).

I'd sequence B behind A: A is shippable this week and immediately makes the current
screen calmer without inventing anything; B is the real "more intuitive" win but
needs a proper spec first.

## 6. Open questions for Luis

1. **Font system** — keep single-family Plus Jakarta Sans (current, already rolled
   out) or adopt the mock's 3-family system (Sora/Inter/IBM Plex Mono)? This is a
   brand decision I won't make unilaterally.
2. **Surface depth** — add the mock's 3-tier dark surface (void/panel/raised) as
   new tokens, or keep the current flat 2-tier system?
3. Should I write the Analyst spec for track B (objective-driven defaults +
   outcome-tagged deck library + reference-deck generation input) now, or do you
   want to see the Frontend restyle (track A) live first before committing to B's
   scope?
4. Confirmed: accent color used will be our existing `--brand-accent: #E08A34`
   token, not the mock's `#E8963C` — flagging so it's explicit, not assumed.

---
🔴 **Fin de sesión (rol UX/UI)** — este brief cubre identidad visual + propuesta de
flujo. Track A (restyle contenido) puede pasar directo a **Frontend Dev**. Track B
(objective-driven config + outcome tracking + reference decks) necesita pasar por
**Analista → Arquitecto** antes de implementarse — no es un cambio de UI contenido.
