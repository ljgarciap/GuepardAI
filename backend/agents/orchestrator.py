import logging
import traceback
from agents.redactor import GenerateTextTool
from agents.arquitecto import ComposeLayoutTool
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
      - run_generation_pipeline: Orquesta Redactor → Arquitecto → QA → Render.
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
        """
        logger.info(f"[Orchestrator] Starting Ingestion Pipeline for brand_id={brand_id}, file={source_filename}")

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
        try:
            _update_step("Agent: Brand Analyst extracting artistic essence (Vision)...", 10)
            logger.info("[Orchestrator] Brand Analyst → ExtractPaletteTool (Artistic Essence)")
            self.extract_palette(
                job_id=ingestion_job_id,
                file_path=file_path,
                upload_dir=upload_dir,
                brand_id=brand_id,
            )
            _update_step("Artistic essence extracted.", 45)
            logger.info("[Orchestrator] ExtractPaletteTool completed.")
        except Exception as e:
            logger.error(f"[Orchestrator] ExtractPaletteTool failed (non-fatal): {e}")
            _update_step(f"Warning: Artistic essence failed — {str(e)[:100]}. Continuing...", 45)

        # ── PASO 2: ADN Visual Programático (Context-Aware) ─────────────────
        # Se ejecuta DESPUÉS del palette para que el LLM tenga el Rulebook disponible
        try:
            _update_step("Agent: Brand Analyst reading visual DNA (programmatic)...", 50)
            logger.info("[Orchestrator] Brand Analyst → ReadPPTXTool (Visual DNA)")
            self.read_pptx(
                job_id=ingestion_job_id,
                file_path=file_path,
                upload_dir=upload_dir,
            )
            _update_step("Visual DNA extracted.", 90)
            logger.info("[Orchestrator] ReadPPTXTool completed.")
        except Exception as e:
            logger.error(f"[Orchestrator] ReadPPTXTool failed (non-fatal): {e}")
            logger.error(traceback.format_exc())
            _update_step(f"Warning: Visual DNA failed — {str(e)[:100]}. Continuing...", 90)

        # ── FINALIZACIÓN ────────────────────────────────────────────────────
        _update_step("Brand Analyst pipeline complete.", 100)
        _set_status("completed")
        logger.info(f"[Orchestrator] Ingestion Pipeline completed for brand_id={brand_id}")

    def run_generation_pipeline(self, job_id: int, req_data: dict):
        """
        Flujo de trabajo para Generar una Presentación.
        """
        logger.info(f"[Orchestrator] Starting Agent Pipeline for Job {job_id}")
        
        try:
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

            # Bucle de Diseño y QA
            retries = 0
            qa_passed = False
            
            while retries <= self.MAX_RETRIES and not qa_passed:
                logger.info(f"[Orchestrator] Delegating to Arquitecto (ComposeLayoutTool) - Attempt {retries + 1}")
                self.compose_layout(job_id=job_id, is_premium=(req_data.get("tier") == "premium"))

                logger.info(f"[Orchestrator] Delegating to QA Validator (ScoreFidelityTool/ValidateBrandTool)...")
                # Determinista
                brand_validation = self.validate_brand(job_id=job_id)
                if brand_validation["status"] == "failed":
                    logger.warning(f"[Orchestrator] QA Deterministic Failed: {brand_validation['violations']}")
                    needs_rework = True
                else:
                    # Híbrido/LLM
                    qa_result = self.score_fidelity(job_id=job_id)
                    needs_rework = qa_result.get("needs_rework", False)

                if needs_rework:
                    retries += 1
                    logger.info(f"[Orchestrator] QA rejected design. Retries used: {retries}/{self.MAX_RETRIES}")
                    if retries > self.MAX_RETRIES:
                        logger.warning(f"[Orchestrator] Max retries reached. Forcing acceptance.")
                        qa_passed = True # Forzamos el pase porque nos quedamos sin reintentos
                else:
                    logger.info(f"[Orchestrator] QA Approved design!")
                    qa_passed = True

            # 4. Render Engine
            logger.info(f"[Orchestrator] Calling Render Agent (RenderPPTXTool)...")
            self.render_pptx(
                job_id=job_id,
                output_format=req_data.get("output_format", "pptx"),
                is_premium=(req_data.get("tier") == "premium")
            )
                
            logger.info(f"[Orchestrator] Agent Pipeline completed for Job {job_id}")

        except Exception as e:
            logger.error(f"[Orchestrator] Pipeline failed: {str(e)}")
            logger.error(traceback.format_exc())
            db = SessionLocal()
            try:
                job = db.query(models.GenerationJob).get(job_id)
                if job:
                    job.status = "error"
                    job.current_step = f"Pipeline Error: {str(e)}"
                    db.commit()
            finally:
                db.close()

