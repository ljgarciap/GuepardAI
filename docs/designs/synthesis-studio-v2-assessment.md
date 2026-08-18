# Assessment: Synthesis Studio — is the visual-DNA + RAG approach the right one?

**Date**: 2026-07-08
**Authors**: Analyst + Architect + AI Architect (joint assessment, requested by Luis)
**Status**: ASSESSMENT — direction validated by Luis ("bastante cerca de lo que busco,
pero aún hay detalles"). Next gate: the detail-elicitation session (§5) BEFORE any spec.
**Scope**: the classic generation pipeline only (ingestion → Redactor → Architect →
QA → Render). Template Merge v2 is complete and out of scope here.
**Owner of the next step**: `synthesis-studio-analyst` agent
(`.claude/agents/synthesis-studio-analyst.md`), created from this assessment.

---

## 1. Verdict

**The approach is correct and should not be replaced.** Synthesis Studio and
Template Merge solve complementary problems:

| | Template Merge (v2) | Synthesis Studio |
|---|---|---|
| Input | An exact deck to reuse | Brand documents + knowledge |
| Structure | Frozen (same slides, same layout) | Free (any content, any length) |
| Fidelity | Exact by construction | Approximate by interpretation |
| Right when… | The client hands over THE design | No exact template exists |

Synthesis is the only path for novel presentations. Its architecture —
identity extraction → RAG content synthesis → layout-grammar composition →
QA loop with bounded retries — is the same shape as the serious systems in
this category (Gamma, Beautiful.ai). The real alternatives are strictly
worse: a fine-tuned layout-generation model (expensive, brittle, opaque) or
free-form LLM composition without a grammar (visual soup).

## 2. Where the ceiling is (why "close, but details")

The visual-DNA extraction is a **lossy abstraction**. It captures:

- palette, fonts, physical assets (`BrandVisualDna`, programmatic — exact)
- an "artistic essence" (`BrandArtisticEssence`, Vision-LLM prose — interpretive)
- premium visual patterns (`BrandPremiumVisualPattern` — a few executable recipes)

It does **not** capture the brand's actual layout system: its grid, its box
proportions, its compositional rhythm. At render time, the brand's identity
is poured into **Guepard's** grammar (`GRAMMAR_GEOMETRIES`,
`services/ingestion/brand_composition_dna.py` — ~10 generic named layouts),
not the brand's own. The output reads as "inspired by the brand" rather
than "of the brand": right colors and fonts, slightly generic composition.

Luis's residual "details" are the residue of that abstraction — a structural
property of the current design, not a bug to patch.

## 3. The team's three levers (by expected impact)

### Lever 1 — Brand Grammar Mining (Architect; the big one)

During ingestion, extract the brand deck's **real layouts as executable
geometries** — which compositions the brand actually uses, with which box
proportions and text capacities — and register them as first-class layout
options the Art Director can choose alongside the 10 generic ones.

Feasibility is unusually good because **Template Merge v2's analyzer already
does ~70% of the work**: shared shape traversal (groups, tables, depth-capped),
per-slot geometry, role inference, typographic capacity
(`template_traversal.py`, `template_analyzer.py`, `_typographic_budget`).
Mining = clustering those per-slide slot profiles into named, deduplicated
layout signatures stored per brand. The two pipelines stop being silos and
become a spectrum: exact merge ←→ free composition over a learned brand grammar.

Open design questions (for the spec, not for now): where learned geometries
live (`BrandVisualDna` vs a new table), how the Architect prompt exposes them,
collision policy with the generic grammar, and how the Painter consumes
non-canonical geometries.

### Lever 2 — Unify visual QA (AI Architect; cheap, already validated)

The Phase 4 advisory Vision QA touchpoint
(`vision-template-merge-visual-qa-adr.md`, live-validated 2026-07-08) applies
directly to synthesis output: run it on the rendered deck and attach concrete
overflow/contrast/overlap findings next to `ScoreFidelity`'s holistic score.
Marginal design cost ≈ zero (same call shape, same gating convention).

Also: audit how much the "artistic essence" prose actually influences Art
Director decisions — the `ArtDirectorDecision` audit rows already exist to
answer this with data instead of intuition. If its influence is marginal,
that is budget (prompt space + tokens) to reclaim for learned geometries.

