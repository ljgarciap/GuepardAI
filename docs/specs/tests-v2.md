# Spec: Iniciativa de Tests v2 — Orchestrator, Redactor, LLM Provider

**Date**: 2026-06-29
**Requested by**: Luis
**Status**: Draft
**Project**: GuepardAI

---

## Contexto

La v1 estableció la infraestructura (colección limpia, scope expandido, primeros tests de
`render_agent` y `architect`). El reporte de cobertura de T5 dejó tres módulos en 0%
que son críticos para el pipeline:

| Módulo | Líneas | Cobertura | Riesgo |
|---|---|---|---|
| `agents/orchestrator.py` | 330 | 0% | CRÍTICO — coordina todo el pipeline |
| `agents/redactor.py` | 89 | 0% | CRÍTICO — genera el contenido de cada slide |
| `providers/llm_provider.py` | 604 | 8% | ALTO — routing de todos los LLM |

Un bug en el retry loop del Orchestrator, en el status tracking del Redactor, o
en el routing del LLM Provider no tiene tests que lo atrapen antes de llegar a
producción. Esa es la brecha que cierra esta iteración.

---

## Problema

### Orchestrator (0%)

`run_generation_pipeline` y `run_design_and_render` implementan lógica de control
de flujo compleja: checkpoint interactivo, bucle QA per-slide con retry, conteo
de `qa_retry_count`, set de `qa_forced`, y escritura de métricas de observabilidad.
Ninguna de estas rutas tiene test. Un cambio en el retry loop puede romper silenciosamente
el pipeline completo.

### Redactor (0%)

`GenerateTextTool` cambia el status del job (`SYNTHESIZING_CONTENT → CONTENT_READY`)
y delega en `synthesize_presentation_outline`. `SlideContentTool` tiene tres rutas
distintas: sin config seeded, con config y LLM OK, y con LLM fallido. La ruta
"sin config" devuelve un dict vacío que puede silenciosamente producir slides en blanco.
Ninguna de estas rutas tiene test.

### LLM Provider (8%)

`resolve_provider` es una función pura de 30 líneas con 6 casos de routing.
Está testeada al 0%. `get_system_config` tiene lógica de prioridad ENV > DB que
tampoco está cubierta. Son las funciones más invocadas de toda la codebase y las
más sensibles a regresiones por cambios de variables de entorno.

---

## Solución

Tres grupos de tests unitarios, todos sin BD real ni LLM real. La estrategia
de mocking sigue el patrón establecido en v1: parchear herramientas en el
nivel mínimo necesario para aislar la unidad bajo test.

---

## Criterios de aceptación

### RC1 — `providers/llm_provider.py` (objetivo: ≥ 60%)

Los siguientes tests deben existir en `tests/unit/test_llm_provider.py`:

**`resolve_provider`** (función pura — sin mocks de BD):

- [ ] `test_design_specialization_routes_to_anthropic` — con `ANTHROPIC_API_KEY` set y `specialization="design"` → retorna `"anthropic"`.
- [ ] `test_design_specialization_without_anthropic_key_falls_through` — sin `ANTHROPIC_API_KEY` y `specialization="design"` → retorna el siguiente disponible (no crashea).
- [ ] `test_embedding_specialization_prefers_mistral` — con `MISTRAL_API_KEY` set y `specialization="embedding"` → retorna `"mistral"`.
- [ ] `test_active_llm_env_respected` — con `ACTIVE_LLM=gemini` y `GOOGLE_API_KEY` set → retorna `"gemini"`.
- [ ] `test_no_keys_raises_value_error` — sin ninguna key → `resolve_provider()` lanza `ValueError`.
- [ ] `test_mistral_key_wins_without_active_llm` — sin `ACTIVE_LLM`, solo `MISTRAL_API_KEY` set → retorna `"mistral"`.

**`get_system_config`**:

- [ ] `test_env_var_takes_priority_over_db` — con `MYKEY=env_value` en env, DB tiene `mykey=db_value` → retorna `"env_value"` sin abrir sesión de BD.
- [ ] `test_db_fallback_when_no_env_var` — sin env var, DB tiene la clave → retorna el valor de BD.
- [ ] `test_default_returned_when_neither_env_nor_db` — sin env ni clave en BD → retorna el default.

