# Tasks: Reorganización Jerárquica del Storage

**Date**: 2026-06-11
**PM**: desglose del diseño `docs/designs/reorganizacion-storage.md`
**Spec**: `docs/specs/reorganizacion-storage.md`
**Status**: Pending approval
**Rama**: `feature/storage-reorganization`

## Orden de ejecución

```
S1 (StorageService + tests unit) ──▶ S2 (migrar lecturas) ──▶ S3 (migrar escrituras) ──▶ S5 (alineación Fase 2)
                                                  │                      │
                                                  └──▶ S4 (mounts + URLs + delete de job_dir)
S6 (QA integración) tras S2-S5
S7 (DevOps: compose + gitignore) — paralela, pequeña
S8 (Tech Writer) — paralela
```

---

### S1 — StorageService + tests unitarios

**Agent**: Backend Dev · **Depends on**: none · **Estimación**: 3 h

`services/core/storage_service.py` completo según el diseño (roots, dirs por
marca/job, `tmp_path`, `public_url`, `resolve` con los 5 pasos y contexto de
marca). Tests unit del resolve (absoluta, legacy, basename con/sin marca,
ausente → None) y de `public_url`.

**Files**: `backend/services/core/storage_service.py` (nuevo),
`backend/tests/test_storage_service.py` (nuevo)
**Acceptance**: criterios Fase 0 (1º) de la spec.

---

### S2 — Migrar los sitios de LECTURA a resolve()

**Agent**: Backend Dev · **Depends on**: S1 · **Estimación**: 3-4 h

Reemplazar el patrón "candidates" en: `pptx_renderer.py` (×6), `painter.py`,
`layout_engine.py`, `vision_layout_engine.py`, `painter_bridge.py`,
`artistic_pdf_service.py` (×2), `art_director_service._resolve_asset_dims`,
`utils/backfill_visual_profiles.resolve_asset_path`, `asset_engine.py`.
Criterio verificable: grep de `os.path.join("uploads"` fuera del servicio = 0
en código de lectura.

**Files**: los 9 módulos listados
**Acceptance**: criterios Fase 0 (2º y 3º) — suites en verde sin mover archivos.

---

### S3 — Migrar las ESCRITURAS a la jerarquía nueva

**Agent**: Backend Dev · **Depends on**: S2 · **Estimación**: 3-4 h

Upload de fuentes → `brand_sources_dir`; assets de ingesta →
`brand_assets_dir`; imágenes IA (`generate_ai_image` con `brand_id` opcional);
logos vía `tmp_path` → assets; renders → `job_dir`; LibreOffice/temps →
`tmp_path`. Rutas en BD relativas a `backend/`.

**Files**: `backend/main.py`, `backend/services/core/brand_service.py`,
`backend/providers/llm_provider.py`, `backend/services/ingestion/*`,
`backend/services/rendering/{pptx_renderer,artistic_pdf_service}.py`,
`backend/agents/render_agent.py`
**Acceptance**: criterios Fase 1 (1º y 2º) — generación mixta legacy+nuevo en verde.

---

### S4 — Montajes estáticos, URLs y borrado por job_dir

**Agent**: Backend Dev · **Depends on**: S2 (paralela a S3) · **Estimación**: 2 h

Mount `/files` → `storage/public`; `public_url()` en el endpoint de librería de
imágenes; DELETE de portfolios elimina `job_dir` completo; housekeeping de
`tmp/` (>24h) en el arranque; test de seguridad: requests a `private/` por
todas las rutas montadas → 404.

**Files**: `backend/main.py`
**Acceptance**: criterios Fase 1 (3º a 6º), incluido el de seguridad.

---

### S5 — Alineación de migración del histórico (Fase 2)

**Agent**: Backend Dev · **Depends on**: S3, S4 · **Estimación**: 3 h

`file_reorganization_v1` en el registry: BrandAsset → assets dir (públicos a
`_public`), pptx_path → job_dir, logo_path; lotes de 50; colisiones con sufijo
`_dup{id}`; huérfanos solo reportados; resumen completo en detail.

**Files**: `backend/services/core/data_alignment_service.py`,
`backend/services/core/storage_service.py` (helpers de move)
**Acceptance**: criterios Fase 2 de la spec.

---

### S6 — Tests de integración

**Agent**: QA · **Depends on**: S2-S5 · **Estimación**: 3 h

- Render con asset movido a la jerarquía (resolve por basename).
- Generación mixta (asset legacy + asset nuevo) en verde.
- Alineación con archivos reales en tmp de test: mueve, actualiza BD,
  re-ejecución converge a 0, huérfano reportado sin mover, colisión renombrada.
- Seguridad: `private/` inaccesible vía TestClient.

**Files**: `backend/tests/test_storage_migration.py` (nuevo)
**Acceptance**: criterios transversales; suite completa en verde.

---

### S7 — DevOps

**Agent**: DevOps · **Depends on**: none · **Estimación**: 0.5 h

Línea explícita `./backend/storage:/app/storage` en `backend` y
`celery-worker` del compose; `storage/` en `.gitignore`; verificación
post-deploy: la alineación `file_reorganization_v1` en `done` y árbol
`storage/` poblado en EC2.

**Files**: `docker-compose.yml`, `.gitignore`,
`docs/operations/post-deploy-alignment.md` (checklist)

---

### S8 — Documentación

**Agent**: Tech Writer · **Depends on**: none · **Estimación**: 1 h

CLAUDE.md (StorageService como único punto de acceso a archivos — anti-pattern
nuevo: `os.path.join("uploads", ...)` fuera del servicio), entrada de la
iteración en el ops registry (la migración corre sola como alineación),
estados de spec.

**Files**: `GuepardAI/CLAUDE.md`, `docs/operations/post-deploy-alignment.md`,
`docs/specs/reorganizacion-storage.md`

---

## Resumen

| Agente | Tareas | Horas est. |
|---|---|---|
| Backend Dev | S1-S5 | 14-16 h |
| QA | S6 | 3 h |
| DevOps | S7 | 0.5 h |
| Tech Writer | S8 | 1 h |

**Arranque propuesto**: S1 sola (es el cimiento); S7 y S8 en paralelo desde el
inicio. Fase 3 (retirar legacy) queda explícitamente para una iteración futura.
