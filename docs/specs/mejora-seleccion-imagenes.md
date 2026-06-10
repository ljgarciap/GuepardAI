# Spec: Mejora de Selección de Imágenes (Iteración 1 — Perfil Visual + Aspect Ratio)

**Date**: 2026-06-10
**Requested by**: Luis
**Status**: In Development — implementación completa y tests en verde (55/55); pendiente Senior Review y aprobación final de Luis
**Project**: GuepardAI

## Problem

La selección de imágenes para cada slide se decide con un matching texto-a-texto:
keywords del slide contra una descripción del asset de máximo 15 palabras generada
en la ingesta. Nadie "mira" la imagen en el momento de la decisión (el reranking
visual está deshabilitado por performance), y las dimensiones físicas del asset
solo se usan como umbral mínimo de resolución — el aspect ratio nunca se compara
contra el panel del layout destino. Resultado: fotos semánticamente correctas pero
visualmente inadecuadas (recortes feos, orientación incompatible, composición que
choca con el texto), y placeholders cuando sí había assets aprovechables.

Adicionalmente, el umbral `asset_score_threshold` seedeado en `system_configs`
(0.45) se lee en `art_director_service.py` pero **nunca se usa** — los umbrales
0.40 y 0.45 están hardcodeados, violando la regla de configuración runtime del
proyecto.

## Solution summary

Enriquecer el perfil de cada asset en el momento de la ingesta (una sola llamada
Vision que ya existe hoy, pidiendo más campos): composición, colores dominantes,
orientación, zonas de espacio negativo y aptitud por tipo de layout. Ese perfil
se persiste junto al asset y se usa en generación a costo cero: (a) un filtro
determinista de compatibilidad de aspect ratio entre la imagen y el panel del
layout destino, y (b) inyección del perfil visual de los candidatos en el prompt
del Art Director para que razone visualmente. Se conecta además el umbral
configurable `asset_score_threshold` que hoy está muerto.

## Users and roles

- **Usuario final de GuepardAI**: recibe presentaciones con imágenes mejor
  encajadas visualmente. No hay cambios de UI ni de permisos.
- **Pipeline de ingesta** (Celery worker): genera y persiste el perfil visual.
- **Pipeline de generación** (Art Director / Fase B): consume el perfil.
- **Admin**: puede ejecutar un backfill de perfiles para librerías ya ingestadas.

No hay diferencias de permisos: todo ocurre en procesos backend existentes.

## Acceptance criteria

- [ ] Al registrar un asset nuevo (`register_asset`), se persiste un campo
      `visual_profile` (JSON) con como mínimo: `orientation`
      (`landscape|portrait|square`), `dominant_colors` (lista de hex),
      `composition` (posición del sujeto + zonas de espacio negativo),
      `layout_suitability` (lista de slugs: `hero`, `split`, `accent`, etc.).
- [ ] Si el Vision LLM falla o devuelve JSON malformado, el asset se registra
      igual con el flujo actual (categoría por fallback, `visual_profile = null`)
      sin romper la ingesta.
- [ ] Assets existentes sin `visual_profile` siguen fluyendo por búsqueda,
      filtro y Art Director sin errores (compatibilidad hacia atrás).
- [ ] En la Fase B del Art Director, un asset cuyo aspect ratio difiere más de
      la tolerancia configurada respecto al panel de imagen del `grammar_type`
      destino queda penalizado o rechazado para layouts hi-res; la decisión queda
      registrada en `audit_metadata.rejected` con razón explícita.
- [ ] Si el asset no tiene `width`/`height` ni `visual_profile.orientation`,
      el filtro de aspect ratio no lo rechaza por ese criterio (solo aplican las
      reglas actuales de resolución).
- [ ] El umbral de score de la Fase B se lee de `system_configs.asset_score_threshold`:
      cambiar el valor en BD cambia el comportamiento del filtro sin tocar código.
- [ ] La tolerancia de aspect ratio es una nueva clave en `system_configs`
      (`aspect_ratio_tolerance`, default 0.40) seedeada en `utils/seed.py`.
- [ ] El prompt del Art Director (`prompt_art_director_v1`) recibe el
      `visual_profile` resumido de cada candidato dentro de `{found_assets}`.
- [ ] Existe un script/endpoint de backfill que regenera `visual_profile` para
      assets existentes de una marca, idempotente (no duplica assets ni
      re-procesa los que ya tienen perfil, salvo flag `force`).
- [ ] Tests: parsing y fallback del perfil en `register_asset`, filtro de aspect
      ratio (compatible, incompatible, sin dimensiones), y lectura del threshold
      desde config. Todos con LLM mockeado (patrón de `conftest.py`).

## Edge cases and error scenarios

- **Vision LLM falla en ingesta** → se mantiene el fallback actual (similitud de
  embedding → categoría `photos`); `visual_profile` queda `null`.
- **LLM devuelve campos extra, tipos incorrectos o listas en vez de strings** →
  validar con schema Pydantic; campos inválidos se descartan individualmente,
  no se descarta el perfil completo.
- **Asset deduplicado** (hash ya existe) → se reutiliza el registro existente;
  no se regenera el perfil salvo `force_tagging=True`.
- **Imágenes generadas por IA** (Gemini Creator) → también reciben perfil al
  registrarse, mismo flujo.
- **Panel del layout sin geometría de imagen** (`geo["image"]` ausente, p.ej.
  `big_metric`) → el filtro de aspect ratio no aplica.
- **`layout_override` del Art Director posterior al filtro** → fuera de alcance
  de esta iteración (ver Out of scope), pero el filtro debe calcularse con el
  `grammar_type` del Analista como hoy.
- **Backfill sobre librería grande** → procesamiento secuencial con logging de
  progreso; un fallo en un asset no aborta el lote (mismo patrón que la ingesta).
- **Quota 429 del proveedor Vision durante backfill** → el asset queda sin
  perfil y se reporta en el resumen final; re-ejecutar es seguro (idempotente).

## Out of scope

- Reranking visual con Vision LLM en tiempo de generación (contact sheet) —
  iteración 2.
- Asignación global de assets (anti-greedy) — iteración 2.
- Feedback de QA inyectado en los reintentos del Architect — fix separado.
- Revalidación del filtro de resolución tras `layout_override` — fix separado.
- QA visual sobre el render final (tier premium) — iteración posterior.
- Embeddings de imagen (CLIP-style) en columna vectorial adicional.
- Cambios de frontend o de API pública.

## Open questions

- Ninguna bloqueante. Decisión tomada con el Arquitecto: el perfil se guarda en
  una columna JSON nueva (`visual_profile`) en `BrandAsset` — el esquema se crea
  vía `Base.metadata.create_all()`, sin migración manual (columna nullable).

## References

- Código existente:
  - `backend/services/assets/asset_library_service.py` — `register_asset()` (clasificación Vision), `find_best_assets()` (búsqueda vectorial)
  - `backend/services/generation/art_director_service.py` — Fase B (filtro de candidatos, líneas ~140-228), `THRESHOLD` muerto (línea ~26)
  - `backend/services/ingestion/brand_composition_dna.py` — `GRAMMAR_GEOMETRIES`, `get_layout_geometry()` (geometría de paneles)
  - `backend/utils/seed.py` — `prompt_classifier_v1`, `prompt_art_director_v1`, `asset_score_threshold`
  - `backend/models.py` — `BrandAsset` (ya tiene `width`, `height`)
- Evaluación de arquitectura: conversación con el Arquitecto del 2026-06-10
  (diagnóstico del flujo de selección de imágenes y layout).
- Design doc: `docs/designs/mejora-seleccion-imagenes.md`
