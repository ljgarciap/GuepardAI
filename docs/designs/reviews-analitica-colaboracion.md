# Design: Sistema de Reviews, Analítica de Uso y Colaboración

**Date**: 2026-07-08
**Architect**: aprobado (pendiente confirmación final de Luis en este documento)
**Spec**: `docs/specs/reviews-analitica-colaboracion.md`
**Status**: Draft — listo para revisión de Luis antes de pasar al PM
**Decisiones de negocio confirmadas** (2026-07-08):
- Moderación: filtro de palabras/frases (sin LLM, sin ADR de AI Architect).
- Departamento: catálogo administrado por tenant (no texto libre).
- Reportes mensuales: email + panel en la app.
- (Ver `docs/designs/soporte-indicaciones.md` para la nota de migración combinada de `generation_jobs`.)

## Riesgo arquitectónico principal

Esta es la spec de mayor superficie de cambio: toca `GenerationJob` (ownership),
agrega 4 tablas nuevas, y agrega dos piezas de infraestructura que **no existen
hoy en el proyecto**: envío de email y Celery beat (tareas periódicas). Ambas
requieren trabajo de DevOps antes de que el código de aplicación tenga sentido
en producción. Se desglosa explícitamente para que el PM no las trate como
"tareas de dev" normales.

## Backend

### 1. Ownership y colaboradores

```sql
ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS owner_id INTEGER;
```

- `GenerationJob.owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)`.
  Nullable porque jobs históricos no tienen owner conocido — **no se hace
  backfill** (no hay forma de inferir quién creó un job viejo); se documenta
  como gap aceptado, no como `data_alignment` (no hay nada que calcular).
- `POST /api/presentations/generate` (`main.py:796`) agrega
  `owner_id=current_user.id` al construir el `GenerationJob` — `current_user`
  ya está disponible en ese handler, cambio de una línea.
- Nueva tabla `generation_job_collaborators`: `id`, `job_id` (FK), `user_id`
  (FK), `added_at`. `UniqueConstraint(job_id, user_id)`.
- Nuevos endpoints:
  - `POST /api/presentations/{job_id}/collaborators` — body `{user_id}`.
    Autorización: solo `owner_id == current_user.id` o admin del tenant.
    Valida que el usuario destino pertenezca al mismo tenant que el `Brand`
    del job (reusa `check_brand_tenant_access` sobre `job.brand_id`).
  - `DELETE /api/presentations/{job_id}/collaborators/{user_id}` — misma
    autorización.
  - `GET /api/presentations/{job_id}/collaborators` — cualquier
    owner/colaborador/admin del tenant.
- Ajuste a `check_job_tenant_access` (`auth/dependencies.py:94`): se mantiene
  igual (sigue siendo la puerta de "pertenece al tenant"); el acceso de
  lectura fino por owner/colaborador se resuelve con un chequeo adicional en
  los endpoints nuevos, no reemplazando el helper existente (evita romper
  las rutas ya scopeadas por tenant que no necesitan este nivel de detalle).

### 2. Reviews y ratings

```sql
CREATE TABLE IF NOT EXISTS presentation_reviews (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES generation_jobs(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    is_deleted BOOLEAN DEFAULT false,
    moderation_status VARCHAR(20) DEFAULT 'visible',
    UNIQUE (job_id, user_id)
);
```

- Modelo `PresentationReview` en `models.py`, tabla nueva (no ALTER — es
  tabla propia, se crea vía `Base.metadata.create_all()` como el resto del
  proyecto).
- `POST /api/presentations/{job_id}/reviews` (upsert por `(job_id, user_id)`):
  - Autorización: `current_user.id == job.owner_id` o colaborador registrado
    en `generation_job_collaborators`.
  - Ventana de edición: rechaza (409) si `now() > job.created_at + 6 meses`
    — **excepto** si es la primera vez que ese usuario califica ese job y aún
    no existe fila (una review nueva tampoco debería crearse pasada la
    ventana; se aplica el mismo corte a creación y edición, tal como pide la
    spec: "editable hasta 6 meses después de la creación").
  - Corre el review a través del filtro de moderación (ver más abajo) antes
    de persistir; el resultado define `moderation_status` inicial.
