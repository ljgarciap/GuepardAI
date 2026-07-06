# Tasks: Autenticación, Roles Multi-Usuario y Base Multi-Tenant

**Date**: 2026-07-05
**PM**: desglose del diseño `docs/designs/autenticacion-multitenant-design.md`
**Spec**: `docs/specs/autenticacion-multiusuario-multitenant.md`
**Status**: B1-B9 completadas y validadas; Senior Reviewer encontró 2 blockers de seguridad (timing side-channel en login, `JWT_SECRET_KEY` sin guard) — ambos cerrados + 2 suggestions (rotación atómica de refresh, race de email duplicado). Suite completa 424 passed/1 skipped (2026-07-05). **D1 completo** (2026-07-06): `passlib[bcrypt]`/`python-jose` en `requirements.txt`; vars JWT y `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` en `.env.example`/`docker-compose.yml`; `JWT_SECRET_KEY` y `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` (valor de prueba `password`, rotar antes de ir a producción real) seteados en el `.env` de EC2 (backend + celery_worker reiniciados y verificados — nota: EC2 corre `master`, que aún no tiene este feature mergeado, así que estas vars quedan listas mas inertes hasta el merge); `utils/seed_superadmin.py` probado localmente end-to-end. **F1-F4 completas** (2026-07-06): `auth.service.ts` (login/register/logout/refresh single-flight, access token en memoria + refresh en localStorage), `auth.interceptor.ts` (adjunta Bearer, deduplica refresh ante 401 concurrentes), `auth.guard.ts`/`role.guard.ts`, páginas `login`/`register` standalone, rutas protegidas (`/`, `/brands`, `/directory`, `/library`, `/template-merge`), sidebar con usuario real + logout. Verificado con Playwright real (login/logout end-to-end, screenshots) y `ng test` (46/46 verde, incluye 13 specs nuevos). **Nota**: F3 no oculta ningún ítem de "gestión de usuarios" en el nav porque esa pantalla no existe todavía (depende de B7/B8, que no tienen UI); no hay nada que gatear ahí por ahora. **T1 completa** (2026-07-06): API doc `docs/api/auth-and-users.md` (todos los endpoints de `/api/auth/*` y `/api/users`, request/response, códigos de error); `docs/architecture/GuepardAI-overview.md` creado (no existía — primer doc de arquitectura consolidada del proyecto, incluye la nueva sección de multi-tenancy y la convención `routers/`); `docs/manuals/technical/auth-deployment.md` (env vars nuevas, uso de `seed_superadmin.py`, checklist de deploy); `CLAUDE.md` del proyecto actualizado (routers/ convention, modelos `Tenant`/`User`, env vars, anti-patrones para Senior Reviewer) — **nota**: `CLAUDE.md` está gitignorado en este repo, el cambio es solo local, no se propaga por git. **Confirmado con Luis (2026-07-06)**: el spec de auth multi-tenant SÍ satisface el prerequisito de roles para desbloquear `docs/manuals/user/{superadmin,admin,cliente}.md` — queda como tarea siguiente de Tech Writer, fuera de esta iteración.

