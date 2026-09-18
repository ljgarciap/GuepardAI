# Spec: Coherencia Artística del Pipeline de Generación (Iteración 1 — Deck Design Brief)

**Date**: 2026-09-09
**Requested by**: Luis
**Status**: Done — 8/8 tareas del desglose de PM completas (2026-09-18). Validación AI Architect (`docs/ai/contracts/deck-design-brief-adr.md`) y QA visual (path legacy + premium, `docs/qa/`) aprobadas. Pendiente solo el commit del diff acumulado y el PR al Senior Reviewer.
**Project**: GuepardAI

## Problem

La esencia artística que se extrae en ingestión (`BrandArtisticEssence`: `visual_strategy`,
`design_gestures`, `composition_rules`, `executable_visual_patterns`) casi no llega al
contenido que redacta el pipeline de generación, y las decisiones de layout se toman
slide por slide sin un plan de deck completo. Resultado: presentaciones que salen
simples (contenido redactado sin conocer el tono/densidad real de la marca) e
inconexas (sin ritmo narrativo ni visual entre slides).

Rastreo exacto del flujo actual:

- `content_service.py` (`synthesize_presentation_outline`) — el Prompt Architect
  (Step 2) y el Outline Generator (Step 3) solo reciben `tone_guideline`, que sale de
  `BrandVisualDna.raw_extraction.get("tone_description")` (extracción programática de
  `ReadPPTXTool`) con fallback genérico `"Professional executive tone."`. Nunca ven
  `BrandArtisticEssence` (`visual_strategy`, `design_gestures`, `composition_rules`).
- `art_director_service.py:147-148` — `art_direction_note` (`BrandArtisticEssence.art_direction_note`)
  sí se inyecta, pero solo aquí, por slide, y solo afecta layout/assets — nunca contenido.
- El Outline Generator y el Art Director planean **slide por slide** (`for slide in
  slides:` en ambos). El único paso con visión del deck completo es `NarratorTool`
  (`agents/narrator.py`, Step 4.5), que corre **antes** del Architect, solo puede tocar
  `subtitle`/`bullets`/`objective` (máx. 40% de slides) y no ve nada de layout.

Esto ya se documentó en la conversación previa con Arquitecto/Analista/AI Architect
del 2026-09-09; esta spec formaliza la solución con una restricción adicional que
Luis marcó como bloqueante: **todo lo que la spec proponga usar debe tener un
ejecutor real** en el renderer que corresponda (PPTX o PDF), no solo existir como
texto descriptivo en el JSON de ingestión.

## Auditoría de implementabilidad (hallazgo crítico)

Antes de diseñar la solución se auditó qué parte de `BrandArtisticEssence` tiene
efectivamente un ejecutor en cada canal de render. El resultado cambia el diseño:

| Vocabulario | Quién lo genera | Quién lo ejecuta | Cobertura real |
|---|---|---|---|
| `grammar_type` (10 tipos: `strategic_split`, `executive_quote`, `impact_number`, `section_break`, `case_study`, `two_column`, `cover_hero`, `data_grid_cards`, + aliases) | Analyst (`infer_grammar_type` en `brand_composition_dna.py`) o Art Director LLM | `painter_bridge.GRAMMAR_TO_PAINTER` → métodos reales de `GammaPainter` (`paint_split`, `paint_quote`, `paint_big_metric`, `paint_hero`, `paint_grid`, `paint_data_grid_cards`, `paint_pillars`, `paint_custom_canvas`) | ✅ **Completa** — los 10 tipos tienen geometría (`GRAMMAR_GEOMETRIES`) y método de pintado real en PPTX. |
| `design_gestures` (`corner_style`, `visual_density`) / `composition_rules` (`max_img_ratio`, `typography_style`, `color_application`) | Vision LLM en ingestión (`artistic_essence_service.py`) | — | ❌ **Muerta en el renderer determinista.** `painter_bridge._patch_dna_for_painter` la adjunta a `dna_record.visual_strategy.vision_insights` pero `painter.py` (verificado: cero referencias a `corner_style`, `design_gestures`, `visual_density`, `vision_insights`) nunca la lee al pintar formas — `kerning`/`padding_percent` están hardcodeados. Solo existe como texto libre dentro de `art_direction_note` para el prompt del Art Director. |
| `pattern_type` premium (declarado en `visual_pattern_service.SUPPORTED_PATTERN_TYPES`: `object_as_letter`, `typographic_substitution`, `editorial_split`, `brand_footer`, `logo_locked_footer`, `full_bleed_hero`, `image_masked_title`, `data_cards_brand_grid`) | Vision LLM en ingestión + `PremiumVisualAgent._vision_adjust_loop` | `premium_pdf.html` (verificado línea por línea) | ⚠️ **Parcial — 3 de 8 reales.** El template solo tiene ramas Jinja para `full_bleed_hero` (línea 339) y `data_cards_brand_grid` (línea 382); todo lo demás cae al bloque `editorial_split` por defecto (línea 442). `image_masked_title` solo agrega una clase CSS (`masked-title`) sobre el split, no es un layout distinto. `object_as_letter`, `typographic_substitution`, `brand_footer`, `logo_locked_footer` **no tienen ninguna implementación** — si el Vision LLM o el Art Director los eligen, el resultado visual es idéntico a un `editorial_split` cualquiera, silenciosamente. |
| Legacy PDF / `pdf_base.html` (**tier y formato por defecto en el frontend** — `generator.component.ts:37-38`, `selectedFormat='pptx'`, `selectedTier='free'`) | `render_agent.py:103` pasa `content_json["layout_type"]` (el `grammar_type` del Analyst/Art Director) **sin traducir**, como `"layout"` | `pdf_base.html:118-129` — solo 4 ramas Jinja explícitas: `hero`/`composition_hero`, `data_grid`/`data_grid_cards`, `quote`/`composition_quote`, `pillars`/`composition_pillars`; todo lo demás → `artistic_split.html` | ❌❌ **Peor que el path premium.** Ninguno de los nombres reales de `grammar_type` (`cover_hero`, `executive_quote`, `case_study`, `two_column`, `section_break`, `closing_cta`, `impact_number`, `strategic_split`, `marketing_hero`, `asymmetric_overlay`) coincide textualmente con las 4 ramas — ni siquiera `cover_hero` matchea `hero`. Solo `data_grid_cards` calza por casualidad. En la práctica, **9 de 10 `grammar_type` colapsan silenciosamente a `artistic_split`** en el path que la mayoría de usuarios ve por default. Esto es independiente del problema de contenido/esencia — es un bug de traducción de vocabulario que hace irrelevante cualquier trabajo fino del Art Director en este canal. |

