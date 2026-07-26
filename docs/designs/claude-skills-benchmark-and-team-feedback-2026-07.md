# Assessment: Marie/Marta's "Claude Skills" benchmark vs. GuepardAI's pipeline

**Date**: 2026-07-25
**Authors**: Analyst + Architect + AI Architect + UX/UI Designer (joint, requested by Luis)
**Trigger**: WhatsApp thread with Marie/Marta (2026-07-08 → 2026-07-14) testing Guepard with 3 real
decks (L Founders of Loyalty, Harry Potter, Tesco financial report), in parallel with a hand-built
Claude Skills workflow, plus Andres' meeting recap listing Priorities #1–#6 and the next meeting
**Monday 2026-07-27 @ 11am EST**.
**Inputs reviewed**: `Insumos/brand-guideline.skill` (unzipped), `Insumos/tree.jpeg`
("Two-Layer Storytelling Architecture"), `Insumos/ToS v1.1.pdf`.
**Status**: Working analysis — for Luis's review before Monday's meeting. Not yet a spec.

---

## 1. What Marie/Marta actually tested — and against what

Re-reading the thread carefully: the 3 decks (L Founders, Harry Potter, Tesco) are **exact decks
to reuse**, and the complaint is "it didn't take the design, the logo, or it got blocked by the word
'confidential'." That is **Template Merge**, not Synthesis Studio — this is exact-template reuse
territory (see `docs/designs/synthesis-studio-v2-assessment.md` §1 table: Template Merge = frozen
structure, exact fidelity; Synthesis = free composition). Their in-parallel Claude Skills experiment
is a manual, from-scratch simulation of the same job.

Confirmed against the actual code — this is not speculation:

### 1a. "The word 'confidential' would not allow it" — CONFIRMED, root cause identified

`backend/services/templates/template_analyzer.py:315-323` (`_infer_action`):
```python
# 2. Legal / confidential keywords
hint_lower = hint.lower()
for kw in config.preserve_keywords.split(","):
    kw = kw.strip().lower()
    if kw and kw in hint_lower:
        return "preserve"
```
Config (`backend/utils/seed.py:884-887`, key `tm_preserve_keywords`):
```
confidential,proprietary,©,for reference only,preparado exclusivamente
```
Any shape whose **existing text** contains one of these substrings is marked `preserve` and
**never reaches the LLM** (`template_content.py:104`: `active_slots = [s for s in profile.slots
if s.action != "preserve"]`). This is intentional — it exists so legal disclaimers don't get
silently rewritten — but it operates **per-shape by substring match**, with no distinction between
"this shape is a one-line legal footer" and "this shape is the slide's body text that happens to
mention the word confidential in a client's Harry Potter-brand deck." If the deck uses a
recurring "CONFIDENTIAL — for internal use" watermark/footer on every slide (plausible for a
corporate financial report like Tesco's), every slide's footer freezes — which reads to a user as
"it didn't take the design," even though visually the colors/fonts DNA extraction is a separate,
working path. This is the same open item already logged in memory
(`project-template-merge-engine.md`: "contenido sin reemplazo sensato deja texto viejo intacto") —
Marie's report is real-world confirmation of that exact gap, not a new bug.

**Fix direction (Backend Dev, small)**: scope rule #2 to short hints only (merge with rule #4's
`preserve_max_hint_chars` ceiling), or require the keyword to be the *dominant* content of the
shape rather than a substring anywhere in it. Either way this is a config/logic tune, not an
architecture change — cheap, and should ship before Monday if feasible.

### 1b. "Didn't take the proper L Founders of Loyalty logo" — plausible, weaker root cause

`template_analyzer.py` has **no logo-specific role** at all (confirmed: no `"logo"` string
anywhere in that file). Logo shapes fall through the same `role in {title, body, footnote}` +
hint-length heuristic as any other image/shape slot — there's no equivalent of Synthesis's
`BrandAsset.category == "logos"` exclusion/targeting (`asset_library_service.py:292`,
`find_best_assets`). Template Merge's traversal (`template_traversal.py`) was built for slot
*text* profiling; image slots don't get the same semantic classification Synthesis has via the
Vision LLM ingestion step. **This is a real gap**, not a misconfiguration — worth a QA pass
(reproduce with the actual L Founders deck) before deciding whether it's a quick fix (reuse the
existing `BrandAsset.category` tagging inside Template Merge's image-slot resolution) or needs
its own slice of work.

