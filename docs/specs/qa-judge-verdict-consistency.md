# Spec: Consistencia del veredicto del QA Judge (score vs needs_rework)

**Date**: 2026-06-11
**Analista**: mini-spec derivada del incidente de producción del 2026-06-11
**Rama**: `feature/storage-reorganization` (se incluye en el mismo PR que el
hardening de `log_decision`, commit `8b7950a`)
**Status**: Aprobada por Luis (daily 2026-06-11)

## Problema

`ScoreFidelityTool` (`agents/qa_validator.py`) pide al LLM judge un JSON con
`score` (0.0–1.0), `needs_rework` (bool) y `reasoning`. El veredicto actual es:

```python
needs_rework = bool(result.get("needs_rework", score < threshold))
```

Es decir: **la flag explícita del LLM prevalece sobre el score**, y el umbral
solo actúa como fallback cuando la flag no viene. En el incidente de
producción el LLM devolvió `score=0.92` (≥ threshold 0.8) y a la vez
`needs_rework=true`: el job entró en QA_FAILED y quemó un ciclo de retry pese
a tener score aprobatorio. En el peor caso (LLM contradictorio en todos los
intentos) el job termina con `qa_forced=1` — marcado como "no pasó QA por
mérito" — habiendo superado el umbral siempre.

Problemas adicionales del parse actual:

- `bool("false") is True`: si el LLM devuelve la flag como string, el fallback
  la malinterpreta.
- `float(result.get("score", 1.0))` lanza `ValueError` si el score viene no
  numérico (`"high"`), abortando el QA.
- El threshold (0.8) vive como default del `args_schema` — un límite de
  sistema hardcodeado, contra la regla de configuración en runtime.

## Decisión

**El score numérico contra el umbral es la autoridad del veredicto. La flag
del LLM es opinión auditada, nunca decisión.**

### Reglas

1. **Veredicto**: si el LLM devuelve un `score` parseable a float, se normaliza
   por clamp a `[0.0, 1.0]` y el veredicto es `needs_rework = score < threshold`.
   La flag del LLM no participa.
2. **Fallback 1 — score ausente o no parseable**: se usa la flag explícita
   `needs_rework` del LLM, parseada tolerantemente (bool nativo, o strings
   `"true"`/`"false"` case-insensitive). El `score` se reporta como `None`.
3. **Fallback 2 — ni score ni flag utilizables**: auto-pass (fail-open),
   consistente con el comportamiento existente de "Missing data for QA,
   auto-passing". Nunca se aborta el pipeline por un JSON malformado del judge.
4. **Auditoría de discrepancia**: cuando la flag del LLM contradice el
   veredicto por score (en cualquier dirección), la decisión `qa_score` en
   `ArtDirectorDecision` lleva en metadata `llm_needs_rework` (lo que dijo el
   LLM) y `llm_flag_overridden: true`. El summary lo refleja.
5. **Threshold en runtime**: nueva clave `qa_fidelity_threshold` en
   `system_configs` (seed: `"0.8"`), leída vía `get_system_config()` (ENV
   `QA_FIDELITY_THRESHOLD` tiene prioridad, como todas las claves). El
   parámetro `threshold` del tool queda como fallback si la config no parsea.

### Fuera de alcance

- No se toca el prompt del judge (pedir un schema más estricto es deseable
  pero independiente; el parse tolerante cubre el riesgo).
- No se toca el loop de retries del orquestador ni `qa_forced`.

## Criterios de aceptación

| # | Escenario (respuesta del LLM) | Veredicto esperado |
|---|---|---|
| 1 | `score=0.92, needs_rework=true` (threshold 0.8) | PASS; metadata `llm_flag_overridden=true`, `llm_needs_rework=true` |
| 2 | `score=0.5, needs_rework=false` (threshold 0.8) | REWORK; metadata `llm_flag_overridden=true` |
| 3 | `score` ausente, `needs_rework="true"` (string) | REWORK (fallback 1, parse tolerante) |
| 4 | `score="high"`, sin flag | PASS (fallback 2, fail-open) |
| 5 | `score=0.92` con `qa_fidelity_threshold=0.95` en system_configs | REWORK (config de runtime gobierna) |
| 6 | `score=4.5` (fuera de rango) | clamp a 1.0 → PASS |

Todos los casos dejan traza `qa_score` en `ArtDirectorDecision` y la suite
completa del backend queda en verde.
