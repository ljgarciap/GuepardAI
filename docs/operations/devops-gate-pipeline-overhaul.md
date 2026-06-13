# DevOps Gate A — Sign-off: Generation Pipeline Overhaul

**Date**: 2026-06-12
**Reviewer**: DevOps
**Design reviewed**: `docs/designs/generation-pipeline-overhaul-design.md`
**Spec reviewed**: `docs/specs/generation-pipeline-overhaul.md`
**Status**: APPROVED — no YML changes required

---

## Verdict

**All five fixes are cleared to proceed.** No Docker Compose, CI/CD, or Dockerfile changes are required for any of the five fixes. Findings per question below.

---

## Finding 1 — Docker Compose service changes

**No changes needed.**

`docker-compose.yml` has five services: `db`, `backend`, `redis`, `celery_worker`, `frontend`. There is no `vision` service defined anywhere in the file. The Ollama endpoint that Fix 2 removes was only referenced in application code — it was never declared as a compose service. Removing `vision_layout_engine.py` has zero impact on the compose topology.

No new services are introduced by any of the five fixes.

---

## Finding 2 — requirements.txt changes and Docker image rebuild

**No special CI/CD step needed. Standard `--build` handles it.**

`backend/requirements.txt` currently contains both `google-generativeai` and `google-genai`. Fix 5 removes `google-generativeai`.

The Dockerfile (`backend/Dockerfile` line 20) runs:
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

The deploy script in `ci_cd.yml` already runs `sudo docker compose up -d --build`, which triggers a full image rebuild. Docker layer caching will invalidate the pip install layer when `requirements.txt` changes (because `COPY requirements.txt .` precedes the pip install). The removal of `google-generativeai` will be picked up automatically on the next deploy with no manual intervention.

**No explicit rebuild step needed in the deploy workflow.**

---

## Finding 3 — CI/CD workflow changes

**No changes to `.github/workflows/ci_cd.yml` needed.**

The CI pipeline (`backend-tests` job) installs `pip install -r backend/requirements.txt` and runs pytest. When `google-generativeai` is removed from requirements.txt, it will no longer be installed in the CI environment. This is correct behavior — it is the Backend Dev's responsibility (Fix 5 test sub-task) to update any test patches from `google.generativeai` to `google.genai` before merging.

The CI pipeline does not reference any of the affected application modules directly. No workflow step changes are required.

---

## Annotations (non-blocking observations)

1. **CI env var mismatch (pre-existing, out of scope)**: The CI job sets `GOOGLE_AI_API_KEY: "fake-key"` but `llm_provider.py` reads `GOOGLE_API_KEY` or `GEMINI_API_KEY`. This was present before this overhaul and does not affect test outcomes (LLM calls are mocked globally in conftest.py). Not introduced by any fix in this spec.

2. **Docker layer cache on first Fix 5 deploy**: Removing a package from requirements.txt invalidates the pip layer cache and triggers a full `pip install`. On the EC2 deploy, the script already runs `docker system prune -a -f` before the build, so there is no stale cache risk. Estimated additional build time: ~60–90 seconds (standard).

3. **OLLAMA_URL env var**: The variable `OLLAMA_URL` is referenced in `llm_provider.py` for optional Ollama text/embedding paths (not removed by Fix 2 per the spec). It is not defined in `docker-compose.yml` and does not need to be. If it is never set, the Ollama paths in llm_provider.py silently skip — no action needed.

---

## Summary

| Fix | Docker Compose | CI/CD YML | Dockerfile | Notes |
|-----|---------------|-----------|------------|-------|
| Fix 1 — QA per-slide | No change | No change | No change | DB column is additive, auto-healed at startup |
| Fix 2 — AutonomousVLM removal | No change | No change | No change | `vision` service was never in compose |
| Fix 3 — Image routing | No change | No change | No change | `openai` SDK already in requirements |
| Fix 4 — Layout slugs | No change | No change | No change | Config-only change via seed.py |
| Fix 5 — google.genai migration | No change | No change | No change | `--build` on deploy picks up requirements.txt change automatically |
