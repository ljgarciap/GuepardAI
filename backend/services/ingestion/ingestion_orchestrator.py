"""
ingestion_orchestrator.py — PowerAI
Ingestion orchestration with Single Responsibility (v22.0).
Separates Visual DNA, Artistic Essence, and Corporate Knowledge.
"""
import os
import time
import logging
from typing import List, Optional, Callable
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from services.assets.asset_library_service import register_asset
from services.ingestion.visual_dna_service import extract_visual_dna as run_visual_dna_extraction
from services.ingestion.artistic_essence_service import extract_artistic_essence as run_artistic_essence_extraction
import subprocess

logger = logging.getLogger(__name__)

def convert_pptx_to_pdf(pptx_path: str, output_dir: str) -> Optional[str]:
    """Uses LibreOffice to convert PPTX a PDF para análisis de visión fiel."""
    try:
        from services.rendering.font_extractor import extract_and_install_fonts
        extract_and_install_fonts(pptx_path)
        
        logger.info(f"  [Orchestrator] Converting {pptx_path} to PDF...")
        cmd = [
            "libreoffice", "--headless", "--convert-to", "pdf",
            "--outdir", output_dir, pptx_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        pdf_name = os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf"
        pdf_path = os.path.join(output_dir, pdf_name)
        if os.path.exists(pdf_path):
            return pdf_path
    except Exception as e:
        logger.warning(f"  [Orchestrator] PPTX to PDF failed: {e}")
    return None

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

def set_job_status(job_key: str, ingestion_type: str, status: str, message: str = None):
    db = SessionLocal()
    try:
        job = db.query(models.IngestionJob).filter(
            models.IngestionJob.client_name == job_key,
            models.IngestionJob.ingestion_type == ingestion_type
        ).first()
        if job:
            job.status = status
            if message:
                job.current_step = message
            db.commit()
    finally:
        db.close()

def task_extract_visual_dna(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Extracts Visual DNA (v21.0) with atomic asset registration."""
    logger.info(f"[Orchestrator] Visual DNA started: {source_filename}")
    # v41.0: Reportar a brand_style para visibilidad granular en la UI
    cb = lambda msg, p=0: update_job_step(job_key, "brand_style", msg, p)
    is_public = (visibility_scope == "public")
    
    try:
        from services.core.storage_service import brand_assets_dir
        upload_dir = brand_assets_dir(brand_id)
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

            # Persistencia de Dimensiones Físicas (v12.5 - Anti-Stretch)
            record.slide_width_inches  = dna.get("slide_width_inches", 13.33)
            record.slide_height_inches = dna.get("slide_height_inches", 7.5)

            # REGISTRO ATÓMICO DE ACTIVOS (v20.5 - PARALLEL BATCHING v24.0)
            final_library_assets = {}
            raw_assets = dna.get("extracted_assets", {})
            
            # 1. Aplanar lista de activos a procesar
            flat_items = []
            for cat, items in raw_assets.items():
                for item in items:
                    flat_items.append((cat, item))
                    
            total_items = len(flat_items)
            processed_count = 0
            
            if total_items > 0:
                import concurrent.futures
                
                # Isolated (Thread-Safe) function for each worker
                def process_asset_worker(cat, item):
                    from database import SessionLocal
                    local_db = SessionLocal()
                    try:
                        raw_path = os.path.join(upload_dir, item["path"])
                        if os.path.exists(raw_path):
                            # Respetar el logo manual, si no, usar lo que diga Visión
                            cat_val = item.get("category", cat)
                            # Defensa contra LLM devolviendo objetos en lugar de strings (v19.2)
                            if not isinstance(cat_val, str):
                                cat_val = str(cat_val)
                            final_category = cat_val.lower()
                            
                            asset_record = register_asset(
                                local_db, brand_id, raw_path, category=final_category,
                                is_public=is_public, source_doc=source_filename,
                                manual_tags=manual_tags,
                                width=item.get("width"), height=item.get("height")
                            )
                            # Ensure local_path is just the filename
                            asset_record.local_path = os.path.basename(asset_record.local_path)
                            local_db.commit() # Local commit per thread
                            
                            real_cat = asset_record.category
                            return {
                                "success": True,
                                "real_cat": real_cat,
                                "id": asset_record.id,
                                "path": os.path.basename(asset_record.local_path)
                            }
                        return {"success": False, "error": "File not found"}
                    except Exception as asset_err:
                        local_db.rollback()
                        logger.warning(f"  [Orchestrator] Skip asset {item.get('path')}: {asset_err}")
                        return {"success": False, "error": str(asset_err)}
                    finally:
                        local_db.close()
                
                # Restored Concurrency: Limit to 1 worker to respect Mistral's 1 RPS Free Tier limit
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future_to_item = {executor.submit(process_asset_worker, cat, item): item for cat, item in flat_items}
                    for future in concurrent.futures.as_completed(future_to_item):
                        processed_count += 1
                        
                        # DYNAMIC PROGRESS BAR: 40% to 95%
                        prog_percent = 40 + int((processed_count / total_items) * 55)
                        cb(f"Analyzing images with Vision LLM ({processed_count}/{total_items})...", prog_percent)
                        
                        res = future.result()
                        if res and res.get("success"):
                            real_cat = res["real_cat"]
                            if real_cat != "noise":
                                if real_cat not in final_library_assets: final_library_assets[real_cat] = []
                                final_library_assets[real_cat].append({
                                    "id": res["id"],
                                    "path": res["path"],
                                    "category": real_cat
                                })
            
            record.extracted_assets = final_library_assets
            db.commit()
        finally:
            db.close()
        set_job_status(job_key, "visual_dna", models.IngestionJobStatus.COMPLETED)
    except Exception as e:
        err_msg = f"Visual DNA error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "visual_dna", models.IngestionJobStatus.ERROR, message=err_msg)

def task_extract_artistic_essence(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Extracts Artistic Essence (v21.0) in isolation."""
    logger.info(f"[Orchestrator] Artistic Essence started: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "artistic", msg, p)

    try:
        from services.core.storage_service import brand_assets_dir
        upload_dir = brand_assets_dir(brand_id)
        brand_essence = run_artistic_essence_extraction(file_path, upload_dir, cb=cb, brand_id=brand_id)

        db = SessionLocal()
        try:
            record = db.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == brand_id).first()
            if not record:
                record = models.BrandArtisticEssence(brand_id=brand_id, source_filename=source_filename)
                db.add(record)
            
            record.source_filename       = source_filename
            record.visual_strategy       = brand_essence.get("visual_strategy", "")
            record.art_direction_note    = brand_essence.get("branding_rulebook", "")
            record.structural_archetypes = brand_essence.get("structural_archetypes", {})
            record.design_gestures       = brand_essence.get("design_gestures", {})
            record.composition_rules     = brand_essence.get("composition_rules", {})
            record.art_direction_note    = brand_essence.get("art_direction_note", "")
            record.raw_vision_response   = brand_essence.get("raw_vision_response", {})

            from services.ingestion.visual_pattern_service import (
                normalize_executable_patterns,
                upsert_brand_patterns,
            )
            executable_patterns = brand_essence.get("executable_visual_patterns") or normalize_executable_patterns(brand_essence)
            upsert_brand_patterns(
                db,
                brand_id=brand_id,
                source_filename=source_filename,
                patterns=executable_patterns,
                raw_extraction=brand_essence.get("raw_vision_response", brand_essence),
            )
            db.commit()
        finally:
            db.close()
        set_job_status(job_key, "artistic", models.IngestionJobStatus.COMPLETED)
    except Exception as e:
        err_msg = f"Artistic Essence error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "artistic", models.IngestionJobStatus.ERROR, message=err_msg)

def task_extract_full_brand_style(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """
    Orquestación de identidad de marca — GAP 2: Enruta al AgentOrchestrator (v25.0).

    El Brand Analyst Agent (ReadPPTXTool + ExtractPaletteTool) ahora corre bajo
    el mismo Orquestador Central que el pipeline de generación, cerrando el ciclo MCP.
    """
    logger.info(f"[Orchestrator] task_extract_full_brand_style → AgentOrchestrator for brand_id={brand_id}")
    from agents.orchestrator import AgentOrchestrator

    # Los assets extraídos van al árbol público de la marca (la fuente vive en private/)
    from services.core.storage_service import brand_assets_dir
    upload_dir = brand_assets_dir(brand_id)

    # Obtener el ID del IngestionJob para que los BrandAnalyst Tools puedan actualizar su estado
    ingestion_job_id = -1  # Valor centinela: si no hay job en BD, las Tools actuarán sin actualizar estado
    db = SessionLocal()
    try:
        job_record = db.query(models.IngestionJob).filter(
            models.IngestionJob.client_name == job_key,
            models.IngestionJob.ingestion_type == "brand_style"
        ).first()
        if job_record:
            ingestion_job_id = job_record.id
    finally:
        db.close()

    # Delegar al AgentOrchestrator (cierra el GAP 2)
    orchestrator = AgentOrchestrator()
    orchestrator.run_ingestion_pipeline(
        ingestion_job_id=ingestion_job_id,
        file_path=file_path,
        source_filename=source_filename,
        brand_id=brand_id,
        upload_dir=upload_dir,
        job_key=job_key,
        visibility_scope=visibility_scope,
        manual_tags=manual_tags,
    )

def task_ingest_knowledge(job_key: str, file_path: str, source_filename: str, brand_id: int = None, visibility_scope: str = "exclusive", document_type: str = "company_knowledge"):
    """Ingesta RAG con Soberanía (v21.0)."""
    logger.info(f"[Orchestrator] Knowledge Ingest started: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "knowledge", msg, p)
    try:
        from services.ingestion.ingest_knowledge import ingest_document as ingest_rag
        is_public = (visibility_scope == "public")
        ingest_rag(file_path, client_name=source_filename, update_callback=cb, brand_id=brand_id, is_public=is_public)
        set_job_status(job_key, "knowledge", models.IngestionJobStatus.COMPLETED)
    except Exception as e:
        err_msg = f"Knowledge error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "knowledge", models.IngestionJobStatus.ERROR, message=err_msg)

def task_extract_pure_assets(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Pure asset harvest (v21.0). Supports individual images and documents."""
    logger.info(f"[Orchestrator] Pure Asset Harvest: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "pure_assets", msg, p)
    
    try:
        is_public = (visibility_scope == "public")
        # Assets cosechados van al árbol público de la marca (storage v1)
        from services.core.storage_service import brand_assets_dir, move_into
        upload_dir = brand_assets_dir(brand_id)
        ext = os.path.splitext(file_path)[1].lower()

        db = SessionLocal()
        try:
            # Si es una imagen individual, registrarla directamente
            if ext in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
                # La imagen subida ES un asset: moverla al árbol de assets
                file_path = move_into(file_path, upload_dir) or file_path

                # Extraer dimensiones (v36.5)
                width, height = 0, 0
                try:
                    from PIL import Image
                    with Image.open(file_path) as img:
                        width, height = img.size
                except: pass

                # v36.6: Definir categoría por defecto para evitar NameError
                category = "photos"
                register_asset(db, brand_id, file_path, category=category, is_public=is_public, source_doc=source_filename, manual_tags=manual_tags, width=width, height=height)
                db.commit()
            else:
                # Si es un documento, intentar extraer activos de él
                cb("Extracting assets from document...", 20)
                dna = run_visual_dna_extraction(file_path, upload_dir, cb=cb)
                raw_assets = dna.get("extracted_assets", {})
                
                flat_items = []
                for cat, items in raw_assets.items():
                    for item in items:
                        flat_items.append((cat, item))
                        
                total_items = len(flat_items)
                processed_count = 0
                
                for cat, item in flat_items:
                    try:
                        processed_count += 1
                        prog_percent = 30 + int((processed_count / total_items) * 65) if total_items > 0 else 95
                        cb(f"Registering harvested asset ({processed_count}/{total_items})...", prog_percent)
                        
                        with db.begin_nested():
                            raw_path = os.path.join(upload_dir, item["path"])
                            register_asset(db, brand_id, raw_path, category=cat, is_public=is_public, source_doc=source_filename, manual_tags=manual_tags)
                        db.commit()
                    except Exception as loop_err:
                        db.rollback()
                        logger.warning(f"Failed to register asset in pure harvest: {loop_err}")
        finally:
            db.close()
            
        set_job_status(job_key, "pure_assets", models.IngestionJobStatus.COMPLETED)
        update_job_step(job_key, "pure_assets", "Asset harvest complete.", 100)
    except Exception as e:
        err_msg = f"Pure Assets error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "pure_assets", models.IngestionJobStatus.ERROR, message=err_msg)

def task_generate_presentation(job_id: int, req_data: dict):
    """
    Background task for generation (v24.0 - Agent Orchestrator).
    Enruta el job al AgentOrchestrator MCP.
    """
    logger.info(f"[Orchestrator] Generation started for Job: {job_id} via AgentOrchestrator")
    from agents.orchestrator import AgentOrchestrator
    
    try:
        # Instanciar el orquestador inteligente
        orchestrator = AgentOrchestrator()
        orchestrator.run_generation_pipeline(job_id, req_data)
        
    except Exception as e:
        err_msg = f"Generation error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.status = models.GenerationJobStatus.ERROR
                job.current_step = err_msg
                db.commit()
        finally:
            db.close()
