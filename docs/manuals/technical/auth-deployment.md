# Manual técnico — Despliegue de Autenticación Multi-Tenant

Qué configurar al desplegar (o actualizar) un entorno con el módulo de auth
(`backend/auth/`, B1-B9 de `docs/tasks/autenticacion-multiusuario-multitenant.md`).

## Env vars nuevas

Agregar en el `.env` del entorno (local, EC2, o cualquier deploy nuevo):

| Variable | Obligatoria | Default si se omite | Notas |
|---|---|---|---|
| `JWT_SECRET_KEY` | **Sí** | ninguno — el backend **no arranca** sin ella (`RuntimeError` en `auth/security.py`) | Generar con `openssl rand -hex 32` (o `python -c "import secrets; print(secrets.token_hex(32))"`). Nunca reusar entre entornos; rotarla invalida todas las sesiones activas. |
| `JWT_ACCESS_TOKEN_TTL_MINUTES` | No | `15` | TTL del access token. |
| `JWT_REFRESH_TOKEN_TTL_DAYS` | No | `7` | TTL del refresh token. |
| `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | No | `5` | Intentos de login permitidos por ventana antes de `429`. |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Duración de la ventana deslizante (Redis). |
| `SUPERADMIN_EMAIL` | No* | ninguno | *Si se omite junto con `SUPERADMIN_PASSWORD`, el seed de superadmin se salta sin bloquear el arranque — pero entonces **nadie puede loguearse** en un entorno nuevo hasta que se cree un usuario por otra vía. |
| `SUPERADMIN_PASSWORD` | No* | ninguno | Ver arriba. Usar una contraseña fuerte en cualquier entorno que no sea de pruebas descartables. |

`JWT_SECRET_KEY` y `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` viven **solo** en el
`.env` físico del servidor (nunca en `docker-compose.yml` como valor literal,
nunca en git) — ver `docker-compose.yml`, que los referencia como
`${JWT_SECRET_KEY}` / `${SUPERADMIN_EMAIL}` / `${SUPERADMIN_PASSWORD}` en el
servicio `backend` (y `JWT_SECRET_KEY` también en `celery_worker`, que valida
tokens en tareas asíncronas).

## `seed_superadmin.py`

`backend/utils/seed_superadmin.py` se ejecuta automáticamente al arrancar el
backend (`main.py`, junto a `seed_data()`), no requiere invocación manual.

- **Idempotente**: si ya existe un `User` con el email de `SUPERADMIN_EMAIL`, lo
  salta sin duplicar ni actualizar la password.
- **No bloqueante**: si `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` no están seteadas,
  imprime un warning y continúa el arranque (mismo patrón que `seed_data()` —
  ver el `try/except` en `main.py`).
- **Rotar la password de un superadmin ya sembrado**: cambiar `SUPERADMIN_PASSWORD`
  en el `.env` **no** actualiza el usuario existente (por el idempotente de
  arriba). Para rotarla hay que borrar la fila (`DELETE FROM users WHERE email =
  '<email>'`) y reiniciar el backend, o cambiar la password directamente por
  SQL con un hash bcrypt nuevo (`passlib.context.CryptContext(schemes=["bcrypt"]).hash(...)`).

Para ejecutarlo manualmente fuera del arranque (ej. debugging):
```bash
cd backend && python -m utils.seed_superadmin
```

## Checklist al desplegar a un entorno nuevo (o EC2 antes del próximo `git reset --hard` + `docker compose up -d --build`)

1. `JWT_SECRET_KEY` generado y seteado en el `.env` del servidor.
2. `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` seteados con una password fuerte (no el valor de pruebas `password` usado en desarrollo local).
3. `docker compose up -d --no-deps backend celery_worker` (no hace falta `--build` si solo cambió el `.env`, sí si cambió código).
4. Verificar: `docker exec <backend-container> printenv | grep -c JWT_SECRET_KEY` → `1`.
5. Verificar login real: `curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"<SUPERADMIN_EMAIL>","password":"<SUPERADMIN_PASSWORD>"}'` → `200` con `access_token`/`refresh_token`.
6. Registrar el paso en `docs/operations/post-deploy-alignment.md` (convención del proyecto para cualquier comando manual post-deploy).
