# Technical Design: Autenticación, Roles Multi-Usuario y Base Multi-Tenant

**Date**: 2026-07-05
**Author**: Architect
**Status**: Approved by Luis 2026-07-05 — ready for PM task breakdown
**Spec**: `docs/specs/autenticacion-multiusuario-multitenant.md`

---

## 1. Scope recap

Greenfield build — no existing `User`, JWT, session, RBAC or frontend auth code to reconcile with (confirmed by codebase survey). Three pieces, in dependency order:

| # | Piece | Depends on |
|---|---|---|
| 1 | `Tenant` + `User` models, JWT core (login/register/refresh/logout) | Nothing |
| 2 | Retrofit auth + tenant scoping across existing routes/services | (1) |
| 3 | Frontend auth (service, interceptor, guards, login/register pages) | (1), and (2)'s API contract |

No AI Decision Records needed — this spec has no AI/LLM touchpoints, so the AI Architect gate does not apply.

---

## 2. Data model

### 2.1 New tables (`backend/models.py`)

```python
class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    CLIENTE = "cliente"


class Tenant(Base):
    __tablename__ = "tenants"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    is_active  = Column(Integer, default=1)   # 0/1 convention, per project style
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    users  = relationship("User", back_populates="tenant")
    brands = relationship("Brand", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, nullable=False)   # UserRole value
    tenant_id       = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)  # null only for superadmin
    is_active       = Column(Integer, default=1)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)

    tenant = relationship("Tenant", back_populates="users")
```

`role` as `String` (not a native Postgres enum) to match the existing convention — `IngestionJobStatus`/`GenerationJobStatus` are `str, Enum` validated at the Python layer, not DB-level enums, so a new value never requires a migration.

### 2.2 Existing tables — additive column

`Brand` gains `tenant_id` (nullable at first, enforced not-null after backfill):

```python
tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
```

Added via the existing idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` mechanism in `database.py` — same pattern as `qa_forced`/`qa_retry_count` in the generation-pipeline-overhaul design. No other table needs a direct `tenant_id` — every domain table already keys off `brand_id` (`BrandVisualDna`, `BrandAsset`, `BrandArtisticEssence`, `BrandPremiumVisualPattern`, `GenerationJob`, `CorporateKnowledge`, `TemplateMergeJob`), so tenant scoping for those is a join through `Brand.tenant_id`, not a duplicated column. This keeps the blast radius of the schema change to two new tables + one new column.

### 2.3 Data alignment — backfill

Register `tenant_backfill_v1` in `ALIGNMENT_REGISTRY` (`services/core/data_alignment_service.py`), following the project's mandatory convention for one-time data fixes:

- For each existing `Brand` with `tenant_id IS NULL`: create one `Tenant` named `"{brand.name} (legacy)"`, set `brand.tenant_id`.
- Idempotent (only touches `tenant_id IS NULL` rows), no LLM tokens spent, safe to run on every boot.
- Document in `docs/operations/post-deploy-alignment.md` per the project's non-negotiable rule (a backfill without a documented entry there doesn't count as done).
- Runs before `tenant_id` is made `NOT NULL` in a later cleanup step — do **not** enforce not-null in the same release, to avoid a startup race between the alignment task and route traffic.

### 2.4 Refresh token storage — Redis, not a table

Decision (resolves the spec's open question): refresh tokens are **not** persisted in Postgres. On issuance, store `refresh:{jti} → user_id` in Redis with `EX` = refresh TTL (7 days). Rotation: on `/api/auth/refresh`, delete the old key and issue a new one atomically. Logout: delete the key. Rationale: Redis is already a hard dependency (Celery broker) so this adds no new infrastructure; revocation is O(1); no extra table/migration for something that's inherently ephemeral session state, not a durable business record.

---

## 3. Backend implementation

### 3.1 New module `backend/auth/`

```
backend/auth/
  security.py       # password hashing (passlib[bcrypt]), JWT encode/decode (python-jose)
  dependencies.py    # get_current_user, require_role(*roles), require_tenant_access(brand_id)
  schemas.py         # RegisterRequest, LoginRequest, TokenResponse, UserOut, RefreshRequest
```

`dependencies.py` — the two reusable pieces every other route will import:

```python
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    # decode JWT, 401 on invalid/expired, load User, 401 if inactive
    ...

def require_role(*roles: UserRole):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return checker

def require_tenant_access(brand_id: int):
    # superadmin bypasses; admin/cliente: 403 if Brand.tenant_id != user.tenant_id
    ...