**D2 completa — ITERACIÓN CERRADA (2026-07-06)**: mergeado a `master` (`5fcc1bd`) y desplegado a EC2 vía CI/CD. Se encontraron y corrigieron 2 problemas reales durante el rollout (no del código de la feature): (1) el workflow de CI no provisionaba Redis para el job de backend tests — 8 tests de auth fallaban por `ConnectionError`, fix en `4ccee30`; (2) el secret `EC2_HOST` de GitHub Actions apuntaba a una IP vieja de la instancia (sin Elastic IP, cambia en cada stop/start) — Luis lo actualizó manualmente. Checklist verificado en producción: CI verde, tablas `tenants`/`users` + columna `brands.tenant_id` existen, `tenant_backfill_v1` corrió (1 tenant, 1 brand, 0 fallos), login real con superadmin sembrado devuelve 200. Detalle completo en `docs/operations/post-deploy-alignment.md` (Iteración 7). **Manuales de usuario por rol completos (2026-07-06)**: `docs/manuals/user/{superadmin,admin,cliente}.md`, escritos a partir del comportamiento real de cada pantalla (Synthesis Studio, Intelligence Hub, Brand Directory, Strategic Assets, Template Merge). **2 hallazgos reales documentados** (no arreglados, solo documentados tal cual están hoy): (1) el botón "Reset System"/"Factory Reset" es visible para todos los roles pero el endpoint es `superadmin`-only — `admin`/`cliente` reciben error si lo usan; (2) la opción "★ SUPERUSER / ALL ACCESS" en los dropdowns de Identity quedó de una época pre-multi-tenant — el backend ya la restringe correctamente a `superadmin` (ver comentarios en `main.py` sobre el reemplazo del sentinel legacy `brand_id=-1`), pero el frontend no oculta la opción para `admin`/`cliente`, que verán un error 403 si la eligen. Ambos son candidatos a un fix de UI (ocultar condicionalmente por rol), pendiente de decisión de Luis.

**Pendiente fuera de esta iteración**: considerar Elastic IP para EC2; decidir si se arregla el gateo por rol de "Reset System" y "SUPERUSER / ALL ACCESS" en el frontend.

**Pendiente**: rotar `SUPERADMIN_PASSWORD` en EC2 a un valor fuerte antes del merge a `master`, correr D2, y (nueva tarea siguiente) manuales de usuario por rol.
**Rama**: `feature/auth-multitenant` (no existe rama activa hoy — crear al arrancar B1)

## Orden de ejecución

```
D1 (env vars + deps) ── en paralelo, no bloquea el arranque de B1

B1 (Tenant/User models + backfill) ──▶ B2 (security.py + schemas) ──▶ B3 (dependencies.py + rate limit)
                                                                            │
                                                                            ▼
                                                                     B4 (routers/auth.py)
                                                                       │            │
                                                                       ▼            ▼
                                                                B5 (routers/users.py)  B6 (retrofit auth en rutas existentes)
                                                                                        │
                                                                                        ▼
                                                                        B7 (scoping: brand+generation) ──▶ B8 (scoping: library+template-merge)
                                                                                                                     │
                                                                                                                     ▼
                                                                                                              B9 (QA backend)

F1 (AuthService+interceptor+guards) ──▶ F2 (login/register pages) ──▶ F3 (gate páginas existentes) ──▶ F4 (QA frontend)
   ↑ depende solo del contrato de B4, no espera a B5-B8              ↑ depende también de B7, B8

D2 (verificación post-merge) — corre después de B9 y F4
T1 (Tech Writer) — en paralelo desde B1, cierra junto con B5/F2
```

Backend y Frontend trabajan en paralelo desde que el contrato de B4 está definido (F1 no necesita esperar a B5-B8). Dentro de Backend, B7/B8 son secuenciales entre sí — ambas tocan `main.py` y las lleva el mismo dev para evitar conflictos de merge.

---

### B1 — Modelos `Tenant`/`User` + backfill

**Agent**: Backend Dev · **Depends on**: none · **Estimación**: 3-4 h

`UserRole(str, Enum)` (superadmin/admin/cliente); `Tenant` (id, name, is_active, created_at); `User` (id, email único, hashed_password, role, tenant_id nullable, is_active, created_at); `Brand.tenant_id` (ALTER idempotente en `database.py`, nullable por ahora). Alta de `tenant_backfill_v1` en `ALIGNMENT_REGISTRY`: un `Tenant` "{brand.name} (legacy)" por cada `Brand` con `tenant_id IS NULL`. Entrada en `docs/operations/post-deploy-alignment.md` (la documenta el mismo Backend Dev, no esperar a T1).

