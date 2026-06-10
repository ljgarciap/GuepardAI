# Tasks: Mejora de Selección de Imágenes (Iteración 1)

**Date**: 2026-06-10
**PM**: desglose del diseño `docs/designs/mejora-seleccion-imagenes.md`
**Spec**: `docs/specs/mejora-seleccion-imagenes.md`
**Status**: Done — T1-T7 completadas, validadas por Luis (2026-06-10)

> Nota de contexto crítica (verificado en código): el seeder (`utils/seed.py:241-253`)
> **omite claves que ya existen** en `system_configs` — no hace upsert. Todo cambio
> de prompt debe ir en una clave nueva versionada (`prompt_classifier_v2`,
> `prompt_art_director_v2`) y el código debe leer la clave nueva con fallback a la
> anterior. Las claves de configuración nuevas (`aspect_ratio_tolerance`) sí se
> insertan automáticamente al arrancar.

---

## Orden de ejecución

```
T1 ──▶ T2 ──▶ T5
 │      │
 └─▶ T4 ┘
T3 (sin dependencias, paralela a T1)
T6 (QA) después de T1+T2+T3
T7 (Tech Writer) en paralelo desde el inicio
```

---

### T1 — Perfil visual en ingesta

**Agent**: Backend Dev
**Depends on**: none
**Estimación**: 3-4 h

Crear `AssetVisualProfile` (schema Pydantic tolerante: campos inválidos se
descartan individualmente), añadir columna `visual_profile` (JSON, nullable) a
`models.BrandAsset`, crear clave `prompt_classifier_v2` en `seed.py` con los
campos nuevos (`orientation`, `dominant_colors`, `composition`,
`layout_suitability`), y extraer la lógica Vision+parseo de `register_asset` a
una función compartida `build_visual_profile()`. `register_asset` lee
`prompt_classifier_v2` con fallback a `v1`/hardcoded.

**Files**: `backend/models.py`, `backend/services/assets/asset_library_service.py`,
`backend/utils/seed.py`, `backend/schemas/asset_profile.py` (nuevo)
**Acceptance**: criterios 1, 2 y 3 de la spec. Vision mockeado devuelve perfil →
se persiste; mock lanza excepción → asset se registra con `visual_profile=None`
y categoría por fallback. Firma de `register_asset` compatible con callers
existentes (`orchestrator.py`, `art_director_service.py`).
**Notify**: `.claude/scripts/notify.sh "🔧 Backend: T1 perfil visual en ingesta listo para review."`

---

### T2 — Filtro de aspect ratio en Fase B

**Agent**: Backend Dev
**Depends on**: T1 (usa `visual_profile.orientation`; con fallback a width/height puede empezar en paralelo si T1 se retrasa)
**Estimación**: 3-4 h

Crear `services/generation/asset_fit.py` con `compute_aspect_fit(asset_w, asset_h,
panel_geometry) -> float` (función pura, sin BD). Integrarla en el bucle de
filtrado de `plan_presentation_design()`: rechazo con razón explícita en
`audit_metadata.rejected` para layouts hi-res fuera de tolerancia; penalización
de score para el resto. Sin dimensiones disponibles → el criterio no aplica.
Relajación en el fallback de degradación elegante, igual que la resolución.

**Files**: `backend/services/generation/asset_fit.py` (nuevo),
`backend/services/generation/art_director_service.py`
**Acceptance**: criterios 4 y 5 de la spec. El panel se obtiene de
`get_layout_geometry()`; el rechazo aparece en `audit_metadata` con razón
`"Aspect ratio mismatch"`.
**Notify**: `.claude/scripts/notify.sh "🔧 Backend: T2 filtro aspect ratio listo para review."`

---

### T3 — Configuración runtime (threshold muerto + tolerancia)

**Agent**: Backend Dev
**Depends on**: none (paralela a T1)
**Estimación**: 2 h

Reemplazar el `0.40` hardcodeado del filtro y el `0.45` del recovery floor en
`art_director_service.py` por `THRESHOLD` (ya leído de
`asset_score_threshold`, valor seedeado 0.45). Añadir clave nueva
`aspect_ratio_tolerance` = `"0.40"` en `seed.py` y leerla en el filtro de T2
(coordinar la interfaz: T2 recibe la tolerancia como parámetro).
Actualizar también el valor que se persiste en `planning_json.art_director.threshold`.

**Files**: `backend/services/generation/art_director_service.py`, `backend/utils/seed.py`
**Acceptance**: criterios 6 y 7 de la spec. Cambiar `asset_score_threshold` en BD
modifica el filtrado sin tocar código (test de integración con `db_session`).
**Notify**: `.claude/scripts/notify.sh "🔧 Backend: T3 config runtime de thresholds lista para review."`

