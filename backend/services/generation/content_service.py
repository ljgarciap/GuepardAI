import os
import json
import concurrent.futures
import models
from sqlalchemy.orm import Session
from providers.llm_provider import generate_json, get_embedding
from utils.content_utils import normalize_bullets, normalize_metrics, sanitize_text_field
import psycopg
from typing import List, Dict

DB_URL = os.getenv("DATABASE_URL", "postgresql://root:root@localhost:5432/ai_db").replace("+psycopg", "")

def search_rag(query: str, knowledge_source: str, k: int = 15, brand_id=None) -> str:
    """Vector similarity search over corporate_knowledge, optionally scoped to a brand."""
    try:
        query_embedding = get_embedding(query)
    except Exception as e:
        print(f"  [ContentService] Embedding failed: {e}")
        return ""

    results = []
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                if brand_id is not None:
                    cur.execute(
                        """
                        SELECT content, 1 - (embedding <=> %s::vector) as similarity
                        FROM corporate_knowledge
                        WHERE source_filename = %s
                          AND (brand_id = %s OR is_public = 1)
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (str(query_embedding), knowledge_source, brand_id, str(query_embedding), k)
                    )
                else:
                    cur.execute(
                        """
                        SELECT content, 1 - (embedding <=> %s::vector) as similarity
                        FROM corporate_knowledge
                        WHERE source_filename = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (str(query_embedding), knowledge_source, str(query_embedding), k)
                    )
                for row in cur.fetchall():
                    results.append(row[0])
    except Exception as e:
        print(f"  [ContentService] Postgres Vector error: {e}")
        return ""

    return "\n---\n".join(results)


def _generate_slide_content(args):
    """Thread worker: per-slide targeted RAG search + LLM content generation."""
    idx, outline_slide, prompt_template, knowledge_source, brand_id, brand_name, region = args
    slide_title = sanitize_text_field(outline_slide.get("title", "Untitled Slide"))
    section_label = outline_slide.get("section_label", "STRATEGY")
    layout_type = outline_slide.get("layout_type", "composition_split")

    targeted_rag = search_rag(
        f"{slide_title} {section_label}",
        knowledge_source,
        brand_id=brand_id,
        k=10
    )

    slide_prompt = prompt_template.format(
        slide_title=slide_title,
        section_label=section_label,
        layout_type=layout_type,
        rag_context=targeted_rag or "No specific context available.",
        brand_name=brand_name,
        target_lang=region,
    )

    try:
        content = generate_json(slide_prompt, specialization="general")
        if not isinstance(content, dict):
            content = {}
    except Exception as e:
        print(f"  [ContentService] Slide {idx+1} generation failed: {e}", flush=True)
        content = {}

    return idx, {
        **outline_slide,
        "title": slide_title,
        "bullets": content.get("bullets", []),
        "subtitle": content.get("subtitle"),
        "metrics": content.get("metrics", []),
        "visual_intent": content.get("visual_intent", ""),
        "visual_tags": content.get("visual_tags", []),
        "objective": content.get("objective", ""),
        "metadata": content.get("metadata", {}),
        "_rag_chars": len(targeted_rag),
    }


