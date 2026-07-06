# Spec: Autenticación, Roles Multi-Usuario y Base Multi-Tenant

**Date**: 2026-07-05
**Requested by**: Luis
**Status**: Approved — confirmado por Luis 2026-07-05 (ver decisiones cerradas abajo)
**Project**: GuepardAI

## Problem

Toda la API de GuepardAI está hoy sin autenticación. La única verificación existente es un `ADMIN_TOKEN` en texto plano comparado por query param, usado solo por `DELETE /api/admin/reset-db` (`backend/main.py:927-935`) — no hay hashing, no hay esquema, no se reutiliza en ningún otro endpoint. No existe modelo `User`, no hay sesión, no hay roles, no hay concepto de tenant/organización (confirmado: cero referencias a `User`/`role`/`tenant` en `backend/models.py`, cero rutas de login en `backend/main.py`, cero librerías de auth en `requirements.txt`, cero infraestructura de auth en el frontend Angular).

A medida que GuepardAI onboardea clientes reales, la plataforma necesita: (1) identidad de usuario, (2) control de acceso por rol, y (3) una base de datos que soporte aislar la información de una organización cliente de otra — hoy cualquiera con la URL puede leer o generar sobre cualquier `Brand`. Esto es un requisito de seguridad indispensable antes de seguir escalando el onboarding.

## Solution summary

Introducir una entidad `Tenant` (organización) como límite de propiedad por encima de `Brand` (un tenant puede tener una o más brands; hoy será típicamente 1:1, pero el esquema soporta más desde el día uno). Agregar un modelo `User` con `role` (`superadmin`, `admin`, `cliente`) y `tenant_id` (nulo solo para `superadmin`). Implementar login basado en JWT (access token corto + refresh token largo, revocable vía Redis), hashing de contraseñas con bcrypt, y dependencias de autorización reutilizables que se aplican sobre las rutas existentes para scopear cada consulta al `tenant_id` del usuario autenticado (excepto `superadmin`, que ve todo). En el frontend: login/registro, un `AuthService`, un interceptor HTTP que adjunta el token y maneja refresh en 401, y guards de ruta por rol.

## Users and roles

| Rol | Alcance | Puede hacer |
|---|---|---|
| `superadmin` | Global (todas las tenants/brands) | Todo — soporte, administración de plataforma, crear/desactivar tenants y admins |
| `admin` | Su propio tenant | Gestiona el/los Brand(s) de su tenant, crea/desactiva usuarios `cliente` de su tenant, no ve otros tenants |
| `cliente` | Su propio tenant | Sube documentos de marca, genera presentaciones dentro de las brands de su tenant; no administra usuarios |

**Resolución de auto-registro (confirmado por Luis):** el registro público crea un tenant nuevo **y promueve al registrante a `admin` de ese tenant** (es el único usuario, debe poder gestionar su marca e invitar `cliente`s después). Los usuarios `cliente` puros se crean por invitación de un `admin` ya existente dentro de un tenant, no por registro público directo. `superadmin` nunca se crea por registro — solo por seed/script, igual que `ADMIN_TOKEN` hoy.

## Acceptance criteria

- [ ] `POST /api/auth/register` crea un `Tenant` nuevo + un `User` con rol `admin` en ese tenant, devuelve `access_token` + `refresh_token`
- [ ] `POST /api/auth/login` con credenciales válidas devuelve `access_token` (TTL corto, ~15 min) + `refresh_token` (TTL largo, ~7 días)
- [ ] `POST /api/auth/login` con credenciales inválidas devuelve 401 con mensaje genérico (no revela si el email existe)
- [ ] `POST /api/auth/refresh` con un refresh token válido devuelve un nuevo `access_token` (y rota el refresh token); con uno expirado/revocado devuelve 401
- [ ] `POST /api/auth/logout` revoca el refresh token (ya no puede usarse para refrescar)
- [ ] Cualquier endpoint protegido sin token, con token expirado o con token manipulado devuelve 401
- [ ] `superadmin` puede acceder a datos de cualquier tenant; `admin`/`cliente` que intentan acceder a un `brand_id`/recurso que no pertenece a su tenant reciben 403
- [ ] `admin` puede crear/desactivar usuarios `cliente` solo dentro de su propio tenant; intentar gestionar usuarios de otro tenant devuelve 403
- [ ] `cliente` no puede acceder a endpoints de gestión de usuarios (403)
- [ ] Las filas existentes de `Brand`/`GenerationJob`/`CorporateKnowledge`/`BrandAsset`/etc. quedan con `tenant_id` asignado vía data alignment (siguiendo el patrón `ALIGNMENT_REGISTRY` del proyecto) — sin comando manual
- [ ] Contraseñas almacenadas con hash (bcrypt), nunca logueadas ni devueltas en ninguna respuesta de API
- [ ] Frontend: un usuario no autenticado que navega a una ruta protegida es redirigido a `/login`
- [ ] Frontend: una respuesta 401 dispara un intento de refresh una sola vez; si el refresh también falla, el usuario es deslogueado y redirigido a `/login`
- [ ] Frontend: elementos de navegación/acciones se ocultan o deshabilitan según el rol (ej. un `cliente` no ve la sección de gestión de usuarios)
- [ ] `POST /api/auth/login` aplica rate limiting básico por IP+email (ventana deslizante en Redis); al superar el umbral devuelve 429 sin importar si las credenciales enviadas son correctas

