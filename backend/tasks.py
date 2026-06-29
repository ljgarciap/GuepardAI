import logging
from celery_app import celery_app
from services.ingestion.ingestion_orchestrator import (
    task_extract_full_brand_style as run_extract_full_brand_style,
    task_ingest_knowledge as run_ingest_knowledge,
    task_extract_pure_assets as run_extract_pure_assets,
    task_generate_presentation as run_generate_presentation,
)

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.celery_extract_full_brand_style")
def celery_extract_full_brand_style(job_key: str, file_path: str, source_filename: str, visibility_scope: str, brand_id: int, manual_tags: list):
    logger.info(f"[Celery] Ingestion Brand Style task started for job_key={job_key}")
    run_extract_full_brand_style(
        job_key=job_key,
        file_path=file_path,
        source_filename=source_filename,
        visibility_scope=visibility_scope,
        brand_id=brand_id,
        manual_tags=manual_tags
    )

@celery_app.task(name="tasks.celery_ingest_knowledge")
def celery_ingest_knowledge(job_key: str, file_path: str, source_filename: str, brand_id: int, visibility_scope: str, document_type: str):
    logger.info(f"[Celery] Ingestion Knowledge task started for job_key={job_key}")
    run_ingest_knowledge(
        job_key=job_key,
        file_path=file_path,
        source_filename=source_filename,
        brand_id=brand_id,
        visibility_scope=visibility_scope,
        document_type=document_type
    )

@celery_app.task(name="tasks.celery_extract_pure_assets")
def celery_extract_pure_assets(job_key: str, file_path: str, source_filename: str, visibility_scope: str, brand_id: int, manual_tags: list):
    logger.info(f"[Celery] Ingestion Pure Assets task started for job_key={job_key}")
    run_extract_pure_assets(
        job_key=job_key,
        file_path=file_path,
        source_filename=source_filename,
        visibility_scope=visibility_scope,
        brand_id=brand_id,
        manual_tags=manual_tags
    )

@celery_app.task(name="tasks.celery_generate_presentation")
def celery_generate_presentation(job_id: int, req_payload: dict):
    logger.info(f"[Celery] Presentation Generation task started for job_id={job_id}")
    run_generate_presentation(
        job_id=job_id,
        req_data=req_payload
    )

@celery_app.task(name="tasks.celery_resume_generation_pipeline")
def celery_resume_generation_pipeline(job_id: int, req_payload: dict):
    logger.info(f"[Celery] Resuming Presentation Generation task for job_id={job_id}")
    from agents.orchestrator import AgentOrchestrator
    try:
        orchestrator = AgentOrchestrator()
        orchestrator.resume_generation_pipeline(job_id, req_payload)
    except Exception as e:
        logger.error(f"[Celery] Resume pipeline task failed for job_id={job_id}: {e}")

@celery_app.task(name="tasks.run_data_alignment")
def task_run_data_alignment(name: str):
    logger.info(f"[Celery] Data alignment task started: {name}")
    from services.core.data_alignment_service import run_alignment
    return run_alignment(name)


@celery_app.task(name="tasks.celery_run_template_merge")
def celery_run_template_merge(job_id: int):
    logger.info(f"[Celery] Template Merge task started for job_id={job_id}")
    from services.templates.template_merge_orchestrator import run_template_merge
    run_template_merge(job_id)

