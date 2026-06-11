# Tasks: Alineaciones de Datos Automáticas en el Arranque

**Date**: 2026-06-11
**PM**: desglose del diseño `docs/designs/alineaciones-de-datos.md`
**Spec**: `docs/specs/alineaciones-de-datos.md`
**Status**: Ready — arranca cuando Luis abra la iteración
**Rama**: `feature/data-alignments`

## Orden de ejecución

```
A1 (modelo + servicio + registry) ──▶ A2 (tarea Celery + dispatch en arranque) ──▶ A4 (QA)
A3 (config seed + guard) — paralela a A1
A5 (Tech Writer) — en paralelo, cierra al final
```

---

### A1 — Modelo, servicio y registry con la alineación v1

**Agent**: Backend Dev · **Depends on**: none · **Estimación**: 3 h

`DataAlignment` en `models.py`; `services/core/data_alignment_service.py` con
`ALIGNMENT_REGISTRY`, `dispatch_pending_alignments()` y `run_alignment()`
(claim atómico vía UPDATE condicional, detail truncado, métricas). Registrar
`visual_profile_backfill_v1` reutilizando `backfill(process_all=True)`.

**Files**: `backend/models.py`, `backend/services/core/data_alignment_service.py` (nuevo)
**Acceptance**: criterios 1, 2, 4, 5 y 9 de la spec; contrato de idempotencia
documentado en el docstring del registry.

---

### A2 — Tarea Celery y dispatch en el arranque

**Agent**: Backend Dev · **Depends on**: A1 · **Estimación**: 2 h

`task_run_data_alignment` en `tasks.py` (wrapper fino); llamada a
`dispatch_pending_alignments()` en `main.py` tras `seed_data()`, envuelta en
try/except que jamás bloquea el boot.

**Files**: `backend/tasks.py`, `backend/main.py`
**Acceptance**: criterios 3 y 8 de la spec; con Redis caído el API arranca y
loggea warning.

---

### A3 — Config guard

**Agent**: Backend Dev · **Depends on**: none (paralela a A1) · **Estimación**: 1 h

Clave `auto_data_alignment_enabled` = `"true"` en `seed.py`; lectura en el
dispatch con default seguro; en `"false"` solo loggea pendientes.

**Files**: `backend/utils/seed.py`, `backend/services/core/data_alignment_service.py`
**Acceptance**: criterio 6 de la spec.

---

### A4 — Tests

**Agent**: QA · **Depends on**: A1, A2, A3 · **Estimación**: 3 h

`backend/tests/test_data_alignments.py`: transición de estados; `done` no se
reencola; `failed` se reintenta; claim atómico (segunda llamada a
`run_alignment` con estado `running` no ejecuta); guard apagado; fallo de
encolado no rompe el dispatch; alineación huérfana no registrada → `failed`
informativo; alineación v1 con Vision mockeado marca `done` con summary.

**Files**: `backend/tests/test_data_alignments.py` (nuevo)
**Acceptance**: criterio 11 de la spec; suite completa en verde.
**Nota de entorno** (lección 2026-06-10): runs largos siempre con salida
incremental visible y monitor; cuidado con sesiones sin cerrar — el claim usa
UPDATE condicional precisamente para no depender de estado de sesión.

---

### A5 — Documentación

**Agent**: Tech Writer · **Depends on**: none · **Estimación**: 1 h

- `docs/operations/post-deploy-alignment.md`: reescribir la intro — la capa de
  datos pasa a ser automática; el doc queda como registro/auditoría y para el
  caso `auto_data_alignment_enabled=false`. Marcar el backfill de la Iteración 1
  como "cubierto por `visual_profile_backfill_v1` al desplegar esta feature".
- `CLAUDE.md`: añadir la capa de datos a la tabla de alineaciones automáticas
  del arranque + cómo registrar una alineación nueva.
- Estado de la spec al cierre.

**Files**: `docs/operations/post-deploy-alignment.md`, `GuepardAI/CLAUDE.md`,
`docs/specs/alineaciones-de-datos.md`

---

## Resumen

| Agente | Tareas | Horas est. |
|---|---|---|
| Backend Dev | A1, A2, A3 | 6 h |
| QA | A4 | 3 h |
| Tech Writer | A5 | 1 h |

**Beneficio inmediato al desplegar**: el backfill pendiente en EC2 se ejecuta
solo (la alineación v1 detecta los assets con `visual_profile IS NULL` y
converge), eliminando el último pendiente de la iteración anterior.
