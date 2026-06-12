# Spec: Calidad de Selección de Imágenes v2 (Degradación Invertida + Dedup Perceptual + QA Visual)

**Date**: 2026-06-11
**Requested by**: Luis
**Status**: Approved — plan validado por Luis en daily con el Arquitecto (2026-06-11)
**Project**: GuepardAI

## Problem

Diagnóstico forense del job 27 (premium, `pdf_artistic`, IA autorizada): slides 12
y 13 salieron con la misma fotografía y la slide 14 con una imagen pixelada de
426×427 px, pese a que la generación IA estaba habilitada (`allow_ai_images=true`)
y el QA aprobó a la primera (score 0.92, 0 violaciones). Se generaron **0 imágenes
IA** en todo el job. Cuatro causas raíz aisladas con el rastro de auditoría
(`art_director_decisions`) y verificación visual de los archivos:

1. **La "graceful degradation" anula el filtro de calidad y bloquea la IA**
   (`art_director_service.py`, Fase B). Cuando ningún candidato pasa el filtro
   estricto, el fallback re-admite los assets rechazados — incluso los rechazados
   explícitamente por resolución (la slide 14 usó el asset 137, rechazado con
   "Resolution too low (426px < 1200px)"). Como la degradación garantiza un pool
   no vacío, la Guardia de Hierro siempre fija `primary_id` y las fases de
   generación IA (B.X y E.2) se vuelven inalcanzables en la práctica.
2. **Duplicados visuales en la librería evaden la no-repetición.** Los assets 173
   (1591×2048) y 174 (591×591) son la misma foto extraída dos veces del documento
   fuente. El dedup de `register_asset` es por hash exacto de bytes y
   `exclude_ids` opera por ID; sus embeddings (descripciones casi idénticas)
   rankean igual → slides consecutivas reciben gemelos visuales.
3. **El gate de aspect ratio vacía el pool de fotos buenas.** Con
   `aspect_ratio_tolerance=0.40`, en las slides 13–14 TODAS las fotos landscape
   de alta calidad fueron rechazadas (mismatch 1.28 contra paneles verticales),
   dejando como únicos supervivientes los recortes cuadrados de baja resolución
   que luego entró a buscar la degradación. El render usa `cover` (recorta, no
   estira), así que un mismatch con sujeto centrado es un crop fuerte, no un
   defecto fatal.
4. **El QA es estructuralmente ciego a ambos defectos.** `ValidateBrandTool`
   valida una sola regla (logo/ícono como fondo hi-res) y `ScoreFidelityTool`
   ni siquiera recibe las imágenes asignadas: su contexto por slide es
   `{número, título, layout, reasoning}`. No puede detectar ni duplicados ni
   pixelación.

## Solution summary

Cuatro intervenciones coordinadas:

- **Degradación invertida**: si el pool estricto queda vacío y la IA está
  autorizada, generar imagen IA *antes* de degradar. La degradación pasa a ser
  último recurso (solo si la IA falla o está deshabilitada), con pisos duros de
  resolución (hi-res: nunca re-admitir rechazados por resolución; no hi-res:
  piso configurable) y dejando rastro (`degraded: true`) en auditoría y
  `planning_json`.
- **Dedup perceptual (dHash)**: hash perceptual puro-PIL persistido en
  `BrandAsset.perceptual_hash`; en ingesta, las variantes del mismo visual se
  resuelven conservando la de mayor resolución; en selección, la exclusión de
  no-repetición se expande a los gemelos visuales de los assets ya usados.
  Backfill como data alignment (sin tokens LLM).
- **Aspect ratio con crop seguro**: para layouts hi-res, un mismatch fuera de
  tolerancia con `visual_profile.composition.subject_position == "center"` se
  penaliza en el ranking en lugar de rechazarse (el `cover` recorta de forma
  segura un sujeto centrado); sin perfil o con sujeto descentrado se mantiene el
  rechazo actual.
- **QA con ojos**: dos reglas deterministas nuevas en `ValidateBrandTool`
  (resolución insuficiente vs layout final; imagen duplicada entre slides por id
  o por hash perceptual) que alimentan el bucle de retry existente vía
  `qa_feedback`; y el juez LLM (`ScoreFidelityTool`) recibe por slide el asset
  asignado (archivo, dimensiones, categoría, descripción, flag `degraded`).

## Users and roles

- **Usuario final de GuepardAI**: presentaciones sin imágenes repetidas ni
  pixeladas; con IA autorizada, la IA se usa de verdad cuando la librería no da.
  Sin cambios de UI ni permisos.