- `DELETE /api/presentations/{job_id}/reviews/me` — soft delete
  (`is_deleted=true`), mismo corte de ventana de 6 meses.
- `GET /api/presentations/{job_id}/reviews` — lista reviews visibles
  (`is_deleted=false AND moderation_status != 'hidden'`) para
  clientes/colaboradores; admin/superadmin también ven `flagged`/`hidden`
  con el status explícito en la respuesta.
- `rating_average`/`rating_count` se calculan on-the-fly con una agregación
  SQL en el mismo query de detalle de portfolio
  (`GET /api/library/portfolios/{job_id}`, definido en la spec de
  soporte-indicaciones) — no se desnormaliza en `generation_jobs` en v1 para
  evitar inconsistencia; se revisita si el volumen lo justifica.

### 3. Moderación (filtro de palabras)

- Nueva key en `system_configs`: `review_moderation_blocklist_v1` — lista
  JSON de términos/patrones (case-insensitive, coincidencia de substring).
  Seedeada vacía por defecto en `utils/seed.py`; el equipo de negocio la puebla
  vía `system_configs` directo o un pequeño endpoint de administración simple
  (`PATCH /api/admin/config/review-moderation-blocklist`, superadmin only —
  reusa el patrón de config existente, no requiere UI dedicada para v1).
- `services/core/content_moderation_service.py` (nuevo, función pura):
  `evaluate(text: str) -> Literal["visible", "flagged"]`. Sin LLM, sin
  `BaseAgentTool` (no es un agente de IA, es una función determinista de
  servicio) — se llama sincrónicamente dentro del endpoint de review, sin
  impacto de latencia relevante.
- `PATCH /api/admin/reviews/{review_id}/moderation` — body
  `{status: "visible"|"hidden"}`. Solo admin del tenant del job (o
  superadmin). Nunca permite pasar a `flagged` manualmente (ese estado solo
  lo pone el filtro automático).

