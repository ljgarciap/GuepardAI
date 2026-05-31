# Memory Summary – Consolidated Progress & Adjustments

## What was achieved
- **Cleaned Ollama blobs**: removed all `-partial` files and large leftover model blobs (Llama, Qwen) that caused disk pressure and corrupted downloads.
- **Successfully pulled `minicpm-v`** (4.4 GB + 1 GB layers) after cleanup.
- **Removed unused `cairosvg` import** and the legacy `generate_premium_json` import from `decoupled_art_director.py`.
- **Adjusted VLM concurrency**: changed semaphore from `5` to `1` in `decoupled_art_director.py` to process images sequentially on a CPU‑only environment.
- **Added a quick‑test limit**: modified `backend/scratch/run_premium_full.py` to query only the first **5 slides** (`limit(5)`) for fast iteration.
- **Ran a test generation** (5 slides) – VLM timed out (120 s) for each image, so the `PremiumArtDirector` fell back to the default layout. No `.pptx` was produced because the pipeline stopped before the render stage.
- **Docker image size** reduced to **3.01 GB** after removing heavy dependencies (`sentence‑transformers`, `playwright`).
- **Disk space**: Docker Desktop virtual disk now has ~189 GB free.

## Files Modified
| File | Change |
|------|--------|
| `backend/services/decoupled_art_director.py` | - Removed `import cairosvg` and legacy LLM import.<br>- Changed `self.sem = asyncio.Semaphore(5)` → `self.sem = asyncio.Semaphore(1)  # CPU‑only VLM` |
| `backend/scratch/run_premium_full.py` | Limited slide query: `.order_by(...).limit(5).all()` |

## Observed logs (excerpt)
```
[INFO]   [PremiumArtDirector] Autonomous VLM Design for Slide 1...
[INFO]   [AutonomousVLM] Analyzing img_bc744e9934bdae67.png...
[ERROR] [AutonomousVLM] Failed to generate layout for img_bc744e9934bdae67.png: HTTPConnectionPool(host='vision', port=11434): Read timed out. (read timeout=120)
[WARNING] [PremiumArtDirector] VLM failed to return valid JSON. Using fallback.
... (repeated for slides 2‑5)
```
The fallback layout still renders (split/pillars/quote) but no final PPTX was saved because the painter step never ran.

## Next steps for the new machine (higher resources)
1. **Increase VLM timeout** (e.g., `timeout=300` in `services/vision_service.py`).
2. **Optionally keep semaphore at 1** if you prefer sequential processing, or raise it (e.g., `5`) to parallelize now that you have more CPU cores.
3. **Consider a faster vision model** (`phi‑3‑mini‑vision` or similar) if latency remains an issue.
4. **Run the full job** (remove the `limit(5)` line) once the VLM can respond reliably.
5. **Verify generated PPTX**: after the run, the file will appear in `/app/uploads/` – copy it out with `docker cp` as done before.

---
*This memory.md file captures all the modifications and observations to help you replicate the environment on another machine.*
