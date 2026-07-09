# API — Reviews, Colaboración y Analítica

Referencia de `/api/presentations/{job_id}/collaborators`, `/api/presentations/{job_id}/reviews`,
`/api/admin/reviews`, `/api/admin/departments`, `/api/users/directory`,
`/api/users/{id}/department`, `/api/presentations/{job_id}/activity`,
`/api/admin/analytics/usage`, `/api/admin/usage-reports`, `/api/users/me/badges`.

Implementación: `backend/routers/collaborators.py`, `backend/routers/reviews.py`,
`backend/routers/departments.py`, `backend/routers/analytics.py`,
`backend/routers/badges.py`, más las adiciones en `backend/routers/users.py`
(`/directory`, `/{id}/department`). Servicios: `backend/services/core/content_moderation_service.py`,
`backend/services/core/usage_report_service.py`, `backend/services/core/email_service.py`.

Spec: `docs/specs/reviews-analitica-colaboracion.md`
Design: `docs/designs/reviews-analitica-colaboracion.md`

Todas las rutas de este documento requieren `Authorization: Bearer <access_token>`
(ver `docs/api/auth-and-users.md`). El scoping por tenant sigue el criterio
estándar del proyecto: `superadmin` bypassa **explícitamente por rol**, nunca
por `tenant_id IS NULL`.

## Colaboradores

Un `GenerationJob` tiene un `owner_id` (quien lo generó) y, opcionalmente,
colaboradores adicionales que pueden calificarlo igual que el owner.

### `POST /api/presentations/{job_id}/collaborators`

**Body**: `{ "user_id": int }`

**Autorización**: el owner del job, un admin del tenant del job, o superadmin.
El usuario objetivo debe pertenecer al mismo tenant que el `Brand` del job —
si el job no tiene `brand_id` (generación "Public/Generic"), **nadie** puede
ser agregado como colaborador (no hay tenant contra el cual validar).

**Respuestas**:
- `200` → `{ user_id, added_at }` (idempotente: agregar dos veces al mismo
  usuario no crea una fila duplicada, devuelve la existente)
- `403` → quien llama no es owner/admin del tenant, o el usuario objetivo es
  de otro tenant, o el job no tiene brand
- `404` → el usuario objetivo no existe

### `DELETE /api/presentations/{job_id}/collaborators/{user_id}`

Misma autorización que el alta. `200` → `{ status: "removed" }` · `404` → esa
fila de colaborador no existe.

### `GET /api/presentations/{job_id}/collaborators`

Cualquier miembro del tenant del job puede listar (no hace falta ser owner,
colaborador, ni admin). `200` → `[{ user_id, email, added_at }]`.

## Reviews

Un review es `{ rating: 1-5, comment?: string }` por `(job_id, user_id)` —
"upsert": volver a calificar actualiza la fila existente, no crea otra.

### `POST /api/presentations/{job_id}/reviews`

**Body**: `{ "rating": int (1-5), "comment": string | null }`

**Autorización**: el owner del job, un colaborador registrado, o superadmin.

**Ventana de edición**: rechaza con `409` si `now() > job.created_at + 6 meses`
— la ventana se cuenta desde la **creación del job**, no desde la review.
Aplica igual a la creación de la primera review y a su edición.

**Moderación automática**: el `comment` pasa por
`content_moderation_service.evaluate()` (filtro de palabras determinista,
blocklist en `system_configs`, ver más abajo) antes de guardarse. Si matchea,
`moderation_status` queda en `"flagged"` — la review se guarda igual, sigue
siendo visible para el usuario y sus compañeros, y queda en la cola de
moderación del admin. Solo `moderation_status = "hidden"` (una acción
explícita de un admin, ver `PATCH .../moderation` abajo) la oculta.

**Respuestas**:
- `200` → la review (`{ id, job_id, user_id, user_email, rating, comment, created_at, updated_at, moderation_status }`)
- `422` → `rating` fuera de 1-5
- `403` → no es owner ni colaborador
- `409` → ventana de 6 meses cerrada