**Conclusión de diseño**: esta spec construye sobre `grammar_type` (cobertura
completa en PPTX) y sobre el subconjunto de `pattern_type` premium que ya renderiza
distinto (`full_bleed_hero`, `data_cards_brand_grid`, `editorial_split`) — y, dado
que Luis confirmó incluir el path legacy PDF en esta misma iteración, agrega una
tabla de traducción `grammar_type → layout` (análoga a `GRAMMAR_TO_PAINTER`) para
que ese path deje de perder el 90% de las decisiones de layout por un simple
mismatch de nombres. Cualquier uso de `design_gestures`/`composition_rules` sigue
limitado a razonamiento de LLM sobre decisiones que sí tienen efecto real — nunca
como un atributo que "se cuela" a un renderer que no lo interpreta.

## Solution summary

Un **Deck Design Brief**: un JSON compacto, construido una sola vez por job (no por
slide) a partir de `BrandArtisticEssence` + `BrandPremiumVisualPattern`, filtrado por
una whitelist de vocabulario ejecutable, e inyectado en las tres etapas de contenido
que hoy lo ignoran (Prompt Architect, Outline Generator, Narrator). El Art Director
sigue recibiendo `art_direction_note` como hoy, pero ahora coherente con lo que ya
decidió el contenido, no como una capa de maquillaje aislada.

Nuevo módulo `services/generation/deck_brief_service.py`:

```python
IMPLEMENTED_PREMIUM_PATTERNS = {"full_bleed_hero", "data_cards_brand_grid", "editorial_split"}

def build_deck_brief(db: Session, brand_id: int) -> dict:
    """
    Devuelve, o {} si no hay esencia (fallback: pipeline actual sin cambios):
    {
      "tone_note": str,               # de essence.visual_strategy, truncado
      "visual_density": "dense|balanced|minimal",   # de design_gestures, default "balanced"
      "preferred_grammar_types": [str],  # subset de GRAMMAR_GEOMETRIES.keys() inferido de
                                          # structural_archetypes/slide_archetypes
      "renderable_premium_patterns": [str],  # intersección de BrandPremiumVisualPattern
                                              # .patterns_json con IMPLEMENTED_PREMIUM_PATTERNS
      "opening_closing_hint": str,     # cómo debería abrir/cerrar el deck (de slide_archetypes)
    }
    """
```

`IMPLEMENTED_PREMIUM_PATTERNS` vive en `system_configs` (decisión confirmada con
Luis 2026-09-09, key `implemented_premium_patterns`, seedeada en `utils/seed.py`
con el default `["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]`) —
así, el día que `premium_pdf.html` gane un bloque real para, p. ej.,
`image_masked_title`, se activa cambiando el valor en BD, sin deploy de código.
La usan tanto `deck_brief_service` como `visual_pattern_service.normalize_executable_patterns`
(hoy acepta los 8 declarados; pasa a filtrar contra esta config), cerrando el
hallazgo crítico de la auditoría.

**Fix del path legacy PDF** (en scope de esta iteración): nueva tabla
`GRAMMAR_TO_ARTISTIC_PDF` en `services/rendering/artistic_pdf_service.py` (mismo
espíritu que `painter_bridge.GRAMMAR_TO_PAINTER`, pero mapeando a los 5 `layout`
reales de `pdf_base.html`: `hero`, `data_grid`, `quote`, `pillars`, `split`).
`render_agent.py:103` deja de pasar `layout_type` crudo y pasa
`GRAMMAR_TO_ARTISTIC_PDF.get(grammar_type, "split")`. Propuesta inicial de mapeo
(a validar visualmente por Frontend/Backend Dev antes de cerrar, no asumida como
definitiva):

```python
GRAMMAR_TO_ARTISTIC_PDF = {
    "cover_hero":          "hero",
    "marketing_hero":      "hero",
    "asymmetric_overlay":  "hero",
    "executive_quote":     "quote",
    "closing_cta":         "quote",
    "data_grid_cards":     "data_grid",
    "impact_number":       "data_grid",   # single-metric card dentro del grid; a validar
    "two_column":          "pillars",
    "case_study":          "pillars",     # métrica + imagen lateral; a validar contra "split"
    "section_break":       "hero",        # fondo de color + título grande, igual que PPTX
    "strategic_split":     "split",       # ya es el fallback, explícito por claridad
}
```

Este mapeo por sí solo (sin tocar el Deck Brief) ya es un fix independiente y de
alto impacto: hace que el 90% de decisiones de layout que hoy se pierden en el
path por defecto empiecen a reflejarse visualmente. El Deck Brief lo aprovecha
para que `preferred_grammar_types` tenga efecto visible también en PDF legacy, no
solo en PPTX.

Consumo (versionado de prompts, patrón del proyecto — nunca se edita un
`prompt_*` existente):

- `prompt_architect_v2` → `prompt_architect_v3`: agrega `{deck_brief}` junto a
  `{tone_guideline}` (no lo reemplaza — `tone_guideline` sigue siendo el fallback si
  `deck_brief` viene vacío).
- `prompt_content_outline_v2` → `prompt_content_outline_v3`: agrega
  `{preferred_grammar_types}` y `{opening_closing_hint}` para que la secuencia de
  `layout_type` del outline refleje el ritmo real de la marca, no una elección
  genérica del LLM.