**`clean_json_string`**:

- [ ] `test_strips_markdown_json_fences` — input con `\`\`\`json ... \`\`\`` → retorna solo el contenido interno.
- [ ] `test_empty_string_returns_empty_braces` — `""` → `"{}"`.
- [ ] `test_clean_string_passes_through` — JSON limpio sin fences → sin modificación.

---

### RC2 — `agents/redactor.py` (objetivo: ≥ 65%)

Tests en `tests/unit/test_redactor.py`:

**`SearchKnowledgeTool`**:

- [ ] `test_search_knowledge_delegates_to_search_rag` — verifica que `search_rag` es llamado con los mismos args que recibió la tool; retorna lo que `search_rag` retorna.

**`SlideContentTool`**:

- [ ] `test_slide_content_no_config_returns_default_dict` — con la BD retornando `None` para ambas claves de config (`prompt_slide_content_v2`, `prompt_slide_content_v1`) → retorna un dict con `"bullets": []` y `"title"` correcto; NO llama a `generate_json`.
- [ ] `test_slide_content_with_config_calls_generate_json` — con config seeded y `generate_json` mockeado retornando `{"bullets": ["A", "B"], "subtitle": "Sub"}` → retorna esos valores en el dict de salida.
- [ ] `test_slide_content_llm_failure_returns_empty_content_gracefully` — con `generate_json` lanzando `Exception("timeout")` → retorna dict con `"bullets": []` sin propagar la excepción (non-fatal).
- [ ] `test_slide_content_returns_idx_as_first_element` — el return es una tupla `(idx, content_dict)`; el `idx` es el que se pasó como argumento.

**`GenerateTextTool`**:

- [ ] `test_generate_text_sets_status_synthesizing_then_content_ready` — con job encontrado y `synthesize_presentation_outline` mockeado → `job.status` pasa por `SYNTHESIZING_CONTENT` y termina en `CONTENT_READY`.
- [ ] `test_generate_text_job_not_found_still_calls_synthesize` — con `db.query(GenerationJob).get()` retornando `None` → `synthesize_presentation_outline` aún se llama (no hay guard).
- [ ] `test_generate_text_logs_decision_with_slide_count` — `self.log_decision` es llamado con `decision_type="content_synthesis"` y el summary incluye el conteo de slides.

---

### RC3 — `agents/orchestrator.py` (objetivo: ≥ 45%)

Tests en `tests/unit/test_orchestrator.py`.

El Orchestrator instancia las tools en `__init__`. La estrategia es: crear una instancia
de `AgentOrchestrator` y parchear sus atributos (`orchestrator.generate_text`,
`orchestrator.compose_layout`, etc.) con MagicMock directamente — más limpio que
parchear la clase.

**`run_generation_pipeline`**:

- [ ] `test_run_generation_sets_initial_progress` — al inicio, `job.progress = 10` y `job.current_step` contiene "Redactor".
- [ ] `test_run_generation_happy_path_calls_tool_chain` — con todas las tools mockeadas y QA aprobando → `generate_text`, `compose_layout`, `score_fidelity`, `render_pptx` son llamadas en orden; no se llama a `validate_brand` si `score_fidelity` aprueba todo. *(Nota: `validate_brand` siempre se llama primero; si pasa, entonces `score_fidelity`. Ambas deben ser mockeadas.)*
- [ ] `test_run_generation_interactive_mode_pauses_after_redactor` — con `req_data["interactive_mode"] = True` → se llama a `generate_text` pero NO a `compose_layout` ni `render_pptx`; `job.progress = 40`.
- [ ] `test_run_generation_exception_sets_error_status` — con `generate_text` lanzando `Exception("boom")` → `job.status = ERROR` y `job.current_step` contiene el mensaje de error.

**`run_design_and_render`** (el bucle QA per-slide):

