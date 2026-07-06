# Review: Autenticación, Roles Multi-Usuario y Base Multi-Tenant (B1-B9)

**Date**: 2026-07-05
**Reviewer**: Senior Reviewer
**Scope**: `backend/auth/`, `backend/routers/`, `backend/services/core/auth_service.py`, `backend/main.py` (retrofit de las 34 rutas existentes), `backend/models.py`, `backend/services/core/data_alignment_service.py`, tests asociados
**Spec**: `docs/specs/autenticacion-multiusuario-multitenant.md`
**Design**: `docs/designs/autenticacion-multitenant-design.md`
**Tests**: 421 passed, 1 skipped (verificado, no solo confiado en el reporte del dev)

**Veredicto: Cambios requeridos antes de pasar a QA.** El trabajo es sólido y la arquitectura sigue el diseño aprobado, pero hay dos hallazgos 🔴 de seguridad genuinos que contradicen criterios de aceptación explícitos de la spec, no cosméticos.

**Actualización 2026-07-05 (post-fix)**: Backend Dev cerró los 2 blockers y las suggestions #3 y #5 (a pedido de Luis). Suite completa: 424 passed, 1 skipped. Detalle de cada fix al pie de su hallazgo. #4, #6, #7 y #8 quedan documentados como fast-follow, sin tocar en esta iteración.

---

## 🔴 Blockers

### 1. Enumeración de usuarios por timing en `/api/auth/login`

`services/core/auth_service.py:67-77` (`authenticate_user`):

```python
user = db.query(models.User).filter(models.User.email == email).first()
if user is None or not user.is_active:
    raise generic_error
if not security.verify_password(password, user.hashed_password):
    raise generic_error
```

El mensaje de error es genérico en ambas ramas, pero el **tiempo de respuesta no lo es**: si `user is None` (o está desactivado), la función retorna de inmediato; si el email existe y la password es incorrecta, corre `verify_password` (un hash bcrypt, deliberadamente costoso, ~decenas de ms). Un atacante puede medir la latencia y distinguir "email no existe" de "email existe, password incorrecta" — exactamente el vector que la spec pide cerrar ("no revela si el email existe") y que el propio design doc señaló como pendiente de verificar en QA (§8). Se verificó en el código, no es hipotético.

**Fix**: cuando `user is None`, correr `security.verify_password(password, <hash dummy precalculado>)` antes de lanzar `generic_error`, para que el costo de CPU sea equivalente en ambas ramas. Lo mismo aplica a la rama `not user.is_active`.

**✅ Resuelto**: `_DUMMY_PASSWORD_HASH` precalculado a nivel de módulo en `auth_service.py`; `verify_password` corre siempre (contra el hash real o el dummy) antes de cualquier chequeo de existencia/actividad. Test: `test_nonexistent_email_still_runs_password_hash_check`.

### 2. `JWT_SECRET_KEY` cae en un default hardcodeado si no está seteado

`backend/auth/security.py:22`:

```python
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-insecure-secret-change-me")
```

Si el env var no está configurado (D1, la tarea de DevOps que lo agrega a `.env.example`/`docker-compose.yml`/secrets de EC2, **todavía no corrió**), el backend arranca igual y firma tokens con un secreto público (está en el repo). Cualquiera que lea el código puede forjar un access token válido para **cualquier `user_id` y cualquier rol, incluido `superadmin`**, apuntando a producción. No es un escenario remoto: B1-B9 ya están mergeables y D1 es una tarea aparte que puede quedar pendiente por error humano.

**Fix**: fallar el arranque (o al menos loggear un error crítico y negarse a emitir tokens) si `JWT_SECRET_KEY` no está seteado — no hay un modo "dev" seguro para un secreto de firma. Comparar con el patrón de `ADMIN_TOKEN` (que sí falla abierto si no está seteado) no aplica acá: ese es un precedente ya señalado en la spec como "no imitar", no como modelo a seguir.

**✅ Resuelto**: `auth/security.py` ahora lanza `RuntimeError` al importarse si `JWT_SECRET_KEY` no está en el entorno — el backend no arranca sin él. Agregado a `.env.example` (raíz y `backend/`), `.env.test.example`, `.env.test` local y el `.env` local real (con un secreto generado, no el placeholder). **Pendiente**: DevOps (D1) todavía debe agregarlo a `docker-compose.yml` y a los secrets de GitHub Actions para EC2 — sin eso, el próximo deploy a producción va a crashear al arrancar. Test: `test_module_import_fails_without_jwt_secret_key` (subproceso aislado).

---

## 🟡 Suggestions

### 3. Rotación de refresh token no es atómica (ventana TOCTOU pequeña)
`services/core/auth_service.py` (`refresh_access_token`): `r.get(...)` y `r.delete(...)` son dos operaciones Redis separadas. Dos requests de refresh concurrentes con el mismo token podrían ambas pasar la verificación antes de que cualquiera borre la key, emitiendo dos pares de tokens válidos desde un solo refresh. Severidad baja (no permite que un token robado ya rotado se reutilice más allá de esa ventana), pero un `GETDEL` atómico (Redis ≥6.2) o un script Lua lo cierra del todo.

**✅ Resuelto**: `refresh_access_token` usa `r.getdel(...)` (lee y borra atómicamente); ya no hay `r.get()` + `r.delete()` separados.

