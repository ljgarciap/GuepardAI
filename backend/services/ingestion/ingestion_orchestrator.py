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
                
                # Restored Concurrency: LLM provider will serialize if local model is used
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
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
        set_job_status(job_key, "visual_dna", "completed")
    except Exception as e:
        err_msg = f"Visual DNA error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "visual_dna", "error", message=err_msg)

def task_extract_artistic_essence(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Extracts Artistic Essence (v21.0) in isolation."""
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
        set_job_status(job_key, "artistic", "completed")
    except Exception as e:
        err_msg = f"Artistic Essence error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "artistic", "error", message=err_msg)

def task_extract_full_brand_style(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Decoupled brand identity orchestration (Context-Aware v22.0)."""
    cb = lambda msg, p=0: update_job_step(job_key, "brand_style", msg, p)
    
    # 1. Esencia (Aislada) - USAR PDF SI ES POSIBLE (v34.0)
    # Se extrae PRIMERO para generar el Contexto de Marca (Brand Rulebook)
    try:
        cb("Analyzing Artistic Essence (Vision High-Fidelity)...", 10)
        essence_file = file_path
        if file_path.lower().endswith(".pptx"):
            pdf_path = convert_pptx_to_pdf(file_path, os.path.dirname(file_path))
            if pdf_path:
                essence_file = pdf_path
                logger.info(f"  [Orchestrator] Using PDF for essence: {pdf_path}")
        
        task_extract_artistic_essence(job_key, essence_file, source_filename, visibility_scope, brand_id, manual_tags)
    except Exception as e:
        logger.error(f"  [Orchestrator] Failed Artistic Essence: {e}")

    # 2. DNA (Aislado) - Context-Aware
    # Se ejecuta DESPUÉS para que el modelo de Visión tenga acceso al Brand Rulebook al clasificar imágenes
    try:
        cb("Extracting Visual DNA (Atomic & Context-Aware)...", 50)
        task_extract_visual_dna(job_key, file_path, source_filename, visibility_scope, brand_id, manual_tags)
    except Exception as e:
        logger.error(f"  [Orchestrator] Failed Visual DNA: {e}")

    update_job_step(job_key, "brand_style", "Process finished.", 100)
    set_job_status(job_key, "brand_style", "completed")

def task_ingest_knowledge(job_key: str, file_path: str, source_filename: str, brand_id: int = None, visibility_scope: str = "exclusive", document_type: str = "company_knowledge"):
    """Ingesta RAG con Soberanía (v21.0)."""
    logger.info(f"[Orchestrator] Knowledge Ingest started: {source_filename}")
    cb = lambda msg, p=0: update_job_step(job_key, "knowledge", msg, p)
    try:
        from services.ingestion.ingest_knowledge import ingest_document as ingest_rag
        is_public = (visibility_scope == "public")
        ingest_rag(file_path, client_name=source_filename, update_callback=cb, brand_id=brand_id, is_public=is_public)
        set_job_status(job_key, "knowledge", "completed")
    except Exception as e:
        err_msg = f"Knowledge error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "knowledge", "error", message=err_msg)

def task_extract_pure_assets(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Pure asset harvest (v21.0). Supports individual images and documents."""
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
        err_msg = f"Pure Assets error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        set_job_status(job_key, "pure_assets", "error", message=err_msg)

def task_generate_presentation(job_id: int, req_data: dict):
    """
    Background task for generation (v23.0 - Modular).
    """
    logger.info(f"[Orchestrator] Generation started for Job: {job_id}")
    from services.rendering.layout_engine import generate_presentation_flow
    
    try:
        db = SessionLocal()
        # El motor espera db, job_id, y los datos.
        # Asumimos que la ruta del PPTX se define dentro de generate_presentation_flow o se pasa aquí.
        generate_presentation_flow(db, job_id, req_data)
        db.close()
    except Exception as e:
        err_msg = f"Generation error: {str(e)}"
        logger.error(f"[Orchestrator] {err_msg}")
        db = SessionLocal()
        job = db.query(models.GenerationJob).get(job_id)
        if job:
            job.status = "error"
            job.current_step = err_msg
            db.commit()
        db.close()
