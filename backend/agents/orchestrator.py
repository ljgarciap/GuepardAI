import logging
import traceback
from agents.redactor import GenerateTextTool
from agents.architect import ComposeLayoutTool
from agents.qa_validator import ScoreFidelityTool, ValidateBrandTool
from agents.render_agent import RenderPPTXTool
from agents.brand_analyst import ReadPPTXTool, ExtractPaletteTool
from database import SessionLocal
import models

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Orquestador Central de Agentes (MCP).
    Enruta las peticiones basándose en el estado del Job e implementa ciclos de validación.

    Responsabilidades:
      - run_generation_pipeline: Orquesta Redactor → Architect → QA → Render.
      - run_ingestion_pipeline:  Orquesta Brand Analyst (ReadPPTX → ExtractPalette).
    """
    def __init__(self):
        # Herramientas de Generación
        self.generate_text = GenerateTextTool()
        self.compose_layout = ComposeLayoutTool()
        self.score_fidelity = ScoreFidelityTool()
        self.validate_brand = ValidateBrandTool()
        self.render_pptx = RenderPPTXTool()
        self.MAX_RETRIES = 2

        # Herramientas de Ingesta (Brand Analyst)
        self.read_pptx = ReadPPTXTool()
        self.extract_palette = ExtractPaletteTool()

    def run_ingestion_pipeline(
        self,
        ingestion_job_id: int,
        file_path: str,
        source_filename: str,
        brand_id: int,
        upload_dir: str,
        job_key: str,
        visibility_scope: str = "exclusive",
        manual_tags: list = None,
    ):
        """
        Pipeline de Ingesta orquestado por el Brand Analyst.

        Flujo:
          1. ExtractPaletteTool → Esencia artística (Vision LLM primero para generar Brand Rulebook).
          2. ReadPPTXTool       → ADN visual programático (Context-Aware: usa el Rulebook).

        Reemplaza las llamadas directas a `task_extract_artistic_essence` y
        `task_extract_visual_dna` en `ingestion_orchestrator.py`.

        Args:
            ingestion_job_id: ID del IngestionJob en BD (para tracking de estado).
            file_path:        Ruta absoluta al archivo fuente (PPTX o PDF).
            source_filename:  Nombre del archivo (para metadata en BD).
            brand_id:         ID de la marca destino.
            upload_dir:       Directorio donde guardar los assets extraídos.
            job_key:          Clave del job para actualizar el estado en la UI.
            visibility_scope: Scope de visibilidad ('exclusive' o 'public').
            manual_tags:      Tags manuales opcionales para los activos.
        """
        logger.info(f"[Orchestrator] Starting Ingestion Pipeline for brand_id={brand_id}, file={source_filename}")
        import time
        from utils.observability import log_performance_metric
        start_time = time.perf_counter()

        # Helper local para actualizar el paso visible en la UI
        def _update_step(msg: str, progress: int = 0):
            db = SessionLocal()
            try:
                job = db.query(models.IngestionJob).filter(
                    models.IngestionJob.client_name == job_key,
                    models.IngestionJob.ingestion_type == "brand_style"
                ).first()
                if job:
                    job.current_step = msg
                    job.progress = progress
                    db.commit()
            finally:
                db.close()

        def _set_status(status: str, message: str = None):
            db = SessionLocal()
            try:
                job = db.query(models.IngestionJob).filter(
                    models.IngestionJob.client_name == job_key,
                    models.IngestionJob.ingestion_type == "brand_style"
                ).first()
                if job:
                    job.status = status
                    if message:
                        job.current_step = message
                    db.commit()
            finally:
                db.close()

        # ── PASO 1: Esencia Artística (Vision LLM) ──────────────────────────
        # Se extrae PRIMERO para generar el Brand Rulebook que usará el DNA
        essence = {}
        try:
            _update_step("Agent: Brand Analyst extracting artistic essence (Vision)...", 10)
            logger.info("[Orchestrator] Brand Analyst → ExtractPaletteTool (Artistic Essence)")
            essence = self.extract_palette(
                job_id=ingestion_job_id,
                file_path=file_path,
                upload_dir=upload_dir,
                brand_id=brand_id,
            )
            _update_step("Artistic essence extracted. Storing in database...", 40)
            logger.info("[Orchestrator] ExtractPaletteTool completed. Saving to DB...")
            
            # Guardar esencia artística en Base de Datos
            db = SessionLocal()
            try:
                record = db.query(models.BrandArtisticEssence).filter(
                    models.BrandArtisticEssence.brand_id == brand_id
                ).first()
                if not record:
                    record = models.BrandArtisticEssence(brand_id=brand_id, source_filename=source_filename)
                    db.add(record)
                
                record.source_filename       = source_filename
                record.visual_strategy       = essence.get("visual_strategy", "")
                record.art_direction_note    = essence.get("branding_rulebook", "")
                record.structural_archetypes = essence.get("structural_archetypes", {})
                record.design_gestures       = essence.get("design_gestures", {})
                record.composition_rules     = essence.get("composition_rules", {})
                record.art_direction_note    = essence.get("art_direction_note", "") or essence.get("branding_rulebook", "")
                record.raw_vision_response   = essence.get("raw_vision_response", {})

                from services.ingestion.visual_pattern_service import (
                    normalize_executable_patterns,
                    upsert_brand_patterns,
                )
                executable_patterns = essence.get("executable_visual_patterns") or normalize_executable_patterns(essence)
                upsert_brand_patterns(
                    db,
                    brand_id=brand_id,
                    source_filename=source_filename,
                    patterns=executable_patterns,
                )
                db.commit()
            except Exception as db_err:
                logger.error(f"[Orchestrator] Failed to save BrandArtisticEssence to DB: {db_err}")
                db.rollback()
            finally:
                db.close()
                
            _update_step("Artistic essence database records updated.", 45)
        except Exception as e:
            logger.error(f"[Orchestrator] ExtractPaletteTool failed (non-fatal): {e}")
            _update_step(f"Warning: Artistic essence failed — {str(e)[:100]}. Continuing...", 45)

        # ── PASO 2: ADN Visual Programático (Context-Aware) ─────────────────
        # Se ejecuta DESPUÉS del palette para que el LLM tenga el Rulebook disponible
        try:
            _update_step("Agent: Brand Analyst reading visual DNA (programmatic)...", 50)
            logger.info("[Orchestrator] Brand Analyst → ReadPPTXTool (Visual DNA)")
            raw_dna = self.read_pptx(
                job_id=ingestion_job_id,
                file_path=file_path,
                upload_dir=upload_dir,
            )
            _update_step("Visual DNA extracted. Indexing assets...", 85)
            logger.info("[Orchestrator] ReadPPTXTool completed. Registering assets...")
            
            # Guardar ADN visual y registrar activos en Base de Datos
            db = SessionLocal()
            try:
                record = db.query(models.BrandVisualDna).filter(
                    models.BrandVisualDna.brand_id == brand_id
                ).first()
                if not record:
                    record = models.BrandVisualDna(brand_id=brand_id, source_filename=source_filename)
                    db.add(record)
                
                record.primary_color    = raw_dna.get("primary_color", "#000000")
                record.secondary_color  = raw_dna.get("secondary_color", "#404040")
                record.background_color = raw_dna.get("background_color", "#FFFFFF")
                record.text_main_color  = raw_dna.get("text_main_color", "#111111")
                record.primary_font     = raw_dna.get("primary_font", "Arial")
                record.raw_extraction   = raw_dna

                record.slide_width_inches  = raw_dna.get("slide_width_inches", 13.33)
                record.slide_height_inches = raw_dna.get("slide_height_inches", 7.5)
                record.is_public = 1 if visibility_scope == "public" else 0

                # REGISTRO ATÓMICO DE ACTIVOS (Soversanía e Ingesta RAG)
                from services.assets.asset_library_service import register_asset
                import os
                import concurrent.futures
                
                final_library_assets = {}
                raw_assets = raw_dna.get("extracted_assets", {})
                
                flat_items = []
                for cat, items in raw_assets.items():
                    for item in items:
                        flat_items.append((cat, item))
                        
                total_items = len(flat_items)
                processed_count = 0
                is_public_bool = (visibility_scope == "public")
                
                if total_items > 0:
                    def process_asset_worker(cat, item):
                        from database import SessionLocal
                        local_db = SessionLocal()
                        try:
                            raw_path = os.path.join(upload_dir, item["path"])
                            if os.path.exists(raw_path):
                                cat_val = item.get("category", cat)
                                if not isinstance(cat_val, str):
                                    cat_val = str(cat_val)
                                final_category = cat_val.lower()
                                
                                asset_record = register_asset(
                                    local_db, brand_id, raw_path, category=final_category,
                                    is_public=is_public_bool, source_doc=source_filename,
                                    manual_tags=manual_tags,
                                    width=item.get("width"), height=item.get("height")
                                )
                                asset_record.local_path = os.path.basename(asset_record.local_path)
                                local_db.commit()
                                
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
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future_to_item = {executor.submit(process_asset_worker, cat, item): item for cat, item in flat_items}
                        for future in concurrent.futures.as_completed(future_to_item):
                            processed_count += 1
                            prog_percent = 50 + int((processed_count / total_items) * 40)
                            _update_step(f"Analyzing images with Vision LLM ({processed_count}/{total_items})...", prog_percent)
                            
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
            except Exception as db_err:
                logger.error(f"[Orchestrator] Failed to save BrandVisualDna to DB: {db_err}")
                logger.error(traceback.format_exc())
                db.rollback()
            finally:
                db.close()
            
            _update_step("Visual DNA extracted and library assets registered.", 90)
        except Exception as e:
            logger.error(f"[Orchestrator] ReadPPTXTool failed (non-fatal): {e}")
            logger.error(traceback.format_exc())
            _update_step(f"Warning: Visual DNA failed — {str(e)[:100]}. Continuing...", 90)

        # ── FINALIZACIÓN ────────────────────────────────────────────────────
        _update_step("Brand Analyst pipeline complete.", 100)
        _set_status(models.IngestionJobStatus.COMPLETED)
        logger.info(f"[Orchestrator] Ingestion Pipeline completed for brand_id={brand_id}")
        duration = time.perf_counter() - start_time
        log_performance_metric(
            event_name="pipeline.ingestion.complete",
            duration=duration,
            metadata={"ingestion_job_id": ingestion_job_id, "brand_id": brand_id, "filename": source_filename}
        )

    def run_generation_pipeline(self, job_id: int, req_data: dict):
        """
        Flujo de trabajo para Generar una Presentación.
        """
        logger.info(f"[Orchestrator] Starting Agent Pipeline for Job {job_id}")
        import time
        from utils.observability import log_performance_metric
        start_time = time.perf_counter()

        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.progress = 10
                job.current_step = "Agent: Redactor is starting to write the slides..."
                db.commit()
        
            # 1. Agente Redactor (Contenido)
            logger.info(f"[Orchestrator] Delegating to Redactor (GenerateTextTool)...")
            self.generate_text(
                job_id=job_id,
                prompt=req_data.get("prompt", ""),
                style_filename=req_data.get("style_filename", ""),
                knowledge_filename=req_data.get("knowledge_filename", ""),
                region=req_data.get("region", "Global"),
                allow_ai_images=req_data.get("allow_ai_images", False)
            )

            # Checkpoint Human-in-the-Loop
            if req_data.get("interactive_mode", False):
                logger.info(f"[Orchestrator] Interactive mode enabled. Pausing pipeline for Job {job_id} at CONTENT_READY.")
                if job:
                    job.progress = 40
                    job.current_step = "Content structure ready for review."
                    db.commit()

                duration = time.perf_counter() - start_time
                log_performance_metric(
                    event_name="pipeline.generation.paused",
                    duration=duration,
                    metadata={"job_id": job_id, "interactive_mode": True}
                )
                return

            if job:
                job.progress = 40
                job.current_step = "Content structure generated. Passing to Architect..."
                db.commit()

            self.run_design_and_render(job_id, req_data, db=db)
            duration = time.perf_counter() - start_time
            log_performance_metric(
                event_name="pipeline.generation.complete",
                duration=duration,
                metadata={"job_id": job_id, "interactive_mode": False}
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            log_performance_metric(
                event_name="pipeline.generation.failed",
                duration=duration,
                metadata={"job_id": job_id, "error": str(e)}
            )
            logger.error(f"[Orchestrator] Pipeline failed: {str(e)}")
            logger.error(traceback.format_exc())
            try:
                job = db.query(models.GenerationJob).get(job_id)
                if job:
                    job.status = models.GenerationJobStatus.ERROR
                    job.current_step = f"Pipeline Error: {str(e)}"
                    db.commit()
            except Exception as db_err:
                logger.error(f"Failed to set error status: {db_err}")
        finally:
            # Cerrar SIEMPRE: la sesión abierta deja una transacción 'idle in
            # transaction' que bloquea el teardown del schema en tests.
            db.close()

    def run_design_and_render(self, job_id: int, req_data: dict, db=None):
        """
        Ejecuta las etapas de diseño (Architect), QA y renderizado final.
        """
        local_db = db or SessionLocal()
        try:
            # Bucle de Diseño y QA
            retries = 0
            qa_passed = False
            # F1 (fixes-resiliencia): el rechazo de QA del ciclo anterior se inyecta
            # en el siguiente intento del Architect (el más reciente reemplaza al anterior)
            qa_feedback = None

            while retries <= self.MAX_RETRIES and not qa_passed:
                logger.info(f"[Orchestrator] Delegating to Architect (ComposeLayoutTool) - Attempt {retries + 1}")

                job = local_db.query(models.GenerationJob).get(job_id)
                if job:
                    job.progress = min(80, 50 + retries * 10)
                    job.current_step = f"Agent: Architect is planning layouts and images (Attempt {retries + 1})..."
                    local_db.commit()

                self.compose_layout(job_id=job_id, is_premium=(req_data.get("tier") == "premium"), qa_feedback=qa_feedback)

                logger.info(f"[Orchestrator] Delegating to QA Validator (ScoreFidelityTool/ValidateBrandTool)...")
                
                job = local_db.query(models.GenerationJob).get(job_id)
                if job:
                    job.progress = min(82, 60 + retries * 10)
                    job.current_step = "Agent: QA Validator is verifying design compliance..."
                    local_db.commit()

                # Determinista
                brand_validation = self.validate_brand(job_id=job_id)
                if brand_validation["status"] == "failed":
                    logger.warning(f"[Orchestrator] QA Deterministic Failed: {brand_validation['violations']}")
                    needs_rework = True
                    import json as _json
                    qa_feedback = f"Deterministic QA violations: {_json.dumps(brand_validation.get('violations', []))}"
                else:
                    # Híbrido/LLM
                    qa_result = self.score_fidelity(job_id=job_id)
                    needs_rework = qa_result.get("needs_rework", False)
                    if needs_rework:
                        import json as _json
                        reasoning = qa_result.get("reasoning", "")
                        if isinstance(reasoning, (dict, list)):
                            reasoning = _json.dumps(reasoning)
                        if str(reasoning).strip():
                            qa_feedback = f"QA Judge rejection (score {qa_result.get('score', '?')}): {reasoning}"
                        else:
                            qa_feedback = None

                if needs_rework:
                    retries += 1
                    logger.info(f"[Orchestrator] QA rejected design. Retries used: {retries}/{self.MAX_RETRIES}")
                    
                    # Reset slides to CONTENT_READY so the architect can re-plan them
                    try:
                        slides_to_reset = local_db.query(models.PresentationSlide).filter(
                            models.PresentationSlide.job_id == job_id
                        ).all()
                        for s in slides_to_reset:
                            s.status = models.PresentationSlideStatus.CONTENT_READY
                        local_db.commit()
                        logger.info(f"[Orchestrator] Reset {len(slides_to_reset)} slides status to CONTENT_READY for retry.")
                    except Exception as reset_err:
                        logger.error(f"[Orchestrator] Failed to reset slides for retry: {reset_err}")
                        local_db.rollback()

                    job = local_db.query(models.GenerationJob).get(job_id)
                    if job:
                        job.current_step = f"QA validation failed (Attempt {retries}). Retrying layout planning..."
                        local_db.commit()
                    if retries > self.MAX_RETRIES:
                        logger.warning(f"[Orchestrator] Max retries reached. Forcing acceptance.")
                        # F4 (fixes-resiliencia): dejar rastro consultable del forzado
                        try:
                            job = local_db.query(models.GenerationJob).get(job_id)
                            if job:
                                job.qa_forced = 1
                                job.current_step = "QA exhausted retries; design accepted by force."
                                local_db.commit()
                        except Exception as flag_err:
                            logger.error(f"[Orchestrator] Failed to persist qa_forced flag: {flag_err}")
                            local_db.rollback()
                        qa_passed = True # Forzamos el pase porque nos quedamos sin reintentos
                else:
                    logger.info(f"[Orchestrator] QA Approved design!")
                    qa_passed = True

            # 4. Render Engine
            logger.info(f"[Orchestrator] Calling Render Agent (RenderPPTXTool)...")
            job = local_db.query(models.GenerationJob).get(job_id)
            if job:
                job.progress = 85
                job.current_step = "Agent: Render Agent is assembling the final presentation..."
                local_db.commit()

            self.render_pptx(
                job_id=job_id,
                output_format=req_data.get("output_format", "pptx"),
                is_premium=(req_data.get("tier") == "premium")
            )

            logger.info(f"[Orchestrator] Agent Pipeline completed for Job {job_id}")
        finally:
            # Cerrar SIEMPRE la sesión que creamos nosotros: dejarla viva mantiene
            # una transacción 'idle in transaction' que bloquea DROP/ALTER posteriores
            # (en tests colgaba el teardown del schema de forma intermitente).
            if not db:
                local_db.close()

    def resume_generation_pipeline(self, job_id: int, req_data: dict):
        """
        Reanuda el pipeline de generación desde la etapa del Architect.
        """
        logger.info(f"[Orchestrator] Resuming Agent Pipeline for Job {job_id}")
        import time
        from utils.observability import log_performance_metric
        start_time = time.perf_counter()
        
        try:
            # Nos aseguramos de que el job vuelva a estar en procesamiento
            db = SessionLocal()
            try:
                job = db.query(models.GenerationJob).get(job_id)
                if job:
                    job.status = models.GenerationJobStatus.PROCESSING
                    job.current_step = "Resuming pipeline from CONTENT_READY checkpoint..."
                    db.commit()
            finally:
                db.close()

            self.run_design_and_render(job_id, req_data)
            duration = time.perf_counter() - start_time
            log_performance_metric(
                event_name="pipeline.generation.resumed_complete",
                duration=duration,
                metadata={"job_id": job_id}
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            log_performance_metric(
                event_name="pipeline.generation.resumed_failed",
                duration=duration,
                metadata={"job_id": job_id, "error": str(e)}
            )
            logger.error(f"[Orchestrator] Resume failed: {str(e)}")
            logger.error(traceback.format_exc())
            db = SessionLocal()
            try:
                job = db.query(models.GenerationJob).get(job_id)
                if job:
                    job.status = models.GenerationJobStatus.ERROR
                    job.current_step = f"Resume Error: {str(e)}"
                    db.commit()
            finally:
                db.close()

