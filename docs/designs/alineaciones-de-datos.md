# Design: Alineaciones de Datos Automáticas en el Arranque

**Date**: 2026-06-11
**Architect**: aprobado
**Spec**: `docs/specs/alineaciones-de-datos.md`
**Status**: Approved — listo para desglose del PM (implementación en la siguiente iteración)

## Decisiones de diseño

### Modelo (`models.py`)

```python
class DataAlignment(Base):
    __tablename__ = "data_alignments"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(120), unique=True, index=True)  # ej. visual_profile_backfill_v1
    status      = Column(String(20), default="pending")  # pending | running | done | failed
    detail      = Column(Text, nullable=True)            # resumen truncado (procesados/fallidos/error)
    started_at  = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
```
Tabla nueva → `create_all` la crea; no requiere ALTER.

### Servicio (`services/core/data_alignment_service.py` — nuevo)

- `ALIGNMENT_REGISTRY: dict[str, Callable[[], dict]]` — registro declarativo.
  v1: `{"visual_profile_backfill_v1": _run_visual_profile_backfill}` que llama
  `utils.backfill_visual_profiles.backfill(process_all=True)` y devuelve su summary.
- `dispatch_pending_alignments()` — llamada desde el arranque del API:
  1. Lee `auto_data_alignment_enabled` (patrón SystemConfig; default `"true"`).
     Si es false → log de pendientes y return.
  2. Por cada nombre del registry: inserta fila `pending` si no existe
     (idempotente). Si la fila está en `done` o `running` → skip. Si `pending`
     o `failed` → encolar.
  3. Encolado en try/except amplio: cualquier fallo (Redis caído) → warning y
     continúa. El boot jamás se bloquea.
- `run_alignment(name)` — ejecutada por la tarea Celery:
  1. Claim atómico: `UPDATE data_alignments SET status='running', started_at=now()
     WHERE name=:n AND status IN ('pending','failed')` — si `rowcount == 0`,
     otra réplica la tomó → return (protección de doble ejecución).
  2. Ejecuta el callable del registry; nombre no registrado → marca `failed`
     con detail informativo (caso de alineación huérfana de versión anterior).
  3. `done`/`failed` + `detail` (truncado a 2000 chars) + `finished_at` +
     `log_performance_metric("data_alignment.<name>.complete|failed", ...)`.

### Tarea Celery (`tasks.py`)

Wrapper fino (patrón del proyecto — sin lógica en el body):
```python
@celery_app.task(name="tasks.run_data_alignment")
def task_run_data_alignment(name: str):
    from services.core.data_alignment_service import run_alignment
    return run_alignment(name)
```

### Arranque (`main.py`)

Después de `Base.metadata.create_all` + `seed_data()`:
```python
try:
    from services.core.data_alignment_service import dispatch_pending_alignments
    dispatch_pending_alignments()
except Exception as e:
    print(f"  [System] Warning: data alignment dispatch failed: {e}")
```

### Refactor mínimo del backfill

`utils/backfill_visual_profiles.py` ya expone `backfill(brand_id, process_all,
force) -> dict` con summary — se reutiliza tal cual. El `__main__` CLI no cambia.

### Config (`seed.py`)

Clave nueva: `auto_data_alignment_enabled` = `"true"`.

## Restricciones (no negociables)

- El dispatch NUNCA bloquea ni rompe el arranque (try/except total).
- La tarea Celery es un wrapper fino; la lógica vive en el servicio.
- Claim de ejecución atómico vía UPDATE condicional (no SELECT-then-UPDATE).
- Las alineaciones deben ser idempotentes por contrato — es requisito para
  registrar una nueva (documentarlo en el propio módulo del registry).
- Config runtime vía `system_configs` seedeada; nada hardcodeado.
- Tests con mocking global (la alineación v1 se testea con Vision mockeado).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Gasto automático de tokens al arrancar un server con librería grande | Guard `auto_data_alignment_enabled` + la alineación solo procesa NULL (converge a 0 trabajo) |
| Alineación colgada deja estado `running` para siempre | Aceptado en v1 (volumen bajo); operador puede resetear la fila a `failed` para reintentar; anotar como mejora futura (timeout/heartbeat) |
| Dos réplicas encolan a la vez | El claim atómico hace inocuo el doble encolado: la segunda tarea no obtiene el claim |
