import os
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

# Importamos las funciones originales (sin mover su lógica interna)
from services.ingestion.visual_dna_service import extract_visual_dna
from services.ingestion.artistic_essence_service import extract_artistic_essence
from database import SessionLocal
import models

class ReadPPTXArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo de ingestión")
    file_path: str = Field(..., description="Ruta absoluta al archivo (PPTX o PDF)")
    upload_dir: str = Field(..., description="Directorio donde se guardarán los assets extraídos")

class ReadPPTXTool(BaseAgentTool):
    name = "read_pptx"
    description = "Analiza el documento fuente física y programáticamente, extrayendo imágenes recortadas, fuentes y hexadecimale crudos."
    args_schema = ReadPPTXArgs

    def run(self, job_id: int, file_path: str, upload_dir: str) -> Dict[str, Any]:
        """
        Ejecuta la extracción de ADN visual.
        Actualiza el estado en la base de datos para mantener trazas del proceso.
        """
        db = SessionLocal()
        try:
            job = db.query(models.IngestionJob).get(job_id)
            if job:
                job.status = models.IngestionJobStatus.PROCESSING_VISUAL_DNA
                db.commit()

            # Llama a la lógica original de extracción programática
            raw_dna = extract_visual_dna(file_path, upload_dir)

            if job:
                job.status = models.IngestionJobStatus.VISUAL_DNA_EXTRACTED
                db.commit()

            return raw_dna
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        # Envolvemos en asíncrono si es necesario
        return self.run(**kwargs)


class ExtractPaletteArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo de ingestión")
    file_path: str = Field(..., description="Ruta absoluta al archivo para extraer esencia artística")
    upload_dir: str = Field(..., description="Directorio para assets/imágenes de visión")
    brand_id: Optional[int] = Field(None, description="ID de la marca (opcional)")

class ExtractPaletteTool(BaseAgentTool):
    name = "extract_palette"
    description = "Usa Vision LLMs para inferir la paleta refinada, la esencia artística y reglas de composición."
    args_schema = ExtractPaletteArgs

    def run(self, job_id: int, file_path: str, upload_dir: str, brand_id: Optional[int] = None) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            job = db.query(models.IngestionJob).get(job_id)
            if job:
                job.status = models.IngestionJobStatus.PROCESSING_ARTISTIC_ESSENCE
                db.commit()

            # Llama a la lógica original de esencia artística
            essence = extract_artistic_essence(file_path, upload_dir, brand_id=brand_id)

            if job:
                job.status = models.IngestionJobStatus.ARTISTIC_ESSENCE_EXTRACTED
                db.commit()

            return essence
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