### 1c. "Didn't take any of the design of Tesco / Harry Potter" — needs reproduction, not yet explained

Colors/fonts DNA extraction (`BrandVisualDna`) is a separate pipeline stage from slot-action
classification, and nothing found so far explains a full design miss. Most likely explanation:
1a+1b combined read as "nothing changed" to a non-technical reviewer, without necessarily meaning
palette/font extraction itself failed. **Needs QA to actually reproduce with Marie's 3 files**
before diagnosing further — don't guess past this point.

---

## 2. The "Claude Skills" approach, on its own merits (AI Architect read)

`brand-guideline.skill` unzips to a 4-line `SKILL.md`:
```yaml
---
name: brand-guideline
description: "Ensure every presentation follows our brand identity L-Founders of Loyalty"
---
You are brand guardian and your job is to ensure every presentation follows our brand identity
with the right logo, colors, typography, lay out consistency, tone of voice, image style, icon
style. Never invent branding elements, when uncertain, follow the design system provided in the
knowledge base
```
That's it — a system-prompt fragment plus an attached "knowledge base" (files uploaded alongside
in Claude.ai). Marie's own numbers make the shape of this approach clear: **~1 hour to get step 1
(brand guideline) working, 5 more steps estimated, ~5 more hours total** — and even step 1's
output has "no creativity and no text alignment" per her 07-09 message. This is not a different
*architecture*, it's the same problem (brand-conditioned generation) solved by **hand-authoring
the system prompt per client, manually, in a chat UI**, with no persistence, no vector search over
a brand's asset library, no layout grammar, no QA/retry loop, and no audit trail. Every new client
brand = redo the ~6-hour training from scratch. That is precisely the manual-labor cost GuepardAI's
pipeline exists to remove (ingestion → `BrandVisualDna`/`BrandArtisticEssence`/`CorporateKnowledge`
persisted once per brand, reused across unlimited generations).

**The fair comparison is not "Claude Skills vs. GuepardAI"** — it's "one bespoke prompt someone
hand-tuned for an hour on one brand" vs. "our automated ingestion, which for these same 2-3 brands
is currently shipping visible defects (1a, 1b)." Their experiment is not a competing product; it's
unintentionally a **manual proof that the underlying LLM can approximate brand adherence given
enough hand-holding** — useful signal, not a threat to the architecture.

### On Marie's retention/lock-in comment
"I hope Claude won't be able to do that so our users stay dependent on our platform" — this is a
legitimate business worry but the wrong place to look for the moat. A generic chat skill will
always be able to *draft* branded text; it cannot replicate, without becoming a full product:
persistent multi-tenant brand libraries with vector search, an audit trail per decision
(`ArtDirectorDecision`), a bounded QA/retry loop, exact-geometry PPTX/PDF rendering, or portfolio
management. **Recommendation**: reframe this for the team as "our moat is automation + governance
+ output fidelity, not withholding a capability Claude already has for free in chat" — don't
compete on secrecy, compete on shipping 1a/1b fixed and the QA loop Marie doesn't have.

---

## 3. Reconciling the two workstreams (the actual ask for Monday)

Marie and Marta are already doing, by hand, the exact methodology the Synthesis Studio v2
assessment (`docs/designs/synthesis-studio-v2-assessment.md`, §5, "Lever 3 — the blocking step")
calls for: **generate against real decks, mark concrete defects, classify them.** Priority #2
("Recipes" — chronological steps, model, skill, prompts, satisfaction %) is, functionally, exactly
the elicitation input the `synthesis-studio-analyst` agent was built to collect. Don't run two
parallel tracks that don't talk to each other.

**Recommendation to bring Monday**: fold Marie/Marta's "Recipes" directly into the
`synthesis-studio-analyst` session as real input, instead of treating their Claude Skills
experiment as a side benchmark to react to informally over WhatsApp. Concretely:
- Their 3 test decks (L Founders, Harry Potter, Tesco) become the real-brand test set for the
  elicitation session (assessment §5 asked for "2 real brands" — this already exceeds that).
