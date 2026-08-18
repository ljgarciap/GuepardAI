# Flow design: Generation — information architecture

**Date**: 2026-08-18
**Role**: UX Flow Designer (new agent, `.claude/agents/ux-flow-designer.md`, created this session)
**Constraint given by Luis (2026-08-18)**: the existing process must not change — same
fields, same order, same required-ness, prompt field stays the only thing that
triggers generation. This proposal touches sequencing and emphasis only.

---

## 1. What already reaches the generator today (full inventory)

Read every input surface on the screen before proposing anything — there's more
here than the 6-dropdown toolbar already discussed:

| Surface | Where | Captures | Required? |
|---|---|---|---|
| Toolbar | Top of screen | Identity, Blueprint, Knowledge, Region, Delivery format, Engine tier | Yes, all 6 |
| **Reuse Previous Prompt** | "Ayuda" card 1 | Picks a past presentation, loads its prompt as a starting point | No — shortcut |
| **Intent Library** | "Ayuda" card 2 | Picks a pre-made intent; tone/structure pre-set | No — shortcut |
| **Guide / Write My Own** | "Ayuda" card 3 | Guided composer: Objective, Tone, Audience, Slide type, Story, Visual rules, Output format, "no buzzwords" flag → assembles structured text into the prompt + saves as `prompt_metadata` | No — shortcut |
| **Load from Favorites** | "Ayuda" card 4 | Loads a saved favorite prompt | No — shortcut |
| Prompt textarea | Command area | Free text — the actual instruction sent to the pipeline | **Yes — the only true trigger** |
| "Use AI generated images" | Command area | `allow_ai_images` flag | No |

**Finding: the "complete information" capability already exists and is thorough.**
The guided composer alone already captures objective, tone, audience, slide type,
story, visual rules, output format, and a buzzword constraint — that's a genuinely
complete brief. This isn't a data-capture gap. It's a **sequencing** problem.

## 2. Friction diagnosis

A first-time user lands on the screen and has to resolve, unguided, in this order:
1. Fill in 6 technical dropdowns with no idea which matter most.
2. Choose between **4 equal-weight buttons** — Reuse / Intent Library / Guide /
   Favorites — each proposing a different way to arrive at the same textarea,
   with no signal for which one is "the" way to start.
3. Only then reach the actual text box.

That middle step is the real friction: **4 parallel doors with no default**, not
missing capability. Someone who's never used the tool has no reason to know that
"Guide / Write My Own" is the one that actually guarantees a complete brief — it
reads as one option among four equally plausible ones.

## 3. Proposed flow

No new capability, no removed capability — a change in **emphasis**:

- One path becomes the visible default: **Guide / Write My Own**, shown open
  inline (not behind a button click) for a first-time or empty-prompt session —
  it's the only one of the four that reliably produces complete information,
  which is the stated goal.
- The other three (Reuse, Intent Library, Favorites) become secondary, smaller
  links — "or start from: a past prompt · an intent template · a favorite" —
  visible, one click away, but visually subordinate instead of co-equal buttons.
- Toolbar keeps its 6 fields, same order, plus the helper-text pass already
  agreed for Track A — unaffected by this proposal.
- Nothing here calls a new endpoint or stores new data — it's a front-end
  weighting change over four capabilities that already work.

## 4. Completeness audit

| Current entry point | Still exists? | Where |
|---|---|---|
| Reuse Previous Prompt | Yes | Secondary link, same modal behind it |
| Intent Library | Yes | Secondary link, same modal behind it |
| Guide / Write My Own | Yes | **Promoted to default, shown inline** |
| Load from Favorites | Yes | Secondary link, same modal behind it |
| Prompt textarea | Yes, unchanged | Still the sole trigger |
| Toolbar (6 fields) | Yes, unchanged | Per Track A — helper text only |
| `allow_ai_images` toggle | Yes, unchanged | — |

Nothing is removed. Nothing is reordered against a constraint Luis set. Everything
that exists today is still reachable in exactly as many clicks, except the one
path that produces complete structured input, which now requires zero clicks
instead of one.

## 5. Open question for Luis

Confirm the default: is **"Guide / Write My Own"** the right one to promote, or
is there a different one of the four you'd want first-time users to land on? My
read is Guide is correct because it's the only one of the four that produces
complete structured information by construction — Reuse/Favorites depend on
something existing already, Intent Library depends on a pre-built library being
populated.

## 6. Handoff

- **UX/UI Designer** — visual hierarchy for "one open panel + 3 subordinate
  links" (this doc defines the *what*, not spacing/color/type).
- **Frontend Dev** — re-weighting is a `showCards`/default-state change in
  `prompt-support.component`, not a new component.
- **Architect** — not needed; no new data, no new endpoint.