- `prompt_narrator_v1` → `prompt_narrator_v2`: el Narrator ya recibe `layout_type`
  por slide (`agents/narrator.py:59`); se le agrega `{visual_density}` y
  `{preferred_grammar_types}` para que su `cohesion_score` también evalúe si la
  secuencia de layouts respeta el ritmo del brief, no solo el texto.

## Users and roles

- **Usuario final de GuepardAI**: recibe presentaciones donde el contenido y el
  diseño comparten la misma lectura de marca. Sin cambios de UI ni permisos.
- **Pipeline de generación** (`AgentOrchestrator.run_generation_pipeline` →
  `content_service.synthesize_presentation_outline`): construye y propaga el brief.
- **Admin**: sin cambios — el brief se calcula on-the-fly, no requiere backfill
  (a diferencia de `visual_profile` en `mejora-seleccion-imagenes.md`).

## Acceptance criteria

- [ ] `deck_brief_service.build_deck_brief()` devuelve `{}` (no `None`, no excepción)
      cuando la marca no tiene `BrandArtisticEssence` — el pipeline sigue funcionando
      exactamente igual que hoy con los prompts `_v2`/`_v1` de fallback.
- [ ] `renderable_premium_patterns` es siempre un subconjunto de
      `IMPLEMENTED_PREMIUM_PATTERNS` (`full_bleed_hero`, `data_cards_brand_grid`,
      `editorial_split`) — nunca contiene `object_as_letter`, `typographic_substitution`,
      `brand_footer`, `logo_locked_footer`, `image_masked_title` mientras no tengan
      implementación real en `premium_pdf.html`.
- [ ] `visual_pattern_service.normalize_executable_patterns()` filtra contra
      `IMPLEMENTED_PREMIUM_PATTERNS` antes de persistir `BrandPremiumVisualPattern.patterns_json`
      — un test verifica que un `executable_visual_patterns` del Vision LLM con
      `pattern_type: "object_as_letter"` no sobrevive la normalización.
- [ ] `preferred_grammar_types` solo contiene claves presentes en
      `GRAMMAR_GEOMETRIES` (`brand_composition_dna.py`) — un valor no reconocido se
      descarta individualmente, no invalida el brief completo.
- [ ] El Outline Generator, con `prompt_content_outline_v3` seedeado, produce una
      secuencia de `layout_type` verificablemente distinta (test con LLM mockeado
      que confirma que el prompt renderizado contiene `{preferred_grammar_types}`
      con los valores del brief) frente al mismo input sin brief.
- [ ] El Narrator (`prompt_narrator_v2`) recibe `visual_density` y
      `preferred_grammar_types` en su prompt — test que confirma el formato del
      prompt, no solo que la llamada no falla.
- [ ] **Criterio de verificación visual (no solo JSON)**: un test de integración
      genera un deck completo tier=premium con una marca de fixture que tiene
      `BrandArtisticEssence` con `visual_strategy` distintivo, y confirma que
      `slide.pattern_type` persistido en cada slide pertenece a
      `IMPLEMENTED_PREMIUM_PATTERNS`. Adicionalmente, QA manual local (una corrida
      real, no mockeada) debe adjuntar capturas antes/después del mismo prompt para
      confirmar que el cambio es perceptible, no solo que el JSON cambió — sigue el
      patrón de `docs/manuals/technical/` de no declarar un fix cerrado sin probarlo
      contra el caso real (ver memoria "No claims externos sin validar").
- [ ] Ningún `prompt_*` existente se edita in-place; todas las nuevas versiones
      (`_v3`, `_v2` según el caso) se agregan en `utils/seed.py` con el código
      leyendo la nueva key con fallback a la anterior.
- [ ] `system_configs` no gana ningún umbral o límite hardcodeado nuevo sin pasar
      por `seed.py` (p. ej. si se decide truncar `tone_note`/`opening_closing_hint`
      a N caracteres, N es una config, no un literal).
- [ ] `implemented_premium_patterns` existe como key en `system_configs` (seedeada
      en `utils/seed.py`), se lee vía `get_system_config()` como el resto de config
      runtime del proyecto, y `IMPLEMENTED_PREMIUM_PATTERNS` deja de ser una
      constante fija en `visual_pattern_service.py`.
- [ ] `render_agent.py` usa `GRAMMAR_TO_ARTISTIC_PDF.get(grammar_type, "split")` en
      vez de pasar `content_json["layout_type"]` crudo a `pdf_base.html` — test
      parametrizado que confirma que **cada uno** de los 10 `grammar_type` (+
      aliases de `SLUG_ALIASES`) resuelve a uno de los 5 `layout` reales (`hero`,
      `data_grid`, `quote`, `pillars`, `split`), nunca a un valor no reconocido por
      `pdf_base.html`.
- [ ] **QA visual del path legacy** (mismo espíritu que el criterio premium): una
      corrida real (no mockeada) genera un PDF con al menos un slide por cada
      `grammar_type` mapeado, y una revisión manual confirma que el layout
      resultante es visualmente distinto según el mapeo — no todos colapsando a
      `artistic_split` como ocurre hoy. Este es el criterio que prueba que el fix
      del path legacy realmente cierra el hallazgo, no solo que el código compila.

## Edge cases and error scenarios

- **Marca sin `BrandArtisticEssence`** (nunca se ingirió `style_filename`, o falló
  la extracción Vision) → `build_deck_brief` devuelve `{}`; los prompts `_v3`
  formatean el placeholder vacío sin romper — comportamiento idéntico al actual.
- **`BrandPremiumVisualPattern` existe pero todos sus patrones son de los 5 no
  implementados** → `renderable_premium_patterns` queda vacío; `PremiumVisualAgent`
  usa su fallback ya existente (`_choose_pattern` → `editorial_split`), sin cambio
  de comportamiento visible salvo que ya no hay una promesa incumplida en el brief.
- **Outline Generator ignora `preferred_grammar_types`** (el LLM no sigue la
  sugerencia) → no es un error; el Art Director sigue siendo la autoridad final de
  `grammar_type` por slide (vía `infer_grammar_type` o su propio criterio) como hoy.
  El brief es una guía de contenido, no un contrato que el Architect deba cumplir
  ciegamente.