- Their "satisfaction %" per step becomes the acceptance-criteria baseline in the resulting spec.
- 1a and 1b get filed as concrete Template Merge defects (not folded into the Synthesis spec —
  different pipeline, per the assessment's own scope line).

---

## 4. The "Two-Layer Storytelling Architecture" (`tree.jpeg`)

Whiteboard concept, presumably from Marie/Marta's 07-08 "review with another technique" session:
splits input documents into a **Constraint Layer** (NDA, licensing terms, term sheet, exclusivity
windows, what's confidential, IP usage limits — "must be true, checked by a Guardrail Engine") and
a **Content Layer** (brand briefs, audience data, past campaigns, tone/visual ID — "creative, can
be drafted by a Storytelling Draft Engine"), reconciled into output where facts are cited/traceable
and creative language is marked DRAFT pending brand approval.

This targets a **different use case than anything currently in scope**: co-branded /
partnership decks between two brands under a legal agreement (deal terms, exclusivity, NDA) — not
single-brand ingestion or exact-template reuse. It is a legitimate pattern (fact-grounding +
draft-marking is a real, cheap-to-borrow idea — Lever 2 in the Synthesis assessment already adds a
provenance/confidence signal for QA findings; this is the same instinct applied to legal
provenance instead of visual provenance). **Recommendation**: log it, do not design against it yet
— it's Priority #6 territory per Andres' own recap ("once #1-4 more advanced"). Worth 10 minutes
Monday to confirm it's Marie/Marta's proposal and whether a real client deal is driving it, or if
it's speculative.

---

## 5. Data Protection & Confidentiality — Priority #5 (PM + Architect read)

`ToS v1.1.pdf` is a real, lawyer-facing draft with Luis's own decisions already annotated inline
(">>"). Engineering-relevant takeaways, cross-checked against current architecture:

| ToS clause | Current state | Gap |
|---|---|---|
| §9 "Client Content not used to train general AI models absent opt-in" (Luis: keep default-off, opt-in checkbox) | All LLM calls route through `providers/llm_provider.py`; no fine-tuning/training pipeline exists anywhere in the codebase today | No gap technically — but **no opt-in consent UI/flag exists yet**. If this ships, `User`/`Tenant` needs a consent flag before any future training use, per Luis's own annotation. |
| §11 Subprocessors table (AWS + Anthropic listed) | Matches reality — `llm_provider.py` routes `specialization="design"` to Anthropic; storage is AWS-hosted per `storage_service.py` | Needs the actual AWS region confirmed and stated (currently `[AWS region — confirm]` placeholder) |
| §10 Data Retention (90-day grace period post-termination, export in `.pptx`/`.json`) | Portfolio export exists (`GET /api/library/portfolios`); no automatic deletion/anonymization job on subscription end | **Gap**: no scheduled deletion job tied to subscription/tenant termination. This is real backend work, not just a legal doc. |
| §23 "three ToS by jurisdiction, default EU" (Luis's own proposal) | N/A — no ToS/consent versioning exists in `User`/`Tenant` today | **Gap**: needs a `terms_version` / `accepted_at` field if/when this ships, plus a backoffice surface (per Andres' recap: "Luis will code a back office area... for priority #5") |

**PM recommendation**: Priority #5 is two separate deliverables, not one — (a) finish the legal
document (Luis + counsel, not engineering's call), and (b) the backoffice surface + minimal schema
(consent flag, terms version/acceptance timestamp, retention job) that the ToS depends on to be
true rather than aspirational. (b) can start now without waiting on legal sign-off of the wording.

---

## 5a. Implemented 2026-07-25 (ahead of the Monday meeting)

Both items Luis greenlit same-day, shipped and tested:

- **§1a fix** — `template_analyzer.py` `_infer_action` now only force-preserves a
  shape on a legal keyword match when the shape's hint is also
  `<= tm_preserve_max_hint_chars` (50 chars by default). A long body/title
  that merely mentions "confidential" once now falls through to normal
  adapt/rewrite classification instead of freezing its entire text. Covered
  by `tests/test_template_merge.py` (updated + 1 new case).
- **ToS consent schema + enforcement** (§5, ahead of legal sign-off, per
  Luis: "no importa que haya que actualizar después"):
  - `User` gained `tos_accepted` (nullable int, NULL/0 = not accepted —
    default stays negative even for rows added by the additive-column
    reconciler), `tos_accepted_version`, `tos_accepted_at`, `tos_rejected_at`.
  - `system_configs.tos_current_version` (seeded "1.1") is the single source
    of truth for "current" — bumping it re-blocks every user whose
    `tos_accepted_version` doesn't match, until they re-accept.
  - `GET/POST /api/tos/status|accept|reject` (`routers/tos.py`, logic in
    `services/core/auth_service.py`, matching the project's routers-are-glue
    convention).
  - The gate itself lives in `auth/dependencies.py::get_current_user` — the
    one dependency virtually every route already goes through — and 403s
    with `TOS_NOT_ACCEPTED` unless the path starts with `/api/auth` or
    `/api/tos` (so a blocked user can still log out or re-accept), or the
    user is `superadmin` (platform operator account, not a `Client`).
  - Frontend: `TosService` + `tosGuard` (paired with `authGuard` on every
    protected route) redirect to `/tos` — a shell-less page (no sidebar) —
    whenever the backend says not accepted. `TosComponent` shows Accept only
    when unaccepted; reachable afterwards via a sidebar link to view/Reject.
    Rejecting immediately re-triggers the same lockout on the next
    navigation.
  - Full suites green: backend 650 passed / 1 pre-existing unrelated flake
    (`test_status_null_brand_id_still_rejects_non_owner`, confirmed failing
    on master before this work too — an `id(object())` email-collision
    flake, not a ToS regression); frontend 199/199 (Karma).
  - **Flag for Luis**: the ToS PDF's own header says "INTERNAL WORKING DRAFT
    — NOT FOR EXTERNAL DISTRIBUTION UNTIL REVIEWED BY QUALIFIED COUNSEL."
    The in-app text was rewritten in plain language (no bracketed
    `[DECISION NEEDED]` notes or inline "›" comments — those are internal
    working artifacts) and explicitly marked as a draft with an "open items"
    section, but it is still pulled from that same unreviewed document.
    Worth a conscious yes/no from Luis before real (non-pilot) clients see
    it, independent of the mechanism being ready.

## 6. Recommendations to bring to the 2026-07-27 meeting

1. **Ship the preserve-keyword scoping fix (§1a)** before Monday if feasible — cheapest, highest-visibility fix; directly answers Marie's top complaint.
2. **QA reproduction pass** on the exact 3 decks Marie used (L Founders, Harry Potter, Tesco) for 1b and 1c — don't diagnose further from this doc alone.
3. **Reframe Priority #2** ("Recipes") as direct input to the already-planned `synthesis-studio-analyst` elicitation session, not a separate benchmarking exercise — one track, not two.
4. **Park the Two-Layer Storytelling concept** as a Priority #6 candidate; ask Marie/Marta Monday whether it's driven by an actual client deal.
5. **Split Priority #5** into legal-document work (Luis) and backoffice/schema work (Backend Dev can start now: consent flag, terms acceptance tracking, retention job).
6. **Don't react to the lock-in worry with secrecy** — the differentiation talking point for the team is automation + governance + fidelity, which Claude Skills structurally cannot replicate per-seat in a chat UI.

## References
- `docs/designs/synthesis-studio-v2-assessment.md` (Lever 3 methodology, reused here)
- `backend/services/templates/template_analyzer.py:295-336` (`_infer_action`)
- `backend/services/templates/template_content.py:103-108` (preserve slots skip LLM)
- `backend/utils/seed.py:882-887` (`tm_preserve_keywords`), `:1034-1040` (L Founders/Tesco footer seed)
- `backend/services/assets/asset_library_service.py:288-296` (`find_best_assets` logo exclusion — Synthesis-side pattern absent in Template Merge)
- `Insumos/brand-guideline.skill`, `Insumos/tree.jpeg`, `Insumos/ToS v1.1.pdf`