- [ ] `test_qa_passes_first_try_calls_render` — `validate_brand` retorna `{"status": "passed"}` y `score_fidelity` retorna `[]` (cero slides con `needs_rework`) → sale del loop en la primera iteración y llama a `render_pptx`.
- [ ] `test_qa_deterministic_fail_resets_slide_status` — `validate_brand` retorna `{"status": "failed", "violations": [{"rule": "LOW_RES", "slide_number": 2, "message": "px too low"}]}` → el slide 2 tiene su status reseteado a `CONTENT_READY` y `qa_feedback` contiene el slide 2.
- [ ] `test_qa_slide_exhausts_retries_sets_qa_forced` — un slide llega a `qa_retry_count > MAX_RETRIES` → `slide.qa_forced = 1`; ese slide ya no entra en `slides_to_retry`; el pipeline continúa al render (no loop infinito).
- [ ] `test_qa_all_slides_forced_sets_job_qa_forced` — cuando todos los slides failing agotan retries → `job.qa_forced = 1` y se procede al render.

**`resume_generation_pipeline`**:

- [ ] `test_resume_sets_status_processing_and_delegates` — con job encontrado → `job.status = PROCESSING` y `run_design_and_render` es llamado con el mismo `job_id` y `req_data`.

---

## Diseño técnico (para el Arquitecto)

### Patrón de mock para Orchestrator

```python
from agents.orchestrator import AgentOrchestrator

orc = AgentOrchestrator()

# Parchar tools como atributos directos
orc.generate_text = MagicMock(return_value=MagicMock(slides=[]))
orc.compose_layout = MagicMock(return_value={"success": True})
orc.validate_brand = MagicMock(return_value={"status": "passed", "violations": []})
orc.score_fidelity = MagicMock(return_value=[])  # lista vacía = todo OK
orc.render_pptx = MagicMock(return_value={"success": True, "path": "/out.pptx"})

# Parchar SessionLocal para evitar conexión a BD
with patch("agents.orchestrator.SessionLocal", return_value=db_mock):
    orc.run_generation_pipeline(job_id=1, req_data={...})
```

Para los tests del bucle QA, el mock de `db.query(PresentationSlide).filter().first()`
necesita retornar un slide con `qa_retry_count` configurable — usar `_make_slide()`
similar al patrón de `test_compose_layout.py`.

### Patrón de mock para LLM Provider

`resolve_provider` solo lee variables de entorno. Usar `monkeypatch.setenv` o
`patch.dict(os.environ, {...})` para cada caso. Sin mocks de BD.

`get_system_config` llama a `SessionLocal()`. Parchar
`providers.llm_provider.SessionLocal`.

### Patrón de mock para Redactor

`SlideContentTool.run` abre `SessionLocal()`. Parchar
`agents.redactor.SessionLocal`. La config se devuelve via:
```python
db.query.return_value.filter.return_value.first.return_value = None  # sin config
```
O con un MagicMock con `.key = "prompt_slide_content_v2"` y `.value = "template {slide_title}"`.

`synthesize_presentation_outline` debe parcharse en:
```python
patch("agents.redactor.synthesize_presentation_outline", return_value=MagicMock(slides=[...]))
```

---

## Orden de implementación recomendado

1. **`test_llm_provider.py`** primero — funciones puras, mocks mínimos, más rápidos de escribir.
2. **`test_redactor.py`** segundo — patrón similar a `test_render_agent.py`.
3. **`test_orchestrator.py`** último — más complejo, depende de patrones establecidos.

---

## Fuera de scope

- `run_ingestion_pipeline` — el bucle de assets usa `ThreadPoolExecutor` y lógica de
  archivos físicos; mejor cubierto por tests de integración.
- `services/rendering/painter.py` y `pptx_renderer.py` — requieren python-pptx y fixtures
  de PPTX; se abordan en v3 junto con la cobertura de rendering.
- `services/generation/art_director_service.py` — ya tiene 1 test; su cobertura ampliada
  va en v3 cuando se aborde el rendering completo.

---

## Cobertura proyectada al finalizar v2

| Módulo | Antes | Objetivo v2 |
|---|---|---|
| `providers/llm_provider.py` | 8% | ≥ 60% |
| `agents/redactor.py` | 0% | ≥ 65% |
| `agents/orchestrator.py` | 0% | ≥ 45% |
| Total suite unit | 100 passing | ≥ 120 passing |