### Lever 3 — Specify the "details" first (Analyst; the blocking step)

"Aún hay detalles" is not yet specifiable. The method that worked for
Template Merge v2 was: concrete, verifiable defects first, then architecture.
Same here — generate 3–5 decks across 2 real brands, have Luis mark what
bothers him on the renders, and classify each mark:

| If the details cluster in… | The right lever is… |
|---|---|
| Composition / layout genericness | Lever 1 (Brand Grammar Mining) |
| Typography scale/hierarchy | Cheaper: extend DNA typography rules into the Painter |
| Image choice/placement | Asset-fit tuning (`asset_fit.py`, visual profiles — exists) |
| Slide rhythm / text density | Redactor prompt + outline work (cheap) |
| Rendering defects (overflow/contrast) | Lever 2 (visual QA port) |

**Recommendation**: do NOT start Lever 1 blind. Its exact shape depends on
where the marks land. Lever 2 is safe to schedule regardless.

## 4. What this is NOT

- Not a rewrite of the generation pipeline.
- Not a merger of the two pipelines into one UI/flow (out of scope).
- Not a commitment to Brand Grammar Mining until the detail session says so.
- **Not an in-place change to today's Synthesis Studio screen** — see §5a.

## 5a. Rollout constraint (confirmed by Luis, 2026-08-18)

v2 ships as an **isolated, parallel view — not a modification of the
existing one.**

- New nav entry / route, separate from today's Synthesis Studio (v1). v1's
  frontend and backend path stay untouched, visually and logically — no
  shared component gets edited in place to "become" v2.
- The v2 view supports running a **batch of generations** with the new
  approach, so Luis can evaluate output quality across several decks before
  any decision to promote v2 or retire v1.
- Backend implication for the Architect to resolve at design time: v1 and v2
  need to run through `AgentOrchestrator` without either affecting the
  other's behavior — most likely an explicit pipeline-variant flag on
  `GenerationJob` (e.g. `engine_version`) routed at the orchestrator level,
  not a fork of the tools themselves. Exact mechanism is an Architect
  decision after the spec exists, not decided here.
- This constraint applies regardless of which lever(s) the detail session
  lands on — it's about *where users encounter v2*, not which lever ships.

## 5b. New grounding found (2026-08-18)

Anthropic's own official `pptx` skill (`anthropics/skills`, used by Claude
Code itself to generate PowerPoints) encodes an explicit, non-obvious design
system — layout dominance ratios, mandatory layout variety across a deck, a
banned list of "AI-generated" visual markers (accent bars, cream
backgrounds), and a 3-phase QA pipeline (content → file → visual, with
text-overflow checked first as the most common defect). Full findings and a
gap-check against our current QA/layout logic: this conversation's session
log — to be folded into `synthesis-studio-analyst`'s elicitation as source
material for Lever 2 (visual QA) and as a checklist input to Lever 1's
layout-grammar rules, not as a replacement for the elicitation itself (the
checklist tells us what "well-designed" looks like in general; the elicitation
still has to find where *our* brand-specific decks fall short of it).

## 6. Next step (the only one)

Run the detail-elicitation session with the **`synthesis-studio-analyst`**
agent (created 2026-07-08 from this assessment): it drives the 3–5 deck
generation, collects and classifies Luis's marks, and produces
`docs/specs/synthesis-studio-v2.md` mapping each detail to a lever with
acceptance criteria — the spec must also carry the §5a rollout constraint
and reference the §5b checklist. The Architect designs only after that spec
exists — same governance that shipped Template Merge v2.

## References

- Pipeline map: `docs/architecture/GuepardAI-overview.md`, project `CLAUDE.md`
  (§Generation Pipeline, §Layout Grammar, §Agent Team Context)
- Grammar: `backend/services/ingestion/brand_composition_dna.py`
- Art direction: `backend/services/generation/art_director_service.py`,
  `decoupled_art_director.py`
- Reusable v2 machinery: `backend/services/templates/template_traversal.py`,
  `template_analyzer.py` (typographic budgets)
- Visual QA touchpoint: `docs/ai/contracts/vision-template-merge-visual-qa-adr.md`
- Asset selection: `docs/specs/mejora-seleccion-imagenes.md`