**Files**: `backend/models.py`, `backend/database.py`, `services/core/data_alignment_service.py`, `docs/operations/post-deploy-alignment.md`
**Acceptance**: modelos creados; alignment idempotente (correrlo dos veces no duplica tenants); `Brand` preexistente queda con `tenant_id` asignado tras un arranque.

---

### B2 — `security.py` + `schemas.py`

**Agent**: Backend Dev · **Depends on**: B1 · **Estimación**: 2-3 h

Hashing de password con `passlib[bcrypt]`; encode/decode de JWT con `python-jose` (access ~15 min, refresh ~7 días vía `JWT_ACCESS_TOKEN_TTL_MINUTES`/`JWT_REFRESH_TOKEN_TTL_DAYS`); Pydantic schemas `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `TokenResponse`, `UserOut` (nunca serializa `hashed_password`).

**Files**: `backend/auth/security.py` (nuevo), `backend/auth/schemas.py` (nuevo)
**Acceptance**: hash/verify roundtrip correcto; token expirado/con firma inválida falla al decode; `UserOut` nunca expone el hash.

---

### B3 — `dependencies.py` + rate limiting de login

**Agent**: Backend Dev · **Depends on**: B2 · **Estimación**: 3 h

`get_current_user` (401 si token inválido/expirado/usuario inactivo); `require_role(*roles)`; `require_tenant_access(brand_id)` (bypass explícito para `superadmin`, nunca por `tenant_id IS NULL` incidental); dependencia `check_login_rate_limit` — contador en Redis `login_attempts:{ip}:{email}`, ventana deslizante, 429 antes de comparar password (`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/`_WINDOW_SECONDS`).

**Files**: `backend/auth/dependencies.py` (nuevo)
**Acceptance**: `superadmin` nunca bloqueado por scoping; `admin`/`cliente` con `brand_id` de otro tenant → 403; 6º intento de login en la ventana → 429.

---

### B4 — `routers/auth.py` + `auth_service.py`

**Agent**: Backend Dev · **Depends on**: B3 · **Estimación**: 4 h

`POST /register` (crea `Tenant` + `User` rol `admin`), `POST /login`, `POST /refresh` (rota el refresh token en Redis), `POST /logout` (revoca), `GET /me`. Lógica de negocio en `services/core/auth_service.py` (routers solo glue, según convención del proyecto).

**Files**: `backend/routers/auth.py` (nuevo), `services/core/auth_service.py` (nuevo), `backend/main.py` (incluir router)
**Acceptance criteria** de la spec: registro/login/refresh/logout/credenciales inválidas/email duplicado, todos los casos de la sección "Acceptance criteria" relacionados con `/api/auth/*`.

---

### B5 — `routers/users.py`

**Agent**: Backend Dev · **Depends on**: B4 · **Estimación**: 2 h

`POST /api/users` (admin crea `cliente` en su propio tenant), `GET /api/users` (scopeado a tenant; `superadmin` ve todos), `PATCH /api/users/{id}/deactivate`. Gestionar usuario de otro tenant → 403.

**Files**: `backend/routers/users.py` (nuevo), `backend/main.py`
**Acceptance**: criterios de gestión de usuarios de la spec (admin scopeado, cliente sin acceso, 403 cross-tenant).

---

### B6 — Retrofit: `get_current_user` en rutas existentes (sin scoping)

**Agent**: Backend Dev · **Depends on**: B4 · **Estimación**: 4 h

Agregar `Depends(get_current_user)` a **todas** las rutas existentes de `main.py` (brand, generación, library/portfolios, template-merge, asset-library). Ningún cambio de comportamiento más allá de exigir token válido — el scoping por tenant se agrega en B7/B8. PR mecánico, revisable como diff de decoradores.

**Files**: `backend/main.py`
**Acceptance**: toda ruta sin token devuelve 401; con token válido de cualquier rol, comportamiento igual al actual (todavía sin scoping).

---

### B7 — Scoping por tenant: brand + generación

