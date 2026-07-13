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

## Follow-up: shared tenant scope for Departments + Users (same day)

### `routers/users.py`

`list_users` gained an optional `tenant_id` query param, honored only for
`SUPERADMIN` (identical pattern to `departments.py::list_departments`):

```python
def list_users(tenant_id: Optional[int] = None, ...):
    query = _tenant_scoped_users(db, current_user)
    if current_user.role == SUPERADMIN and tenant_id is not None:
        query = query.filter(models.User.tenant_id == tenant_id)
    return query...
```

### `admin.component.ts`

`newDepartmentTenantId` (create-department-only) became `selectedTenantId` —
one piece of state now driving four things for a superadmin: the Departments
list filter, the Users list filter, and the target tenant for both "Create
Department" and the new "Create User". `onTenantScopeChange()` reloads both
lists and clears `assignUserId`/`assignDepartmentId` so a stale cross-tenant
pick can't survive a scope switch. This makes the 403 structurally
unreachable through the UI: the two dropdowns feeding `assignDepartment()`
can never contain entries from different tenants once a scope is selected.

`admin.component.html` gained a "Managing Tenant" card (superadmin-only, top
of the Departments tab) and a "Create User" card (email + password,
`createUser()` → `POST /api/users`).

## Follow-up #2: a new Tenant was invisible without a Brand

### `main.py` — `/api/brands`

`_serialize_brand()` gained `tenant_id`/`tenant_name` (`Brand.tenant` was
already a relationship — `back_populates="brands"` on `Tenant`, unlike
`Department.tenant` which is one-directional). `list_brands()` now accepts an
optional `tenant_id`, honored only for superadmin, with `joinedload` to avoid
N+1 — same pattern as `departments.py`/`users.py`. `create_brand()` now 422s
if a superadmin omits `tenant_id`, closing the path that silently produced an
"unaligned" Brand (`tenant_id IS NULL`, invisible to `admin`/`cliente` since
their list query is `tenant_id == current_user.tenant_id`, never `IS NULL`).
`admin`/`cliente` callers are unaffected — `tenant_id` was already implicit to
`current_user.tenant_id` for them and still is.

These are edits to existing legacy routes, not new ones — stayed in `main.py`
rather than moving to `routers/`, consistent with "new routes go in
`routers/`, existing legacy routes stay where they are" from CLAUDE.md.

### `brand.service.ts` / `brand-hub.component.ts` / `.html`

Same shape as the Departments/Users fix: `getBrands(tenantId?)` /
`createBrand(..., tenantId?)` gain the parameter; `BrandHubComponent` gains
`tenants: Tenant[]`, `selectedTenantId`, `loadTenants()` (superadmin only,
loaded in `ngOnInit`), and `onTenantScopeChange()` that reloads `officialBrands`
scoped to the new tenant. `createNewBrand()` blocks (with an `alert()`,
matching this component's existing error-handling convention — it doesn't use
the `.detail-error` paragraph pattern `admin.component.ts` uses) when a
superadmin hasn't picked a tenant. The selector renders as a second
`.brand-registry-pill` in the page header, `*ngIf="isSuperadmin"`.

`brand-hub.component.spec.ts` is new — the component had zero test coverage
before this change. Scope was kept to the tenant-scoping logic actually added
(not a full retrofit of the pre-existing upload/polling/footer logic, which
was out of scope for this fix).

## Testing

- `backend/tests/test_tenants_routes.py` — role gating (403 for admin/cliente),
  successful creation, duplicate email (409), short password (422), list
  scoping.
- `backend/tests/test_departments_routes.py` — added a `tenant_name` assertion.
- `backend/tests/test_users_routes.py` — `tenant_id` filter (superadmin-only,
  ignored for admin).
- `backend/tests/test_tenant_scoping.py` — `tenant_id` filter on `/api/brands`,
  `tenant_name` in response, 422 when superadmin omits `tenant_id`, successful
  targeted creation.
- `frontend/.../admin.component.spec.ts` — tenant load on init, `createTenant()`
  success/error/blank-field paths, `tenantName()` resolution, `createUser()`,
  `onTenantScopeChange()`.
- `frontend/.../brand-hub.component.spec.ts` (new) — tenant load on init,
  scoped `createNewBrand()`/`onTenantScopeChange()`.
- Manual verification: Playwright against the local Docker stack for all three
  rounds (Tenants tab → dropdowns; Departments/Users scope + assign; Brand
  Directory scope + blocked-without-tenant), including the negative case
  (create blocked without a tenant selected) each time.
