import json
from typing import Any, Dict, List
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

from services.generation.content_service import search_rag, synthesize_presentation_outline
from database import SessionLocal
import models

class SearchKnowledgeArgs(BaseModel):
    query: str = Field(..., description="Consulta semántica para buscar en la base de datos de conocimiento corporativo")
    knowledge_source: str = Field(..., description="Nombre del archivo/source que se usó como knowledge base")
    k: int = Field(15, description="Cantidad de fragmentos a recuperar")

class SearchKnowledgeTool(BaseAgentTool):
    name = "search_knowledge"
    description = "Recupera conocimiento corporativo relevante de la base de datos usando RAG y búsqueda vectorial (pgvector)."
    args_schema = SearchKnowledgeArgs

    def run(self, query: str, knowledge_source: str, k: int = 15) -> str:
        """
        Ejecuta la búsqueda RAG y retorna el contexto como string.
        """
        return search_rag(query=query, knowledge_source=knowledge_source, k=k)

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)


class GenerateTextArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo de generación")
    prompt: str = Field(..., description="El prompt original del usuario")
    style_filename: str = Field(..., description="Referencia visual / estilo a usar")
    knowledge_filename: str = Field(..., description="Nombre del archivo de contexto / RAG")
    region: str = Field("Global", description="Región o idioma del texto objetivo")
    allow_ai_images: bool = Field(False, description="Si se permiten imágenes IA como fallback")

class GenerateTextTool(BaseAgentTool):
    name = "generate_text"
    description = "Sintetiza la estructura de la presentación (ContentManifest) usando un LLM y conocimiento RAG corporativo. Guarda los resultados en BD."
    args_schema = GenerateTextArgs

    def run(self, job_id: int, prompt: str, style_filename: str, knowledge_filename: str, region: str = "Global", allow_ai_images: bool = False) -> Any:
        """
        Genera el contenido estructurado.
        Guarda los slides generados en la base de datos (PresentationSlide) como 'trazas' de este paso,
        permitiendo que el usuario pueda intervenir/editar el texto antes de pasar al arquitecto.
        """
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.status = "synthesizing_content"
                job.current_step = "Agent: Redactor is writing the slides..."
                db.commit()

            # Preparamos el diccionario req_data como lo espera la función legacy
            req_data = {
                "prompt": prompt,
                "style_filename": style_filename,
                "knowledge_filename": knowledge_filename,
                "region": region,
                "allow_ai_images": allow_ai_images
            }

            # Llama a la lógica original de síntesis de contenido (que ya guarda en BD)
            content_manifest = synthesize_presentation_outline(db, job_id, req_data)

            if job:
                job.status = "content_ready"
                job.current_step = "Content structure ready for review or layout."
                db.commit()

            return content_manifest
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