def _synthesize_monolithic(db: Session, job_id: int, polished_prompt: str, rag_context: str, region: str, knowledge_source: str):
    """
    Fallback: classic 2-step synthesizer used when new prompt keys are not yet seeded.
    Produces all slide content in a single LLM call (no per-slide RAG).
    """
    cfg_synthesizer = (
        db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_content_synthesizer_v3").first()
        or db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_content_synthesizer_v2").first()
    )
    if not cfg_synthesizer:
        return False

    final_prompt = cfg_synthesizer.value.format(
        polished_prompt=polished_prompt,
        rag_context=rag_context,
        target_lang=region
    )
    response = generate_json(final_prompt)
    if isinstance(response, list):
        slides_data = response
    else:
        slides_data = response.get("slides", [])

    db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).delete()
    for i, s_data in enumerate(slides_data):
        slide_title = sanitize_text_field(s_data.get("title", "Untitled Slide"))
        db.add(models.PresentationSlide(
            job_id=job_id,
            slide_number=i + 1,
            title=slide_title,
            content_json={
                "title": slide_title,
                "bullets": s_data.get("bullets", []),
                "subtitle": s_data.get("subtitle"),
                "metrics": s_data.get("metrics", []),
                "section_label": s_data.get("section_label", "STRATEGY"),
                "layout_type": s_data.get("layout_type"),
                "objective": s_data.get("objective", ""),
                "visual_intent": s_data.get("visual_intent", ""),
                "visual_tags": s_data.get("visual_tags", []),
                "metadata": s_data.get("metadata") if isinstance(s_data.get("metadata"), dict) else {},
            },
            planning_json={"strategy": "Monolithic Fallback"},
            status=models.PresentationSlideStatus.CONTENT_READY
        ))
    db.commit()
    return _build_manifest(db, job_id)


def _build_manifest(db: Session, job_id: int):
    """Builds ContentManifest from persisted slides."""
    from schemas.presentation import ContentManifest, ContentManifestSlide
    saved_slides = (
        db.query(models.PresentationSlide)
        .filter(models.PresentationSlide.job_id == job_id)
        .order_by(models.PresentationSlide.slide_number.asc())
        .all()
    )
    manifest_slides = []
    for s in saved_slides:
        cjson = s.content_json or {}
        manifest_slides.append(ContentManifestSlide(
            slide_number=s.slide_number,
            title=s.title,
            subtitle=cjson.get("subtitle"),
            bullets=normalize_bullets(cjson.get("bullets", [])),
            metrics=normalize_metrics(cjson.get("metrics", [])),
            metric=cjson.get("metric"),
            label=cjson.get("label"),
            layout_type=cjson.get("layout_type", "strategic_split"),
            section_label=cjson.get("section_label"),
            metadata=cjson.get("metadata", {}),
            planning_json=s.planning_json or {}
        ))
    return ContentManifest(job_id=job_id, slides=manifest_slides, client_name=None)