### `DELETE /api/presentations/{job_id}/reviews/me`

Soft-delete (`is_deleted=true`) de la review propia. Misma ventana de 6 meses
que la edición. `200` → `{ status: "deleted" }` · `404` → no existe review
propia · `409` → ventana cerrada.

### `GET /api/presentations/{job_id}/reviews`

**Autorización**: cualquier miembro del tenant del job.

Un usuario `cliente`/`admin` normal ve las reviews con `moderation_status != "hidden"`
(o sea, `visible` **y** `flagged` — solo `hidden` se oculta). Un `admin`/`superadmin`
ve absolutamente todas, incluidas las `hidden`.

`rating_average`/`rating_count` se calculan sobre el mismo criterio
(`moderation_status != "hidden"`, `is_deleted = false`) — **no** es el mismo
subconjunto que "solo visible": una review `flagged` sigue contando en el
promedio hasta que un admin la pase explícitamente a `hidden`.

**Respuesta**: `200` → `{ reviews: [...], rating_average: float | null, rating_count: int }`

## Moderación (solo admin/superadmin)

### `GET /api/admin/reviews?status_filter=`

Listado cross-job para la cola de moderación. `status_filter` es opcional:
`visible` | `flagged` | `hidden` (omitirlo trae todas, sin contar las
soft-deleted). Un `admin` ve solo las reviews de jobs de su propio tenant; un
`superadmin` ve todas.

**Respuesta**: `200` → `[{ ...review, job_display_name }]` · `422` → `status_filter` inválido.

### `PATCH /api/admin/reviews/{review_id}/moderation`

**Body**: `{ "status": "visible" | "hidden" }` — nunca se puede setear
`"flagged"` manualmente, ese estado solo lo asigna el filtro automático.

**Autorización**: admin del tenant del job de esa review, o superadmin.

`200` → la review actualizada · `422` → `status` inválido · `403` → tenant
distinto · `404` → no existe.

### `GET` / `PATCH /api/admin/config/review-moderation-blocklist`

**Solo superadmin** (config global, no por tenant). `GET` → `{ terms: string[] }`
(términos tal cual se guardaron, sin normalizar). `PATCH` con
`{ "terms": string[] }` reemplaza la lista completa. El matching en
`evaluate()` es substring, case-insensitive.

## Departamentos (solo admin/superadmin)

Catálogo simple por tenant — asignación opcional a un `User`, usado por
Analítica para agrupar.

### `POST /api/admin/departments`

**Body**: `{ "name": string, "tenant_id": int | null }` — un `admin` siempre
crea en su propio tenant (`tenant_id` del body se ignora); un `superadmin`
**debe** pasar `tenant_id` explícito (`422` si lo omite, no tiene uno propio).

`201` → el departamento · `409` → ya existe un departamento con ese nombre en
ese tenant.

### `GET /api/admin/departments?tenant_id=`

`admin` ve solo su tenant (el query param se ignora); `superadmin` ve todos o
filtra por `tenant_id` si lo pasa.

### `DELETE /api/admin/departments/{department_id}`

`200` → borrado · `403` → tenant distinto · `404` → no existe · `409` → tiene
usuarios asignados (hay que reasignarlos o vaciarlos primero — nunca deja
huérfanos silenciosos).

### `PATCH /api/users/{user_id}/department`

**Body**: `{ "department_id": int | null }` (`null` = quitar la asignación).
Autorización: admin/superadmin. `403` si el usuario objetivo es de otro
tenant, o si el departamento pertenece a un tenant distinto al del usuario.
`404` → usuario o departamento no existe. `200` → el usuario actualizado
(`UserOut`, ver `docs/api/auth-and-users.md`).

## Directorio de usuarios

### `GET /api/users/directory`

