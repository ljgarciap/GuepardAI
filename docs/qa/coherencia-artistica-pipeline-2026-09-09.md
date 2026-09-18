# QA Report: Coherencia Artística del Pipeline — Tasks 1 y 2

**Feature**: docs/specs/coherencia-artistica-pipeline.md
**Date**: 2026-09-09
**Tested by**: QA Agent
**Scope de esta corrida**: solo las 2 tareas de Backend Dev ya implementadas y
aprobadas por Senior Reviewer — "Mover `IMPLEMENTED_PREMIUM_PATTERNS` a
`system_configs`" y "Traducir `grammar_type` → `layout` real en el path PDF
legacy". El resto del desglose de PM (`deck_brief_service`, wiring a
Architect/Outline/Narrator, seeds de prompts, validación AI Architect, QA del
path premium/PPTX) **sigue pendiente** — este reporte no cierra el spec
completo, solo valida lo que existe hoy en el código.

## Paso 2 — Tests automatizados

```
pytest --cov=agents --cov=services --cov=providers tests/
695 passed, 1 failed in ~91s
```

El único fallo (`test_template_merge_history.py::TestTemplateMergeHistoryTenantScoping::test_status_null_brand_id_still_rejects_non_owner`)
es preexistente — confirmado con `git stash` contra `master` sin este cambio,
falla igual. No relacionado con esta feature, no bloquea.

Tests nuevos de esta feature, todos pasando: `test_visual_pattern_service.py` (8),
`test_artistic_pdf_legacy_layout.py` (29), `test_seed_configs.py` (3).

## Paso 3 — Validación manual contra criterios de aceptación

| Criterio (spec) | Input | Esperado | Actual | Resultado |
|---|---|---|---|---|
| `implemented_premium_patterns` existe en `system_configs`, seedeada en `utils/seed.py` | `seed_data()` corrido contra BD fresca | key presente con default `["full_bleed_hero","data_cards_brand_grid","editorial_split"]` | Confirmado en log de seed (`[Seed] Inserted: implemented_premium_patterns`) durante la corrida de la suite | ✅ |
| `normalize_executable_patterns()` descarta `pattern_type` reconocidos pero no implementados | `{"executable_visual_patterns":[{"pattern_type":"object_as_letter"},{"pattern_type":"full_bleed_hero"}]}` | solo sobrevive `full_bleed_hero` | Confirmado (`test_recognized_but_unimplemented_pattern_type_is_dropped`) | ✅ |
| `render_agent.py` traduce `grammar_type` a uno de los 5 `layout` reales, no lo pasa crudo | Los 10 `grammar_type` canónicos + 14 aliases de `SLUG_ALIASES` | todos resuelven a `{hero, data_grid, quote, pillars, split}` | Confirmado por test parametrizado (37 casos) | ✅ |
| **Verificación visual real** (no mockeada) del path legacy — el layout resultante es visualmente distinto según el `grammar_type`, no todos colapsan a `artistic_split` | PDF real (Playwright, sin mocks) con un slide por cada familia: `cover_hero`, `executive_quote`, `data_grid_cards`, `two_column`, `strategic_split` | 5 layouts visualmente distintos | **Confirmado** — ver capturas abajo. Antes del fix, los 5 habrían producido la misma página (`artistic_split.html`, el fallback de `pdf_base.html`) | ✅ |

### Evidencia visual (corrida real, Chromium vía Playwright)

Script: `scratchpad/qa_legacy_pdf/render_qa.py` (usa `resolve_legacy_pdf_layout()`
— la misma función que `render_agent.py` llama en producción — sobre los 5
`grammar_type` de prueba, y genera el PDF con `artistic_pdf_service.generate_pdf()`
sin ningún mock).

| grammar_type | layout resuelto | Resultado visual |
|---|---|---|
| `cover_hero` | `hero` | Portada oscura a sangre completa, título grande centrado, bloque "prepared for" |
| `executive_quote` | `quote` | Cita centrada en itálica sobre degradado, comillas decorativas grandes |
| `data_grid_cards` | `data_grid` | Fondo claro, header con regla de acento y etiqueta de sección — estructura de grid (vacía en esta prueba porque no se pasaron `metrics`, esperado: el Redactor sí los puebla en producción) |
| `two_column` | `pillars` | Dos tarjetas redondeadas lado a lado, cada una con su propio ícono/bullet |
| `strategic_split` | `split` (default) | Panel izquierdo/derecho clásico con pill de sección, título y bullets |

Las 5 páginas son estructuralmente distintas entre sí (fondo claro vs. oscuro,
una vs. dos columnas, centrado vs. split, con/sin decoración de cita) — el
hallazgo original de la spec (9 de 10 `grammar_type` colapsando a
`artistic_split`) queda cerrado para estos 5 casos representativos.

Nota no bloqueante: la página `data_grid` queda visualmente vacía porque el
script de prueba pasó `bullets` genéricos en vez de `metrics` — la plantilla
`artistic_data_grid.html` espera datos estructurados que el Redactor sí produce
en el pipeline real (`content_json.metric`/`metrics`). No es un defecto del fix
de layout-routing que se está probando aquí.

## Paso 4 — Edge cases

| Caso | Resultado |
|---|---|
| `grammar_type` no reconocido (`"some_future_grammar_type_v99"`) | Cae a `split` sin excepción (`test_unknown_grammar_type_falls_back_to_split`) |
| `grammar_type` `None` / cadena vacía | Cae a `split` sin excepción (`test_falsy_input_falls_back_to_split_without_raising`) |
| `grammar_type` como lista (`["cover_hero"]`) | Usa el primer elemento — mismo guard que `get_layout_geometry()` (`test_list_input_uses_first_element`) |
| Config `implemented_premium_patterns` corrupta (no-JSON) | Cae al default duro (`test_corrupt_config_falls_back_to_hard_default`) |
| Sesión `db` rota (excepción en `.query()`) | Cae al default duro sin propagar — hallazgo del Senior Reviewer, corregido y cubierto (`test_broken_db_session_falls_back_without_raising`) |
| Todos los `executable_visual_patterns` del Vision LLM son no-implementados | Lista vacía, sin excepción (`test_all_unimplemented_yields_empty_list_not_exception`) — `PremiumVisualAgent._choose_pattern()` ya degrada a `editorial_split` en ese caso |

## Veredicto

**✅ Aprobado** para las 2 tareas evaluadas — implementación coincide con el
spec, el hallazgo de implementabilidad que originó la spec está genuinamente
resuelto para el path legacy PDF (confirmado visualmente, no solo por tests),
sin regresiones en la suite completa.

**El spec como conjunto sigue abierto**: faltan `deck_brief_service`, el wiring
a Prompt Architect/Outline Generator/Narrator, el seed de los 3 prompts nuevos,
la validación en vivo del AI Architect, y la QA visual del path premium (que sí
depende de esas piezas). No se puede dar por cerrada la spec completa todavía.
