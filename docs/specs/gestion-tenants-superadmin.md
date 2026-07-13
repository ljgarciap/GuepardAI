# Spec: Gestión de Tenants por el Superadmin + fix de selectores de tenant

**Date**: 2026-07-12
**Requested by**: Luis
**Status**: Implemented
**Project**: GuepardAI

## Problem

Reporte de Luis sobre el Admin Panel: el formulario "Create Department" mostraba
un input numérico crudo de `Tenant ID` — el superadmin tenía que conocer y
teclear un ID de base de datos sin ningún contexto. Investigación confirmó que el
mismo antipatrón se repetía en 3 lugares (`admin.component.html`): crear
departamento, filtro de Analytics y filtro de Reports; además la tabla de
departamentos mostraba `tenant_id` crudo en vez del nombre.

Segundo hallazgo: no existía ninguna vista para que el superadmin cree un Tenant
nuevo junto con su Admin inicial. El único camino para crear un Tenant era el
autoregistro público (`POST /api/auth/register`, ya cubre "el usuario que viene a
suscribirse" — sin cambios). `POST /api/users` (alta de usuario por un admin/
superadmin) fuerza `role=cliente` siempre, así que tampoco servía para este caso.

## Solution summary

1. **Selectores de tenant → dropdown real**: nuevo endpoint `GET
   /api/admin/tenants` (superadmin-only) alimenta un `<select>` en los 3 lugares
   que antes usaban un `<input type="number">`. `DepartmentOut` gana
   `tenant_name` (vía `Department.tenant` relationship + `joinedload`, sin N+1)
   para que la tabla de departamentos y el "scope" de un reporte muestren el
   nombre, no el ID.
2. **Alta de Tenant + Admin por el superadmin**: nuevo endpoint `POST
   /api/admin/tenants` (superadmin-only) — recibe `name`, `admin_email`,
   `admin_password` y crea el `Tenant` + su primer `User` rol `admin`, reusando
   la misma lógica interna que el autoregistro público
   (`auth_service._create_tenant_and_admin`, extraída de `register_user`).
3. Nueva pestaña "TENANTS" en el Admin Panel (`*ngIf="isSuperadmin"`): formulario
   de alta + listado (nombre, fecha de creación).

## Users and roles

- **Superadmin**: único rol que ve la pestaña Tenants, el endpoint `GET/POST
  /api/admin/tenants`, y los dropdowns de tenant en Departments/Analytics/Reports
  (para `admin`/`cliente` esos filtros ni siquiera aplican — su scope es siempre
  su propio tenant, sin selector).
- **Admin/Cliente**: sin cambios de acceso.

## Decisión de producto: cómo recibe la password el admin nuevo

Confirmado por Luis 2026-07-12, tres opciones evaluadas:
1. Password temporal + email de invitación automático.
2. **Superadmin ingresa la password directamente en el formulario — elegida para
   esta iteración.** El superadmin comunica la password al admin nuevo fuera de
   banda (Slack, Telegram, etc.).
3. Link de invitación de un solo uso, el admin define su propia password.

Luis confirmó explícitamente migrar a la opción 1 (password temporal + email, vía
`services/core/email_service.py`, ya existe con fallback tolerante si SMTP no
está configurado) en una iteración futura — no se construyó infraestructura
especulativa para eso ahora (el proyecto evita features/flags para requisitos
hipotéticos, ver CLAUDE.md), pero el endpoint (`create_tenant_with_admin`) queda
aislado en `auth_service.py` para que ese cambio no toque el router ni el
frontend, solo la implementación interna de esa función.

## Acceptance criteria

- [x] Superadmin ve un dropdown de tenants (no un input numérico) al crear un
      departamento, y al filtrar Analytics/Reports.
- [x] La tabla de departamentos muestra el nombre del tenant, no el ID.
- [x] Superadmin puede crear un Tenant nuevo + su Admin inicial desde el Admin
      Panel, sin pasar por el autoregistro público.
- [x] `admin`/`cliente` no pueden acceder a `GET/POST /api/admin/tenants` (403).
- [x] Email de admin duplicado → 409 (mismo criterio que `register_user` y
      `POST /api/users`).
- [x] Password < 8 caracteres → 422 (mismo mínimo que el resto del sistema de auth).

## Out of scope (este ciclo)

- Invitación por email con password temporal (ver decisión arriba).
- Editar/desactivar un Tenant existente desde el panel.
- Agregar un segundo admin a un tenant ya existente (hoy solo se crea el primero
  junto con el tenant; un segundo admin requeriría exponer `role` en `POST
  /api/users`, que hoy fuerza `cliente` siempre — no pedido por Luis en esta
  ronda).
