# Design: Mejora de Selección de Imágenes (Iteración 1)

**Date**: 2026-06-10
**Architect**: aprobado
**Spec**: `docs/specs/mejora-seleccion-imagenes.md`
**Status**: Approved — listo para desglose del PM

## Decisiones de diseño

### 1. Perfil visual en ingesta (costo único, cero costo en generación)

**Dónde**: `register_asset()` en `services/assets/asset_library_service.py` y
`prompt_classifier_v1` en `utils/seed.py`.

- Se amplía `prompt_classifier_v1` para que la llamada Vision existente devuelva,
  además de `category`/`description`/`tags`:
  ```json
  {
    "orientation": "landscape | portrait | square",
    "dominant_colors": ["#RRGGBB", "..."],
    "composition": {
      "subject_position": "left | center | right | full",
      "negative_space": ["top", "left", "..."]
    },
    "layout_suitability": ["hero", "split", "accent"]
  }
  ```
- Validación con un schema Pydantic nuevo (`schemas/` o módulo local):
  `AssetVisualProfile`. Campos inválidos se descartan campo a campo
  (validators tolerantes), nunca se aborta el registro del asset.
- Persistencia: columna nueva `visual_profile` (tipo `JSON`, nullable) en
  `models.BrandAsset`. Se crea vía `Base.metadata.create_all()` — sin migración.
- El fallback actual (Vision falla → embedding similarity → `photos`) se
  mantiene intacto; en ese caso `visual_profile = None`.

### 2. Filtro determinista de aspect ratio (Fase B del Art Director)

**Dónde**: `plan_presentation_design()` en
`services/generation/art_director_service.py`, dentro del bucle de filtrado
de candidatos (junto al filtro de resolución existente).

- Nueva función pura `compute_aspect_fit(asset_w, asset_h, panel_geometry) -> float`
  (módulo nuevo `services/generation/asset_fit.py` para que sea testeable sin BD).
- El ratio del panel se obtiene de `get_layout_geometry(grammar_type, s_w, s_h)`
  → `geo["image"]` (width/height en porcentaje sobre dimensiones del slide).
- Regla: si `|ratio_imagen − ratio_panel| / ratio_panel > aspect_ratio_tolerance`
  y el layout es hi-res → rechazar con razón `"Aspect ratio mismatch"` en
  `audit_metadata.rejected`. Para layouts no hi-res, solo penalizar el score
  (multiplicador), no rechazar.
- Dimensiones: prioridad `asset.width/height` → verificación física PIL (reutilizar
  el bloque existente) → si no hay datos, el criterio no aplica (no rechazar).
- En el fallback de degradación elegante (cuando ningún asset pasa los filtros
  estrictos) el criterio de aspect ratio se relaja igual que la resolución.

### 3. Configuración runtime (fix del threshold muerto)

**Dónde**: `art_director_service.py` + `utils/seed.py`.

- `THRESHOLD` (leído de `asset_score_threshold`, hoy sin uso) reemplaza el
  `0.40` hardcodeado del filtro y el `0.45` del recovery floor. Si se quiere
  mantener dos valores distintos, añadir `asset_recovery_floor` como clave
  separada (decisión: una sola clave, los dos puntos usan `THRESHOLD`;
  el seed pasa a `0.45` que ya es el valor seedeado).
- Nueva clave seedeada: `aspect_ratio_tolerance` = `"0.40"`.
- Lectura vía el patrón existente (query a `SystemConfig`), no hardcodear.

### 4. Prompt del Art Director enriquecido

**Dónde**: construcción de `filtered_assets` en `art_director_service.py` y
`prompt_art_director_v1` en `seed.py`.

- Cada entrada de `found_assets` incluye un resumen compacto del perfil:
  `orientation`, `subject_position`, `negative_space`, `layout_suitability`.
- Se añade una instrucción al prompt: preferir assets cuyo `negative_space`
  coincide con la zona de texto del layout y cuya `layout_suitability`
  incluye el grammar_type destino.

### 5. Backfill para librerías existentes

**Dónde**: script nuevo `utils/backfill_visual_profiles.py` (mismo patrón que
los scripts admin existentes).

- Recorre `BrandAsset` de una marca (o todas con `--all`), procesa solo los que
  tienen `visual_profile IS NULL` salvo `--force`. Secuencial, con logging de
  progreso y resumen final (ok / fallidos). Un fallo no aborta el lote.
- Reutiliza la misma función de perfilado que `register_asset` (extraer la
  lógica Vision+parseo a una función compartida `build_visual_profile(file_path, db, brand_id)`).

## Restricciones (no negociables)

- Todas las llamadas LLM vía `providers/llm_provider.py` (`generate_vision_json`).
- Sin nuevos imports directos de SDKs de proveedores.
- Config runtime en `system_configs` vía `seed.py`, nunca hardcodeada.
- `register_asset` no debe romperse para callers existentes (firma compatible).
- Tests con el patrón de mocking global de `conftest.py` (cero tokens reales).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El Vision LLM ignora los campos nuevos del schema | Validación Pydantic tolerante + `visual_profile` nullable; el pipeline no depende del perfil |
| Filtro de aspect ratio demasiado agresivo → más placeholders | Tolerancia configurable en BD + degradación elegante existente lo relaja |
| Prompt del classifier más largo → respuestas más lentas en ingesta | Aceptable: la ingesta es batch/async; no afecta generación |
| Cambiar el seed no actualiza BDs ya seedeadas | `seed.py` debe hacer upsert del prompt (verificar comportamiento actual del seeder con claves existentes) — tarea explícita |