**Agent**: Backend Dev · **Depends on**: B6 · **Estimación**: 3 h

Aplicar `require_tenant_access` a las rutas de `Brand` (upload, listado, detalle) y de `GenerationJob` (crear, status, resume). `admin`/`cliente` que apuntan a un `brand_id` fuera de su tenant → 403; `superadmin` sin restricción.

**Files**: `backend/main.py`
**Acceptance**: criterio "403 cross-tenant" de la spec verificado en estas rutas específicamente.

---

### B8 — Scoping por tenant: library/portfolios + template-merge

**Agent**: Backend Dev · **Depends on**: B6 (secuencial tras B7, mismo archivo) · **Estimación**: 3 h

Mismo patrón que B7 aplicado a `/api/library/portfolios/*` y `/api/template-merge/*`.

**Files**: `backend/main.py`
**Acceptance**: mismo criterio 403 cross-tenant, ahora cubriendo estas rutas.

---

### B9 — Tests backend: fuga cross-tenant + JWT + rate limit

**Agent**: QA · **Depends on**: B7, B8 · **Estimación**: 4 h

Checklist ruta por ruta (todas las tocadas en B6-B8): sin token → 401; token de otro tenant → 403; `superadmin` sin restricción. JWT malformado/expirado/manipulado → 401, nunca 500. Rate limit → 429 al superar umbral. Timing de login (usuario inexistente vs password incorrecta) no debe permitir enumeración de emails.

**Files**: `backend/tests/test_auth.py` (nuevo)
**Acceptance**: suite completa en verde; checklist de rutas adjunto como comentario/fixture en el test file.

---

### F1 — `AuthService` + interceptor + guards

**Agent**: Frontend Dev · **Depends on**: contrato de B4 (no espera a B5-B8) · **Estimación**: 4 h

`auth.service.ts` (login/register/logout/refresh, `BehaviorSubject` de usuario/rol; access token en memoria, refresh token en `localStorage` — tradeoff documentado en el design doc); `auth.interceptor.ts` (adjunta Bearer, un solo refresh en vuelo con cola para 401 concurrentes, logout+redirect si el refresh también falla); `auth.guard.ts`; `role.guard.ts`.

**Files**: `frontend/src/app/services/auth.service.ts` (nuevo), `frontend/src/app/interceptors/auth.interceptor.ts` (nuevo), `frontend/src/app/guards/auth.guard.ts` (nuevo), `frontend/src/app/guards/role.guard.ts` (nuevo)
**Acceptance**: interceptor no dispara N refresh en paralelo ante N 401 simultáneos; guard redirige a `/login` sin sesión.

---

### F2 — Páginas de login/registro

**Agent**: Frontend Dev · **Depends on**: F1 · **Estimación**: 3 h

Componentes standalone `pages/login/`, `pages/register/` + rutas. Registro crea tenant+admin (mensaje de éxito acorde, no dice "cliente creado").

**Files**: `frontend/src/app/pages/login/*`, `frontend/src/app/pages/register/*`, archivo de rutas de la app
**Acceptance**: login/registro exitoso navega a la vista principal; error de credenciales muestra mensaje genérico.

---

### F3 — Gatear páginas existentes + nav por rol

**Agent**: Frontend Dev · **Depends on**: F1, F2, B7, B8 · **Estimación**: 3 h

`auth.guard` en las rutas de `brand-hub`, `brand-manager`, `generator`, `asset-library`, `template-merge`. Ocultar en el nav las acciones de gestión de usuarios si el rol activo es `cliente` — lógica centralizada vía el observable de rol de `AuthService`, no duplicada por componente.

**Files**: archivo de rutas de la app, `frontend/src/app/components/layout/sidebar/*`
**Acceptance**: `cliente` no ve el ítem de gestión de usuarios; navegación no autenticada a cualquier página protegida redirige a `/login`.

---

### F4 — Tests frontend: flujo de auth

**Agent**: QA · **Depends on**: F3 · **Estimación**: 2 h

