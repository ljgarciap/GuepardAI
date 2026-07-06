# GuepardAI — Arquitectura Consolidada

Vista de sistema para onboarding y decisiones de diseño. El detalle operativo
día a día (cómo correr el stack, convenciones de código, contratos exactos de
cada agente) vive en `CLAUDE.md`; este documento es el mapa de más alto nivel.

## Qué es

Plataforma de síntesis de presentaciones estratégicas. Ingiere documentos de
marca (PPTX/PDF), extrae ADN visual y conocimiento corporativo, y genera
presentaciones autoría-IA vía un pipeline multi-agente. Salida en `.pptx`
(python-pptx) o `pdf_artistic` (HTML/Jinja2 renderizado vía Playwright/WeasyPrint).

## Componentes principales

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────────┐
│  Angular     │◄────►│  FastAPI     │◄────►│  PostgreSQL+pgvector│
│  Frontend    │ HTTP │  (main.py)   │      │  (modelos, vectores)│
└─────────────┘      └──────┬───────┘      └─────────────────────┘
                             │ enqueue
                             ▼
                      ┌──────────────┐      ┌─────────────────────┐
                      │  Celery      │◄────►│  Redis              │
                      │  Worker      │      │  (broker + sesiones)│
                      └──────┬───────┘
                             ▼
                      ┌──────────────┐
                      │ AgentOrchestr│
                      │ + Tools      │
                      └──────────────┘
```

- **Frontend**: Angular 19.2 standalone, sin SSR. `AuthService` mantiene el
  estado de sesión; `HttpClient` con interceptor de auth habla con la API bajo
  `/api`.
- **API (`backend/main.py` + `backend/routers/`)**: FastAPI. Las rutas nuevas
  (desde el módulo de auth en adelante) viven en `routers/` y se registran con
  `app.include_router(...)`; las rutas legacy siguen en `main.py` (ver
  "Convención de rutas" abajo). Toda ruta (legacy o nueva) exige un usuario
  autenticado salvo `/api/auth/*` y los docs de Swagger.
- **Celery + Redis**: ejecuta los pipelines de ingestión y generación de forma
  asíncrona; Redis también guarda la revocación de refresh tokens y el rate
  limit de login.
- **PostgreSQL + pgvector**: modelos ORM (`models.py`) y embeddings
  (`Vector(1024)`) para RAG y búsqueda semántica de assets.
- **AgentOrchestrator + Tools**: cada paso de un pipeline (Redactor, Architect,
  QA Validator, Render Agent, extractores de ingestión) es un `BaseAgentTool`
  stateless, orquestado por `AgentOrchestrator` — nunca se llaman entre sí
  directamente.

## Límite de autenticación y multi-tenancy

Desde `feature/auth-multitenant` (spec:
`docs/specs/autenticacion-multiusuario-multitenant.md`, API:
`docs/api/auth-and-users.md`), toda la superficie de la API vive detrás de un
límite de autenticación:

- **`Tenant`** es el límite de propiedad por encima de `Brand` (1 tenant → N
  brands). Todo dato operativo (`Brand`, y transitivamente
  `GenerationJob`/`IngestionJob`/assets/knowledge) pertenece a un tenant.
- **`User`** tiene un `role` (`superadmin | admin | cliente`) y, salvo
  `superadmin`, un `tenant_id` fijo. `superadmin` es la única excepción con
  `tenant_id = null` y ve todos los tenants — el bypass es siempre explícito
  por rol, nunca implícito por un `tenant_id` nulo incidental (eso sería un
  `Brand` mal alineado, no un superadmin).
- El scoping se aplica en el punto único `auth/dependencies.py`
  (`require_tenant_access`, `check_brand_tenant_access`,
  `check_job_tenant_access`, `tenant_brand_ids_filter`) — cualquier ruta nueva
  que toque un recurso con `tenant_id` debe pasar por ahí, no reimplementar el
  chequeo.
- Sesión: JWT de acceso (corto, en memoria en el frontend) + refresh token de
  un solo uso (rotado en Redis). Detalle completo en
  `docs/api/auth-and-users.md`.

## Convención de rutas: `routers/` vs `main.py`

Antes de este feature, todas las rutas vivían inline en `main.py`. El módulo
de auth introduce `backend/routers/` (`auth.py`, `users.py`) como el patrón a
seguir para rutas nuevas: cada router es un archivo con su propio
`APIRouter(prefix=...)`, registrado en `main.py` vía `include_router()`. Las
rutas legacy no se migraron (fuera de alcance de este feature) pero **rutas
nuevas de aquí en adelante deben usar `routers/`**, no agregarse a `main.py`.

## Pipelines (sin cambios por el feature de auth, ahora requieren sesión)

### Ingestión
`POST /api/brand/upload` → Celery → `ingestion_orchestrator` → extracción de
paleta/ADN visual (Vision LLM), lectura programática de PPTX, embeddings de
conocimiento corporativo (RAG).

### Generación
`POST /api/presentations/generate` → Celery →
`AgentOrchestrator.run_generation_pipeline`: Redactor (contenido + RAG) →
checkpoint humano opcional → Architect (layout) → QA Validator (determinístico
+ LLM judge, hasta `MAX_RETRIES` reintentos) → Render Agent (`.pptx` o PDF
artístico).

Ver `CLAUDE.md` para el detalle línea por línea de cada pipeline, el enrutado
de proveedores LLM, y las convenciones de código por agente.

## Modelo de datos (resumen)

| Modelo | Rol |
|---|---|
| `Tenant` | Límite de propiedad multi-tenant |
| `User` | Cuenta con rol y tenant (auth) |
| `Brand` | Directorio maestro de marcas, ahora con `tenant_id` |
| `BrandVisualDna` / `BrandArtisticEssence` / `BrandPremiumVisualPattern` | ADN visual extraído |
| `CorporateKnowledge` / `BrandAsset` | RAG y biblioteca de imágenes (embeddings pgvector) |
| `GenerationJob` / `IngestionJob` / `PresentationSlide` | Tracking de pipelines |
| `ArtDirectorDecision` | Auditoría de decisiones IA |
| `SystemConfig` | Configuración runtime (modelos, umbrales) |

Detalle completo de columnas y relaciones: `backend/models.py`.

## Dónde profundizar

- Contratos y decisiones de diseño de IA: `docs/ai/contracts/`
- Specs de features: `docs/specs/`
- Decisiones de diseño técnico: `docs/designs/`
- Alineaciones post-deploy (schema/config/data): `docs/operations/post-deploy-alignment.md`
- Manuales técnicos de despliegue: `docs/manuals/technical/`
