# Spec: Alineaciones de Datos Automáticas en el Arranque

**Date**: 2026-06-11
**Requested by**: Luis
**Status**: In Development — implementación completa, suite en verde (76/76); pendiente validación de Luis
**Project**: GuepardAI

## Problem

El arranque del backend alinea automáticamente dos de las tres capas que una
release puede desalinear: el **esquema** (ALTERs idempotentes en `database.py`)
y la **configuración** (`seed.py`). La tercera capa — **datos** — depende de
comandos manuales documentados en `docs/operations/post-deploy-alignment.md`
(ej.: el backfill de `visual_profile` de la Iteración 1, aún pendiente en EC2).

El deploy a producción es automático (push a `master` → EC2), así que cualquier
paso manual olvidado deja producción desalineada en silencio: nada falla, pero
el valor de la release no se materializa. Hoy el único mecanismo de defensa es
la disciplina de leer el doc de operaciones.

## Solution summary

Un registro de **alineaciones de datos** como ciudadanos de primera clase del
arranque, análogo a las migraciones de esquema: cada alineación es una función
idempotente con nombre versionado, registrada en código; una tabla
`data_alignments` lleva el estado (`pending/running/done/failed`); al arrancar,
el backend detecta las pendientes y las **encola como tareas Celery** (nunca
bloqueando el boot). Una clave de configuración permite apagar la ejecución
automática (a diferencia de un ALTER, una alineación puede gastar tokens LLM).
La primera alineación registrada envuelve el backfill de perfiles visuales
existente — al desplegar esta feature, el pendiente de EC2 se resuelve solo.

## Users and roles

- **Backend al arrancar** (API container): detecta y encola alineaciones pendientes.
- **Celery worker**: ejecuta las alineaciones en background.
- **Operador/Luis**: puede consultar el estado en la tabla, deshabilitar la
  ejecución automática vía config, o ejecutar manualmente el script existente
  (que sigue funcionando y comparte la misma lógica e idempotencia).
- Sin cambios de permisos ni de frontend.

## Acceptance criteria

- [ ] Existe el modelo/tabla `data_alignments` (name único, status, started_at,
      finished_at, detail/resumen, created_at) creada vía `create_all`.
- [ ] Existe un registro declarativo en código (dict nombre → callable) donde
      registrar alineaciones; la v1 incluye `visual_profile_backfill_v1`, que
      reutiliza la lógica de `utils/backfill_visual_profiles.py` para todas las
      marcas (solo assets con `visual_profile IS NULL`).
- [ ] Al arrancar el backend: las alineaciones registradas sin fila `done` se
      insertan/encolan como tarea Celery. El boot NUNCA se bloquea: si Redis o
      el encolado fallan, se loggea warning y el arranque continúa.
- [ ] La tarea Celery marca `running` al iniciar y `done`/`failed` al terminar,
      con resumen (procesados/fallidos) en `detail`.
- [ ] Doble-encolado protegido: una alineación en `running` o `done` no se
      vuelve a encolar en arranques subsecuentes; una en `failed` sí se
      reintenta en el siguiente arranque.
- [ ] Clave `auto_data_alignment_enabled` en `system_configs` (seedeada,
      default `"true"`): en `"false"`, el arranque solo loggea las alineaciones
      pendientes sin ejecutarlas.
- [ ] Una alineación que falla parcialmente (ej. 429 de cuota a mitad del
      backfill) queda `failed` con el conteo parcial; re-ejecutarla es seguro
      (la idempotencia del backfill ya lo garantiza: solo procesa NULL).
- [ ] `log_performance_metric()` registra inicio/fin de cada alineación
      (`data_alignment.<name>.complete` / `.failed`).
- [ ] El script manual `utils/backfill_visual_profiles.py` sigue funcionando
      sin cambios de interfaz (comparte la función núcleo).
- [ ] Tests: registro y transición de estados, no-reencolado de `done`,
      reintento de `failed`, guard de config apagado, y fallo de encolado sin
      romper el arranque. Patrón de mocking de `conftest.py` (cero tokens).

## Edge cases and error scenarios

- **Celery/Redis caídos al arrancar** → warning loggeado, alineación queda
  `pending`, se reintenta el encolado en el siguiente arranque. El API sirve normal.
- **Worker arranca después del API** (orden de `depends_on`) → sin problema: la
  tarea espera en el broker.
- **Dos réplicas del backend arrancando a la vez** → la transición
  `pending→running` debe ser atómica (UPDATE condicional por estado); la
  réplica que pierde no encola duplicado.
- **Alineación desconocida en BD** (registrada por una versión anterior del
  código y ya eliminada del registro) → se ignora con log informativo, no rompe.
- **`detail` con error muy largo** → truncar a un tamaño razonable.
- **Backfill sobre librería vacía o ya alineada** → la tarea corre, procesa 0 y
  marca `done` (es el caso normal en instalaciones nuevas: las ingestas ya
  generan perfil).

## Out of scope

- Adoptar alembic para esquema (se mantienen los ALTERs idempotentes actuales).
- UI/endpoint de administración de alineaciones (consulta directa a la tabla).
- Rollback de alineaciones (son convergentes/idempotentes, no reversibles).
- Paralelización del backfill (sigue secuencial, suficiente para el volumen actual).
- Migrar los ALTERs o seeds existentes a este mecanismo.

## Open questions

- Ninguna bloqueante. Decisión con el Arquitecto: el dispatch vive en el
  arranque del API (después de `create_all` + `seed_data`), no en el worker,
  porque el API es el único punto de arranque garantizado y el encolado es barato.

## References

- Código existente:
  - `backend/utils/backfill_visual_profiles.py` — lógica a envolver como alineación v1
  - `backend/database.py` — patrón de in-place migrations (capa de esquema)
  - `backend/utils/seed.py` — patrón de seeds (capa de config)
  - `backend/main.py` — punto de arranque (líneas ~50-56: create_all + seed)
  - `backend/tasks.py` — patrón de tareas Celery (wrappers finos)
  - `backend/utils/observability.py` — `log_performance_metric()`
- Docs: `docs/operations/post-deploy-alignment.md` (el problema que esto elimina)
- Origen: cierre de la iteración de Selección de Imágenes (2026-06-10/11)