Specs Karma: guard redirige sin sesión; interceptor adjunta el token y dedup­lica refresh ante 401 concurrentes; logout limpia estado y redirige.

**Files**: `frontend/src/app/services/auth.service.spec.ts`, `frontend/src/app/interceptors/auth.interceptor.spec.ts`, `frontend/src/app/guards/auth.guard.spec.ts`
**Acceptance**: `npx ng test --watch=false --browsers=ChromeHeadless` en verde.

---

### D1 — Env vars y dependencias nuevas

**Agent**: DevOps · **Depends on**: none (en paralelo, debe estar listo antes de mergear B4) · **Estimación**: 2 h

Agregar a `backend/requirements.txt`: `passlib[bcrypt]`, `python-jose[cryptography]`. Nuevas env vars (`JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_TTL_MINUTES`, `JWT_REFRESH_TOKEN_TTL_DAYS`, `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS`, `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD`) en `.env.example`, `docker-compose.yml` y GitHub Actions secrets para el deploy a EC2. Script `utils/seed_superadmin.py` (siembra el superadmin inicial, idempotente).

**Files**: `backend/requirements.txt`, `.env.example`, `docker-compose.yml`, `backend/utils/seed_superadmin.py` (nuevo)
**Acceptance**: `docker compose up --build` levanta con las nuevas env vars documentadas; superadmin sembrado existe tras el primer arranque y el script no lo duplica en el segundo.

---

### D2 — Verificación post-merge

**Agent**: DevOps · **Depends on**: B9, F4 (corre tras el merge) · **Estimación**: 1 h

Checklist post-deploy: CI en verde (pytest + Karma); columnas `tenants`/`users`/`brands.tenant_id` existen en EC2; `tenant_backfill_v1` corrió (brands preexistentes con `tenant_id` no nulo); login real contra producción con el superadmin sembrado.

**Files**: ninguno (verificación)
**Acceptance**: checklist completo y reportado; entrada agregada a `docs/operations/post-deploy-alignment.md` (Iteración correspondiente).

---

### T1 — Documentación

**Agent**: Tech Writer · **Depends on**: none, en paralelo desde B1 · **Estimación**: 4 h

API docs de `/api/auth/*` y `/api/users` (auth, roles, request/response, errores); `CLAUDE.md` del proyecto (nuevo módulo `backend/auth/`, convención de `routers/`, nuevas env vars, nuevas deps); actualización de `docs/architecture/GuepardAI-overview.md` (nuevos componentes `Tenant`/`User`, límite de auth); `docs/manuals/technical/` (env vars nuevas para deploy, uso de `seed_superadmin.py`). Confirmar con Luis si esta spec satisface el prerequisito de `docs/specs/roles-de-usuario.md` que hoy bloquea los manuales de usuario por rol — si sí, iniciar `docs/manuals/user/{superadmin,admin,cliente}.md` como tarea siguiente, no en esta iteración.

**Files**: `docs/architecture/GuepardAI-overview.md`, `GuepardAI/CLAUDE.md`, `docs/manuals/technical/*`, doc de API (ubicación según convención existente del proyecto)
**Acceptance**: ningún endpoint nuevo sin documentar; `CLAUDE.md` refleja el módulo `backend/auth/` y las env vars nuevas.

---

## Resumen

| Agente | Tareas | Horas est. |
|---|---|---|
| Backend Dev | B1-B8 | 24-26 h |
| Frontend Dev | F1-F3 | 10 h |
| QA | B9, F4 | 6 h |
| DevOps | D1, D2 | 3 h |
| Tech Writer | T1 | 4 h |

**Arranque propuesto**: crear la rama `feature/auth-multitenant`; B1 y D1 en paralelo; F1 puede empezar en cuanto el contrato de B4 esté definido (no necesita esperar a que B4 esté mergeado, solo el shape de request/response). T1 arranca desde B1 y cierra junto con B5/F2.