- **Narrator con `cohesion_score` bajo por ritmo de layout repetido** → ya existe la
  regla de variedad en `painter_bridge.py:276-294` (fuerza cambio si un layout se
  repite 3 veces); el Narrator no debe duplicar esa lógica, solo debe poder
  *señalarlo* en `gaps_found` para el log de auditoría.
- **Job legacy (tier no premium, sin `BrandPremiumVisualPattern`)** →
  `renderable_premium_patterns` queda `[]`; el resto del brief (`tone_note`,
  `visual_density`, `preferred_grammar_types`) sigue aplicando porque son
  independientes del tier (`grammar_type` cubre PPTX legacy también).
- **`visual_strategy`/`slide_archetypes` con texto muy largo** → truncar antes de
  interpolar en los prompts (mismo patrón que `qa_feedback_max_chars` /
  `strategic_context[:400]` ya usados en `content_service.py`).

## Out of scope

- Implementar `object_as_letter`, `typographic_substitution`, `brand_footer`,
  `logo_locked_footer` como layouts reales en `premium_pdf.html` (requiere HTML/CSS
  nuevo + método de render + QA visual) — trabajo de Frontend/Backend Dev + DevOps,
  candidato a iteración 2 una vez validado que el Deck Brief mejora el resultado con
  el vocabulario ya implementable.
- Nuevos layouts en `pdf_base.html` para `grammar_type` sin una familia visual
  cercana entre los 5 templates existentes (p. ej. un template propio para
  `impact_number` en vez de reusar `data_grid`) — se evalúa después de medir si el
  mapeo `GRAMMAR_TO_ARTISTIC_PDF` inicial ya resuelve la variedad percibida.
- Wire `design_gestures`/`composition_rules` (corner_style, kerning, padding) a
  geometría determinista en `painter.py` (hoy es texto libre para el LLM del Art
  Director) — cambiaría `paint_*` methods, es un fix de renderer aparte, no de
  contenido.
- Reestructurar el `NarratorTool` para que pueda corregir layout, no solo texto
  (hoy corre antes del Architect y no ve `grammar_type` asignado) — se deja para
  cuando se mida si el brief ya resuelve suficiente cohesión sin tocar el orden del
  pipeline.
- Cambios de frontend o de API pública — el brief es interno al pipeline.

## Open questions (resueltas con Luis — 2026-09-09)

- **¿Alcance del path legacy PDF?** → El frontend confirma `selectedFormat='pptx'`
  y `selectedTier='free'` como default (`generator.component.ts:37-38`) — el path
  legacy no es un remanente, es lo que ve la mayoría de usuarios por defecto. Luis
  confirmó incluirlo en esta misma iteración; de ahí salió el hallazgo de
  `render_agent.py:103` (9 de 10 `grammar_type` colapsando a `artistic_split`) y el
  fix `GRAMMAR_TO_ARTISTIC_PDF` ya incorporado arriba.
- **¿Dónde vive `IMPLEMENTED_PREMIUM_PATTERNS`?** → Luis confirmó `system_configs`
  (key `implemented_premium_patterns`), ya reflejado en Solution summary y
  Acceptance criteria.

## Cierre del Arquitecto (2026-09-09)

Revisión contra el contrato de `BaseAgentTool`, el patrón de auditoría
(`ArtDirectorDecision`), el routing de LLM y los ADRs ya validados del proyecto.
Veredicto: **diseño aprobado**, con las siguientes decisiones de implementación
fijadas para que PM y Backend Dev no tengan que re-derivarlas (evita el patrón que
generó el hallazgo de esta spec: decisiones tomadas ad hoc sin quedar registradas):

1. **`deck_brief_service.build_deck_brief()` no es un `BaseAgentTool`.** No hace
   ninguna llamada a LLM — es una lectura determinista de `BrandArtisticEssence` +
   `BrandPremiumVisualPattern` filtrada por whitelist. Mismo criterio que
   `search_rag()`/`_build_manifest()` en `content_service.py`: función de servicio
   plana, sin `args_schema` ni `log_decision` propio. Se llama con el `db: Session`
   que `synthesize_presentation_outline` ya tiene abierto (mismo hilo, antes del
   `ThreadPoolExecutor` del Step 4) — no aplica la restricción de sesiones
   compartidas entre hilos.

2. **Trazabilidad del brief**: no se crea un `log_decision` nuevo. `ContentManifest`
   (`schemas/presentation.py`) gana un campo opcional
   `deck_brief: Optional[dict] = None` (backward-compatible); `synthesize_presentation_outline`
   lo puebla y lo devuelve. `GenerateTextTool.run()` (`agents/redactor.py:214-227`)
   ya llama `self.log_decision(decision_type="content_synthesis", metadata={...})`
   — ese `metadata` dict existente se extiende con `deck_brief`, sin duplicar el
   patrón de auditoría.

3. **`specialization` de los prompts modificados no cambia** — `prompt_architect_v3`
   y `prompt_content_outline_v3` se mantienen en `specialization="general"` (o sin
   especializar), igual que hoy. Es framing editorial/narrativo, no juicio visual;
   mismo razonamiento ya validado en
   `docs/ai/contracts/default-llm-template-merge-outline-adr.md`. No usar
   `specialization="design"` aquí — esa ruta es para decisiones de layout/Art
   Director, no para tono de contenido.

4. **`GRAMMAR_TO_ARTISTIC_PDF` es una constante en código**, no `system_configs` —
   a diferencia de `implemented_premium_patterns`. Distinción: `implemented_premium_patterns`
   es "qué está construido hoy" (cambia según qué se implemente en `premium_pdf.html`,
   por eso es runtime-toggle); `GRAMMAR_TO_ARTISTIC_PDF` es una relación estructural
   fija entre dos vocabularios (igual que su precedente directo,
   `painter_bridge.GRAMMAR_TO_PAINTER`, que también es una constante de código).