## Edge cases and error scenarios

- Payload de login/registro vacío o malformado → 422 (validación Pydantic)
- Email duplicado en registro → 409 Conflict
- Reintento de un refresh token ya rotado/usado → se revoca toda la sesión de ese usuario (mitigación de replay); a confirmar si esta dureza aplica desde v1 o es fast-follow (ver Open Questions)
- Carrera de refresh concurrente en el frontend (dos requests 401 simultáneos) → el interceptor debe encolar/deduplicar la llamada de refresh, no disparar dos refresh en paralelo
- Tenant recién creado sin ninguna `Brand` todavía → endpoints de generación/ingestión devuelven un error claro ("no hay marca configurada"), no un 500
- Usuario desactivado que intenta loguearse → 401, mismo mensaje genérico que credenciales inválidas
- `superadmin` nunca debe quedar sujeto a un filtro `tenant_id` por accidente (bypass explícito en la dependencia de autorización, no "tenant_id que coincide por casualidad")
- Falla de Redis (donde viven los refresh tokens) → login/access token siguen funcionando (JWT es stateless), pero refresh/logout deben fallar de forma explícita (503), no silenciosa

## Out of scope

- SSO / login social (Google, Microsoft)
- Permisos finos dentro de un mismo tenant (ej. que un `cliente` no vea los jobs de otro `cliente` del mismo tenant) — v1 asume que todos los usuarios de un tenant ven todo lo de su tenant
- UI de gestión de múltiples brands por tenant (el esquema lo soporta; la pantalla para agregar una 2da brand a un tenant existente es trabajo futuro)
- Reseteo de contraseña por email / verificación de email — **confirmado fast-follow**: entra como spec inmediatamente después de cerrar esta iteración, no bloquea el cierre de esta

## Open questions

Todas las preguntas bloqueantes para el Architect quedaron resueltas por Luis el 2026-07-05 (ver "Resolución de auto-registro" arriba, rate limiting en Acceptance criteria, y reset de contraseña en Out of scope). Queda una decisión puramente técnica para el Architect, ya resuelta en el diseño:

- [Architect] ¿Revocación de refresh tokens vía Redis (key por `jti` con TTL) o tabla `RefreshToken` en Postgres? → **Resuelto en `docs/designs/autenticacion-multitenant-design.md` §2.4**: Redis, ya es dependencia dura por Celery.

## References

- Modelo `Brand` y su rol como límite de scoping de facto hoy: `backend/models.py:42-61` (y `brand_id` en `BrandVisualDna:68`, `BrandAsset:107`, `BrandArtisticEssence:149`, `BrandPremiumVisualPattern:210`, `GenerationJob:248`, `CorporateKnowledge:291`, `TemplateMergeJob:464`)
- Único precedente de "auth" existente (a reemplazar, no a imitar): `backend/main.py:927-935` (`ADMIN_TOKEN` en texto plano)
- Convención de enums de estado a seguir para `role`: `backend/models.py:21` (`GenerationJobStatus(str, Enum)`)
- Convención de alineación de datos post-deploy: `services/core/data_alignment_service.py`, `ALIGNMENT_REGISTRY`, `docs/operations/post-deploy-alignment.md`
- Specs previas que documentaban explícitamente "single role / sin usuarios" (ahora superadas por esta spec): `docs/specs/gestion-portfolios.md:24-26,111`, `docs/specs/template-merge.md:25-27`
