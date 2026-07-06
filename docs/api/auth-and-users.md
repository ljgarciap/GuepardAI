# API — Autenticación y Gestión de Usuarios

Referencia de `/api/auth/*` y `/api/users`. Implementación: `backend/routers/auth.py`,
`backend/routers/users.py`, `backend/services/core/auth_service.py`,
`backend/auth/` (security.py, dependencies.py, schemas.py, redis_client.py).

Spec: `docs/specs/autenticacion-multiusuario-multitenant.md`
Design: `docs/designs/autenticacion-multitenant-design.md`

## Modelo de sesión

- **Access token** (JWT, `HS256`): TTL corto (`JWT_ACCESS_TOKEN_TTL_MINUTES`, default 15 min). Se envía como `Authorization: Bearer <token>` en cada request. Contiene `sub` (user id), `role`, `tenant_id`.
- **Refresh token** (JWT + registro en Redis): TTL largo (`JWT_REFRESH_TOKEN_TTL_DAYS`, default 7 días). Cada refresh token es de **un solo uso**: `POST /api/auth/refresh` lo invalida atómicamente (Redis `GETDEL`) al mismo tiempo que emite un par nuevo — dos requests de refresh concurrentes con el mismo token nunca pueden ambos tener éxito.
- **Logout** revoca el refresh token en Redis (idempotente: un token ya inválido no produce error).
- Si Redis no está disponible: `refresh`/`logout` devuelven `503` (fail-closed, dependen de Redis para revocación). El **rate limit de login** en cambio falla abierto (una caída de Redis no debe bloquear todos los logins de la plataforma).

## Endpoints

### `POST /api/auth/register`

Registro público. Crea un `Tenant` nuevo y un `User` con rol `admin` en ese tenant (nunca crea un `cliente` suelto — un tenant nuevo necesita alguien que lo administre).

**Body**:
```json
{ "email": "string (email)", "password": "string (min 8 chars)", "tenant_name": "string | null" }
```
`tenant_name` es opcional; si se omite, el tenant toma el email como nombre visible.

**Respuestas**:
- `201` → `TokenResponse` (ver abajo)
- `409` → email ya en uso

### `POST /api/auth/login`

**Body**: `{ "email": "string", "password": "string" }`

**Respuestas**:
- `200` → `TokenResponse`
- `401` → mensaje genérico ("Incorrect email or password") — el mismo mensaje y el mismo costo de CPU (hash bcrypt siempre se ejecuta, contra un hash dummy si el email no existe) se usan para email inexistente, cuenta inactiva y password incorrecta, para no filtrar por contenido ni por timing cuál caso ocurrió.
- `429` → demasiados intentos (rate limit por IP+email, ventana deslizante en Redis: `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` intentos por `LOGIN_RATE_LIMIT_WINDOW_SECONDS` segundos, defaults 5/60s)

### `POST /api/auth/refresh`

**Body**: `{ "refresh_token": "string" }`

**Respuestas**:
- `200` → `TokenResponse` (nuevo access + nuevo refresh; el refresh enviado queda invalidado)
- `401` → refresh token inválido, expirado, ya usado, o del tipo incorrecto
- `503` → Redis no disponible

### `POST /api/auth/logout`

**Body**: `{ "refresh_token": "string" }`

**Respuestas**:
- `204` → revocado (o ya inválido — logout es idempotente)
- `503` → Redis no disponible

### `GET /api/auth/me`

Requiere `Authorization: Bearer <access_token>`.

**Respuestas**:
- `200` → `UserOut` del usuario autenticado
- `401` → sin token, token inválido/expirado, o usuario inactivo

## `TokenResponse`

```json
{ "access_token": "string", "refresh_token": "string", "token_type": "bearer" }
```

## `UserOut`

```json
{ "id": 1, "email": "string", "role": "superadmin | admin | cliente", "tenant_id": "int | null", "is_active": 1 }
```
`tenant_id` es `null` únicamente para `superadmin`.

## `POST /api/users` — Alta de usuario `cliente`

Requiere rol `admin` o `superadmin` (`Depends(require_role("admin", "superadmin"))`).

**Body**:
```json
{ "email": "string", "password": "string (min 8 chars)", "tenant_id": "int | null" }
```
- Un `admin` siempre crea el usuario en **su propio** tenant; `tenant_id` en el body se ignora si lo manda.
- Un `superadmin` puede pasar `tenant_id` explícito; si lo omite, usa su propio `tenant_id` (que es `null`, así que en la práctica un superadmin debe pasar `tenant_id` para que el alta tenga sentido).
- El nuevo usuario siempre nace con rol `cliente` — este endpoint no crea `admin` ni `superadmin`.

**Respuestas**: `201` → `UserOut` · `409` → email ya en uso

## `GET /api/users` — Listado

Requiere rol `admin` o `superadmin`. Un `admin` solo ve usuarios de su propio tenant; un `superadmin` ve todos.

**Respuestas**: `200` → `UserOut[]`

## `PATCH /api/users/{user_id}/deactivate`

Requiere rol `admin` o `superadmin`. Un `admin` solo puede desactivar usuarios de su propio tenant.

**Respuestas**: `200` → `UserOut` (con `is_active: 0`) · `404` → no existe · `403` → pertenece a otro tenant

## Scoping por tenant en el resto de la API

Todas las rutas existentes de `main.py` (brands, ingestion, generation, library, etc.) ahora requieren `Authorization: Bearer <access_token>` vía `Depends(get_current_user)`. El acceso a recursos (`Brand`, `GenerationJob`, etc.) se filtra por `tenant_id` salvo para `superadmin`, que es un bypass **explícito por rol** (nunca implícito por `tenant_id IS NULL`). Ver `auth/dependencies.py`: `require_tenant_access`, `check_brand_tenant_access`, `check_job_tenant_access`, `tenant_brand_ids_filter`.
