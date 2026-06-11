# Design: Fixes de Resiliencia del Pipeline de Diseño

**Date**: 2026-06-10
**Architect**: aprobado
**Spec**: `docs/specs/fixes-resiliencia-pipeline.md`
**Status**: Approved — listo para desglose del PM

## Decisiones de diseño

### F1 — Feedback de QA en retries

**Flujo del dato**: `run_design_and_render()` → `ComposeLayoutTool` →
`plan_presentation_design()` → prompt del Art Director.

- En `orchestrator.run_design_and_render()`: variable local `qa_feedback: str = None`.
  Al fallar el determinista: `qa_feedback = "Deterministic QA violations: " +
  json.dumps(violations)`. Al rechazar el juez LLM: `qa_feedback = "QA Judge
  rejection (score X): " + reasoning` (serializar dicts con `json.dumps`; el
  más reciente reemplaza al anterior). Se pasa en el siguiente
  `self.compose_layout(job_id=..., is_premium=..., qa_feedback=qa_feedback)`.
- `ComposeLayoutArgs`: nuevo campo `qa_feedback: Optional[str] = Field(None, ...)`.
  `ComposeLayoutTool.run()` lo propaga a `plan_presentation_design`.
- `plan_presentation_design(db, job_id, is_premium=False, qa_feedback=None)`:
  si `qa_feedback` no vacío, truncar a `qa_feedback_max_chars` (nueva clave de
  `system_configs`, default `"1500"`) y anexar a `art_direction_note`:
  `"\n\nPREVIOUS QA REJECTION (MUST ADDRESS IN THIS ATTEMPT): {feedback}"`.
  Sin feedback → prompt idéntico al actual (sin bloque vacío).

### F2 — Revalidación tras layout_override

**Dónde**: `art_director_service.py`, FASE E, inmediatamente después de
`layout_override`.

- Si hay `layout_override` Y `primary_id` resuelto:
  1. Calcular `requires_hi_res_override` y `panel_geo_override` con el slug
     del override (vía `get_layout_geometry`, que ya resuelve aliases y
     desconocidos a `strategic_split`).
  2. Reutilizar las dimensiones ya resueltas del asset (BD o PIL — extraer el
     bloque de resolución de dimensiones a un helper `_resolve_asset_dims(asset)`
     para no duplicarlo por tercera vez).
  3. Reglas (mismas de Fase B): hi-res sin dimensiones → descartar override;
     `width < 1200` para hi-res → descartar; `compute_aspect_fit(...) >
     ASPECT_TOLERANCE` para hi-res → descartar.
  4. Al descartar: `grammar_type` vuelve al del Analista, `slide.layout_slug`
     NO se pisa con el override, y se registra en
     `planning_json.art_director.layout_override_rejected = {"override": slug,
     "reason": "..."}`. Print de log con el patrón `[ArtDirector] OVERRIDE
     REJECTED: ...`.
- Sin `primary_id` → override se aplica sin revalidar (nada que validar).
- No se re-selecciona asset (decisión de spec: no reabrir Fase B).

### F3 — Bug bullet_icon

**Dónde**: `art_director_service.py`, FASE E (persistencia).

- Una sola lectura al inicio del bloque: `current_planning =
  dict(slide.planning_json or {})` (copia → garantiza que SQLAlchemy detecte
  el cambio en la columna JSON al reasignar).
- Eliminar la segunda re-lectura (`current_planning = slide.planning_json or {}`
  bajo el comentario v8.80) que descarta `bullet_icon`.
- `slide.planning_json = current_planning` una sola vez al final del bloque.

### F4 — Flag qa_forced

- `models.GenerationJob`: `qa_forced = Column(Integer, default=0)` (convención
  del proyecto: integer booleans).
- `database.py`: añadir `ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS
  qa_forced INTEGER DEFAULT 0;` al bloque de in-place migrations existente.
- `orchestrator.run_design_and_render()`: en la rama de aceptación forzada
  (`retries > self.MAX_RETRIES`), antes de `qa_passed = True`:
  `job.qa_forced = 1` + commit (ya hay un bloque que actualiza el job ahí).
- `main.py` `get_generation_status()`: añadir `"qa_forced": bool(job.qa_forced)`
  al dict de respuesta.

## Restricciones (no negociables)

- `qa_feedback_max_chars` en `system_configs` vía `seed.py` (clave nueva → el
  seeder la inserta solo; no tocar claves existentes).
- F2 reutiliza `compute_aspect_fit` de `asset_fit.py` — no duplicar la lógica.
- Tests con mocking global de `conftest.py`; los cuatro fixes son testeables
  sin llamadas reales.
- `ComposeLayoutArgs` con campo opcional → callers existentes (orchestrator en
  primer intento, tests) no cambian.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El feedback de QA empuja al LLM a sobre-corregir (cambiar todo el plan) | El bloque se anexa a `art_direction_note`, no reemplaza instrucciones; truncado a 1500 chars |
| Descartar overrides reduce variedad visual | Solo se descartan los que violarían calidad física; trazado en planning_json para medir frecuencia |
| `dict()` superficial en planning_json | Suficiente: solo se mutan claves de primer nivel (`bullet_icon`, `art_director`) |
