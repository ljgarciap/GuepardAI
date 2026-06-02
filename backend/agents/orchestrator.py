import logging
import traceback
from agents.redactor import GenerateTextTool
from agents.arquitecto import ComposeLayoutTool
from agents.qa_validator import ScoreFidelityTool, ValidateBrandTool
from agents.render_agent import RenderPPTXTool
from database import SessionLocal
import models

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Orquestador Central de Agentes (MCP).
    Enruta las peticiones basándose en el estado del Job e implementa ciclos de validación.
    """
    def __init__(self):
        self.generate_text = GenerateTextTool()
        self.compose_layout = ComposeLayoutTool()
        self.score_fidelity = ScoreFidelityTool()
        self.validate_brand = ValidateBrandTool()
        self.render_pptx = RenderPPTXTool()
        self.MAX_RETRIES = 2

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

