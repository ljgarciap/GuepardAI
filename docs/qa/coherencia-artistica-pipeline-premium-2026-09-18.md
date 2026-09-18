# QA Report: Coherencia Artística del Pipeline — Path Premium (PDF)

**Feature**: docs/specs/coherencia-artistica-pipeline.md
**Date**: 2026-09-18
**Tested by**: QA Agent
**Scope de esta corrida**: la mitad "PDF premium" que quedaba pendiente en
`docs/qa/coherencia-artistica-pipeline-2026-09-09.md` (la mitad "PDF legacy" ya estaba
✅ aprobada en ese reporte). Cierra el desglose de PM completo — con esto, las 8 tareas
de la spec quedan hechas.

## Hallazgo encontrado durante esta QA (corregido antes de continuar)

Antes de poder afirmar "cada `slide.pattern_type` persistido pertenece a
`implemented_premium_patterns`", se auditó **todo** el camino que escribe
`pattern_type`, no solo el de ingestión ya cubierto por `test_visual_pattern_service.py`
(Task 1). Se encontró un segundo punto de escritura sin el mismo filtro:

`PremiumVisualAgent._vision_adjust_loop()` (`services/rendering/premium_visual_agent.py`)
hace una llamada aparte al Vision LLM (canal premium dedicado, Claude Sonnet) para
"mejorar" la asignación de patrones de Iteración 1, y aplicaba
`adj.get("pattern_type")` a la slide **sin volver a pasar por
`get_implemented_premium_patterns()`**. El prompt le pide al modelo elegir solo de la
lista de patrones disponibles (ya filtrada), pero nada en código lo garantizaba — un
valor alucinado o reconocido-pero-no-implementado (p. ej. `object_as_letter`) se
escribía igual, y `premium_pdf.html` lo colapsaba en silencio a `editorial_split` al
renderizar. Es el mismo bug que motivó la spec, reintroducido en un segundo punto que
el Task 1 no cubría.

**Fix aplicado** (`services/rendering/premium_visual_agent.py`): el ajuste se descarta
individualmente si su `pattern_type` no está en `implemented_premium_patterns` — la
slide conserva su `pattern_type` correcto de Iteración 1, nunca se invalida el loop
completo. 5 tests de regresión nuevos:
`tests/test_premium_visual_agent_vision_adjust_whitelist.py`.

## Paso 2 — Tests automatizados

```
pytest --cov=agents --cov=services --cov=providers tests/
729 passed, 1 failed in ~111s
```

El único fallo (`test_template_merge_history.py::...test_status_null_brand_id_still_rejects_non_owner`)
sigue siendo el mismo preexistente y ajeno documentado en el reporte del 2026-09-09 (no
relacionado, no se tocó). Los 5 tests nuevos de esta QA pasan, más los ya existentes de
esta spec (`test_visual_pattern_service.py`, `test_artistic_pdf_legacy_layout.py`,
`test_seed_configs.py`, `test_deck_brief_service.py`,
`test_content_service_deck_brief.py`, `test_seed_prompts_deck_brief.py`).

## Paso 3 — Validación manual contra criterios de aceptación

Corrida real (sin mocks — DB local, Claude Sonnet real vía el canal premium dedicado,
Playwright real). Script: `scratchpad/qa_premium_pdf/render_qa.py` (no commiteado,
mismo criterio que el script de la QA del path legacy).