### 4. Departamentos (catálogo por tenant)

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS department_id INTEGER;
```

- Nuevo modelo `Department`: `id`, `tenant_id` (FK), `name`, `created_at`.
  `UniqueConstraint(tenant_id, name)`.
- `User.department_id` (FK a `departments.id`, nullable — asignación
  opcional, no bloquea el registro de usuarios existentes).
- CRUD simple, admin del tenant: `GET/POST/DELETE /api/admin/departments`.
  Confirmado en `routers/users.py`: hoy solo existen `POST /api/users`
  (crear) y `PATCH /api/users/{user_id}/deactivate` — no hay un endpoint
  genérico de edición de usuario. Se agrega
  `PATCH /api/users/{user_id}/department` (body `{department_id: int |
  null}`) como su propia ruta en el mismo router, siguiendo el estilo ya
  usado por `/deactivate` (verbo específico en vez de un PATCH genérico).
- `DELETE` de un departamento con usuarios asignados: 409 (debe reasignarse
  o vaciarse primero) — evita huérfanos silenciosos.

### 5. Analítica de uso (ediciones + tiempo invertido)

```sql
CREATE TABLE IF NOT EXISTS user_activity_events (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES generation_jobs(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    event_type VARCHAR(30) NOT NULL,   -- 'slide_edit' | 'session_time_seconds'
    value INTEGER NOT NULL DEFAULT 1,  -- 1 para slide_edit, segundos para session_time
    created_at TIMESTAMP DEFAULT now()
);
```

- Tabla genérica única para ambas métricas (evita dos tablas casi idénticas).
  Explícitamente **no** es `PerformanceMetric` — esa tabla es telemetría de
  sistema (duración de llamadas LLM/pipeline), esta es analítica de producto
  por usuario, con retención y consultas distintas.
- `PUT /api/presentations/{job_id}/slides/{slide_id}` (`main.py:849`, ya
  existe y ya requiere `current_user`): al final del handler, inserta un
  `UserActivityEvent(event_type="slide_edit", value=1)`. Cambio pequeño y
  localizado — no se toca la lógica de edición en sí.
- Nuevo evento de frontend: `POST /api/presentations/{job_id}/activity` body
  `{event_type: "session_time_seconds", value: <segundos>}`, disparado por el
  frontend al cerrar/salir de la vista del generador (usa `navigator.sendBeacon`
  para no perder el evento en el unload de la página — patrón estándar para
  este caso, sin dependencias nuevas).
- `GET /api/admin/analytics/usage` (admin/superadmin): agrega por
  usuario/departamento — presentaciones creadas (`COUNT(GenerationJob) GROUP
  BY owner_id`), ediciones (`SUM(value) WHERE event_type='slide_edit'`),
  tiempo invertido (`SUM(value) WHERE event_type='session_time_seconds'`),
  rating promedio recibido. Admin ve solo su tenant (join a través de
  `Brand.tenant_id`); superadmin ve todo con filtro opcional por tenant.

### 6. Reportes mensuales (email + panel)

- **Nueva infraestructura — no existe hoy en el proyecto**:
  - `backend/services/core/email_service.py`: envío vía `smtplib` (stdlib,
    sin dependencia nueva) usando SMTP genérico. Nuevas env vars:
    `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`,
    `EMAIL_SMTP_PASSWORD`, `EMAIL_FROM_ADDRESS`. Si no están configuradas,
    el servicio hace `log.warning` y no falla el proceso que lo llama
    (igual que `SUPERADMIN_EMAIL` es "skipped, no blocking" en el seed
    actual — mismo criterio de tolerancia).
  - Celery beat: `celery_app.py` no tiene `beat_schedule` hoy. Se agrega:
    ```python
    celery_app.conf.beat_schedule = {
        "monthly-usage-report": {
            "task": "tasks.generate_monthly_usage_report",
            "schedule": crontab(day_of_month=1, hour=6, minute=0),
        }
    }
    ```
  - **DevOps**: nuevo servicio en `docker-compose.yml`,
    `celery -A celery_app.celery_app beat --loglevel=info`, comparte imagen
    con el worker existente. Sin esto el `beat_schedule` nunca dispara —
    tarea explícita, no implícita.
- Nueva tabla `usage_reports`: `id`, `tenant_id` (nullable = reporte de
  plataforma completa, solo superadmin), `period_start`, `period_end`,
  `payload_json` (JSONB con el agregado), `created_at`, `sent_at` (nullable).
- Tarea Celery `generate_monthly_usage_report`: agrega el mes anterior por
  tenant + uno global, persiste `UsageReport`, envía email a superadmin
  (global) y a cada admin de tenant (su recorte) vía `email_service`.
- `GET /api/admin/usage-reports` — panel en la app, mismo scoping que el
  resto (tenant admin ve los suyos, superadmin ve todos).

### 7. Gamificación (badges)

- Sin tabla nueva en v1: cálculo on-demand,
  `COUNT(GenerationJob) WHERE owner_id = user.id` (join a `Brand` para
  confirmar que el tenant coincide, ya que `owner_id` no repite `tenant_id`
  directamente — es más simple filtrar por `owner_id` solo, dado que un
  usuario pertenece a un único tenant fijo, `User.tenant_id`, así que el
  conteo ya es de-facto por tenant sin join extra).
- `GET /api/users/me/badges` → `{count, current_badge, next_badge,
  progress_to_next}` con los umbrales fijos (5/10/20) leídos de
  `system_configs` (`badge_thresholds_v1`, no hardcodeados — regla del
  proyecto de no hardcodear umbrales).

### AI Decision Records
No aplica — moderación es un filtro determinista (no LLM). No hay llamadas
nuevas a `providers/llm_provider.py`. No requiere consulta al AI Architect.
Si en una iteración futura se reemplaza el filtro de palabras por
clasificación LLM, **eso sí** requeriría un ADR antes de diseñar (ya
documentado como decisión descartada para v1 en la spec).

## Frontend (Angular 19, standalone)

- `presentation-detail` (o donde viva hoy el detalle de un job en la
  biblioteca): sección de reviews (lista + form de calificar/comentar propio),
  sección de colaboradores (owner/admin puede agregar/quitar).
- Panel de admin nuevo: gestión de departamentos, moderación de reviews
  flagged, analítica de uso (tabla + export simple), reportes mensuales
  (lista descargable/visualizable).
- Perfil de usuario: widget de progreso de insignias.
- `brand.service.ts` (o un nuevo `collaboration.service.ts` para no sobrecargar
  el servicio existente): métodos para reviews, colaboradores, analítica,
  departamentos, badges.

## Dependencias entre tareas

1. Migración de schema (`owner_id` + tablas nuevas) — bloquea todo lo demás.
   Se hace junto con `prompt_metadata` de la otra spec en el mismo PR.
2. Ownership + colaboradores (backend) — bloquea reviews (necesita saber
   quién puede calificar).
3. Reviews + moderación (backend) — puede avanzar en paralelo con (4)/(5).
4. Departamentos (backend + mini-CRUD) — independiente, puede ir en paralelo.
5. Analítica de uso (evento en `PUT slides`, nuevo endpoint de actividad) —
   depende de (2) para poder agregar por usuario con sentido.
6. Infra de email + Celery beat (**DevOps**) — bloquea el envío real de
   reportes mensuales, pero no bloquea el resto (el panel en la app puede
   funcionar sin email listo, mostrando reportes generados manualmente para
   pruebas).
7. Reportes mensuales (backend, depende de 5 y 6) — última pieza.
8. Badges — depende solo de (1)/(2), independiente del resto.
9. Frontend — depende de cada endpoint respectivo estando desplegado en un
   entorno de prueba.

## Riesgos y mitigación

- **Infra de email nueva sin proveedor elegido**: se diseña sobre SMTP
  genérico (sin acoplarse a un vendor) para no bloquear el diseño en una
  decisión de proveedor — Luis/DevOps eligen el proveedor SMTP (SES, Gmail
  workspace, SendGrid vía SMTP, etc.) al desplegar. Riesgo: si no se
  configura, los reportes solo quedan en el panel — comportamiento
  degradado aceptable, no bloqueante.
- **Celery beat es infraestructura nueva**: un beat mal desplegado (o
  ausente) hace que la tarea mensual simplemente nunca corra, sin error
  visible. Mitigación: `GET /api/admin/usage-reports` como fuente de verdad
  visual — si no hay reportes generados, es evidente en el panel.
- **Filtro de palabras tiene falsos negativos/positivos**: aceptado
  explícitamente por Luis para v1 (ver spec). Mitigación: blocklist vive en
  `system_configs`, ajustable sin deploy de código; admin puede revertir
  `flagged`→`visible` manualmente.
- **`owner_id` nulo en jobs históricos**: cualquier query de analítica/badges
  que agregue por `owner_id` debe excluir explícitamente `owner_id IS NULL`
  (no contarlos como "un usuario más" ni fallar) — a validar en QA con datos
  reales de producción.
- **Reasignación de colaboradores no afecta reviews existentes**: documentado
  como comportamiento esperado en la spec (edge case ya cubierto), no es un
  riesgo nuevo, se menciona aquí para que QA lo tenga en su checklist.

## Estimación de esfuerzo
- Backend ownership + colaboradores: 1 día.
- Backend reviews + moderación: 1.5 días.
- Backend departamentos (modelo + CRUD): 0.5 día.
- Backend analítica de uso (evento + endpoint agregado): 1 día.
- DevOps (email service + celery beat + docker-compose): 1 día.
- Backend reportes mensuales (tarea + persistencia + envío): 1 día.
- Backend badges: 0.5 día.
- Frontend (reviews, colaboradores, panel admin, analítica, badges): 3–4 días.
- Tech Writer (API docs + manual de admin de departamentos/moderación): 1 día, en paralelo.
- QA: caso de prueba dedicado para `owner_id IS NULL` en agregaciones, ventana
  de 6 meses (edición/borrado), y idempotencia del upsert de review.
