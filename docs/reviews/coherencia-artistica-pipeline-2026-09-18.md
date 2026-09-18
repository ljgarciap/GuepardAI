# Review: Coherencia Artística del Pipeline (Deck Design Brief)

**Date**: 2026-09-18
**Reviewer**: Senior Reviewer
**Decision**: ✅ Approved
**Commit reviewed**: `3663943` — `feat(generation): add Deck Design Brief and fix layout-routing gaps`
**Spec**: `docs/specs/coherencia-artistica-pipeline.md`

## Scope

Este commit trae de una sola vez las 8 tareas del desglose de PM. La revisión del
2026-09-09 (ver sección "Revisión del Senior Reviewer" dentro del spec) ya cubrió las
2 primeras tareas (whitelist a `system_configs` + fix `grammar_type`→`layout` legacy,
695 tests) contra el estado en disco de ese momento — nada de eso había llegado a
`master` todavía. Esta revisión relee esas 2 tareas contra el diff final y cubre por
primera vez el resto: `deck_brief_service.py`, el wiring a Architect/Outline/Narrator,
los 3 prompts nuevos, el ADR del AI Architect, y el fix de
`PremiumVisualAgent._vision_adjust_loop` que salió de la QA visual de hoy.

## Paso 2 — Tests

```
pytest --cov=agents --cov=services --cov=providers tests/
729 passed, 1 failed in ~111s
```

El único fallo (`test_template_merge_history.py::...test_status_null_brand_id_still_rejects_non_owner`)
es preexistente y ajeno — confirmado contra `master` sin este cambio en la sesión de
implementación original, no relacionado con esta feature.

## Findings

### 🔴 Blockers
Ninguno.

### 🟡 Suggestions (no bloquean)

1. **`content_service.py:106` (`_synthesize_monolithic`)** — el fallback monolítico
   (solo se activa si ni `prompt_content_outline_v1/v2/v3` está seedeado, caso que no
   ocurre en este código base) llama `_build_manifest(db, job_id)` sin `deck_brief` —
   el manifest resultante queda con `deck_brief=None`. Correcto por default del schema,
   pero si algún día ese path deja de ser puramente teórico, conviene pasarle el brief
   también por consistencia.
2. **Hallazgo ya documentado por el propio AI Architect, no de esta revisión** —
   `docs/ai/contracts/deck-design-brief-adr.md` y `CLAUDE.md` ya dejan constancia de
   que `specialization="design"` no enruta a Anthropic en `generate_json`
   (`resolve_provider()` es código muerto para ese call path). No es una regresión de
   este commit — el Narrator ya llamaba así desde `v1` — pero queda abierta la decisión
   de si el Arquitecto quiere que se conecte o se elimine `resolve_provider()`.

### 🟢 Well done

- **El hallazgo de esta misma iteración de QA es el ejemplo correcto de por qué existe
  este spec**: `PremiumVisualAgent._vision_adjust_loop` escribía `pattern_type` desde
  una llamada LLM aparte (Iteración 2) sin pasar por la misma whitelist que ya protegía
  la ingestión (`normalize_executable_patterns`, Task 1). Se encontró auditando el
  camino completo de escritura, no solo el punto que la spec original señalaba, se
  corrigió con el mismo criterio ("descartar el ajuste individual, nunca invalidar el
  loop completo") ya establecido en el resto del código, y se cubrió con 5 tests que
  reproducen exactamente el escenario adversarial (incluyendo un `slide_number`
  inexistente y una mezcla de ajustes válidos/inválidos en la misma respuesta).
- **Decisiones del Arquitecto respetadas al pie de la letra**: `deck_brief_service.py`
  no es un `BaseAgentTool` (función plana, sin `log_decision` propio — decisión #1);
  la trazabilidad se agregó extendiendo el `metadata` dict que `GenerateTextTool.run()`
  ya escribía, sin duplicar el patrón de auditoría (decisión #2); `specialization` de
  Architect/Outline se mantiene en `"general"` (decisión #3); `GRAMMAR_TO_ARTISTIC_PDF`
  quedó como constante de código, no en `system_configs` (decisión #4).
- **Ningún `prompt_*` existente se editó in-place** — `_v3`/`v2` se agregaron como
  claves nuevas con fallback explícito a la versión anterior, siguiendo la convención
  del proyecto (`utils/seed.py`).
- **Validación real, no solo mocks**: el ADR del AI Architect y ambos reportes de QA
  (`docs/qa/`) corren contra proveedores y Playwright reales, no solo contra
  `mock_llm_calls` — coherente con la exigencia explícita de la spec ("QA manual local,
  una corrida real, no mockeada").
- **Tests nuevos son de comportamiento, no de implementación**: cubren edge cases reales
  de la spec (marca sin esencia, texto largo truncado, alias que no matchea, mezcla de
  ajustes válidos/inválidos) en vez de solo perseguir cobertura de líneas.

## Alineación con el cierre del Arquitecto

Confirmado punto por punto contra las 5 decisiones fijadas en
`docs/specs/coherencia-artistica-pipeline.md` ("Cierre del Arquitecto") — sin
desviaciones.

## Next steps

Ready for QA — ya ejecutada y aprobada (`docs/qa/coherencia-artistica-pipeline-2026-09-09.md`,
`docs/qa/coherencia-artistica-pipeline-premium-2026-09-18.md`). No queda trabajo de
código pendiente en esta spec; el pendiente operativo es exclusivamente el deploy a EC2
(bloqueado por la IP de la instancia, no relacionado con este código).
