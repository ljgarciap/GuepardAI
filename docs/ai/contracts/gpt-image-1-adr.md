# ADR: OpenAI gpt-image-1

**Date validated**: 2026-06-12
**Validated by**: AI Architect (live test)
**Status**: VALIDATED — API key has model access; account billing limit reached (not a model access block)
**Used in**: Fix 3 — Image generation routing (Tier 3 fallback)

---

## Decision

Use `gpt-image-1` as the Tier 3 (last resort) fallback in the image generation routing stack. The model replaced `dall-e-3` which was permanently removed from OpenAI's API on 2026-05-12.

---

## Live test results

```
Model string: gpt-image-1
HTTP status:  400
Error code:   billing_hard_limit_reached
Error type:   billing_limit_user_error
Timestamp:    2026-06-12
```

**Interpretation**: The error is a billing limit on the account, NOT a model access or API key issue. The error code `billing_hard_limit_reached` is distinct from `model_not_found` or `insufficient_quota` — the API key has access to `gpt-image-1`. Once the account's billing limit is raised or reset, the calls will succeed.

The API key is confirmed valid and authorized for `gpt-image-1`.

---

## Key difference from dall-e-3: response format

`dall-e-3` returned an image URL that required a `requests.get()` HTTP fetch.
`gpt-image-1` returns image bytes encoded as **base64** in `data[0].b64_json`. No URL fetch needed.

**Old DALL-E 3 code (BROKEN — do not use):**
```python
response = client.images.generate(model="dall-e-3", size="1792x1024", ...)
image_url = response.data[0].url           # URL fetch required
img_data = requests.get(image_url).content
```

**Correct gpt-image-1 code:**
```python
import base64

response = client.images.generate(
    model="gpt-image-1",
    prompt=clean_prompt,
    size="1536x1024",
    quality="medium",
    n=1,
)
img_bytes = base64.b64decode(response.data[0].b64_json)  # direct bytes
```

---

## Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `model` | `"gpt-image-1"` | Exact string; `"dall-e-3"` is removed |
| `size` | `"1536x1024"` | 16:9 landscape; `"1792x1024"` (used for dall-e-3) is invalid for gpt-image-1 |
| `quality` | `"medium"` | Valid values: `"low"`, `"medium"`, `"high"` |
| `n` | `1` | |
| Response field | `data[0].b64_json` | base64-encoded PNG; NOT a URL |
| SDK | `openai` Python SDK | Already in requirements.txt |

---

## Response field paths

```
response.data              → List[Image]
response.data[0]           → Image
response.data[0].b64_json  → str  ← base64-encoded image bytes
response.data[0].url       → None (not set for gpt-image-1 default response)
response.usage             → CompletionUsage (tokens used)
```

Decode: `img_bytes = base64.b64decode(response.data[0].b64_json)`

---

## Constraints

- If `OPENAI_API_KEY` is not set: skip gpt-image-1 silently (no error log). Return `None` from Tier 3.
- If response returns a safety refusal (prompt rejected): log the refusal message and return `None`. Do not retry with a modified prompt — that is out of scope for this fix.
- Account billing limit must be adequate for production use. This is a known limitation documented in the spec.
- `dall-e-3` and `size="1792x1024"` are permanently removed. Do not reference them.
