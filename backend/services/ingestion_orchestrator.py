"""
ingestion_orchestrator.py — PowerAI
Orquestador de procesos de ingesta con Responsabilidad Única (v21.0).
Separa el DNA Visual, la Esencia Artística y el Conocimiento Corporativo.
"""
import os
import time
import logging
from typing import List, Optional, Callable
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from services.asset_library_service import register_asset
from services.visual_dna_service import extract_visual_dna as run_visual_dna_extraction
from services.artistic_essence_service import extract_artistic_essence as run_artistic_essence_extraction

logger = logging.getLogger(__name__)

def update_job_step(job_key: str, ingestion_type: str, step_details: str, progress: int):
    db = SessionLocal()
    try:
        job = db.query(models.IngestionJob).filter(
            models.IngestionJob.client_name == job_key,
            models.IngestionJob.ingestion_type == ingestion_type
        ).first()
        if job:
            job.current_step = step_details
            job.progress = progress
            db.commit()
    finally:
        db.close()

def set_job_status(job_key: str, ingestion_type: str, status: str):
    db = SessionLocal()
    try:
        job = db.query(models.IngestionJob).filter(
            models.IngestionJob.client_name == job_key,
            models.IngestionJob.ingestion_type == ingestion_type
        ).first()
        if job:
            job.status = status
            db.commit()
    finally:
        db.close()

