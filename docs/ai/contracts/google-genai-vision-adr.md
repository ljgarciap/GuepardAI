# ADR: google.genai SDK Migration — Text, Vision, and Embeddings

**Date validated**: 2026-06-12
**Validated by**: AI Architect (live tests on all three call types)
**Status**: VALIDATED
**Used in**: Fix 5 — Migrate google.generativeai to google.genai in llm_provider.py

---

## Decision

Migrate all `google.generativeai` (`genai.*`) calls in `llm_provider.py` to `google.genai` (`google_genai.*`). The new SDK is already imported in the file (`from google import genai as google_genai`). The old package produces `FutureWarning` on every startup.

---

## Live test results

All three call types validated on 2026-06-12:

| Call type | Model | Latency | Status |
|-----------|-------|---------|--------|
| Text / JSON | `gemini-2.5-flash` | 1.0s | SUCCESS |
| Vision (multimodal) | `gemini-2.5-flash` | 1.9s | SUCCESS |
| Embeddings | `gemini-embedding-001` | 0.5s | SUCCESS |

---

## Migration contract: Text / JSON generation

**Old (google.generativeai):**
```python
genai.configure(api_key=gem_key)
m = genai.GenerativeModel(model_name)
response = m.generate_content(
    prompt,
    generation_config=genai.GenerationConfig(
        temperature=0.3,
        response_mime_type="application/json"
    )
)
result = response.text  # str
```

**New (google.genai) — validated:**
```python
client = google_genai.Client(api_key=gem_key)
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=genai_types.GenerateContentConfig(
        temperature=0.3,
        response_mime_type="application/json"
    )
)
result = response.text  # str — identical field path
```

Notes:
- `genai.configure(api_key=...)` + `genai.GenerativeModel(...)` collapses into `google_genai.Client(api_key=...)`
- `genai.GenerationConfig` → `genai_types.GenerateContentConfig` (import: `from google.genai import types as genai_types`)
- `response.text` field path is unchanged
- `request_options={"timeout": 60}` (old pattern) is dropped — SDK default timeouts apply

---

## Migration contract: Vision (multimodal)

**Old (google.generativeai):**
```python
genai.configure(api_key=gem_key)
m = genai.GenerativeModel(model_name)
content = [prompt]
for img_data in prepared_imgs:
    content.append({"mime_type": "image/jpeg", "data": img_data})  # dict — INVALID in new SDK
response = m.generate_content(
    content,
    generation_config=genai.GenerationConfig(temperature=0.1, response_mime_type="application/json"),
    request_options={"timeout": 60}
)
return json.loads(response.text)
```

**New (google.genai) — validated:**
```python
client = google_genai.Client(api_key=gem_key)

contents = [genai_types.Part(text=prompt)]
for img_data in prepared_imgs:
    contents.append(
        genai_types.Part(inline_data=genai_types.Blob(mime_type="image/jpeg", data=img_data))
    )

response = client.models.generate_content(
    model=model_name,
    contents=contents,
    config=genai_types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json"
    )
)
return json.loads(response.text)
```

**CRITICAL**: The old `{"mime_type": "image/jpeg", "data": bytes}` raw dict format is **rejected by the new SDK** (Pydantic ValidationError — `Extra inputs are not permitted`). Image data **must** be wrapped in `genai_types.Part(inline_data=genai_types.Blob(...))`.

---

## Migration contract: Embeddings

**Old (google.generativeai):**
```python
genai.configure(api_key=gem_key)
res = genai.embed_content(
    model=model_name,
    content=item,                             # str or {"mime_type": ..., "data": bytes}
    task_type="retrieval_document",
    output_dimensionality=TARGET_DIM          # forces 1024 dimensions
)
embedding = res["embedding"]                  # dict key access
```

**New (google.genai) — validated:**
```python
client = google_genai.Client(api_key=gem_key)
response = client.models.embed_content(
    model=model_name,
    contents=item,                            # str; bytes path: see note below
    config=genai_types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT",       # uppercase enum string
        output_dimensionality=TARGET_DIM      # same parameter name, confirmed dim=1024
    )
)
embedding = response.embeddings[0].values    # attribute access, not dict key
```

Notes:
- `output_dimensionality=1024` is supported and confirmed to produce 1024-dimension vectors
- `task_type` changes from lowercase string (`"retrieval_document"`) to uppercase (`"RETRIEVAL_DOCUMENT"`)
- Response access changes from `res["embedding"]` (dict) to `response.embeddings[0].values` (object attribute)
- For image embedding (bytes path): Backend Dev must test `genai_types.Blob` wrapping — the `{"mime_type": ..., "data": bytes}` dict pattern is invalid. Likely: `contents=genai_types.Blob(mime_type="image/jpeg", data=item)`.

---

## Client instantiation pattern

The `genai.configure(api_key=...)` global configuration call is removed entirely. Each call block creates its own client:

```python
client = google_genai.Client(api_key=gem_key)
```

If the codebase currently creates one client per request (which is fine — clients are lightweight).

---

## Required import changes

```python
# Remove:
import google.generativeai as genai

# Keep (already present):
from google import genai as google_genai
from google.genai import types as genai_types  # add this if not present
```

---

## Constraints

- Do NOT pass `http_options={'timeout': N}` to `google_genai.Client()` — causes ReadTimeout (confirmed in Imagen tests)
- The model list returned by `client.models.list()` does NOT include Imagen models — model strings for image generation must remain hardcoded
- Tests patching `google.generativeai` must be updated to patch `google.genai` after Fix 5
- `genai_types` is already importable after `google-genai` installation — it is `from google.genai import types`
