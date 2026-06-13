from typing import Any, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

from agents.narrator import NarratorTool
from services.generation.content_service import search_rag, synthesize_presentation_outline
from providers.llm_provider import generate_json
from database import SessionLocal
import models


# ─────────────────────────────────────────────────────────────────────────────
# SearchKnowledgeTool
# ─────────────────────────────────────────────────────────────────────────────

class SearchKnowledgeArgs(BaseModel):
    query: str = Field(..., description="Consulta semántica para buscar en la base de conocimiento corporativo")
    knowledge_source: str = Field(..., description="Nombre del archivo/source de knowledge base")
    k: int = Field(15, description="Cantidad de fragmentos a recuperar")
    brand_id: Optional[int] = Field(None, description="ID de la marca para filtrar por soberanía de datos")

class SearchKnowledgeTool(BaseAgentTool):
    name = "search_knowledge"
    description = "Recupera conocimiento corporativo usando RAG + pgvector, filtrado por brand_id cuando se proporciona."
    args_schema = SearchKnowledgeArgs

    def run(self, query: str, knowledge_source: str, k: int = 15, brand_id: Optional[int] = None) -> str:
        return search_rag(query=query, knowledge_source=knowledge_source, k=k, brand_id=brand_id)

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# SlideContentTool — per-slide RAG + LLM content generation
# ─────────────────────────────────────────────────────────────────────────────

class SlideContentArgs(BaseModel):
    job_id: int = Field(..., description="ID del GenerationJob al que pertenece este slide")
    idx: int = Field(..., description="Índice del slide (0-based)")
    slide_title: str = Field(..., description="Título del slide (sanitizado)")
    section_label: str = Field("STRATEGY", description="Etiqueta de sección")
    layout_type: str = Field("composition_split", description="Tipo de layout")
    knowledge_source: str = Field(..., description="Nombre del archivo de knowledge base")
    brand_id: int = Field(..., description="ID de la marca")
    brand_name: str = Field(..., description="Nombre de la marca")
    region: str = Field("Global", description="Idioma/región objetivo")
    strategic_context: str = Field("", description="Instrucción estratégica global (polished_prompt truncado)")

class SlideContentTool(BaseAgentTool):
    name = "slide_content"
    description = "Genera contenido para UN slide individual: RAG targeted (k=10) + llamada LLM dedicada."
    args_schema = SlideContentArgs

    def run(
        self,
        job_id: int,
        idx: int,
        slide_title: str,
        section_label: str,
        layout_type: str,
        knowledge_source: str,
        brand_id: int,
        brand_name: str,
        region: str = "Global",
        strategic_context: str = "",
    ):
        db = SessionLocal()
        try:
            targeted_rag = search_rag(
                f"{slide_title} {section_label}",
                knowledge_source,
                brand_id=brand_id,
                k=10,
            )

            cfg = (
                db.query(models.SystemConfig)
                .filter(models.SystemConfig.key == "prompt_slide_content_v2")
                .first()
                or db.query(models.SystemConfig)
                .filter(models.SystemConfig.key == "prompt_slide_content_v1")
                .first()
            )

            if not cfg:
                return idx, {
                    "title": slide_title,
                    "section_label": section_label,
                    "layout_type": layout_type,
                    "bullets": [],
                    "subtitle": None,
                    "metrics": [],
                    "visual_intent": "",
                    "visual_tags": [],
                    "objective": "",
                    "metadata": {},
                    "_rag_chars": len(targeted_rag),
                }

            slide_prompt = cfg.value.format(
                slide_title=slide_title,
                section_label=section_label,
                layout_type=layout_type,
                rag_context=targeted_rag or "No specific context available.",
                brand_name=brand_name,
                target_lang=region,
                strategic_context=str(strategic_context or "")[:400],
            )

            try:
                content = generate_json(slide_prompt, specialization="general")
                if not isinstance(content, dict):
                    content = {}
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).warning(
                    f"[SlideContentTool] Slide {idx + 1} LLM call failed: {e}"
                )
                content = {}

            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="slide_content",
                summary=f"Slide {idx + 1}: '{slide_title[:45]}' — {len(content.get('bullets', []))} bullets, {len(targeted_rag)} RAG chars",
                reasoning=targeted_rag[:600],
                slide_number=idx + 1,
                prompt_used=slide_prompt[:800],
                response_raw=content,
                metadata={
                    "idx": idx,
                    "layout_type": layout_type,
                    "section_label": section_label,
                    "rag_chars": len(targeted_rag),
                    "has_metrics": bool(content.get("metrics")),
                    "prompt_key": cfg.key,
                },
            )
            db.commit()

            return idx, {
                "title": slide_title,
                "section_label": section_label,
                "layout_type": layout_type,
                "bullets": content.get("bullets", []),
                "subtitle": content.get("subtitle"),
                "metrics": content.get("metrics", []),
                "visual_intent": content.get("visual_intent", ""),
                "visual_tags": content.get("visual_tags", []),
                "objective": content.get("objective", ""),
                "metadata": content.get("metadata", {}),
                "_rag_chars": len(targeted_rag),
            }
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# GenerateTextTool — orchestrator entry point for content generation
# ─────────────────────────────────────────────────────────────────────────────

class GenerateTextArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo de generación")
    prompt: str = Field(..., description="El prompt original del usuario")
    style_filename: str = Field(..., description="Referencia visual / estilo a usar")
    knowledge_filename: str = Field(..., description="Nombre del archivo de contexto / RAG")
    region: str = Field("Global", description="Región o idioma del texto objetivo")
    allow_ai_images: bool = Field(False, description="Si se permiten imágenes IA como fallback")

class GenerateTextTool(BaseAgentTool):
    name = "generate_text"
    description = "Sintetiza la estructura de la presentación (ContentManifest) usando el pipeline 3-step RAG + LLM. Guarda slides en BD."
    args_schema = GenerateTextArgs

    def run(
        self,
        job_id: int,
        prompt: str,
        style_filename: str,
        knowledge_filename: str,
        region: str = "Global",
        allow_ai_images: bool = False,
    ) -> Any:
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.status = models.GenerationJobStatus.SYNTHESIZING_CONTENT
                job.current_step = "Agent: Redactor is writing the slides..."
                db.commit()

            req_data = {
                "prompt": prompt,
                "style_filename": style_filename,
                "knowledge_filename": knowledge_filename,
                "region": region,
                "allow_ai_images": allow_ai_images,
            }

            # Pass SlideContentTool class as factory — content_service creates
            # one fresh instance per slide (thread-safe, full BaseAgentTool contract)
            content_manifest = synthesize_presentation_outline(
                db, job_id, req_data,
                slide_generator=SlideContentTool,
                narrator=NarratorTool,
            )

            slide_count = len(content_manifest.slides) if hasattr(content_manifest, "slides") else 0

            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="content_synthesis",
                summary=f"Redactor generated {slide_count} slide(s) via 3-step RAG pipeline.",
                reasoning=f"Prompt: {prompt[:300]}",
                metadata={
                    "slide_count": slide_count,
                    "region": region,
                    "style_filename": style_filename,
                    "knowledge_filename": knowledge_filename,
                    "allow_ai_images": allow_ai_images,
                },
            )

            if job:
                job.status = models.GenerationJobStatus.CONTENT_READY
                job.current_step = "Content structure ready for review or layout."
                db.commit()

            return content_manifest
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