def synthesize_presentation_outline(db: Session, job_id: int, req_data: dict):
    """
    3-Step Content Pipeline (Option A — Surgical per-slide RAG):
      Step 1: Brand-scoped RAG (k=10) for structural context
      Step 2: Prompt Architect → polished_instruction
      Step 3: Outline Generator → [{title, section_label, layout_type}] (structure only)
      Step 4: Parallel per-slide RAG (k=10) + LLM content (ThreadPoolExecutor)
      Step 5: Persist + build ContentManifest
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job:
        return False

    topic = req_data.get("prompt")
    style_slug = req_data.get("style_filename")
    knowledge_source = req_data.get("knowledge_filename")
    region = req_data.get("region", "Global")
    allow_ai_images = req_data.get("allow_ai_images", False)

    job.allow_ai_images = allow_ai_images
    db.commit()

    dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.source_filename == style_slug).first()
    brand_name = "Global Strategy"
    if dna and dna.brand:
        brand_name = dna.brand.name
    tone_guideline = "Professional executive tone."
    if dna and dna.raw_extraction:
        tone_guideline = dna.raw_extraction.get("tone_description", tone_guideline)

    cfg_architect = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_architect_v1").first()
    cfg_outline = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_content_outline_v1").first()
    cfg_slide = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_slide_content_v1").first()

    # STEP 1: Brand-scoped initial RAG (lighter — structure context only)
    print(f"  [ContentService] Step 1/3: Initial RAG (brand_id={job.brand_id}, k=10)...", flush=True)
    initial_rag = search_rag(topic, knowledge_source, brand_id=job.brand_id, k=10)

    # STEP 2: Prompt Architect
    print(f"  [ContentService] Step 2/3: Prompt Architect...", flush=True)
    architect_prompt = cfg_architect.value.format(
        topic=topic,
        brand_name=brand_name,
        tone_guideline=tone_guideline
    )
    architect_response = generate_json(architect_prompt, specialization="general")
    if isinstance(architect_response, dict):
        polished_prompt = architect_response.get("polished_instruction", str(architect_response))
    else:
        polished_prompt = str(architect_response)

    # STEP 3: Outline Generator — structure only (no content)
    if not cfg_outline:
        print(f"  [ContentService] prompt_content_outline_v1 not seeded — monolithic fallback...", flush=True)
        return _synthesize_monolithic(db, job_id, polished_prompt, initial_rag, region, knowledge_source)

    print(f"  [ContentService] Step 3/3: Outline Generator...", flush=True)
    outline_prompt = cfg_outline.value.format(
        polished_prompt=polished_prompt,
        rag_context=initial_rag or "No specific context available.",
        target_lang=region
    )
    outline_response = generate_json(outline_prompt, specialization="general")
    if isinstance(outline_response, list):
        outline_slides = outline_response
    elif isinstance(outline_response, dict):
        outline_slides = outline_response.get("slides", [])
    else:
        outline_slides = []

    if not outline_slides:
        print(f"  [ContentService] Outline returned empty — monolithic fallback...", flush=True)
        return _synthesize_monolithic(db, job_id, polished_prompt, initial_rag, region, knowledge_source)

    # STEP 4: Parallel per-slide content generation
    if not cfg_slide:
        print(f"  [ContentService] prompt_slide_content_v1 not seeded — using outline-only data...", flush=True)
        slides_data = outline_slides
    else:
        _workers_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "content_pipeline_parallel_workers").first()
        try:
            max_workers = int(_workers_cfg.value) if _workers_cfg else 4
        except (AttributeError, ValueError):
            max_workers = 4

        print(f"  [ContentService] Generating content for {len(outline_slides)} slides (max_workers={max_workers})...", flush=True)
        worker_args = [
            (idx, slide, cfg_slide.value, knowledge_source, job.brand_id, brand_name, region)
            for idx, slide in enumerate(outline_slides)
        ]

        results_by_idx = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for idx, slide_data in pool.map(_generate_slide_content, worker_args):
                rag_chars = slide_data.pop("_rag_chars", 0)
                results_by_idx[idx] = slide_data
                print(f"    Slide {idx+1}/{len(outline_slides)}: '{slide_data['title'][:45]}' (RAG: {rag_chars} chars)", flush=True)

        slides_data = [results_by_idx[i] for i in range(len(outline_slides))]

    # STEP 5: Persist + build manifest
    print(f"  [ContentService] Saving {len(slides_data)} slides...", flush=True)
    db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).delete()

    for i, s_data in enumerate(slides_data):
        slide_title = sanitize_text_field(s_data.get("title", "Untitled Slide"))
        db.add(models.PresentationSlide(
            job_id=job_id,
            slide_number=i + 1,
            title=slide_title,
            content_json={
                "title": slide_title,
                "bullets": s_data.get("bullets", []),
                "subtitle": s_data.get("subtitle"),
                "metrics": s_data.get("metrics", []),
                "section_label": s_data.get("section_label", "STRATEGY"),
                "layout_type": s_data.get("layout_type"),
                "objective": s_data.get("objective", ""),
                "visual_intent": s_data.get("visual_intent", ""),
                "visual_tags": s_data.get("visual_tags", []),
                "metadata": s_data.get("metadata") if isinstance(s_data.get("metadata"), dict) else {},
            },
            planning_json={
                "strategy": "Surgical RAG Pipeline v2",
                "objective": s_data.get("objective", "Create strategic slide")
            },
            status=models.PresentationSlideStatus.CONTENT_READY
        ))

    db.commit()
    return _build_manifest(db, job_id)