### 4. Sin rate limiting en `/api/auth/register`
Solo `/login` tiene `check_login_rate_limit`. El registro público es ilimitado — un vector de spam/agotamiento de recursos (creación masiva de tenants) que encaja con "la seguridad es indispensable" tanto como el rate limit de login que sí se implementó. Recomiendo el mismo mecanismo, reusando `check_login_rate_limit` con otra key prefix.

### 5. Condición de carrera en email duplicado (race, no el camino feliz)
Tanto `register_user` como `routers/users.py::create_user` hacen `SELECT ... WHERE email = ?` y luego `INSERT`, sin que la operación sea atómica. Dos registros concurrentes con el mismo email pasarían ambos el chequeo y el segundo `commit()` fallaría con `IntegrityError` (la columna sí tiene `unique=True`) — un 500 crudo en vez del 409 documentado en la spec. Bajo tráfico normal es improbable, pero es la clase de bug que aparece en producción bajo carga. Envolver el commit en `try/except IntegrityError` y convertir a 409 lo cierra.

**✅ Resuelto**: tanto `auth_service.register_user` como `routers/users.py::create_user` envuelven el `db.commit()` en `try/except IntegrityError` → `db.rollback()` + 409. Test: `test_duplicate_email_race_returns_409_not_500` (fuerza la carrera parcheando `Query.first`).

### 6. `_run_tenant_backfill` no hace rollback por ítem fallido
`services/core/data_alignment_service.py` — el `except Exception` dentro del loop loguea y continúa, pero si el error viene de un `db.flush()` fallido (constraint violation), Postgres deja la transacción "abortada" y **todas** las iteraciones siguientes fallarían en cascada silenciosamente hasta el `db.commit()` final, que también fallaría — el summary reportaría números que no reflejan la realidad. Baja probabilidad hoy (`Tenant.name` no tiene unique constraint), pero es el mismo patrón de robustez que ya se sigue en otras alineaciones del registry. Agregar `db.rollback()` (o `db.begin_nested()`/savepoint) dentro del `except` antes de continuar.

### 7. Brand creado por superadmin sin `tenant_id` explícito queda huérfano
`main.py::create_brand` — si un superadmin no pasa `tenant_id`, el Brand queda con `tenant_id=None`, y `check_brand_tenant_access` niega el acceso a CUALQUIER admin/cliente sobre ese Brand (correcto, es el comportamiento fail-closed diseñado), pero no existe ningún endpoint para reasignarle un tenant después. No bloquea esta iteración, pero vale un ticket de fast-follow antes de que un superadmin real tropiece con esto.

### 8. Nits de eficiencia/estilo (no bloquean)
- `create_brand`: `create_brand_logic()` ya hace su propio commit interno; la asignación de `tenant_id` fuerza un tercer round-trip. Pasar `tenant_id` como parámetro de `create_brand_logic` evitaría el commit extra.
- `upload_asset`: ahora abre dos sesiones de DB por request (la inyectada vía `Depends(get_db)`, usada solo para el chequeo de tenant, y la `SessionLocal()` propia que ya existía después). Redundante pero no incorrecto.
- `get_presentation_slides`: quedó una línea en blanco de más tras el refactor (cosmético).

---

## Lo que está bien (y no es poco)

- **Arquitectura fiel al diseño aprobado**: `require_tenant_access`/`check_brand_tenant_access`/`check_job_tenant_access`/`tenant_brand_ids_filter` son exactamente el "punto único" que el design doc pedía — el retrofit de las 34 rutas es mecánico y auditable, no ad hoc.
- **Bypass de `superadmin` es explícito por rol**, nunca implícito por `tenant_id IS NULL` — verificado en código y en tests (`test_brand_without_tenant_denies_admin`).
- **Encontró y corrigió 3 bugs reales que no eran parte del pedido original**: el pin de `bcrypt<4.1`, la duplicación de `get_db` en `main.py` (que además era un riesgo de producción, no solo de tests), y el gap de template cross-tenant en `create_template_merge_job`. Ese tercer hallazgo en particular es exactamente el tipo de cosa que este review existe para atrapar, y el dev ya lo atrapó solo.
- **El sentinel legacy `brand_id=-1`** ("superuser ve todo" sin chequeo de rol) fue reemplazado por un chequeo de rol real — antes de esta iteración cualquier caller sin autenticar podía pasar `-1` y ver todo; ahora requiere ser `superadmin` de verdad.
- **Tests no son de relleno**: `test_tenant_scoping.py` prueba fugas cross-tenant reales con fixtures de dos tenants distintos, no solo happy path; `test_auth_retrofit_smoke.py` cubre las 34 rutas por nombre, no una muestra.
- **Reglas del proyecto respetadas**: nada de LLM directo, `SessionLocal()`/`get_db()` según corresponde, convención `0/1` para booleanos, versión de prompt/config no aplica acá (no hay prompts nuevos).

---

## Siguiente paso

Los blockers #1 y #2 son acotados (un guard de arranque + una comparación dummy) — no requieren rediseño, solo que Backend Dev los cierre antes de QA. Los 🟡 pueden ir en el mismo pase o documentarse como fast-follow explícito si Luis prefiere no bloquear el resto de la iteración (Frontend/DevOps/Tech Writer) por ellos.