A diferencia de `GET /api/users` (admin-only), **cualquier usuario
autenticado** puede llamar este endpoint — un owner de job con rol `cliente`
necesita poder invitar colaboradores sin tener permisos de admin. Devuelve un
shape mínimo, sin `role`/`tenant_id`/`is_active`.

Scoping: mismo criterio que `GET /api/users` (tenant propio, o todos para
superadmin), implementado como el mismo helper `_tenant_scoped_users()`.

**Respuesta**: `200` → `[{ id: int, email: string }]`

## Analítica de uso (solo admin/superadmin para la lectura agregada)

### `POST /api/presentations/{job_id}/activity`

Evento de frontend, disparado por `navigator.sendBeacon` al salir del
generador. **Body**: `{ "event_type": "session_time_seconds", "value": int > 0 }`
— es el único `event_type` que el cliente puede reportar; `slide_edit` se
registra server-side dentro de `PUT /api/presentations/{job_id}/slides/{slide_id}`,
nunca es postable directamente.

`200` → `{ status: "recorded" }` · `422` → `event_type` distinto de
`session_time_seconds`, o `value <= 0` · `403` → tenant distinto.

### `GET /api/admin/analytics/usage?tenant_id=`

Agregado por usuario: presentaciones creadas (`COUNT(GenerationJob) WHERE
owner_id=user.id`), ediciones y tiempo invertido (`SUM(UserActivityEvent.value)`
por `event_type`), y rating promedio recibido (`AVG` de sus reviews con
`moderation_status != "hidden"` — mismo criterio que el endpoint de reviews).
Scoping: `admin` su tenant, `superadmin` todos o filtrado por `tenant_id`.

Implementación: agregado en 4 queries `GROUP BY` (más el listado de
usuarios) en vez de un loop con varias queries por usuario — evita un N+1 sin
paginación en tenants con muchos usuarios.

**Respuesta**: `200` → `{ users: [{ user_id, email, department_id,
department_name, presentations_created, edits, time_spent_seconds,
rating_average_received }] }`

### `GET /api/admin/usage-reports?tenant_id=`

Lista los `UsageReport` ya generados (ver "Reportes mensuales" abajo) —
fuente de verdad visual si el envío por email falla o Celery beat no está
desplegado. `admin` ve solo los de su tenant; `superadmin` ve todos,
**incluido el reporte global** (`tenant_id: null`), salvo que filtre por
`tenant_id` explícito.

**Respuesta**: `200` → `[{ id, tenant_id, period_start, period_end, payload,
created_at, sent_at }]`. `payload` = `{ presentations_created, total_edits,
total_time_spent_seconds, rating_average, contributors_count, top_user,
top_department }`. `sent_at: null` significa que no se pudo enviar por email
(típicamente porque `EMAIL_SMTP_HOST`/`EMAIL_FROM_ADDRESS` no están
configuradas — ver `docs/manuals/technical/email-and-celery-beat-deployment.md`)
pero el reporte igual quedó calculado y persistido.

**Generación**: no hay endpoint para dispararla manualmente — corre por
Celery beat el día 1 de cada mes (tarea `tasks.generate_monthly_usage_report`
→ `services/core/usage_report_service.generate_and_send_monthly_reports()`),
un `UsageReport` por tenant más uno global.

## Badges (cualquier usuario autenticado)

### `GET /api/users/me/badges`

Cálculo on-demand, sin tabla propia: `COUNT(GenerationJob) WHERE
owner_id = current_user.id`. Umbrales configurables en
`system_configs.badge_thresholds_v1` (default: 5 = Starter, 10 = Expert,
20 = Genius) — nunca hardcodeados.

**Respuesta**: `200` → `{ count: int, current_badge: {threshold,label} | null,
next_badge: {threshold,label} | null, progress_to_next: float | null }`.
`next_badge`/`progress_to_next` son `null` cuando ya se alcanzó el tier más
alto configurado.
