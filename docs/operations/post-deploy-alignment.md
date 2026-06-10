# Post-Deploy Alignment Commands

Registro de comandos manuales requeridos para alinear datos/esquema después de
desplegar una release. **Si tu feature necesita un comando de este tipo, regístralo
aquí** — el deploy a EC2 es automático (push a `master`), así que cualquier paso
manual no documentado deja producción desalineada en silencio.

Regla de oro: antes de añadir una entrada aquí, evalúa si el paso puede
automatizarse en el arranque (seeds en `utils/seed.py`, ALTERs idempotentes en
`database.py`). El comando manual es el último recurso.

---

## Iteración 1 — Selección de Imágenes (2026-06-10)

**Qué se alinea automáticamente al desplegar (sin acción manual):**
- Columna `brand_assets.visual_profile` → ALTER idempotente en `database.py` al arrancar.
- Claves nuevas de `system_configs` (`prompt_classifier_v2`, `prompt_art_director_v2`,
  `aspect_ratio_tolerance`) → insertadas por `seed.py` al arrancar.

**Acción manual requerida (una sola vez por marca existente):**

```bash
# Dentro del contenedor backend en EC2:
docker exec -it guepard-backend python utils/backfill_visual_profiles.py --brand-id <id>
# o para todas las marcas:
docker exec -it guepard-backend python utils/backfill_visual_profiles.py --all
```

| Aspecto | Detalle |
|---|---|
| **Por qué** | Los assets ingestados antes de esta release no tienen `visual_profile`; sin él siguen funcionando, pero sin filtro de aspect ratio enriquecido ni perfil en el prompt del Art Director |
| **Cuándo** | Después del primer deploy que incluya `bc7655b`; las marcas ingestadas a partir de esta release NO lo necesitan. **ORDEN CRÍTICO**: el backend nuevo debe haber arrancado al menos una vez antes del backfill (el arranque siembra `prompt_classifier_v2`; sin esa clave el backfill usa el prompt v1 y no genera perfiles — deja todo en NULL sin error) |
| **Idempotencia** | Sí — solo procesa assets con `visual_profile IS NULL`; re-ejecutar es seguro. `--force` regenera todos |
| **Costo** | 1 llamada Vision LLM por asset (secuencial). Un fallo (ej. 429) no aborta el lote; re-ejecutar reintenta solo los fallidos |
| **Verificación** | `SELECT count(*) FROM brand_assets WHERE visual_profile IS NOT NULL AND category != 'noise';` debe acercarse al total de assets útiles |
