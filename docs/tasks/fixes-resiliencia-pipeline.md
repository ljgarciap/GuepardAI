# Tasks: Fixes de Resiliencia del Pipeline de Diseño

**Date**: 2026-06-10
**PM**: desglose del diseño `docs/designs/fixes-resiliencia-pipeline.md`
**Spec**: `docs/specs/fixes-resiliencia-pipeline.md`
**Status**: R1-R6 completadas — suite 65/65 en verde (2026-06-10)

## Orden de ejecución

```
R1 (F3, sin dependencias — el más corto, desbloquea el área de FASE E)
R2 (F2, toca la misma zona que R1 → secuencial tras R1)
R3 (F1, orquestador + tool + servicio — paralelo a R1/R2)
R4 (F4, modelo + orquestador + endpoint — paralelo a R1/R2)
R5 (QA) después de R1-R4
R6 (Tech Writer + ops doc) en paralelo
```

---

### R1 — Fix bug bullet_icon (F3)

**Agent**: Backend Dev · **Depends on**: none · **Estimación**: 1 h

Unificar `current_planning` en una sola copia (`dict(slide.planning_json or {})`)
al inicio del bloque de persistencia de FASE E y eliminar la re-lectura que
descarta `bullet_icon`.

**Files**: `backend/services/generation/art_director_service.py`
**Acceptance**: criterios F3 de la spec — `accent_asset_id` válido →
`planning_json.bullet_icon` persiste junto a `planning_json.art_director`.

---

### R2 — Revalidación tras layout_override (F2)

**Agent**: Backend Dev · **Depends on**: R1 (misma zona de código) · **Estimación**: 2-3 h

Helper `_resolve_asset_dims(asset)` (extrae el bloque BD→PIL ya duplicado),
revalidación del override con las reglas de Fase B (resolución + aspect via
`compute_aspect_fit`), descarte trazado en
`planning_json.art_director.layout_override_rejected`.

**Files**: `backend/services/generation/art_director_service.py`
**Acceptance**: criterios F2 de la spec — override a hi-res con asset que no
califica se descarta y se traza; override válido se aplica como hoy.

---

### R3 — Feedback de QA en retries (F1)

**Agent**: Backend Dev · **Depends on**: none (paralelo a R1/R2; coordinar merge en art_director_service) · **Estimación**: 2-3 h

Variable `qa_feedback` en `run_design_and_render()` (violations del
determinista / reasoning del juez, el más reciente gana), campo opcional en
`ComposeLayoutArgs`, parámetro en `plan_presentation_design` con truncado por
`qa_feedback_max_chars` (nueva clave seedeada, default 1500) y anexo a
`art_direction_note`.

**Files**: `backend/agents/orchestrator.py`, `backend/agents/architect.py`,
`backend/services/generation/art_director_service.py`, `backend/utils/seed.py`
**Acceptance**: criterios F1 de la spec — feedback visible en `prompt_used`
del retry; primer intento sin cambios; truncado aplicado.

---

### R4 — Flag qa_forced (F4)

**Agent**: Backend Dev · **Depends on**: none · **Estimación**: 1-2 h

Columna `qa_forced` (Integer 0/1) en `GenerationJob`, ALTER idempotente en
`database.py`, set en la rama de aceptación forzada del orquestador, campo en
la respuesta de `get_generation_status`.

**Files**: `backend/models.py`, `backend/database.py`,
`backend/agents/orchestrator.py`, `backend/main.py`
**Acceptance**: criterios F4 de la spec — job forzado → `qa_forced=1` en BD y
`true` en el endpoint; job aprobado → `0`/`false`.

---

### R5 — Tests del lote

**Agent**: QA · **Depends on**: R1-R4 · **Estimación**: 2-3 h

- F1: retry con determinista fallando → prompt del segundo intento contiene
  las violations; retry con juez LLM → contiene el reasoning; primer intento
  sin bloque de feedback; truncado.
- F2: override hi-res con asset low-res → descartado y trazado; override
  válido → aplicado; sin asset → aplicado sin revalidar.
- F3: accent_id → bullet_icon persistido con art_director intacto.
- F4: forzado → flag 1 + endpoint true; aprobado → 0/false.

**Files**: `backend/tests/test_pipeline_resilience.py` (nuevo)
**Acceptance**: suite completa en verde.

---

### R6 — Documentación

**Agent**: Tech Writer · **Depends on**: none (cierra al mergear) · **Estimación**: 1 h

CLAUDE.md (anti-pattern del override sin revalidar pasa a estar cubierto;
mención de `qa_forced` en el contexto del Analyst), entrada en
`docs/operations/post-deploy-alignment.md` (la columna `qa_forced` y la clave
`qa_feedback_max_chars` se alinean solas al arrancar — registrar que NO hay
comando manual), estados de spec.

**Files**: `GuepardAI/CLAUDE.md`, `docs/operations/post-deploy-alignment.md`,
`docs/specs/fixes-resiliencia-pipeline.md`

---

## Resumen

| Agente | Tareas | Horas est. |
|---|---|---|
| Backend Dev | R1, R2, R3, R4 | 6-9 h |
| QA | R5 | 2-3 h |
| Tech Writer | R6 | 1 h |

**Arranque**: R1 + R3 + R4 en paralelo; R2 tras R1.