5. **Gate obligatorio antes de que el Senior Reviewer apruebe el PR**: los tres
   prompts nuevos/modificados (`prompt_architect_v3`, `prompt_content_outline_v3`,
   `prompt_narrator_v2`) deben pasar por el AI Architect vía la skill
   `test-ai-request` (llamada real, no mockeada) una vez Backend Dev redacte su
   texto definitivo, produciendo un ADR en `docs/ai/contracts/` con el mismo
   formato que `default-llm-template-merge-outline-adr.md` (shape de request/response,
   resultado de la corrida real, contrato de degradación). Backend Dev **puede**
   escribir el código sin esperar esta validación — el gate bloquea la aprobación
   del PR, no el inicio de la implementación.

PM puede desglosar en tareas de Backend Dev (deck_brief_service, cambios en
content_service.py/redactor.py/render_agent.py, seeds de prompts y de
`implemented_premium_patterns`), una tarea de validación AI Architect (punto 5) y
una tarea de QA visual (los dos criterios de "verificación visual" ya definidos
arriba, PPTX + PDF legacy + PDF premium).

## Desglose de tareas (PM, 2026-09-09)

Tareas de ≤4h, en orden de dependencia. Los grupos sin dependencia entre sí pueden
correr en paralelo.

---

**Task**: Mover `IMPLEMENTED_PREMIUM_PATTERNS` a `system_configs` — ✅ **Done** (2026-09-09)
**Agent**: Backend Dev
**Depends on**: none
**Acceptance**: key `implemented_premium_patterns` seedeada en `utils/seed.py`
(default `["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]`);
`visual_pattern_service.normalize_executable_patterns()` filtra contra el valor
leído vía `get_system_config()` en vez del set hardcodeado `SUPPORTED_PATTERN_TYPES`;
test que confirma que un `executable_visual_patterns` con
`pattern_type: "object_as_letter"` no sobrevive la normalización.
**Files**: `backend/utils/seed.py`, `backend/services/ingestion/visual_pattern_service.py`

---

**Task**: Traducir `grammar_type` → `layout` real en el path PDF legacy — ✅ **Done** (2026-09-09)
**Agent**: Backend Dev
**Depends on**: none
**Acceptance**: nueva tabla `GRAMMAR_TO_ARTISTIC_PDF` en `artistic_pdf_service.py`
(mapeo propuesto en la spec, a validar visualmente — no cerrar el mapeo exacto sin
QA); `render_agent.py:103` resuelve `GRAMMAR_TO_ARTISTIC_PDF.get(grammar_type, "split")`
en vez de pasar `layout_type` crudo; test parametrizado que cubre los 10
`grammar_type` + todas las keys de `SLUG_ALIASES`, confirmando que cada uno resuelve
a uno de `{hero, data_grid, quote, pillars, split}`.
**Files**: `backend/services/rendering/artistic_pdf_service.py`, `backend/agents/render_agent.py`

---

**Task**: Implementar `deck_brief_service.build_deck_brief()` — ✅ **Done** (2026-09-09)
**Agent**: Backend Dev
**Depends on**: Mover `IMPLEMENTED_PREMIUM_PATTERNS` a `system_configs` (necesita
leer `implemented_premium_patterns` para `renderable_premium_patterns`)
**Acceptance**: firma y shape exactos de la spec (Solution summary); devuelve `{}`
sin excepción si la marca no tiene `BrandArtisticEssence`; `preferred_grammar_types`
filtra contra `GRAMMAR_GEOMETRIES.keys()` (entradas inválidas se descartan
individualmente); `ContentManifest` (`schemas/presentation.py`) gana el campo
opcional `deck_brief: Optional[dict] = None`; tests unitarios para cada edge case
listado en la spec (marca sin esencia, `BrandPremiumVisualPattern` con solo
patterns no implementados, texto largo truncado).
**Files**: `backend/services/generation/deck_brief_service.py` (nuevo), `backend/schemas/presentation.py`

---

**Task**: Conectar el Deck Brief a Prompt Architect, Outline Generator y Narrator — ✅ **Done** (2026-09-09)
**Agent**: Backend Dev
**Depends on**: Implementar `deck_brief_service.build_deck_brief()`
**Acceptance**: `synthesize_presentation_outline` llama `build_deck_brief()` una vez
por job y lo pasa a `cfg_architect`/`cfg_outline`; lo adjunta a `ContentManifest.deck_brief`
devuelto; `NarratorTool` recibe `visual_density`/`preferred_grammar_types`; el
`log_decision(decision_type="content_synthesis", ...)` que `GenerateTextTool.run()`
ya hace (`agents/redactor.py:214-227`) incluye `deck_brief` en su `metadata` dict
existente — **no** se agrega un `log_decision` nuevo. El Art Director no cambia
(sigue leyendo `art_direction_note` como hoy).
**Files**: `backend/services/generation/content_service.py`, `backend/agents/redactor.py`, `backend/agents/narrator.py`

---

**Task**: Seedear `prompt_architect_v3`, `prompt_content_outline_v3`, `prompt_narrator_v2` — ✅ **Done** (2026-09-09)
**Agent**: Backend Dev
**Depends on**: Conectar el Deck Brief a Prompt Architect, Outline Generator y Narrator
(necesita los nombres finales de placeholders decididos en esa tarea)
**Acceptance**: las 3 keys nuevas en `utils/seed.py`, ninguna edición in-place de
`prompt_architect_v2`/`prompt_content_outline_v2`/`prompt_narrator_v1`; el código ya
lee la versión nueva con fallback a la anterior (patrón `cfg_x_v2 or cfg_x_v1`);
test que confirma que el prompt renderizado contiene los valores del brief cuando
existe, y el placeholder vacío cuando no.
**Files**: `backend/utils/seed.py`

---

