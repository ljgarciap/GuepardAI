# Design: Soporte para Indicaciones

**Date**: 2026-07-08
**Architect**: aprobado (pendiente confirmación final de Luis en este documento)
**Spec**: `docs/specs/soporte-indicaciones.md`
**Status**: Draft — listo para revisión de Luis antes de pasar al PM
**Decisiones de negocio confirmadas** (2026-07-08): taxonomía de intenciones fija/global (seedeada), no configurable por tenant en esta iteración.

## Coordinación de schema con `reviews-analitica-colaboracion.md`

Esta spec y `docs/designs/reviews-analitica-colaboracion.md` tocan la misma tabla
(`generation_jobs`). Se entregan en **un único commit de migración** con ambas
columnas nuevas, para no romper el patrón idempotente de `database.py` con dos
PRs separados tocando el mismo bloque:

```sql
ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS prompt_metadata JSONB;
ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS owner_id INTEGER;
```

(`owner_id` se define en el design de reviews/colaboración; se menciona aquí solo
para dejar constancia de que ambas van en el mismo bloque de `database.py`.)

## Backend

### Modelo (`models.py` + `database.py`)
- `GenerationJob.prompt_metadata = Column(JSONB, nullable=True)` — guarda la
  selección estructurada del compositor guiado (categoría de intención usada,
  tono, audiencia, tipo de diapositiva, historia, reglas visuales, formato de
  salida, flag "sin buzzwords"). Nunca se usa para lógica de negoción —el
  `prompt` de texto plano sigue siendo la única entrada real al pipeline— es
  solo para reutilización futura y analítica.
- ALTER idempotente (ver bloque combinado arriba).

### Taxonomía de intenciones (`system_configs`, patrón `prompt_*` versionado)
- Nueva key `intent_library_v1` en `system_configs` (seedeada en `utils/seed.py`,
  el seeder ya skippea keys existentes — respeta la convención de versionado).
  Valor: JSON con la lista de categorías, cada una con
  `{slug, label, expected_tone, expected_duration_label, narrative_style,
  visual_density, preferred_layouts[]}`. `preferred_layouts` referencia slugs
  válidos de `GRAMMAR_GEOMETRIES` (`brand_composition_dna.py`) solo como
  sugerencia informativa — no restringe al Architect de generación.
- `expected_duration_label` es texto informativo en esta iteración (p. ej.
  "15-20 min"), **no** se traduce a un parámetro real de número de slides —
  decisión de Architect: el pipeline actual no tiene un input de "duración/N
  slides" explícito hoy, y mapearlo correctamente requeriría tocar
  `content_service.py`/`art_director_service.py`, fuera del alcance de esta
  iteración. Si Luis lo quiere real, es una iteración 2 separada.

### Endpoints nuevos
- `GET /api/config/prompt-intents` (autenticado, cualquier rol): devuelve el
  contenido de `intent_library_v1` tal cual. Sin scoping de tenant (es global).
- `GET /api/library/portfolios/{job_id}` (nuevo — hoy solo existe el listado):
  detalle de un job para "Usar como base", incluye `prompt` y
  `prompt_metadata`. Reusa `check_job_tenant_access`. 404 si no existe o
  `prompt` es null/vacío (regla de la spec: no ofrecer "usar como base" sin
  prompt).

### Sin cambios al contrato de generación
`POST /api/presentations/generate` (`main.py:782`) sigue recibiendo
`prompt: string` como hoy. El ensamblado del compositor ocurre en frontend. Si
el compositor se usó, el frontend además manda `prompt_metadata` (nuevo campo
opcional en `PresentationRequest`) que el backend simplemente persiste en el
job — no lo interpreta.

### AI Decision Records
No aplica — esta spec no agrega ni modifica ninguna llamada a
`providers/llm_provider.py`. No requiere consulta al AI Architect.

## Frontend (Angular 19, standalone)

### `generator.component.ts`
- Pantalla de entrada rediseñada con 3 tarjetas/tabs: "Reutilizar indicación
  anterior", "Biblioteca de intenciones", "Guía / escribir la mía". El
  textarea libre actual sigue siendo el destino final de las tres — se
  mantiene visible y editable después de cualquiera de las tres rutas.
- Ayuda 1: abre selector de la biblioteca existente (`asset-library.component`
  ya tiene la pestaña de portfolios) filtrado a jobs con `prompt` no vacío;
  "Usar como base" llama a `GET /api/library/portfolios/{job_id}` y precarga
  el textarea.
- Ayuda 2: consume `GET /api/config/prompt-intents`, grid de categorías;
  seleccionar una precarga los campos del compositor guiado (Ayuda 3) con los
  valores por defecto de esa categoría.
- Ayuda 3: nuevo sub-componente `prompt-composer` con los campos de la
  fórmula (selects con opción "otro/texto libre" donde la spec lo indica).
  Botón "Insertar en la indicación" ensambla el texto y lo agrega/reemplaza en
  el textarea (con confirmación si el textarea ya tenía contenido manual, para
  no perder trabajo silenciosamente — criterio de la spec).
- Panel de ayuda estático ("Cómo escribir una buena indicación") — contenido
  markdown/HTML embebido en el propio componente, sin necesidad de backend.

### `brand.service.ts`
- `getPromptIntents()`, `getPortfolioDetail(jobId)`.

## Dependencias entre tareas
1. Migración de schema (`prompt_metadata`) — junto con la de `owner_id` de la
   otra spec, en un solo PR de backend.
2. Seed de `intent_library_v1` + endpoint `GET /api/config/prompt-intents` —
   sin dependencias, puede arrancar en paralelo a (1).
3. Endpoint `GET /api/library/portfolios/{job_id}` — sin dependencias.
4. Frontend (las 3 ayudas) — depende de (2) y (3) estar desplegados en un
   entorno de prueba; puede maquetarse en paralelo con datos mock.

## Riesgos y mitigación
- **Categorías desactualizadas o mal calibradas**: al ser fijas/seedeadas,
  ajustarlas requiere una nueva versión de key (`intent_library_v2`) y
  despliegue — igual que cualquier `prompt_*`. Mitigación: documentar esto
  explícitamente para que Product no espere poder editarlas en caliente.
- **`prompt_metadata` sin uso real más allá de guardar**: es deuda intencional
  para no bloquear esta feature en un rediseño de analítica; se consumirá
  cuando la spec de reviews/analítica lo necesite.

## Estimación de esfuerzo
- Backend (modelo + seed + 2 endpoints): 0.5–1 día.
- Frontend (3 ayudas + compositor + panel de ayuda): 2–3 días.
- Tech Writer (doc de API + guía de usuario del compositor): 0.5 día, en paralelo.
