# Spec: Fixes de Resiliencia del Pipeline de Diseño

**Date**: 2026-06-10
**Requested by**: Luis
**Status**: Done — validado por Luis en prueba manual local (2026-06-10); viaja en el merge de 0906-advance a master (sin comandos manuales post-deploy)
**Project**: GuepardAI

## Problem

La evaluación de arquitectura del flujo de selección de imágenes (2026-06-10)
identificó cuatro debilidades de resiliencia que quedaron fuera del alcance de
la Iteración 1. Son independientes entre sí y todas pequeñas:

1. **El bucle de QA no aprende**: cuando QA rechaza el plan, el orquestador
   resetea los slides a `CONTENT_READY` y reintenta, pero el `reasoning` del
   juez LLM y las `violations` del validador determinista nunca llegan al
   siguiente intento del Architect — repite las mismas decisiones a ciegas y
   quema los 2 reintentos.
2. **El `layout_override` evade los filtros de calidad**: el filtro de
   resolución/aspect ratio de la Fase B se calcula con el `grammar_type` del
   Analista, pero el Art Director puede sobreescribir el layout *después* —
   un asset que pasó el filtro para un layout split puede acabar en un
   full_bleed que exige más resolución y otro ratio.
3. **Bug del `bullet_icon`** (pre-existente): en `art_director_service.py`,
   `current_planning` se re-lee de `slide.planning_json` después de haber
   asignado `bullet_icon`, descartándolo — el accent elegido por el Art
   Director nunca se persiste.
4. **Aceptación forzada invisible**: cuando se agotan los reintentos de QA, el
   orquestador fuerza el pase (`qa_passed = True`) sin dejar rastro
   consultable — ni la API ni la UI pueden distinguir un job aprobado por QA
   de uno forzado.

## Solution summary

Cuatro fixes quirúrgicos sin cambios de arquitectura: (1) propagar el feedback
de QA al prompt del Art Director en los reintentos; (2) revalidar
resolución y aspect ratio del asset elegido cuando el Art Director
sobreescribe el layout, descartando el override si el asset no califica;
(3) eliminar la re-lectura que pisa `bullet_icon`; (4) persistir un flag
`qa_forced` en `GenerationJob` cuando la aceptación fue forzada, expuesto en
la respuesta de estado de la API.

## Users and roles

- **Pipeline de generación** (Celery worker): consume los cuatro fixes.
- **Usuario final / operador**: ve `qa_forced` en el estado del job para saber
  que el resultado no pasó QA por mérito propio.
- Sin cambios de permisos. Sin cambios de frontend (el consumo del flag por la
  UI queda fuera de alcance).

## Acceptance criteria

**F1 — Feedback de QA en retries**
- [ ] Cuando el validador determinista falla, las `violations` se inyectan en
      el prompt del Art Director del siguiente intento.
- [ ] Cuando el juez LLM rechaza (`needs_rework=True`), su `reasoning` se
      inyecta en el prompt del siguiente intento.
- [ ] El primer intento (sin feedback previo) genera exactamente el mismo
      prompt que hoy (sin bloque de feedback vacío ni placeholders huérfanos).
- [ ] El feedback inyectado es visible en `ArtDirectorDecision.prompt_used`
      del intento de retry (verificable en test).
- [ ] El feedback se trunca a un máximo configurado (default 1500 chars) para
      no inflar el prompt.

**F2 — Revalidación tras layout_override**
- [ ] Si el Art Director sobreescribe a un layout hi-res y el asset elegido no
      cumple resolución mínima o aspect ratio para el panel del layout nuevo,
      el override se descarta (se mantiene el `grammar_type` del Analista).
- [ ] El descarte queda trazado en `planning_json.art_director`
      (`layout_override_rejected` con la razón).
- [ ] Un override hacia un layout que el asset sí cumple se aplica igual que hoy.
- [ ] Si no hay asset asignado, el override se aplica sin revalidación (no hay
      nada que validar).

**F3 — Bug bullet_icon**
- [ ] Cuando el Art Director devuelve `accent_asset_id` válido,
      `planning_json.bullet_icon` contiene el basename del asset tras el commit.
- [ ] El resto de claves de `planning_json` (incluido `art_director`) se
      conservan intactas.

**F4 — Flag qa_forced**
- [ ] Nueva columna `generation_jobs.qa_forced` (Integer 0/1, default 0) con
      ALTER idempotente para BDs desplegadas.
- [ ] Cuando el orquestador fuerza la aceptación tras agotar `MAX_RETRIES`,
      `qa_forced = 1` se persiste antes del render.
- [ ] Un job aprobado por QA normalmente mantiene `qa_forced = 0`.
- [ ] El endpoint de estado del job incluye `qa_forced` en su respuesta.

**Transversal**
- [ ] Tests para los cuatro fixes con el patrón de mocking de `conftest.py`.
- [ ] Suite completa en verde.

## Edge cases and error scenarios

- **Feedback de QA vacío o no-string** (LLM devuelve dict en `reasoning`) →
  serializar a string; si queda vacío, no inyectar bloque.
- **Ambos QA fallan en el mismo ciclo** (determinista y luego LLM en el ciclo
  siguiente) → el feedback del intento más reciente reemplaza al anterior, no
  se acumulan indefinidamente.
- **Override a layout desconocido** (slug que no existe en
  `GRAMMAR_GEOMETRIES`) → `get_layout_geometry` ya hace fallback a
  `strategic_split`; la revalidación usa esa geometría resuelta.
- **Asset sin dimensiones en la revalidación del override** → mismo criterio
  que la Fase B: para hi-res sin dimensiones conocidas, el override se
  descarta (conservador); el criterio de aspect no aplica.
- **Job legacy sin columna `qa_forced`** (BD desplegada) → cubierto por el
  ALTER idempotente al arranque; el default 0 aplica a jobs históricos.
- **Reintento sin slides** → comportamiento actual sin cambios (el reset ya
  maneja la lista vacía).

## Out of scope

- Visualización de `qa_forced` en el frontend Angular (solo API).
- Cambiar la política de reintentos (`MAX_RETRIES`), el orden de validadores
  o el forzado de aceptación en sí.
- Re-ejecutar la selección de asset cuando se descarta un override (solo se
  conserva el layout del Analista; no se re-planifica).
- Acumulación histórica de feedback de QA entre jobs (solo intra-job).

## Open questions

- Ninguna bloqueante. Decisión con el Arquitecto: F2 descarta el override en
  lugar de re-seleccionar asset (re-seleccionar reabriría el bucle de Fase B y
  no justifica su complejidad para un fix).

## References

- Código afectado:
  - `backend/agents/orchestrator.py` — `run_design_and_render()` (bucle QA, F1 y F4)
  - `backend/agents/architect.py` — `ComposeLayoutTool` (`args_schema`, F1)
  - `backend/services/generation/art_director_service.py` — FASE E (F2, F3), inyección de prompt (F1)
  - `backend/services/generation/asset_fit.py` — reutilizado por F2 (sin cambios)
  - `backend/models.py` + `backend/database.py` — columna `qa_forced` (F4)
  - `backend/main.py` — endpoint de estado del job (F4)
- Spec previa: `docs/specs/mejora-seleccion-imagenes.md` (Iteración 1, Done)
- Evaluación de arquitectura: conversación del 2026-06-10