---

### T4 — Prompt del Art Director enriquecido

**Agent**: Backend Dev
**Depends on**: T1
**Estimación**: 2 h

Incluir en cada entrada de `filtered_assets` un resumen compacto del
`visual_profile` (`orientation`, `subject_position`, `negative_space`,
`layout_suitability`). Crear `prompt_art_director_v2` en `seed.py` con la
instrucción de preferir assets cuyo espacio negativo coincide con la zona de
texto del layout; `art_director_service.py` lee `v2` con fallback a `v1`.

**Files**: `backend/services/generation/art_director_service.py`, `backend/utils/seed.py`
**Acceptance**: criterio 8 de la spec. Assets sin perfil aparecen sin esos campos
(no `null` ruidosos). El prompt renderizado (visible en `ArtDirectorDecision.prompt_used`)
contiene el perfil de los candidatos.
**Notify**: `.claude/scripts/notify.sh "🔧 Backend: T4 prompt Art Director v2 listo para review."`

---

### T5 — Backfill de perfiles para librerías existentes

**Agent**: Backend Dev
**Depends on**: T1 (reutiliza `build_visual_profile()`)
**Estimación**: 2-3 h

Script `backend/utils/backfill_visual_profiles.py`: procesa assets con
`visual_profile IS NULL` de una marca (`--brand-id`) o todas (`--all`), con
`--force` para regenerar. Secuencial, logging de progreso, resumen final
(ok/fallidos), un fallo no aborta el lote, idempotente.

**Files**: `backend/utils/backfill_visual_profiles.py` (nuevo)
**Acceptance**: criterio 9 de la spec. Ejecutar dos veces seguidas no re-procesa
assets ya perfilados; un 429 simulado deja el asset sin perfil y lo reporta.
**Notify**: `.claude/scripts/notify.sh "🔧 Backend: T5 backfill de perfiles visuales listo para review."`

---

### T6 — Suite de tests de la iteración

**Agent**: QA
**Depends on**: T1, T2, T3
**Estimación**: 3-4 h

Tests con el patrón de mocking de `conftest.py` (cero tokens):
- `register_asset`: perfil válido persiste; JSON malformado → campos descartados
  individualmente; excepción Vision → `visual_profile=None` + fallback actual.
- `compute_aspect_fit`: landscape en panel hero (pasa), portrait en panel hero
  (rechaza), sin dimensiones (no aplica), tolerancia límite exacta.
- Threshold desde config: cambiar `asset_score_threshold` en `db_session` altera
  qué candidatos pasan el filtro.
- Regresión: pipeline completo con assets sin `visual_profile` (compatibilidad
  hacia atrás, criterio 3).

**Files**: `backend/tests/test_asset_profile.py` (nuevo),
`backend/tests/test_asset_fit.py` (nuevo), ajustes en `backend/tests/conftest.py`
**Acceptance**: criterio 10 de la spec. `pytest --cov=agents tests/` en verde con
la BD de test (puerto 5433).
**Notify**: `.claude/scripts/notify.sh "✅ QA: suite de tests de selección de imágenes en verde."`

---

### T7 — Documentación

**Agent**: Tech Writer
**Depends on**: none (en paralelo; cierra cuando T1-T5 estén mergeadas)
**Estimación**: 1-2 h

Actualizar `CLAUDE.md` de GuepardAI: sección *Asset system* del Analyst
(perfil visual, nuevas claves de config, convención de versionado de prompts
`_v2`) y la fila correspondiente en *Anti-patterns* del Senior Reviewer
(thresholds hardcodeados ya no aplican). Actualizar `Status` de la spec a
`In Development` → `Done` al cierre.

**Files**: `GuepardAI/CLAUDE.md`, `docs/specs/mejora-seleccion-imagenes.md`
**Acceptance**: un dev nuevo puede entender el flujo de perfil visual solo con
CLAUDE.md; sin referencias a claves de config inexistentes.
**Notify**: `.claude/scripts/notify.sh "📚 Tech Writer: documentación de selección de imágenes actualizada."`

---

## Resumen de asignación

| Agente | Tareas | Horas est. |
|---|---|---|
| Backend Dev | T1, T2, T3, T4, T5 | 12-15 h |
| QA | T6 | 3-4 h |
| Tech Writer | T7 | 1-2 h |
| Frontend Dev / DevOps | — (sin cambios de UI ni infraestructura) | 0 h |

**Primera tarea a ejecutar**: T1 y T3 en paralelo (sin dependencias).
Todo el trabajo pasa por Senior Reviewer antes de QA, según el flujo del equipo.