- **Pipeline de ingesta** (Celery worker): calcula y persiste `perceptual_hash`.
- **Pipeline de generación** (Art Director Fase B + QA): consume el hash, la
  degradación invertida y las reglas nuevas.
- **Admin**: el backfill corre solo como data alignment; sin acción manual.

## Acceptance criteria

### Degradación invertida (RC1)
- [ ] Con `allow_ai_images=true` y pool estricto vacío (todos los candidatos
      rechazados), se invoca `generate_ai_image` ANTES de re-admitir ningún
      asset rechazado; si la IA produce imagen, esta se registra y se usa como
      candidato (la degradación no se ejecuta).
- [ ] Con `allow_ai_images=false` (o IA fallida), la degradación re-admite
      candidatos pero con pisos duros: para layouts hi-res NUNCA re-admite un
      asset con `width < 1200` (los rechazados por resolución quedan fuera);
      para layouts no hi-res el piso es `degraded_min_resolution_px`
      (`system_configs`, default 600, seedeada en `utils/seed.py`).
- [ ] Cuando la degradación asigna un asset, `audit_metadata.degraded == true`
      en la decisión `layout_selection` y `planning_json.art_director.degraded
      == true` en el slide.
- [ ] La lógica de generación IA queda en un helper único reutilizado por los
      tres puntos de invocación (Nivel AI de Fase B.X, pre-degradación, Fase
      E.2) — sin duplicar el bloque generar+registrar.

### Dedup perceptual (RC2)
- [ ] `BrandAsset` tiene columna `perceptual_hash` (string, nullable, indexada);
      `database.py` la crea con `ALTER ... IF NOT EXISTS` en BDs desplegadas.
- [ ] `register_asset` calcula un dHash (implementación pura PIL, sin
      dependencias nuevas) y lo persiste; si el cálculo falla, el asset se
      registra igual con `perceptual_hash = null` (tolerante, como el resto de
      la ingesta).
- [ ] Si al registrar existe un asset del mismo scope (misma marca, o público)
      con el mismo `perceptual_hash` y resolución mayor o igual, se reutiliza el
      registro existente (mismo comportamiento que el dedup por hash exacto).
      Si el nuevo es de mayor resolución, se registra normalmente (la exclusión
      en selección cubre la convivencia de variantes).
- [ ] En la Fase B, la lista de exclusión de no-repetición se expande con todos
      los assets que comparten `perceptual_hash` con los ya usados, en los TRES
      niveles de búsqueda (semántico, 3-tags, 2-tags).
- [ ] Assets con `perceptual_hash = null` (pre-backfill) fluyen sin error por
      búsqueda, exclusión y QA (compatibilidad hacia atrás).
- [ ] Existe la data alignment `perceptual_hash_backfill_v1` registrada en
      `ALIGNMENT_REGISTRY`: idempotente (solo procesa `perceptual_hash IS
      NULL`), sin tokens LLM, con resumen `{processed, failed, missing}`, y
      documentada en `docs/operations/post-deploy-alignment.md`.

### Aspect ratio con crop seguro (RC3)
- [ ] Layout hi-res + `aspect_diff > tolerancia` +
      `visual_profile.composition.subject_position == "center"` → el asset NO se
      rechaza: su score se penaliza con `aspect_penalty_multiplier` y la
      auditoría registra la nota del crop tolerado.
- [ ] Layout hi-res + mismatch + sujeto no centrado (o sin `visual_profile`) →
      rechazo con razón explícita, como hoy.
- [ ] Layouts no hi-res mantienen el comportamiento actual (penalización).

### QA con ojos (RC4)
- [ ] `ValidateBrandTool` emite violación `LOW_RESOLUTION_IMAGE` cuando el asset
      asignado tiene `width` menor al mínimo del layout final del slide (1200
      hi-res / 800 resto, la misma regla única `_requires_hi_res`). Sin
      dimensiones conocidas no se emite violación por este criterio.
- [ ] `ValidateBrandTool` emite violación `DUPLICATE_IMAGE_ACROSS_SLIDES` cuando
      dos o más slides del job comparten asset asignado (mismo id) o el mismo
      `perceptual_hash` no nulo; la violación lista los slide_numbers afectados.
- [ ] Las violaciones nuevas viajan por el `qa_feedback` existente al retry del
      Art Director (sin cambios en el orquestador).
- [ ] `ScoreFidelityTool` incluye por slide en su contexto: archivo de imagen
      asignado, dimensiones, categoría, descripción corta y flag `degraded`.
- [ ] Tests: dHash (igualdad entre escalas de la misma imagen, diferencia entre
      imágenes distintas), expansión de exclusiones por gemelos, pisos de
      degradación, ambas reglas QA nuevas (positivo y negativo) y presencia del
      contexto visual en el prompt del juez. Todos con LLM mockeado (patrón
      `conftest.py`).

