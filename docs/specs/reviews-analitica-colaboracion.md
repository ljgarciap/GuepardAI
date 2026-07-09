# Spec: Sistema de Reviews, Analítica de Uso y Colaboración

**Date**: 2026-07-08
**Requested by**: Luis
**Status**: Draft
**Project**: GuepardAI

## Problem

Hoy `GenerationJob` no tiene dueño ni colaboradores: solo se liga a `brand_id` y se
controla por tenant (`backend/models.py:282-306`). El único mecanismo de feedback
existente es `GenerationJobFeedback` (`models.py:476-490`), una encuesta de
satisfacción de una sola pregunta por job (`UniqueConstraint(job_id, question_id)`)
sin noción de quién la respondió. No existe: colaboradores múltiples por
presentación, moderación de contenido, analítica de uso por usuario/departamento,
reportes automáticos, ni gamificación. El negocio quiere usar el desempeño
percibido (rating) para priorizar qué patrones de generación se refuerzan, dar
feedback continuo a los autores, y medir/incentivar el uso de la plataforma.

Esta es la spec de mayor alcance arquitectónico de las dos pedidas: requiere
extender el modelo de datos de `GenerationJob` para saber qué usuarios participan
en cada presentación — algo que el sistema de auth multi-tenant (ya cerrado en
producción) no cubre hoy porque no lo necesitaba.

## Solution summary

1. **Colaboradores**: `GenerationJob` gana un `owner_id` (usuario creador) y una
   tabla `generation_job_collaborators` (job × usuario) para asignar colaboradores
   adicionales dentro del mismo tenant.
2. **Reviews y ratings**: nuevo modelo `PresentationReview` (reemplaza el uso de
   `GenerationJobFeedback` para este propósito — la encuesta de satisfacción
   existente se mantiene intacta para su caso de uso actual) con rating 1-5
   entero + comentario opcional, una review activa por colaborador por
   presentación, editable hasta 6 meses después de `GenerationJob.created_at`,
   con soft-delete y moderación.
3. **Moderación**: marcado automático (heurística de palabras/frases sensibles en
   v1, ver Open questions) + capacidad de admin de tenant para ocultar/eliminar
   reviews marcadas.
4. **Analítica de uso**: tracking de ediciones por presentación (reusa el endpoint
   existente `PUT /api/presentations/{job_id}/slides/{slide_id}`, que ya requiere
   usuario autenticado) y tiempo invertido (nueva instrumentación de frontend),
   agregado por usuario/departamento, con reportes mensuales.
5. **Gamificación**: insignias (Principiante 5, Experto 10, Genio 20) calculadas
   sobre el conteo de presentaciones creadas (`owner_id`) por usuario.

## Users and roles

- **Cliente / Admin de tenant (colaborador)**: puede ser asignado como
  colaborador de una presentación, calificarla y comentarla, ver su propio
  progreso de insignias.
- **Admin de tenant**: además, puede asignar/quitar colaboradores de las
  presentaciones de su tenant, y moderar (ocultar/eliminar) reviews marcadas
  dentro de su tenant.
- **Superadmin**: ve analítica y reportes agregados a nivel plataforma (todos los
  tenants); recibe/genera el reporte mensual a la empresa.
- No hay un rol nuevo — se apoya en `UserRole` existente (`SUPERADMIN | ADMIN |
  CLIENTE`, `models.py:41-44`).

## Acceptance criteria

### Colaboradores
- [ ] `GenerationJob` tiene `owner_id` (FK a `users.id`, se asigna al usuario que
      dispara `POST /api/presentations/generate`).
- [ ] Nueva tabla `generation_job_collaborators` (`job_id`, `user_id`,
      `added_at`) permite N colaboradores por job, únicos por par
      (job_id, user_id).
- [ ] Solo el owner o un admin del tenant puede añadir/quitar colaboradores;
      el colaborador debe pertenecer al mismo tenant que el `Brand` del job
      (reusa `check_brand_tenant_access`).
- [ ] Owner y colaboradores tienen acceso de lectura al job aunque no sean el
      creador directo (ajuste sobre el scoping actual, que hoy es solo por
      tenant/brand).

### Reviews y ratings
- [ ] Nuevo modelo `PresentationReview`: `id`, `job_id`, `user_id`, `rating`
      (Integer 1-5, `CheckConstraint`), `comment` (Text, nullable),
      `created_at`, `updated_at`, `is_deleted` (soft-delete), `moderation_status`
      (`visible | flagged | hidden`).