```

`require_tenant_access` is the single choke point every existing brand-scoped route will call — this is what makes the retrofit in §3.3 mechanical rather than ad hoc.

### 3.2 New routers

New `APIRouter`s (not more inline routes in `main.py`, which is already large — this is the one structural call in this design):

- `backend/routers/auth.py` → `/api/auth/register`, `/login`, `/refresh`, `/logout`, `/me`
- `backend/routers/users.py` → `/api/users` (admin: CRUD `cliente` users in own tenant; superadmin: CRUD anyone)

Both included in `main.py` via `app.include_router(...)`, consistent with `AgentOrchestrator` owning pipeline logic and `tasks.py` staying thin — these routers hold only request/response glue, business logic (`create_user`, `authenticate_user`) lives in a new `services/core/auth_service.py`.

### 3.3 Retrofitting existing routes (the largest item)

Every existing route in `main.py` that touches `Brand`/`GenerationJob`/`CorporateKnowledge`/`BrandAsset`/etc. gets:

```python
def some_existing_route(
    brand_id: int,
    user: User = Depends(require_tenant_access_factory(...)),  # or get_current_user + explicit check
    db: Session = Depends(get_db),
):
```

Risk-managed rollout, not a big-bang PR:
1. Land auth core (§3.1–3.2) behind the existing unauthenticated surface — no route requires a token yet.
2. Add `Depends(get_current_user)` to every route (auth required, no scoping yet) — one PR, mechanical, reviewable as a diff of decorators.
3. Add `require_tenant_access` scoping route-by-route, grouped by domain (brand routes, generation routes, library/portfolio routes, template-merge routes) — separate PRs per domain so Senior Reviewer can verify each surface independently.
4. QA maintains a checklist enumerating every route and its expected 403 behavior (see §6) — this is the artifact that catches a missed route, not code review alone.

### 3.4 Dependencies

Add to `backend/requirements.txt`:
```
passlib[bcrypt]
python-jose[cryptography]
```

New env vars (add to `.env.example`, `docker-compose.yml`, and GitHub Actions secrets for EC2 deploy — DevOps sign-off required, see Gate A):
```
JWT_SECRET_KEY=...
JWT_ACCESS_TOKEN_TTL_MINUTES=15
JWT_REFRESH_TOKEN_TTL_DAYS=7
```
Read via `get_system_config()`-style pattern is not appropriate here (these are secrets/security parameters, not tunable business config) — plain `os.getenv` with no DB fallback, consistent with how `ADMIN_TOKEN` is read today.

### 3.5 Rate limiting on `/api/auth/login`

Confirmed in scope for v1. Sliding-window counter in Redis keyed by `login_attempts:{ip}:{email}` (both, not just IP — a distributed attacker rotating IPs against one email is the more realistic threat here). Increment on every attempt (success or failure), TTL = window length (e.g. 60s), threshold configurable via env (`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS`, sane defaults 5/60). Exceeding the threshold returns 429 before any password comparison runs (avoids wasting a bcrypt hash cycle on requests that are already going to be rejected). Implemented as a dependency (`Depends(check_login_rate_limit)`) ahead of `get_current_user`-style logic in the login route, not middleware — keeps it scoped to the one endpoint that needs it rather than globally throttling the API.

### 3.6 Self-registration semantics

Per the spec's proposed resolution: `POST /api/auth/register` always creates a new `Tenant` + a `User` with role `admin` (never bare `cliente`). `cliente` users are only created via `POST /api/users` by an existing `admin`/`superadmin` of that tenant. `superadmin` accounts are never created through any API route — seeded only, via a `utils/seed_superadmin.py` script reading `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` env vars at first boot (mirrors the existing `ADMIN_TOKEN` env-var precedent, replaces it for anything beyond the one destructive reset route).

---

## 4. Frontend implementation (Angular)

Confirmed today: zero auth infra (no guard, interceptor, login component, or auth service anywhere in `frontend/src`).

- `services/auth.service.ts` — `login()`, `register()`, `logout()`, `refresh()`, holds current user/role in a `BehaviorSubject`, persists tokens (access in memory, refresh in `httpOnly`-equivalent... browser can't set httpOnly from JS, so refresh token goes in `localStorage` with the accepted tradeoff documented, access token in memory only to limit XSS exposure window).
- `interceptors/auth.interceptor.ts` — attaches `Authorization: Bearer {access_token}` to every request; on 401, attempts exactly one `refresh()`, queues concurrent in-flight requests during that single refresh (a `Subject`-based lock, not a naive per-request refresh) so N parallel 401s don't fire N refresh calls; on refresh failure, calls `logout()` and redirects to `/login`.
- `guards/auth.guard.ts` — blocks unauthenticated access to any protected route, redirects to `/login`.
- `guards/role.guard.ts` — route-level role gate (e.g., user-management pages require `admin`/`superadmin`).
- `pages/login/`, `pages/register/` — new standalone components.
- Existing pages (`brand-hub`, `brand-manager`, `generator`, `asset-library`, `template-merge`) get wrapped by `auth.guard` in the route config; no internal changes to those components' logic beyond hiding role-gated UI affordances (e.g., a `cliente` doesn't see "manage users" nav item — driven by the same `AuthService` role observable, not duplicated logic per component).

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Retrofitting scoping across ~40 existing routes — missing one leaks cross-tenant data | Central `require_tenant_access` choke point (§3.1) + QA route-by-route checklist (§6), rollout in domain-grouped PRs (§3.3) reviewed independently |
| Production already has real `Brand` data with no tenant | `tenant_backfill_v1` data alignment (§2.3), documented per project convention, runs automatically at boot before scoping is enforced |
| Frontend has zero auth infra — building it is not incremental, it's new | Build service/interceptor/guards first (can be developed against a mocked backend contract in parallel with §3), gate existing pages last |
| New secret (`JWT_SECRET_KEY`) needed in prod | DevOps Gate A below — must land in EC2 env and GitHub secrets before deploy, not after |
| Self-registration semantics were ambiguous in the raw requirement | Resolved explicitly in §3.5; flagged to Luis in the spec's Open Questions for final confirmation |
| Refresh token in `localStorage` is readable by any injected script (XSS) | Documented tradeoff, not silently accepted: access token is memory-only and short-lived (15 min) specifically to bound the damage if `localStorage` is compromised; revisit if a same-site cookie-based refresh flow becomes worth the CORS complexity later |

---

## 6. Gate — before any code

**Gate A — DevOps sign-off** (blocks all three pieces): confirm `JWT_SECRET_KEY` / TTL env vars land in `.env.example`, `docker-compose.yml`, and EC2 GitHub Actions secrets; confirm `requirements.txt` additions (`passlib`, `python-jose`) don't need anything beyond the existing `pip install` step in the Dockerfile.

**Gate B — closed 2026-07-05.** Luis confirmed: (1) self-registration creates a new tenant with the registrant as `admin` (§3.6); (2) password reset/email verification is an immediate fast-follow spec, not part of this iteration; (3) rate limiting on login is in v1 (§3.5, folded into the task breakdown below).

---

## 7. Task breakdown for PM (effort, dependency order)

| # | Task | Effort | Depends on |
|---|---|---|---|
| 1 | `Tenant`/`User` models + `tenant_backfill_v1` alignment | M | Gate A |
| 2 | `backend/auth/` core (security, dependencies, schemas) + `routers/auth.py`, incl. login rate limiting (§3.5) | L | 1 |
| 3 | `routers/users.py` (admin user management) | S | 2 |
| 4 | Retrofit `Depends(get_current_user)` across all existing routes (no scoping yet) | L | 2 |
| 5 | Retrofit `require_tenant_access` scoping, per domain (brand / generation / library / template-merge) | L | 4 |
| 6 | Frontend: `AuthService` + interceptor + guards | M | 2 (API contract only, can start in parallel with 3–5) |
| 7 | Frontend: login/register pages | M | 6 |
| 8 | Frontend: gate existing pages + role-based nav hiding | M | 5, 6, 7 |
| 9 | QA: cross-tenant leak test suite (route-by-route checklist) | M | 5 |

Frontend (6–7) can start as soon as the API contract in task 2 is finalized, in parallel with backend tasks 3–5 — it doesn't need the tenant-scoping retrofit to build the login screen itself, only to gate the existing pages (task 8).

---

## 8. Coverage gaps to flag to QA up front

- `require_tenant_access` bypass for `superadmin` — must be an explicit role check, not an incidental `tenant_id IS NULL` match (a bug here silently grants superadmin-equivalent access to any user whose `tenant_id` is accidentally null).
- Refresh token rotation reuse-detection (if Gate B confirms this is in v1, not fast-follow).
- `_is_dark_color`-style edge cases don't apply here, but the equivalent for this feature: malformed/expired/tampered JWT all must resolve to 401, not a 500 from an unhandled decode exception.
- Login timing — response time for "user not found" vs "wrong password" should not differ enough to enable email enumeration via timing (bcrypt's inherent cost helps here, but verify no early-return short-circuits before the hash comparison).
