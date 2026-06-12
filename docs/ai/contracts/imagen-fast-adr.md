# ADR: Imagen 4.0 Fast — imagen-4.0-fast-generate-001

**Date validated**: 2026-06-12
**Validated by**: AI Architect (live test)
**Status**: VALIDATED
**Used in**: Fix 3 — Image generation routing (Tier 1)

---

## Decision

Use `imagen-4.0-fast-generate-001` as the primary tier in the image generation routing stack. This model has a **separate daily quota bucket** from `imagen-4.0-generate-001`, confirmed by a live test where the fast model succeeded while the standard model returned a 429 quota error in the same session.

---

## Live test results

### imagen-4.0-fast-generate-001

```
Model string: imagen-4.0-fast-generate-001
HTTP status:  200
Latency:      4.1 seconds
Output:       1,201,641 bytes, mime_type="image/png"
Timestamp:    2026-06-12
```

**Validated call:**
```python
from google import genai as google_genai
from google.genai import types as genai_types

client = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

response = client.models.generate_images(
    model='imagen-4.0-fast-generate-001',
    prompt=clean_prompt,
    config=genai_types.GenerateImagesConfig(
        number_of_images=1,
        aspect_ratio="16:9"
    )
)

img_bytes = response.generated_images[0].image.image_bytes   # bytes
mime_type  = response.generated_images[0].image.mime_type    # "image/png"
```

### imagen-4.0-generate-001 (standard — for comparison)

```
HTTP status: 429 RESOURCE_EXHAUSTED
Error:       "You exceeded your current quota...limit: 70, model: imagen-4.0-generate"
Quota ID:    PredictRequestsPerDayPerProjectPerModelPaidTier1
```

This error confirms: (a) standard model daily quota is **70 requests/day** and was already exhausted; (b) fast model uses a **different quota bucket** (succeeded when standard was exhausted).

---

## CRITICAL: http_options bug in current production code

The current `generate_ai_image()` in `llm_provider.py` (line 957) uses:
```python
client = google_genai.Client(api_key=gem_key, http_options={'timeout': 600})
```

This `http_options` format causes **immediate ReadTimeout** in the new SDK. The parameter `http_options={'timeout': 600}` is not the correct way to set a timeout in `google-genai`.

**Required fix for Backend Dev (Fix 3):** Remove `http_options={'timeout': 600}` from the Client constructor. Use SDK defaults. Imagen calls complete in 4–15 seconds with default timeout settings.

---

## Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `model` | `imagen-4.0-fast-generate-001` | Exact string |
| `number_of_images` | `1` | Keep as 1 for cost control |
| `aspect_ratio` | `"16:9"` | Required for presentation slides |
| SDK | `google-genai` | NOT `google-generativeai` |
| Auth | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Use whichever is present |

---

## Quota

- Daily limit: **unknown** (separate bucket from standard's 70/day — not yet exhausted in testing)
- Standard model daily limit: **70/day** (confirmed from error message)
- Billing: $0.02/image (fast) vs $0.04/image (standard) — per Google pricing page

---

## Response field paths

```
response.generated_images          → List (length = number_of_images)
response.generated_images[0]       → GeneratedImage
response.generated_images[0].image → Image
response.generated_images[0].image.image_bytes  → bytes  ← the raw PNG/JPEG
response.generated_images[0].image.mime_type    → str    ← "image/png"
```

`image_bytes` is written directly to disk. No URL fetch needed (unlike DALL-E 3).

---

## Constraints

- Imagen models do not appear in `client.models.list()` output. The model string must be hardcoded.
- `http_options={'timeout': 600}` causes ReadTimeout — do not use.
- If `response.generated_images` is empty (no quota error, just no output): fall through to Tier 2, do not retry.
- If response raises any exception: fall through to Tier 2 with a WARNING log.
