# Manual técnico — Email y Celery Beat (reportes mensuales)

Qué configurar al desplegar (o actualizar) un entorno para que los reportes
mensuales de uso (`docs/specs/reviews-analitica-colaboracion.md`, ítem 7) se
generen **y se envíen por email**. Ambas piezas de infraestructura son
**nuevas** en este proyecto — no existían antes de esta iteración.

## Piezas nuevas

1. **`services/core/email_service.py`** — envío vía SMTP genérico (`smtplib`
   de la stdlib, sin dependencia nueva). No está atado a ningún proveedor.
2. **Celery beat** — un servicio nuevo (`docker-compose.yml` → `celery_beat`)
   que dispara tareas periódicas. Antes de esta iteración el proyecto solo
   tenía `celery_worker` (procesa la cola); beat es el planificador que la
   alimenta con la tarea mensual.

## Env vars nuevas

| Variable | Obligatoria | Default si se omite | Notas |
|---|---|---|---|
| `EMAIL_SMTP_HOST` | No* | ninguno | Host del proveedor SMTP (ej. `email-smtp.us-east-1.amazonaws.com` para SES, `smtp.gmail.com` para Gmail Workspace, el host de SendGrid vía SMTP, etc.) |
| `EMAIL_SMTP_PORT` | No | `587` | Puerto SMTP (con `STARTTLS`, que `email_service.py` siempre invoca). |
| `EMAIL_SMTP_USER` | No | ninguno | Si se omite junto con `EMAIL_SMTP_PASSWORD`, el envío se intenta **sin autenticación** (válido para algunos relays internos; la mayoría de proveedores lo van a rechazar). |
| `EMAIL_SMTP_PASSWORD` | No | ninguno | Ver arriba. |
| `EMAIL_FROM_ADDRESS` | No* | ninguno | Dirección remitente. |

*`EMAIL_SMTP_HOST` y `EMAIL_FROM_ADDRESS` son las dos únicas que
`email_service._smtp_config()` chequea para decidir si hay algo configurado
— si **cualquiera** de las dos falta, `send_email()` no intenta conectarse:
loguea un `warning` y devuelve `False`, sin excepción. Es el mismo criterio
de tolerancia que `SUPERADMIN_EMAIL` ("skipped, no blocking") en
`docs/manuals/technical/auth-deployment.md`.

**Comportamiento degradado esperado y aceptado**: sin estas variables, los
reportes mensuales se siguen generando y persistiendo normalmente
(`UsageReport.sent_at` queda `null`) — quedan visibles en el panel
(`GET /api/admin/usage-reports`, tab **Reports** del Admin Panel) aunque
nunca lleguen por email. No es un fallo silencioso: el panel es la fuente de
verdad, ver "Cómo verificar" más abajo.

## Celery beat

`backend/celery_app.py` define `beat_schedule`:

```python
celery_app.conf.beat_schedule = {
    "monthly-usage-report": {
        "task": "tasks.generate_monthly_usage_report",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 06:00 UTC, día 1 de cada mes
    },
}
```

`docker-compose.yml` agrega el servicio `celery_beat` — comparte la imagen
`guepardai-backend:latest` con `backend`/`celery_worker`, corre
`celery -A celery_app.celery_app beat --loglevel=info`. **Sin este servicio
corriendo, `beat_schedule` nunca dispara, sin ningún error visible** — es la
misma clase de fallo silencioso que un cron mal desplegado. Verificar
explícitamente que existe (ver checklist).

`tasks.generate_monthly_usage_report` (en `backend/tasks.py`) es un wrapper
delgado — la lógica real vive en
`services/core/usage_report_service.generate_and_send_monthly_reports()`:
agrega el mes calendario anterior por tenant más un reporte global
(`tenant_id: null`), persiste un `UsageReport` por cada uno, y llama a
`email_service.send_email()` por cada admin del tenant (superadmin para el
global) — best-effort, un fallo de envío no revierte la persistencia del
reporte.

## Checklist al desplegar (o si los reportes no están llegando por email)

1. `EMAIL_SMTP_HOST` y `EMAIL_FROM_ADDRESS` seteados en el `.env` del
   servidor (más `EMAIL_SMTP_USER`/`EMAIL_SMTP_PASSWORD` si el proveedor
   los exige — la mayoría los exige).
2. Confirmar que el servicio `celery_beat` está definido en el
   `docker-compose.yml` desplegado y corriendo:
   `docker compose ps celery_beat` → `Up`. Si no aparece, el `docker-compose.yml`
   del servidor puede estar desactualizado respecto al del repo — comparar
   contra `git show origin/master:docker-compose.yml`.
3. `docker compose up -d --build celery_beat` (o `--no-deps` si solo cambió
   el `.env`) tras cualquier cambio de env vars o código.
4. Verificar que la variable llegó al contenedor:
   `docker exec <backend-container> printenv | grep EMAIL_SMTP_HOST`.
5. **No hay forma de disparar la tarea mensual manualmente vía API** — para
   probar el envío sin esperar al día 1 del mes, ejecutar dentro del
   contenedor backend:
   ```bash
   docker exec <backend-container> python -c "
   from services.core.usage_report_service import generate_and_send_monthly_reports
   print(generate_and_send_monthly_reports())
   "
   ```
   Devuelve `{'reports_created': N, 'emails_sent': N, 'emails_skipped': N}`.
   `emails_skipped > 0` con `EMAIL_SMTP_HOST` configurado indica un problema
   real de conexión/auth SMTP (revisar el log del contenedor, línea
   `[EmailService] Failed to send email to ...`) — no confundir con el caso
   tolerado de "no configurado" (ese loguea un mensaje distinto:
   `EMAIL_SMTP_HOST/EMAIL_FROM_ADDRESS not configured`).
6. Confirmar en el panel (`GET /api/admin/usage-reports` o Admin Panel →
   Reports) que el reporte quedó con `sent_at` no-nulo tras un envío exitoso.
7. Registrar cualquier comando manual de esta lista (más allá de simple
   verificación) en `docs/operations/post-deploy-alignment.md`, convención
   del proyecto para post-deploy.

## Elegir un proveedor SMTP

El diseño es deliberadamente genérico (sin SDK de vendor) — cualquier
proveedor que hable SMTP+STARTTLS sirve: Amazon SES, Gmail Workspace,
SendGrid vía SMTP, Mailgun, etc. La elección del proveedor es una decisión
de Luis/DevOps al desplegar, no algo resuelto en el código.
