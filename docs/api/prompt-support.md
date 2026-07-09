# API — Soporte para Indicaciones (compositor de prompts)

Referencia de `/api/config/prompt-intents`, `/api/library/portfolios/{job_id}`,
y el campo `prompt_metadata` en `POST /api/presentations/generate` /
`GET /api/library/portfolios`.

Implementación: `backend/routers/config.py`, `backend/routers/portfolios.py`,
`backend/main.py` (`PresentationRequest`, `generate_presentation`,
`list_library_portfolios`), `backend/utils/seed.py` (`intent_library_v1`).

Spec: `docs/specs/soporte-indicaciones.md`
Design: `docs/designs/soporte-indicaciones.md`

Esta feature no agrega lógica de negocio nueva al pipeline de generación:
`prompt_metadata` es una selección estructurada que el frontend arma con el
compositor guiado y el backend **solo persiste**, nunca interpreta. El
`prompt` de texto plano sigue siendo la única entrada real al pipeline.

## Biblioteca de intenciones

### `GET /api/config/prompt-intents`

Cualquier usuario autenticado (sin scoping de tenant — es una taxonomía
global). Devuelve el contenido de `system_configs.intent_library_v1` tal
cual: una lista fija de 8 categorías (Executive Presentation, Sales Deck,
Workshop, Training, Strategy, Investor, Retail, Innovation), sembrada por
`utils/seed.py` y no editable en runtime — ajustarla requiere una nueva key
versionada (`intent_library_v2`) y deploy, igual que cualquier `prompt_*`.

**Respuesta**: `200` → `[{ slug, label, expected_tone, expected_duration_label,
narrative_style, visual_density, preferred_layouts: string[] }]`.
`preferred_layouts` referencia slugs de `GRAMMAR_GEOMETRIES`
(`backend/services/ingestion/brand_composition_dna.py`) solo como sugerencia
informativa para el compositor — no restringe al Architect de generación.

## "Usar como base" — reusar una indicación anterior

### `GET /api/library/portfolios/{job_id}`

Detalle de un job para precargar el compositor con un prompt ya usado.
Reusa el scoping estándar (`check_job_tenant_access`).

**Respuestas**:
- `200` → `{ id, filename, display_name, created_at, brand_id, prompt,
  prompt_metadata }`
- `404` → el job no existe, o **no tiene `prompt`** (nada que reusar — regla
  explícita del spec: no ofrecer "usar como base" sin prompt)

### `has_prompt` en `GET /api/library/portfolios`

El listado paginado (`docs/specs/gestion-portfolios.md`) expone
`has_prompt: boolean` en cada item — necesario para que el frontend filtre
la lista de "reutilizar indicación anterior" a solo los jobs con algo que
reusar, sin tener que pedir el detalle de cada uno.

## `prompt_metadata` en la generación

### `POST /api/presentations/generate`

`PresentationRequest` acepta un campo opcional nuevo:

```json
{
  "prompt": "string (sigue siendo obligatorio y es la única entrada real)",
  "prompt_metadata": {
    "objective": "string",
    "tone": "string | undefined",
    "audience": "string | undefined",
    "slide_type": "string | undefined",
    "story": "string | undefined",
    "visual_rules": "string | undefined",
    "output_format": "string | undefined",
    "no_buzzwords": "boolean"
  }
}
```

Si el frontend no usó el compositor guiado (usuario escribió su propio
texto libre), `prompt_metadata` se omite y queda `null` en el
`GenerationJob`. Se persiste tal cual, sin validación de contenido más allá
del tipo — es un registro para reutilización futura y analítica, nunca una
entrada al Redactor/Architect.

## Frontend — dónde vive esto

`generator.component` (`/`, pantalla principal): 3 tarjetas de entrada —
"Reuse Previous Prompt" (llama a `GET /api/library/portfolios` filtrado por
`has_prompt` + `GET /api/library/portfolios/{job_id}` al elegir uno), "Intent
Library" (`GET /api/config/prompt-intents`, seleccionar una precarga el
compositor), "Guide / Write My Own" (abre directamente el compositor +
guía estática). El sub-componente `prompt-composer`
(`components/generator/prompt-composer/`) arma el texto final con la fórmula
Objective+Tone+Audience+SlideType+Story+VisualRules+OutputFormat+noBuzzwords
y emite `{ text, metadata }`; el padre inserta `text` en el textarea (con
confirmación si ya había contenido manual) y guarda `metadata` para mandarla
en `prompt_metadata` al generar.