| Criterio (spec) | Input | Esperado | Actual | Resultado |
|---|---|---|---|---|
| **Verificación visual real, tier=premium**: cada `slide.pattern_type` persistido pertenece a `implemented_premium_patterns` | Deck de 3 slides real (cover, métricas, cierre) a través de `PremiumVisualAgent.render_pdf()` completo — Iteración 1 + Iteración 2 (Claude Sonnet real) + render Playwright real | los 3 `pattern_type` finales ∈ `{full_bleed_hero, data_cards_brand_grid, editorial_split}` | Confirmado — `full_bleed_hero`, `data_cards_brand_grid`, `editorial_split` (ver `ArtDirectorDecision.decision_type="premium_visual_eval"` persistido) | ✅ |
| Los patrones implementados se ven visualmente distintos entre sí | Mismo deck de 3 slides | cover a sangre completa vs. grid de métricas vs. split editorial, claramente diferentes | Confirmado — capturas revisadas: cover con overlay oscuro a sangre completa y bloque de acento dorado; métricas con 3 tarjetas verticales de borde superior dorado mostrando `34%`, `3`, texto libre | ✅ |
| **Regresión del hallazgo de esta QA**: un `pattern_type` no implementado escrito por Iteración 2 no debe sobrevivir ni afectar el render | Slide de métricas forzada a `pattern_type="object_as_letter"` (simulando el comportamiento pre-fix) vs. la misma slide con el fix aplicado | antes: colapsa a `editorial_split` genérico, se pierden las tarjetas de métricas; después: se mantiene `data_cards_brand_grid`, tarjetas de métricas intactas | Confirmado visualmente — capturas `partB_before_slide2.png` (bullets sueltos sobre panel de color sólido, sin tarjetas ni cifra `34%` destacada) vs. `partB_after_slide2.png` (tarjetas con `34%`/`3`/texto, idéntico al render correcto de Iteración 1) | ✅ |

### Evidencia visual (corrida real, Chromium vía Playwright + PyMuPDF para captura)

- `partA_real_slide1.png` — Cover (`full_bleed_hero`): fondo azul-marino a sangre
  completa con degradado sutil, franja de acento dorado a la izquierda, título en
  serif blanco grande, subtítulo, footer con logo y disclaimer.
- `partA_real_slide2.png` — Métricas (`data_cards_brand_grid`): fondo claro, 3
  tarjetas con regla superior dorada, cifra destacada `34%` en azul-marino y label,
  cifra `3`/"New Logos", tercera tarjeta con texto libre.
- `partA_real_slide3.png` — Cierre (`editorial_split`): panel izquierdo oscuro /
  derecho claro, título y bullets de próximos pasos.
- `partB_before_slide2.png` vs. `partB_after_slide2.png` — mismo contenido de la
  slide de métricas; "before" (bug reproducido) pierde las tarjetas y la cifra
  destacada por completo, "after" (fix aplicado) las conserva. Diferencia
  perceptible a simple vista, no solo un cambio de metadata en el JSON.

## Paso 4 — Edge cases

| Caso | Resultado |
|---|---|
| Iteración 2 sugiere un `pattern_type` implementado para un `slide_number` inexistente | Ignorado sin excepción (`test_every_persisted_pattern_type_belongs_to_implemented_patterns`) |
| Iteración 2 sugiere un `pattern_type` fuera de `SUPPORTED_PATTERN_TYPES` (typo/alucinación total) | Ignorado — el filtro compara contra `implemented_premium_patterns`, cualquier valor ausente de ese set se descarta igual, sin necesidad de una segunda validación contra `SUPPORTED_PATTERN_TYPES` |
| `implemented_premium_patterns` se angosta en runtime (se retira `data_cards_brand_grid`) | Iteración 2 respeta el nuevo límite igual que Iteración 1 — misma fuente de verdad, sin caché local (`test_narrower_runtime_whitelist_also_blocks_a_normally_implemented_pattern`) |
| Mezcla de ajustes válidos e inválidos en la misma respuesta del LLM | Solo los válidos se aplican; los inválidos se descartan individualmente sin afectar al resto (`test_mixed_valid_and_invalid_adjustments_only_valid_ones_apply`) |
| Vision Adjust Loop falla por completo (excepción de red, JSON inválido, etc.) | Comportamiento preexistente sin cambios — `render_pdf()` atrapa la excepción y sigue con los `pattern_type` de Iteración 1 |

## Veredicto

**✅ Aprobado.** La mitad "PDF premium" que quedaba pendiente del desglose de QA queda
cerrada, con un hallazgo real encontrado y corregido en el proceso (no solo validación
pasiva). Con este reporte más el de 2026-09-09 (path legacy), **los dos criterios de
verificación visual de la spec están satisfechos** — PPTX no requería cambios de esta
iteración (el `grammar_type`→`GammaPainter` ya tenía cobertura completa, ver Auditoría
de implementabilidad de la spec).

**Spec completa**: las 8 tareas del desglose de PM están ✅ Done. Queda solo la tarea
de Tech Writer (sincronizar `CLAUDE.md`, pasar `Status` de `Approved` a `Done`).