**Task**: Validación real de los 3 prompts nuevos/modificados (gate obligatorio) — ✅ **Done** (2026-09-18)
**Agent**: AI Architect
**Depends on**: Seedear `prompt_architect_v3`, `prompt_content_outline_v3`, `prompt_narrator_v2`
**Acceptance**: corrida real (skill `test-ai-request`, no mockeada) sobre los 3
prompts; ADR nuevo en `docs/ai/contracts/` con el mismo formato que
`default-llm-template-merge-outline-adr.md` (shape de request/response, resultado
de la corrida real, contrato de degradación). **Bloquea la aprobación del PR por
el Senior Reviewer** — no bloquea el inicio de las tareas de Backend Dev.
**Files**: `docs/ai/contracts/deck-design-brief-adr.md` (nuevo)

---

**Task**: QA visual — PPTX, PDF legacy y PDF premium — ✅ **Done** (2026-09-18):
mitad "PDF legacy" aprobada el 2026-09-09, ver
`docs/qa/coherencia-artistica-pipeline-2026-09-09.md` (corrida real con Playwright, 5
grammar_type → 5 layouts visualmente distintos confirmados). Mitad "PDF premium"
aprobada el 2026-09-18, ver `docs/qa/coherencia-artistica-pipeline-premium-2026-09-18.md`
(corrida real end-to-end con Claude Sonnet + Playwright; encontró y corrigió un segundo
punto sin whitelist de implementabilidad en `PremiumVisualAgent._vision_adjust_loop`,
con capturas antes/después confirmando el impacto visual del fix). PPTX no requería
trabajo nuevo — cobertura completa ya confirmada en la Auditoría de implementabilidad.
**Agent**: QA
**Depends on**: Traducir `grammar_type` → `layout` real en el path PDF legacy,
Conectar el Deck Brief a Prompt Architect/Outline/Narrator, Seedear los 3 prompts
**Acceptance**: los dos criterios de verificación visual de la spec —
(a) corrida real tier=premium: cada `slide.pattern_type` persistido pertenece a
`implemented_premium_patterns`, con capturas antes/después del mismo prompt;
(b) corrida real del path legacy: al menos un slide por `grammar_type` mapeado,
confirmando visualmente que ya no todos colapsan a `artistic_split`. Sin este
paso el hallazgo de la spec no se considera cerrado (ver memoria "No claims
externos sin validar").
**Files**: ninguno de producción — capturas/reporte adjuntos a esta spec o al PR

---

**Task**: Sincronizar `GuepardAI/CLAUDE.md` y cerrar el spec — ✅ **Done** (2026-09-18)
**Agent**: Tech Writer
**Depends on**: Conectar el Deck Brief a Prompt Architect/Outline/Narrator, Traducir
`grammar_type` → `layout` real (trabaja en paralelo mientras esas dos avanzan;
cierra una vez ambas aterrizan)
**Acceptance**: sección "Generation Pipeline" de `CLAUDE.md` documenta el Deck
Design Brief y el fix de traducción `grammar_type`→`layout` del path legacy;
`docs/specs/coherencia-artistica-pipeline.md` pasa su `Status` de `Approved` a
`Done` una vez QA visual confirma.
**Files**: `GuepardAI/CLAUDE.md`, `docs/specs/coherencia-artistica-pipeline.md`

---

### Nota de implementación — `deck_brief_service.build_deck_brief()` (2026-09-09)

- `preferred_grammar_types` aplica el criterio de la spec de forma estricta y
  literal: solo sobreviven candidatos que resuelven a una key real de
  `GRAMMAR_GEOMETRIES` (vía `SLUG_ALIASES`). Los candidatos vienen de
  `preferred_layouts` (dentro de `executable_visual_patterns`) y de
  `slide_archetypes.*.layout` — nunca de texto libre (`visual_strategy`,
  `structural_archetypes`), porque ahí no hay ningún nombre de layout real que
  extraer sin inventar una heurística sin ejecutor detrás. Consecuencia
  esperada y documentada en el código: con las esencias de marca típicas de
  hoy, este campo sale vacío la mayoría de las veces — es honesto, no un bug;
  mejora en cuanto se amplíe el vocabulario reconocido (fuera de alcance aquí).
- Al escribir el test de este campo apareció el mismo hallazgo que en la tarea
  de PDF legacy: el alias `"data-grid"` (sin `_cards`) NO es una key de
  `GRAMMAR_GEOMETRIES` — a diferencia de `GRAMMAR_TO_ARTISTIC_PDF` (que sí lo
  cubre explícitamente como excepción), aquí el criterio de la spec es
  literal, así que se descarta. Cubierto con test dedicado
  (`test_bare_data_grid_alias_is_not_recognized_here_unlike_data_grid_cards`)
  para que quede documentado y no se confunda con un bug futuro.
- `visual_density` revisa `design_gestures` y luego `composition_rules` (con
  prioridad al primero) — el campo aparece en cualquiera de los dos según qué
  versión del prompt de ingestión se usó; mismo criterio ya usado en
  `visual_pattern_service.infer_patterns_from_essence()`.
- Nueva config `deck_brief_field_max_chars` (default 400, mismo criterio que
  `strategic_context[:400]`) para truncar `tone_note`/`opening_closing_hint` —
  ninguna longitud quedó hardcodeada.
- `ContentManifest.deck_brief: Optional[dict] = None` agregado
  (`schemas/presentation.py`) — todavía no lo puebla nadie (eso es la
  siguiente tarea); compatible hacia atrás por default `None`.
- Suite completa tras esta tarea: 714 passed / 1 (el mismo preexistente y
  ajeno de siempre).

### Nota de implementación — Wiring a Architect/Outline/Narrator (2026-09-09)

- `synthesize_presentation_outline` computa `deck_brief = build_deck_brief(db, job.brand_id) or {}` una vez, antes del Prompt Architect, y lo reutiliza en las 3 etapas — nunca se recalcula por slide.
- Los `.format()` de los prompts reciben `deck_brief`/`preferred_grammar_types`/`opening_closing_hint` **siempre**, incluso cuando el prompt cargado es `_v1`/`_v2` (sin esos placeholders) — `str.format()` de Python ignora kwargs no referenciados, así que no hace falta ninguna rama condicional y el fallback a versiones anteriores sigue funcionando exactamente igual que hoy.
- `format_grammar_type_list()` y `summarize_for_architect_prompt()` viven en `deck_brief_service.py` (no duplicados en `content_service.py`/`narrator.py`) — Outline Generator y Narrator comparten `preferred_grammar_types` y deben renderizarlo idéntico.
- `GenerateTextTool.run()` no ganó un `log_decision` nuevo: su llamada existente (`decision_type="content_synthesis"`) ahora incluye `deck_brief` en el `metadata` dict ya existente.
- El Art Director no se tocó — sigue leyendo `art_direction_note` como antes de esta spec.
- **Lección de testing para la siguiente tarea**: `synthesize_presentation_outline` llama a `search_rag()`, que llama a `get_embedding()` — un proveedor LLM **real**, no cubierto por el mock global `mock_llm_calls` (que solo cubre `generate_json`/`generate_text`). Un test que invoque esta función sin mockear `search_rag` (o `get_embedding`) se cuelga intentando una llamada de red real — así se descubrió aquí, tras un `TaskStop` a un pytest colgado. `tests/test_content_service_deck_brief.py` mockea `search_rag` explícitamente en los 4 tests; cualquier test futuro sobre este archivo debe hacer lo mismo.
- Suite completa tras esta tarea: 718 passed / 1 (el mismo preexistente y ajeno).

### Nota de implementación — Texto real de `prompt_architect_v3`, `prompt_content_outline_v3`, `prompt_narrator_v2` (2026-09-09)

- Cada `_v3`/`v2` se escribió como el `_v2`/`v1` existente **más** las secciones
  nuevas — nunca una reescritura desde cero, siguiendo el "agrega, no
  reemplaza" de la spec.
- **Hallazgo de vocabulario al escribir el prompt del Outline Generator**: el
  prompt ya tenía su propia lista "Allowed layout_type values"
  (`composition_hero`, `composition_split`, ...) — un vocabulario *distinto*
  al de `preferred_grammar_types` (`cover_hero`, `executive_quote`, ... de
  `GRAMMAR_GEOMETRIES`). Copiar `preferred_grammar_types` como si fueran
  valores válidos de `layout_type` habría hecho que el LLM alucinara un
  `layout_type` fuera de la lista permitida. Se presenta explícitamente como
  "BRAND VISUAL RHYTHM — soft signal... NOT literal layout_type values" en
  ambos prompts (Outline y Narrator) para no contaminar el contrato de salida
  existente.
- El Narrator gana una regla accionable con el nuevo dato (`visual_density`):
  "dense" → bullets más ricos al corregir, "minimal" → bullets más cortos —
  encaja dentro de lo que el Narrator YA puede tocar (nunca `layout_type`).
- Tests: `test_seed_prompts_deck_brief.py` renderiza los 3 prompts reales con
  los kwargs exactos que el código de producción pasa (detecta un placeholder
  mal escrito antes de que llegue a producción); `test_content_service_deck_brief.py`
  ganó un test que corre el pipeline completo con el texto real sembrado (no
  solo plantillas mínimas de prueba). Suite completa: 724 passed / 1 (el mismo
  preexistente y ajeno).
- **Pendiente, no de esta tarea**: la validación en vivo del AI Architect
  (`test-ai-request`, llamada real a un proveedor) — es la siguiente tarea de
  la cadena y es un gate distinto (spend real de tokens), no algo que Backend
  Dev deba correr.

### Nota de implementación — 2 hallazgos incidentales corregidos al testear

Al escribir y correr los tests de las dos primeras tareas (`pytest --cov=agents
--cov=services --cov=providers tests/`, 695 passed / 1 pre-existente sin relación)
aparecieron dos bugs reales, no teóricos, arreglados en el mismo commit:

1. **`from weasyprint import HTML` muerto en `artistic_pdf_service.py`** — el
   módulo migró por completo a Playwright (`sync_playwright()` en ambos
   `generate_pdf()`/`generate_premium_pdf()`); `HTML(` no se llama en ningún lado.
   Ese import rompía la carga del módulo en máquinas sin el runtime nativo GTK de
   WeasyPrint (como esta). Eliminado — cero cambio de comportamiento.
2. **Regresión real detectada por la propia suite**: la `description` de
   `implemented_premium_patterns` (341 caracteres) excedía
   `SystemConfig.description` (`String(255)`), lo que hacía fallar
   `StringDataRightTruncation` en el `commit()` final de `seed_data()` — y como
   ese commit es atómico, arrastraba consigo el insert del `FooterConfig` por
   defecto (`test_footer_api_endpoints` pasaba en `master`, fallaba con el
   cambio). Acortada a 237 caracteres; agregado `test_seed_configs.py` para que
   ninguna entrada futura de `CONFIGS` vuelva a romper esto en silencio (el
   `try/except` de `main.py` solo imprime un warning, no vuelve a lanzar).

Confirmado con `git stash` que `test_template_merge_history.py::...test_status_null_brand_id_still_rejects_non_owner`
(el único fallo restante) ya fallaba en `master` sin este cambio — no relacionado,
no se tocó (bug preexistente de generación de emails duplicados en el test helper
`_make_user`, a reportar aparte).

### Nota de implementación — Validación real del AI Architect (2026-09-18)

- `test-ai-request` corrido en vivo (sin mocks) contra la BD de desarrollo local ya
  poblada por `seed.py` — los 3 prompts (`prompt_architect_v3`, `prompt_content_outline_v3`,
  `prompt_narrator_v2`) responden con JSON válido al primer intento, respetando sus
  contratos existentes (`layout_type` nunca sale del "Allowed list" pese a que
  `preferred_grammar_types` usa un vocabulario distinto; el Narrator corrige solo
  `subtitle`/`bullets`/`objective` y se queda dentro del tope de 40%). ADR completo:
  `docs/ai/contracts/deck-design-brief-adr.md`.
- **Dos hallazgos incidentales, ninguno bloqueante para esta spec**: (1) el primer hop
  del chain (`mistral/mistral-large-latest`) devuelve 403 `tier_not_allowed` con la key
  actual — afecta a **todo** `generate_json` del proyecto, no solo estos 3 prompts, el
  fallback a `gemini-flash-latest` absorbe el fallo sin romper nada; (2)
  `specialization="design"` (usado por el Narrator desde `v1`, sin tocar en esta spec)
  **no enruta a Anthropic hoy** — `resolve_provider()` existe en `llm_provider.py` pero
  `generate_json`/`_generate_json_raw` nunca lo invocan, así que es código muerto y la
  tabla de "LLM Provider Routing" de `CLAUDE.md` no describe el comportamiento real de
  este call path. Ninguno de los dos requiere cambios para cerrar esta spec (decisión
  del Arquitecto #3 ya dejaba `specialization` fuera de alcance); quedan documentados en
  el ADR para que no se den por resueltos sin una decisión explícita del Arquitecto.
- Gate satisfecho: el PR queda desbloqueado para el Senior Reviewer en lo que respecta a
  la validación AI Architect. Sigue pendiente la QA visual del path premium (ver tarea de
  QA más abajo) antes de cerrar la spec completa.

### Revisión del Senior Reviewer (2026-09-09)

Código leído completo (no solo diff), suite corrida dos veces (antes y después
del fix de abajo): **695 passed / 1 failed** — el único fallo
(`test_template_merge_history.py::...test_status_null_brand_id_still_rejects_non_owner`)
es preexistente y ajeno (confirmado contra `master` limpio en la fase de Backend
Dev), no bloquea esta revisión.

**🔴 Blocker (encontrado y corregido en esta revisión)** —
`visual_pattern_service.py`, `get_implemented_premium_patterns()`: la rama que
lee `db` directamente no tenía el mismo `try/except` que protege la rama de
fallback (`get_system_config()`), contradiciendo la promesa del propio docstring
("nunca rompe el flujo ante config ausente o corrupta") — un error de sesión
(transacción abortada, etc.) se habría propagado sin control en el path premium.
Envuelto en `try/except Exception`, con test de regresión
(`test_broken_db_session_falls_back_without_raising`). Suite re-corrida tras el
fix: sigue en 695 passed / 1 (preexistente).

**🟡 Suggestions (no bloquean)**
- `GRAMMAR_TO_ARTISTIC_PDF` está marcado explícitamente como "pendiente de
  validación visual" en su propio comentario — correcto per spec, pero recordar
  que la tarea de QA visual (más abajo) debe confirmarlo antes de considerar el
  mapeo definitivo, no solo "correcto porque compila".
- `import json as _json` / imports de `models` y de `SLUG_ALIASES` dentro de
  función en vez de al tope del archivo: consistente con el estilo lazy-import
  ya usado en `artistic_pdf_service.py` (`_resolve_asset_path`) — no es una
  desviación, se documenta solo para que quede explícito que fue deliberado.

**Alineación con el cierre del Arquitecto**: confirmado — `GRAMMAR_TO_ARTISTIC_PDF`
es constante en código (decisión 4), `implemented_premium_patterns` vive en
`system_configs` (decisión de Luis), ningún `prompt_*` fue tocado (correcto,
esas tareas vienen después), ninguna llamada LLM nueva (N/A para estas 2 tareas).

**🟢 Veredicto: Aprobado.** Listo para QA visual (la tarea ya definida en el
desglose de PM) y, en paralelo, para que Backend Dev continúe con
`deck_brief_service.build_deck_brief()` (siguiente tarea en la cadena de
dependencias).

### Nota de notificación

`notify.sh` no existe todavía en este repo (`.claude/scripts/` está vacío) —
solo la skill `notify.md` documentando el setup. No se envió Telegram; queda
pendiente si Luis quiere activarlo, pero no bloquea el arranque de las tareas.

## References

- Código existente:
  - `backend/services/generation/content_service.py` — `synthesize_presentation_outline` (Steps 1-5, líneas 132-326)
  - `backend/services/generation/art_director_service.py` — inyección de `art_direction_note` (líneas 139-172)
  - `backend/agents/narrator.py` — `NarratorTool` (cohesión de texto, Step 4.5)
  - `backend/services/ingestion/artistic_essence_service.py` — extracción de `BrandArtisticEssence`
  - `backend/services/ingestion/brand_composition_dna.py` — `GRAMMAR_GEOMETRIES`, `infer_grammar_type`
  - `backend/services/rendering/painter_bridge.py` — `GRAMMAR_TO_PAINTER`, `_patch_dna_for_painter` (dónde `design_gestures` queda muerto)
  - `backend/services/rendering/painter.py` — métodos `paint_*` reales (confirmado: sin lectura de `design_gestures`)
  - `backend/services/ingestion/visual_pattern_service.py` — `SUPPORTED_PATTERN_TYPES`, `normalize_executable_patterns`
  - `backend/templates/premium_pdf.html` — ramas reales por `pattern_type` (líneas 338-442)
  - `backend/services/rendering/premium_visual_agent.py` — `_choose_pattern`, `_vision_adjust_loop`
  - `backend/agents/render_agent.py:103` — punto donde `layout_type` crudo entra a `pdf_base.html` sin traducir
  - `backend/templates/pdf_base.html:118-129` — las 4 ramas reales + fallback `artistic_split`
  - `backend/services/ingestion/brand_composition_dna.py:265-280` — `SLUG_ALIASES` (aliases de `grammar_type` a cubrir en el mapeo)
  - `frontend/src/app/pages/generator/generator.component.ts:37-38` — default `selectedFormat='pptx'`, `selectedTier='free'`
  - `backend/utils/seed.py` — convención de versionado de prompts
- Conversación de diagnóstico con Arquitecto/Analista/AI Architect: 2026-09-09
  (auditoría de flujo de esencia artística + investigación externa sobre
  coherencia narrativa/diseño en generación de decks con LLM).
- Investigación externa citada en el diagnóstico: ArcDeck (arxiv 2604.11969),
  DECKBench (arxiv 2602.13318), "Design First, Code Later" (arxiv 2605.26451).