- [ ] `UniqueConstraint(job_id, user_id)` — una review activa por colaborador
      por presentación; volver a calificar actualiza (`updated_at`) en vez de
      crear una fila nueva.
- [ ] Solo owner y colaboradores asignados del job pueden crear/editar una
      review sobre ese job.
- [ ] Edición y borrado bloqueados cuando `now() > GenerationJob.created_at +
      6 meses`; a partir de ahí la review pasa a solo lectura (se sigue
      mostrando, no se oculta).
- [ ] Si `rating <= 2` o `rating >= 4`, el frontend solicita explícitamente
      `comment` (recomendado, no bloqueante — puede omitirse).
- [ ] `GET` de detalle de presentación (biblioteca) expone `rating_average`
      (promedio de todas las reviews `moderation_status != hidden` y
      `is_deleted = false`) y `rating_count`.
- [ ] Borrar la propia review dentro de la ventana de 6 meses la excluye
      inmediatamente del promedio agregado (soft-delete, no hard-delete —
      queda auditable).

### Moderación
- [ ] Al crear/editar una review, se evalúa el texto contra un filtro de
      contenido (ver Open questions para el mecanismo) y si detecta contenido
      abusivo/sensible, `moderation_status = flagged` automáticamente (la review
      igual se guarda; no bloquea al usuario).
- [ ] Un admin del tenant puede ver las reviews `flagged` de su tenant y
      cambiar `moderation_status` a `hidden` (deja de contar en el promedio y no
      se muestra) o revertir a `visible`.
- [ ] Reviews `hidden` no se exponen a clientes/colaboradores normales, solo a
      admins/superadmin.

### Analítica de uso
- [ ] Cada llamada exitosa a `PUT /api/presentations/{job_id}/slides/{slide_id}`
      incrementa un contador de "cambios" asociado al job y al `current_user`
      que la hizo (nueva tabla o columna agregada — no reutilizar
      `PerformanceMetric`, que es telemetría de sistema, no analítica de
      producto, por convención del proyecto).
- [ ] Nueva instrumentación de frontend registra tiempo invertido por sesión de
      trabajo sobre un job (apertura del generador/checkpoint de edición hasta
      cierre o generación final) — evento explícito, no inferido de logs de
      sistema.
- [ ] Endpoint de analítica (solo Admin/Superadmin) agrega por usuario:
      presentaciones creadas, cambios totales, tiempo invertido total, rating
      promedio recibido en sus presentaciones.
- [ ] Agregación por "departamento" requiere un nuevo campo `department`
      (String, nullable) en `User` — ver Open questions sobre si es texto libre
      o catálogo.

### Reportes mensuales
- [ ] Job programado (Celery beat o equivalente) genera un reporte agregado
      mensual (top usuarios/departamentos por uso, rating promedio de la
      plataforma/tenant, insignias otorgadas en el período).
- [ ] El reporte queda disponible para Superadmin a nivel plataforma; Admin de
      tenant ve el recorte de su propio tenant únicamente.

### Gamificación
- [ ] Insignias calculadas sobre `COUNT(GenerationJob) WHERE owner_id = user.id`
      dentro del tenant del usuario: 5 → Principiante, 10 → Experto, 20 → Genio.
- [ ] El conteo de insignias se recalcula on-demand (no requiere tabla de
      estado separada en v1) o se cachea — decisión de Architect según carga.
- [ ] El usuario ve su progreso de insignias en su perfil/dashboard.

## Edge cases and error scenarios

- Un colaborador es removido de un job después de haber dejado una review: la
  review permanece (no se borra en cascada), pero pierde el permiso de editarla
  a futuro salvo que sea re-agregado.
- El owner de un job es también su único colaborador y borra su propia review:
  `rating_average` queda sin datos (0 reviews) — el frontend debe mostrar "sin
  calificaciones" en vez de 0 estrellas.
- Dos colaboradores intentan calificar simultáneamente el mismo job: cada uno
  tiene su propia fila por `UniqueConstraint(job_id, user_id)`, no hay condición
  de carrera entre colaboradores distintos; el mismo usuario reenviando dos
  veces hace `UPSERT` idempotente sobre su propia fila.
- Un job es eliminado (`DELETE /api/library/portfolios/{id}`, solo permitido en
  estados terminales): sus reviews y registros de colaboradores se limpian
  explícitamente en la misma transacción, siguiendo el patrón ya usado para
  `GenerationJobFeedback`/`ArtDirectorDecision` en ese endpoint.
