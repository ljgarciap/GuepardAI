# QA Report: Histórico persistente de Template Merge

**Feature**: Histórico persistente de Template Merge (`docs/specs/template-merge-job-history.md`)
**Date**: 2026-07-07
**Tested by**: QA Agent
**Senior Reviewer sign-off**: `docs/reviews/template-merge-job-history.md` (🟢 Aprobado)

## Veredicto: ✅ Aprobada

## 1. Tests automatizados (corridos de forma independiente, no solo confiados en el reporte de dev/reviewer)

- Backend: `pytest tests/` → **442 passed, 1 skipped** (el skip es preexistente, no relacionado a este feature).
- Frontend: `ng test --watch=false --browsers=ChromeHeadless` → **60/60 SUCCESS**.

## 2. Validación manual end-to-end contra el stack real corriendo (Docker)

**Hallazgo durante QA — corregido en esta misma sesión**: el contenedor `guepard-backend` seguía corriendo la imagen anterior a este feature (nunca se había reconstruido tras los cambios en `main.py`). Las primeras pruebas contra `http://localhost:4200/api/...` devolvían `405 Method Not Allowed` en las 3 rutas nuevas — la ruta `/jobs` exacta coincidía con la de `POST /jobs` ya existente pero no aceptaba `GET/PATCH/DELETE`, señal inequívoca de código viejo. Se corrigió con `docker compose up --build -d backend` (+ `celery_worker`, misma imagen) y se repitió toda la validación desde cero. **Sin este paso, la feature habría llegado a producción sin los endpoints nuevos activos** — dejo esto anotado porque el checklist de deploy no lo habría capturado (CI/CD reconstruye la imagen automáticamente en push a `master`, así que este riesgo es específico de verificación local, no de producción).

Autenticado como `superadmin@guepardai.com`, `testadmin@guepardai-dev.com` (tenant 4) y `testcliente@guepardai-dev.com` (tenant 4) — cuentas ya seedeadas para QA.

| Criterio | Input | Expected | Actual | Result |
|---|---|---|---|---|
| Listado sin token | `GET /template-merge/jobs` sin header | 401 | 401 | ✅ |
| Listado como superadmin | `GET /template-merge/jobs` (superadmin) | Ve jobs reales existentes (`brand_id: null`) | Devolvió los 2 jobs reales preexistentes (`id 1 "TestHP"`, `id 2 "tescohp"`, ambos `brand_id: null`) — **este es exactamente el caso reportado originalmente por Luis**, ahora visible | ✅ |
| Tenant scoping (admin sin brand) | `GET /template-merge/jobs` (testadmin, tenant 4, sin brands) | `{items: [], total: 0}` | `{items: [], total: 0}` | ✅ |
| Validación de fechas | `date_from=2026-06-11&date_to=2026-06-01` | 422 | 422 | ✅ |
| PATCH job inexistente | `PATCH /jobs/999999` | 404 | 404 | ✅ |
| DELETE job inexistente | `DELETE /jobs/999999` | 404 | 404 | ✅ |
| Renombrado + búsqueda | `PATCH /jobs/1 {display_name:"TestHP (QA check)"}` → `GET ?search=QA check` | Rename persiste, search lo encuentra | Persistió; búsqueda devolvió el ítem con el nuevo nombre | ✅ |
| Rename revertido | `PATCH /jobs/1 {display_name:"TestHP"}` | Vuelve al nombre original, sin tocar `output_path`/descarga | Confirmado — `filename` no cambió en ninguna respuesta | ✅ |
| Validación de rename vacío | `PATCH /jobs/1 {display_name:"   "}` | 422 | 422 | ✅ |
| Descarga real | `GET /jobs/2/download` (superadmin) | 200, archivo `.pptx` válido | 200; archivo de 889,079,763 bytes, ZIP válido con 1083 entradas incl. `ppt/presentation.xml` — corresponde a un template con video/imágenes pesadas (nginx.conf ya documenta PPTX >800MB como caso esperado) | ✅ |
| Tenant scoping — escritura cross-tenant | `PATCH`/`DELETE`/`download` de `/jobs/1` (testadmin, job con `brand_id: null`) | 403 en los 3 | 403 en los 3; confirmado que `job 1` siguió intacto (`display_name: "TestHP"`) tras el intento | ✅ |
| Frontend sirve la ruta | `GET /template-merge` (SPA) | 200 | 200 | ✅ |

## 3. Suite de integración (pytest) — cobertura de casos no repetidos manualmente para no mutar datos reales

Ejecutados y verificados en `backend/tests/test_template_merge_history.py` (18/18 passed): orden descendente, escapado de comodines LIKE, rango de fechas inclusivo, paginación fuera de rango, exclusión de jobs `pending`/`processing`/`error` del listado, `DELETE` bloqueado en estado activo (409), `DELETE` permitido en `error`, `DELETE` dos veces (segunda → 404), tolerancia a archivo físico ausente, y 3 casos de tenant scoping con tenants sintéticos (`test_list_scoped_to_tenant`, `test_explicit_brand_id_cross_tenant_rejected`, `test_rename_rejects_other_tenant`). No repetí estos contra datos reales para no borrar/corromper los 2 `TemplateMergeJob` de producción-local existentes.

## 4. Interacción de UI (limitación declarada)

No tengo una herramienta de automatización de navegador disponible en esta sesión, así que **no hice click-through real** del tab History, el debounce de búsqueda, ni el modal de borrado en un navegador. Lo que sí verifiqué como evidencia indirecta pero real:
- Los 9 specs de Karma (`template-merge.component.spec.ts`) ejercitan la lógica real del componente (Angular cambia de estado genuino, no mocks de la clase bajo prueba) para: carga al activar la pestaña, debounce → reset de página, filtro de fecha → reset, cancelar/confirmar el modal de borrado, retroceso de página al borrar el último ítem, y renombrado inline.
- Cada acción que la UI dispara (`getTemplateMergeHistory`, `renameTemplateMergeJob`, `deleteTemplateMergeJob`, descarga) fue validada contra el backend real en la sección 2.
- Confirmé que el frontend reconstruido sirve `/template-merge` sin error 500/404 de Angular routing.

**Recomendación**: si Luis quiere el cierre completo, un passthrough manual de 2 minutos en el navegador (login, tab History, buscar, renombrar, cancelar un borrado) cerraría el único hueco de esta validación.

## 5. Criterios de aceptación del spec

Todos los checkboxes de `docs/specs/template-merge-job-history.md` → Acceptance criteria quedaron marcados `[x]` tras esta validación (ver diff del archivo). Ninguno quedó ambiguo o sin verificar.

## Limpieza post-QA

- `backend/.env.test` restaurado a `host.docker.internal:5433` (se cambió temporalmente a `localhost:5433` para poder correr pytest fuera de Docker — ver nota del Senior Reviewer sobre esto).
- Archivos temporales de la prueba (tokens, `.pptx` descargado) borrados.
- Los 2 `TemplateMergeJob` reales tocados (`id 1`, `id 2`) quedaron con su `display_name` original — el round-trip de rename fue reversible y verificado.
