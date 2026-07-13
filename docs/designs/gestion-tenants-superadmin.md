# Design: Gestión de Tenants por el Superadmin

**Date**: 2026-07-12
**Status**: Implemented
**Spec**: docs/specs/gestion-tenants-superadmin.md

## Backend

### `services/core/auth_service.py`

`register_user()`'s tenant+admin creation logic was extracted into a private
helper so it can be reused by the new superadmin-driven path without
duplicating the email-uniqueness check, the `IntegrityError` race handling, or
the tenant/admin creation itself:

```python
def _create_tenant_and_admin(db, email, password, tenant_name) -> Tuple[Tenant, User]: ...

def register_user(db, email, password, tenant_name=None) -> Tuple[User, str, str]:
    """Public self-registration — issues a token pair, user is logged in."""
    tenant, user = _create_tenant_and_admin(db, email, password, tenant_name or email)
    ...

def create_tenant_with_admin(db, tenant_name, admin_email, admin_password) -> Tuple[Tenant, User]:
    """Superadmin-driven — no tokens issued, superadmin keeps their own session."""
    return _create_tenant_and_admin(db, admin_email, admin_password, tenant_name)
```

### `routers/tenants.py` (new)

`GET /api/admin/tenants` and `POST /api/admin/tenants`, both gated by
`require_role(UserRole.SUPERADMIN.value)` — stricter than the `(ADMIN,
SUPERADMIN)` pattern used by `departments.py`/`users.py`, because tenant
creation and the full tenant list are platform-level operations, not
tenant-scoped ones. Router is thin glue calling `auth_service`, per project
convention.

### `models.py` — `Department.tenant`

```python
tenant = relationship("Tenant")

@property
def tenant_name(self) -> Optional[str]:
    return self.tenant.name if self.tenant else None
```

One-directional relationship (no `back_populates` on `Tenant.departments` —
nothing needs to walk from Tenant to its departments today, avoided per the
project's no-speculative-abstraction convention). `routers/departments.py`'s
`list_departments()` uses `.options(joinedload(models.Department.tenant))` so
listing N departments doesn't cost N extra queries (the project has a documented
history of N+1 bugs in this exact area — reviews/analytics — see commit
`7ee3a13`).

## Frontend

### `collaboration.service.ts`

Added `Tenant` / `TenantCreateResponse` interfaces and `getTenants()` /
`createTenant()`, alongside the existing `Department`/`getDepartments()` etc.
`Department.tenant_name` added to match the backend response.

### `admin.component.ts` / `.html`

- New `'tenants'` tab, gated by `*ngIf="isSuperadmin"` on both the tab button
  and its content — matches how the Moderation tab already gates its blocklist
  card.
- `tenants: Tenant[]` is loaded once in `ngOnInit()` (for superadmin) rather
  than per-tab, because it now feeds four different places: the Tenants tab
  itself, the Departments create-form dropdown, and the Analytics/Reports
  filter dropdowns.
- The three raw `<input type="number">` tenant filters became `<select>`
  bound to the same component fields they already used
  (`newDepartmentTenantId`, `analyticsTenantId`, `reportsTenantId`) — no
  business logic changed, only the input widget.
- `tenantName(id)` helper resolves an id to a name for display (department
  list, report scope tag) with a `—` fallback, mirroring the existing
  `departmentName(id)` helper already in the component.

## Testing

- `backend/tests/test_tenants_routes.py` — role gating (403 for admin/cliente),
  successful creation, duplicate email (409), short password (422), list
  scoping.
- `backend/tests/test_departments_routes.py` — added a `tenant_name` assertion.
- `frontend/.../admin.component.spec.ts` — tenant load on init, `createTenant()`
  success/error/blank-field paths, `tenantName()` resolution.
- Manual verification: Playwright against the local Docker stack (superadmin
  login → Tenants tab → create tenant → appears in Departments dropdown).
