# Setup de dominios — guepardai.com / .fr / .online

Estado: **en producción**, verificado 2026-08-05.

## Topología

- `guepardai.com` es el dominio **canónico** — sirve la app real.
- `guepardai.fr` y `guepardai.online` (con sus `www`) hacen **redirect 301** a `https://guepardai.com`. Decisión de negocio de Luis (evitar contenido duplicado / SEO), no hay lógica de mercado por dominio.
- Los 3 apuntan a la misma instancia EC2 "GUEPARD" (ver `project-d1-jwt-ec2-pending` en memoria), Elastic IP `100.50.59.127`.

## DNS (por dominio, en el panel de cada registrador)

| Registro | Host | Valor |
|---|---|---|
| A | `@` | `100.50.59.127` |
| CNAME | `www` | apex del mismo dominio (ej. `www.guepardai.fr` → `guepardai.fr`) |

Nota: el panel no permite A y CNAME sobre el mismo nombre (`www`) — si ya existe un CNAME por defecto, hay que reapuntarlo al apex propio, no crear un A duplicado.

## AWS

- Cuenta AWS de esta instancia: `905418018576`, región `us-east-1` — **no** es ninguna de las cuentas con AWS CLI configuradas en el workspace local (`445567109897` / `060374132298`). Cambios de Security Group los hace Luis a mano en la consola.
- Security Group `sg-0596811f03e1060e9` (VPC `vpc-0786080566acf9297`): reglas inbound agregadas 2026-08-05 — HTTP 80 y HTTPS 443 desde `0.0.0.0/0`.
- La instancia no tiene IAM role adjunto (no hay camino de credenciales vía metadata).

## Reverse proxy (nginx a nivel de host, fuera de docker compose)

El stack de `docker-compose.yml` publica el frontend en host `4200` → contenedor nginx `80` (`docker-compose.yml:127`), y el backend en `8000`. El nginx de host termina TLS en 80/443 y hace proxy al frontend:

- Paquetes: `nginx`, `certbot`, `python3-certbot-nginx` (instalados vía apt, 2026-08-05).
- Config: `/etc/nginx/sites-available/guepardai` (symlink en `sites-enabled/`; el site `default` fue removido de `sites-enabled/`).
  - Server block canónico: `server_name guepardai.com www.guepardai.com;` → `proxy_pass http://127.0.0.1:4200`.
  - Server block secundario: `server_name guepardai.fr www.guepardai.fr guepardai.online www.guepardai.online;` → `return 301 https://guepardai.com$request_uri;`.
- Certificado: Let's Encrypt vía `certbot --nginx` para los 6 hostnames en un solo comando (`-d guepardai.com -d www.guepardai.com -d guepardai.fr -d www.guepardai.fr -d guepardai.online -d www.guepardai.online --redirect`). Expira 2026-11-03. Renovación automática: `certbot.timer` (systemd), habilitado por default al instalar el paquete — no requiere cron manual.
- `ufw` está inactivo en el host — no es una capa de firewall adicional a considerar.

## Pendiente / no bloqueante

- `backend/main.py:96-100` (`CORSMiddleware.allow_origins`) solo lista `localhost`. Hoy no afecta porque el frontend habla con el backend same-origin (proxy `/api/` en `frontend/nginx.conf`, y ahora también en el nginx de host). Si en el futuro algo llama al backend cross-origin desde `guepardai.com`, hay que agregarlo a la lista.

## Verificación (repetible)

```bash
curl -I https://guepardai.com          # 200
curl -I https://guepardai.fr           # 301 -> https://guepardai.com/
curl -I https://guepardai.online       # 301 -> https://guepardai.com/
curl -I http://guepardai.com           # 301 -> https://guepardai.com/ (http->https)
```
