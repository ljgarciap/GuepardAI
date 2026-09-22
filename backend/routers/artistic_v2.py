"""
routers/artistic_v2.py — Artistic Generation Engine v2 (Phase 4: isolated rollout).
docs/specs/artistic-generation-v2.md

Isolated entry point for engine_version="v2_artistic" jobs — the only new
surface Phase 4 needs. Reuses the exact same Celery task
(tasks.celery_generate_presentation) v1 uses: engine_version lives on the
GenerationJob row, and AgentOrchestrator.run_design_and_render() already
branches on it (agents/orchestrator.py) — no new task, no new pipeline entry
point. Status polling and slide retrieval also reuse the existing
/api/generation/status/{job_id} and /api/presentations/{job_id}/slides
routes in main.py unchanged (neither filters on engine_version).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth.dependencies import check_brand_tenant_access, get_current_user, tenant_brand_ids_filter
from database import get_db
from tasks import celery_generate_presentation

router = APIRouter(prefix="/api/artistic-v2", tags=["Artistic Generation v2"])


class ArtisticV2GenerateRequest(BaseModel):
    brand_id: int
    prompt: str
    style_filename: str = ""
    knowledge_filename: str = ""
    region: str = "LATAM"
    allow_ai_images: bool = False
    output_format: str = "pptx"
    tier: str = "free"


@router.get("/eligible-brands")
def list_eligible_brands(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Brands with at least one mined BrandLayoutGrammar row (Phase 0) AND at
    least a BrandVisualDna row — i.e. brands that can actually complete a
    real generation, not just brands used to test mining in isolation.

    Found live: a brand mined for Phase 0 testing but never run through the
    real v1 ingestion pipeline (no BrandVisualDna/BrandAsset at all) passes
    compose_canvas_for_job() fine (it only needs BrandLayoutGrammar) but then
    crashes deep in the shared render step — first on PainterAgencyBranding's
    logo_path (fixed separately), then on a bare `brand_dna.primary_color`
    access with brand_dna=None. That second one is a pre-existing assumption
    throughout the render pipeline (v1 and v2 alike: every real brand has a
    BrandVisualDna) that's out of scope to chase through every call site
    here — the correct fix at this layer is to never offer a brand that
    can't satisfy it in the first place.
    """
    query = db.query(models.Brand.id, models.Brand.name).join(
        models.BrandLayoutGrammar, models.BrandLayoutGrammar.brand_id == models.Brand.id
    ).join(
        models.BrandVisualDna, models.BrandVisualDna.brand_id == models.Brand.id
    ).distinct()

    tenant_ids = tenant_brand_ids_filter(db, current_user)
    if tenant_ids is not None:
        query = query.filter(models.Brand.id.in_(tenant_ids))

    return {"brands": [{"id": b_id, "name": name} for b_id, name in query.all()]}


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate_artistic_v2(
    request: ArtisticV2GenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    check_brand_tenant_access(db, current_user, request.brand_id)

    has_grammar = db.query(models.BrandLayoutGrammar).filter(
        models.BrandLayoutGrammar.brand_id == request.brand_id
    ).first()
    if not has_grammar:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This brand has no mined layout grammar yet — run grammar mining "
                   "(Artistic Engine v2, Phase 0) before generating with it.",
        )

    # A brand can have mined grammar but never have gone through real v1
    # ingestion (e.g. a Phase 0 mining-only test brand) — the shared render
    # step assumes every brand has a BrandVisualDna row and crashes deep in
    # the pipeline otherwise. Same fail-fast reasoning as the grammar check
    # above: catch it here, not as an opaque mid-pipeline error.
    has_visual_dna = db.query(models.BrandVisualDna).filter(
        models.BrandVisualDna.brand_id == request.brand_id
    ).first()
    if not has_visual_dna:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This brand has mined layout grammar but was never run through "
                   "brand ingestion (no visual DNA) — it can't complete a real "
                   "generation yet, v1 or v2.",
        )

    style_dna = None
    if request.style_filename:
        style_dna = db.query(models.BrandVisualDna).filter(
            models.BrandVisualDna.source_filename == request.style_filename
        ).first()

    job = models.GenerationJob(
        brand_id=request.brand_id,
        style_id=style_dna.id if style_dna else None,
        status=models.GenerationJobStatus.PENDING,
        progress=0,
        current_step="Initializing Artistic Generation Engine v2...",
        allow_ai_images=request.allow_ai_images,
        owner_id=current_user.id,
        prompt=request.prompt,
        engine_version="v2_artistic",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    req_payload = {
        "style_filename": request.style_filename,
        "knowledge_filename": request.knowledge_filename,
        "prompt": request.prompt,
        "region": request.region,
        "allow_ai_images": request.allow_ai_images,
        "output_format": request.output_format,
        "tier": request.tier,
        "interactive_mode": False,
    }
    celery_generate_presentation.delay(job.id, req_payload)

    return {"job_id": job.id, "status": models.GenerationJobStatus.PENDING, "engine_version": "v2_artistic"}