def task_extract_visual_dna(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Extrae el DNA Visual (v21.0) con registro atómico de activos."""
    logger.info(f"[Orchestrator] Visual DNA started: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "visual_dna", msg, p)
    is_public = (visibility_scope == "public")
    
    try:
        upload_dir = os.path.dirname(file_path)
        dna = run_visual_dna_extraction(file_path, upload_dir, cb=cb)
        
        db = SessionLocal()
        try:
            record = db.query(models.BrandVisualDna).filter(
                models.BrandVisualDna.brand_id == brand_id
            ).first()
            if not record:
                record = models.BrandVisualDna(brand_id=brand_id, source_filename=source_filename)
                db.add(record)
            
            record.primary_color    = dna.get("primary_color", "#000000")
            record.secondary_color  = dna.get("secondary_color", "#404040")
            record.background_color = dna.get("background_color", "#FFFFFF")
            record.text_main_color  = dna.get("text_main_color", "#111111")
            record.primary_font     = dna.get("primary_font", "Arial")
            record.raw_extraction   = dna

            # REGISTRO ATÓMICO DE ACTIVOS (v20.5)
            final_library_assets = {}
            raw_assets = dna.get("extracted_assets", {})
            for cat, items in raw_assets.items():
                for item in items:
                    try:
                        with db.begin_nested():
                            raw_path = os.path.join(upload_dir, item["path"])
                            if os.path.exists(raw_path):
                                asset_record = register_asset(
                                    db, brand_id, raw_path, category=cat,
                                    is_public=is_public, source_doc=source_filename,
                                    manual_tags=manual_tags
                                )
                                # Asegurar que local_path sea solo el nombre del archivo
                                asset_record.local_path = os.path.basename(asset_record.local_path)
                                db.commit()
                                
                                real_cat = asset_record.category
                                if real_cat != "noise":
                                    if real_cat not in final_library_assets: final_library_assets[real_cat] = []
                                    final_library_assets[real_cat].append({
                                        "id": asset_record.id,
                                        "path": os.path.basename(asset_record.local_path),
                                        "category": real_cat
                                    })
                        db.commit()
                    except Exception as asset_err:
                        db.rollback()
                        logger.warning(f"  [Orchestrator] Skip asset {item.get('path')}: {asset_err}")
            
            record.extracted_assets = final_library_assets
            db.commit()
        finally:
            db.close()
        set_job_status(job_key, "visual_dna", "completed")
    except Exception as e:
        logger.error(f"[Orchestrator] Visual DNA error: {e}")
        set_job_status(job_key, "visual_dna", "error")

def task_extract_artistic_essence(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Extrae la Esencia Artística (v21.0) de forma aislada."""
    logger.info(f"[Orchestrator] Artistic Essence started: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "artistic", msg, p)

    try:
        upload_dir = os.path.dirname(file_path)
        brand_essence = run_artistic_essence_extraction(file_path, upload_dir, cb=cb, brand_id=brand_id)

        db = SessionLocal()
        try:
            record = db.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == brand_id).first()
            if not record:
                record = models.BrandArtisticEssence(brand_id=brand_id, source_filename=source_filename)
                db.add(record)
            
            record.source_filename       = source_filename
            record.visual_strategy       = brand_essence.get("visual_strategy", "")
            record.structural_archetypes = brand_essence.get("structural_archetypes", {})
            record.design_gestures       = brand_essence.get("design_gestures", {})
            record.composition_rules     = brand_essence.get("composition_rules", {})
            record.art_direction_note    = brand_essence.get("art_direction_note", "")
            db.commit()
        finally:
            db.close()
        set_job_status(job_key, "artistic", "completed")
    except Exception as e:
        logger.error(f"[Orchestrator] Artistic Essence error: {e}")
        set_job_status(job_key, "artistic", "error")

def task_extract_full_brand_style(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Orquestación desacoplada de identidad de marca."""
    cb = lambda msg, p=0: update_job_step(job_key, "brand_style", msg, p)
    
    # DNA (Aislado)
    try:
        cb("Extracting Visual DNA (Atomic)...", 10)
        task_extract_visual_dna(job_key, file_path, source_filename, visibility_scope, brand_id, manual_tags)
    except: pass

    # Esencia (Aislada)
    try:
        cb("Analyzing Artistic Essence (Vision)...", 50)
        task_extract_artistic_essence(job_key, file_path, source_filename, visibility_scope, brand_id, manual_tags)
    except: pass

    update_job_step(job_key, "brand_style", "Process finished.", 100)
    set_job_status(job_key, "brand_style", "completed")

def task_ingest_knowledge(job_key: str, file_path: str, source_filename: str, brand_id: int = None, visibility_scope: str = "exclusive", document_type: str = "company_knowledge"):
    """Ingesta RAG con Soberanía (v21.0)."""
    logger.info(f"[Orchestrator] Knowledge Ingest started: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "knowledge", msg, p)
    try:
        from ingest_knowledge import ingest_document as ingest_rag
        is_public = (visibility_scope == "public")
        ingest_rag(file_path, client_name=source_filename, update_callback=cb, brand_id=brand_id, is_public=is_public)
        set_job_status(job_key, "knowledge", "completed")
    except Exception as e:
        logger.error(f"[Orchestrator] Knowledge error: {e}")
        set_job_status(job_key, "knowledge", "error")

def task_extract_pure_assets(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Cosecha pura de activos (v21.0). Soporta imágenes individuales y documentos."""
    logger.info(f"[Orchestrator] Pure Asset Harvest: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "pure_assets", msg, p)
    
    try:
        is_public = (visibility_scope == "public")
        upload_dir = os.path.dirname(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        
        db = SessionLocal()
        try:
            # Si es una imagen individual, registrarla directamente
            if ext in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
                cb("Registering individual image asset...", 50)
                category = "photos"
                if "logo" in source_filename.lower(): category = "logos"
                if "icon" in source_filename.lower(): category = "icons"
                
                register_asset(db, brand_id, file_path, category=category, is_public=is_public, source_doc=source_filename, manual_tags=manual_tags)
                db.commit()
            else:
                # Si es un documento, intentar extraer activos de él
                cb("Extracting assets from document...", 20)
                dna = run_visual_dna_extraction(file_path, upload_dir, cb=cb)
                raw_assets = dna.get("extracted_assets", {})
                for cat, items in raw_assets.items():
                    for item in items:
                        try:
                            with db.begin_nested():
                                raw_path = os.path.join(upload_dir, item["path"])
                                register_asset(db, brand_id, raw_path, category=cat, is_public=is_public, source_doc=source_filename, manual_tags=manual_tags)
                            db.commit()
                        except: db.rollback()
        finally:
            db.close()
            
        set_job_status(job_key, "pure_assets", "completed")
        update_job_step(job_key, "pure_assets", "Asset harvest complete.", 100)
    except Exception as e:
        logger.error(f"[Orchestrator] Pure Assets error: {e}")
        set_job_status(job_key, "pure_assets", "error")

def task_generate_presentation(job_id: int, req_data: dict):
    """
    Background task for generation (v23.0 - Modular).
    """
    logger.info(f"[Orchestrator] Generation started for Job: {job_id}")
    from services.layout_engine import generate_presentation_flow
    
    try:
        db = SessionLocal()
        # El motor espera db, job_id, y los datos.
        # Asumimos que la ruta del PPTX se define dentro de generate_presentation_flow o se pasa aquí.
        generate_presentation_flow(db, job_id, req_data)
        db.close()
    except Exception as e:
        logger.error(f"[Orchestrator] Generation error: {e}")
        db = SessionLocal()
        job = db.query(models.GenerationJob).get(job_id)
        if job:
            job.status = "error"
            job.current_step = f"Error: {str(e)}"
            db.commit()
        db.close()