- Contenido de review marcado como `flagged` por el filtro pero que un admin
  humano considera aceptable: se puede revertir a `visible` sin perder el
  historial de que fue marcado (auditoría, no lo pide explícitamente el
  negocio pero evita perder trazabilidad — confirmar alcance con Architect).
- Usuario sin ninguna presentación creada consulta su progreso de insignias:
  se muestra 0/5 hacia "Principiante", no error.

## Out of scope

- Edición colaborativa en tiempo real (tipo Google Docs) sobre el contenido de
  las diapositivas — "colaboración" aquí es asignación de colaboradores +
  reviews compartidas, no co-edición simultánea.
- Incremento de rating en pasos de 0.5 — se confirmó escala entera 1-5 con Luis.
- Rediseño del flujo de la encuesta de satisfacción existente
  (`GenerationJobFeedback` / `survey_questions`) — sigue funcionando igual;
  esta spec añade un sistema paralelo de reviews por colaborador, no lo
  reemplaza.
- Notificaciones push/email en tiempo real cuando alguien deja una review o
  gana una insignia — puede ser una iteración futura.
- Uso automático del rating para re-entrenar o ajustar pesos del pipeline de
  generación (el objetivo de negocio lo menciona como visión, pero esta spec
  solo entrega la captura de datos; el consumo por el Art Director/pipeline de
  selección es una spec separada más adelante).
- Catálogo estructurado y jerárquico de departamentos (organigrama) — en esta
  iteración `department` es, como máximo, un campo simple en `User` (ver Open
  questions), no un modelo organizacional completo.

## Open questions

- [Luis] "Moderación automática de contenido abusivo/sensible" — ¿alcanza con
  un filtro de palabras/frases (lista configurable, sin costo de LLM) para v1,
  o se espera una clasificación real vía LLM (que sí tendría costo de tokens y
  debería rutearse por `providers/llm_provider.py` con su propia
  especialización)? Cambia significativamente el esfuerzo de implementación.
- [Luis] Campo `department` en `User`: ¿texto libre que cada usuario/admin
  escribe, o un catálogo fijo que el tenant administra? Afecta si esta spec
  incluye un mini-CRUD de departamentos o solo un `String` nullable.
- [Luis] Reportes mensuales: ¿se entregan por email (requiere integrar envío de
  correo, no existe hoy en el proyecto), se descargan desde un panel en la app,
  o ambos? ¿A quién exactamente — solo Superadmin, o también cada Admin de
  tenant sobre su propio tenant?
- [Architect] Insignias: ¿el conteo de presentaciones para "Principiante /
  Experto / Genio" es por tenant (un usuario que cambia de tenant reinicia su
  progreso) o global por usuario across tenants? Dado que `User.tenant_id` es
  fijo por usuario hoy (`models.py:72`), esto probablemente ya resuelve la
  pregunta (es de facto por tenant), pero requiere confirmación explícita en
  el diseño.
- [Architect] Coordinar con la spec `soporte-indicaciones.md`: ambas tocan
  `GenerationJob` (esta añade `owner_id`; la otra propone `prompt_metadata`).
  Conviene una sola migración/diseño de schema para las dos, no dos PRs
  tocando el mismo modelo por separado.
- [AI Architect] Si la moderación automática termina usando LLM (según la
  respuesta de Luis arriba), requiere un ADR: qué modelo/especialización, cómo
  se valida el output, y qué pasa si la llamada falla (¿se guarda sin marcar,
  o se bloquea la review hasta reintentar?).

## References

- Related existing code:
  - `backend/models.py:282-306` (`GenerationJob`), `:476-490`
    (`GenerationJobFeedback`), `:65-77` (`User`, `Tenant`)
  - `backend/main.py:849-853` (`PUT /api/presentations/{job_id}/slides/{slide_id}`
    — fuente de "número de cambios")
  - `backend/utils/observability.py` (`PerformanceMetric` — telemetría de
    sistema, no reutilizar para analítica de producto)
  - `backend/auth/dependencies.py` (`check_job_tenant_access`,
    `check_brand_tenant_access`, `tenant_brand_ids_filter`)
- Related specs: `docs/specs/gestion-portfolios.md`,
  `docs/specs/autenticacion-multiusuario-multitenant.md`,
  `docs/specs/soporte-indicaciones.md`
- Prototype or mockup: ninguno aún