## Edge cases and error scenarios

- **IA falla en pre-degradación** (quota, key ausente, respuesta vacía) → se
  continúa con la degradación con pisos; el fallo queda en logs como hoy.
- **Degradación con pisos deja el pool vacío** → `primary_id = None`; aplica el
  flujo actual (Fase E.2 reintenta IA; placeholder si `requires_hero`). Mejor un
  placeholder limpio que una imagen pixelada.
- **Imagen corrupta / formato no soportado al calcular dHash** → hash `null`,
  asset registrado igual.
- **Dos fotos legítimamente distintas con dHash igual** (riesgo bajo con dHash
  64-bit) → la exclusión por gemelos las trataría como una; aceptado: es
  preferible variedad forzada a duplicado visible.
- **Misma foto re-encuadrada (crop) con dHash distinto** → dHash compara la
  estructura de gradientes 8×8, así que un recorte con encuadre diferente del
  mismo sujeto produce —correctamente— un hash distinto. El par del incidente
  origen es exactamente este caso: asset 173 (1591×2048, retrato completo) y
  174 (591×591, recorte cuadrado centrado del mismo sujeto) tienen hashes
  distintos, por lo que NI la exclusión de gemelos NI la regla QA
  `DUPLICATE_IMAGE_ACROSS_SLIDES` (id o hash) los fusionan. **Aceptado y
  documentado** (validado en local 2026-06-11 tras el backfill): el incidente
  se mitiga por las otras tres intervenciones (degradación invertida, pisos de
  resolución, penalización de aspect) y por la regla QA por id ante repetición
  literal, pero dos crops del mismo sujeto en slides contiguos siguen siendo
  posibles. Cerrarlo requiere embeddings de imagen CLIP-style (ver Out of scope).
- **Job con más slides que assets únicos disponibles + IA deshabilitada** → la
  regla `DUPLICATE_IMAGE_ACROSS_SLIDES` provocará retries y terminará en
  `qa_forced=1` — comportamiento honesto ya existente (el job no pasó QA por
  mérito).
- **`perceptual_hash` aún null en BDs recién desplegadas (backfill en cola)** →
  exclusión y regla de duplicados operan solo sobre hashes no nulos; el dedup
  por id sigue activo.
- **Slides sin imagen asignada** → ninguna regla nueva aplica (no hay falso
  positivo de duplicado entre `None`s).

## Out of scope

- Fase 3 del plan (render premium): re-validación de resolución al reasignar
  `pattern_type` en `_choose_pattern`/`_vision_adjust_loop`, y eliminación del
  fallback estático único de `hero_image` en `premium_visual_agent.py` — spec
  aparte (`coherencia-render-premium`).
- Juez de QA con visión sobre el PDF renderizado — iteración posterior.
- Embeddings de imagen (CLIP-style) para dedup semántico-visual. Es la única vía
  para fusionar variantes re-encuadradas del mismo sujeto (caso 173/174, ver
  Edge cases) que dHash no puede ver. Candidato a iteración aparte.
- Limpieza retroactiva de variantes duplicadas ya registradas (el backfill solo
  calcula hashes; no borra ni fusiona registros).
- Validación del `accent_asset_id` (ícono de bullets) — menor, backlog.

## Open questions

- Ninguna bloqueante. Decisiones tomadas con el Arquitecto (2026-06-11):
  dHash 64-bit puro PIL (sin dependencia `imagehash`); el piso hi-res en
  degradación no es configurable (coincide con el mínimo estricto de 1200px);
  la convivencia de variantes en BD se tolera y se neutraliza en selección.

## References

- Código:
  - `backend/services/generation/art_director_service.py` — Fase B (filtro,
    degradación, Guardia de Hierro, fases IA B.X/E.2)
  - `backend/services/assets/asset_library_service.py` — `register_asset()`,
    `find_best_assets()`, `find_assets_by_tags()`
  - `backend/agents/qa_validator.py` — `ValidateBrandTool`, `ScoreFidelityTool`
  - `backend/services/core/data_alignment_service.py` — `ALIGNMENT_REGISTRY`
  - `backend/services/generation/asset_fit.py` — `compute_aspect_fit`,
    `aspect_penalty_multiplier`
- Evidencia forense: job 27 local (2026-06-12), decisiones 1487–1515 de
  `art_director_decisions`; assets 137/173/174 verificados visualmente.
- Spec previa: `docs/specs/mejora-seleccion-imagenes.md` (Iteración 1).
