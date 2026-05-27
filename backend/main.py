import os
import time
import json
import uvicorn
import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, text
from sqlalchemy.orm import Session
import models
from database import SessionLocal, engine, Base
from services.ingestion_orchestrator import (
    task_extract_visual_dna,
    task_extract_artistic_essence,
    task_extract_full_brand_style,
    task_ingest_knowledge,
    task_extract_pure_assets,
    task_generate_presentation
)
from services.brand_service import create_brand_logic, update_brand_logic
import uuid
from datetime import datetime
from sqlalchemy import JSON

# ── PIPELINE SERVICES ──
from services.content_engine import synthesize_strategic_content
from services.asset_engine import orchestrate_assets
from services.layout_engine import apply_design_policy
from services.pptx_renderer import render_pptx_manifest

# ── INGESTION SERVICES (nuevos) ──
from services.visual_dna_service import extract_visual_dna
from services.artistic_essence_service import extract_artistic_essence

# ── INGESTION SERVICES (legacy RAG — sin cambios) ──
from ingest_knowledge import ingest_document as ingest_rag

print("[System] PowerAI Engine v11.0 (Clean Architecture) IS LIVE.", flush=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from seed import seed_data

Base.metadata.create_all(bind=engine)
try:
    seed_data()
except Exception as e:
    print(f"  [System] Warning: Seeding failed: {e}")


app = FastAPI(title="PowerAI API — Clean Architecture")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CORSStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads"))
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "outputs"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
app.mount("/uploads", CORSStaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/outputs", CORSStaticFiles(directory=OUTPUT_DIR), name="outputs")


# ──────────────────────────────────────────────
# MODELOS PYDANTIC
# ──────────────────────────────────────────────

class BrandCreate(BaseModel):
    name: str
    about: Optional[str] = None
    core_value: Optional[str] = None
    logo_path: Optional[str] = None

class PresentationRequest(BaseModel):
    style_filename: str        
    knowledge_filename: str    
    prompt: str
    region: str = "LATAM"
    brand_id: Optional[int] = None
    allow_ai_images: bool = False
    output_format: str = "pptx" # 'pptx' or 'pdf_artistic'
    tier: str = "free"         # 'free' | 'premium' (Fix/Roadmap 1)


# ──────────────────────────────────────────────
# DB HELPER
# ──────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────
# JOB TRACKER (thread-safe)
# ──────────────────────────────────────────────

def update_job_step(job_key: str, ingestion_type: str,
                    message: str, progress: int = None):
    """
    job_key: identificador del job (source_filename o client_name)
    ingestion_type: 'visual_dna' | 'artistic' | 'knowledge'
    """
    db = SessionLocal()
    try:
        job = db.query(models.IngestionJob).filter(
            models.IngestionJob.client_name == job_key,
            models.IngestionJob.ingestion_type == ingestion_type
        ).first()
        if job:
            job.current_step = message
            if progress is not None:
                job.progress = max(0, min(100, progress))
            db.commit()
            print(f"[Job] {job_key} ({ingestion_type}) → {message} ({progress or ''}%)", flush=True)
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


# ──────────────────────────────────────────────
# ENDPOINTS — BRAND DIRECTORY (v11.0)
# ──────────────────────────────────────────────

@app.get("/api/brands", tags=["Governance"])
def list_brands(db: Session = Depends(get_db)):
    """Lista el Directorio Oficial de Marcas."""
    return db.query(models.Brand).all()

@app.post("/api/brands", tags=["Governance"])
async def create_brand(
    name: str = Form(...),
    about: Optional[str] = Form(None),
    core_value: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Registra una nueva marca (Delegado a BrandService)."""
    existing = db.query(models.Brand).filter(models.Brand.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Brand already exists.")
    
    brand = await create_brand_logic(db, name, about, core_value, logo)
    return {
        "id": brand.id,
        "name": brand.name,
        "logo_path": brand.logo_path,
        "about": brand.about,
        "core_value": brand.core_value
    }

@app.put("/api/brands/{brand_id}", tags=["Governance"])
async def update_brand(
    brand_id: int,
    name: str = Form(...),
    about: Optional[str] = Form(None),
    core_value: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Actualiza una marca (Delegado a BrandService)."""
    brand = await update_brand_logic(db, brand_id, name, about, core_value, logo)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")
    
    return {
        "id": brand.id,
        "name": brand.name,
        "logo_path": brand.logo_path,
        "about": brand.about,
        "core_value": brand.core_value
    }


# ──────────────────────────────────────────────
# WORKER TASKS (background)
# ──────────────────────────────────────────────
@app.get("/api/library/images", tags=["Library"])
def list_images(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista activos excluyendo datos binarios/vectores para evitar errores de serialización."""
    query = db.query(models.BrandAsset)
    if brand_id:
        query = query.filter(models.BrandAsset.brand_id == brand_id)
    
    assets = query.all()
    # v21.5: Conversión manual para evitar fallos con pgvector/embeddings
    safe_assets = []
    for a in assets:
        # v21.6: Normalizar ruta para el frontend
        filename = os.path.basename(a.local_path)
        safe_assets.append({
            "id": a.id,
            "brand_id": a.brand_id,
            "category": a.category,
            "local_path": f"uploads/{filename}",
            "tags": a.tags,
            "description": a.description,
            "source_doc": a.source_doc,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })
    return safe_assets

@app.get("/api/generation/status/{job_id}", tags=["Generation"])
def get_generation_status(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.GenerationJob).get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "id": job.id, "status": job.status, "progress": job.progress,
        "current_step": job.current_step,
        "download_url": f"/api/generation/download/{job.id}" if job.status == "completed" else None
    }

@app.get("/api/generation/download/{job_id}", tags=["Generation"])
def download_presentation(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.GenerationJob).get(job_id)
    if not job or job.status != "completed": raise HTTPException(status_code=404, detail="File not ready.")
    return FileResponse(job.pptx_path, filename=os.path.basename(job.pptx_path))


# ──────────────────────────────────────────────
# ENDPOINTS — INGESTION (v11.0)
# ──────────────────────────────────────────────

@app.post("/api/brand/upload", tags=["Ingestion"])
async def upload_asset(
    background_tasks: BackgroundTasks,
    ingestion_type: str = Form(...),   
    visibility_scope: str = Form("exclusive"), 
    brand_id: Optional[int] = Form(None),       
    manual_tags: Optional[str] = Form(None),    
    document_type: str = Form("company_knowledge"), 
    file: UploadFile = File(...)
):
    """Punto de entrada para la ingesta de conocimiento y estilo."""
    job_key = file.filename
    safe_tags = [t.strip() for t in manual_tags.split(",")] if manual_tags else []
    
    # Guardar archivo
    file_path = os.path.join(UPLOAD_DIR, job_key)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    db = SessionLocal()
    # Crear o actualizar Job
    job = db.query(models.IngestionJob).filter(
        models.IngestionJob.client_name == job_key,
        models.IngestionJob.ingestion_type == ingestion_type
    ).first()
    
    if not job:
        job = models.IngestionJob(
            client_name=job_key,
            ingestion_type=ingestion_type,
            status="processing",
            progress=0,
            visibility_scope=visibility_scope
        )
        db.add(job)
    else:
        job.status = "processing"
        job.progress = 0
        job.visibility_scope = visibility_scope
    
    db.commit()
    db.close()

    # Disparar tarea en segundo plano (vía Orquestador)
    if ingestion_type == "brand_style":
        background_tasks.add_task(task_extract_full_brand_style, job_key, file_path, job_key, visibility_scope, brand_id, safe_tags)
    elif ingestion_type == "knowledge":
        background_tasks.add_task(task_ingest_knowledge, job_key, file_path, job_key, brand_id, visibility_scope, document_type)
    elif ingestion_type == "pure_assets":
        background_tasks.add_task(task_extract_pure_assets, job_key, file_path, job_key, visibility_scope, brand_id, safe_tags)

    return {"status": "processing", "job_key": job_key}

@app.get("/api/ingestion/status/{job_key}", tags=["Ingestion"])
def get_ingestion_status(job_key: str, ingestion_type: str = "brand_style", db: Session = Depends(get_db)):
    """Consulta el progreso de una tarea de ingesta."""
    job = db.query(models.IngestionJob).filter(
        models.IngestionJob.client_name == job_key,
        models.IngestionJob.ingestion_type == ingestion_type
    ).first()
    if not job: raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step
    }

@app.get("/api/library/blueprints", tags=["Library"])
def list_library_blueprints(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista los blueprints de estilo en la librería (usando BrandVisualDna)."""
    query = db.query(models.BrandVisualDna)
    if brand_id:
        query = query.filter(models.BrandVisualDna.brand_id == brand_id)
    
    blueprints = query.all()
    return [{"id": b.id, "source_filename": b.source_filename, "brand_id": b.brand_id} for b in blueprints]

@app.get("/api/library/knowledge", tags=["Library"])
def list_library_knowledge(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista los documentos de conocimiento procesados en la librería, agrupados por archivo."""
    # Usamos DISTINCT ON o GROUP BY para devolver solo una entrada por archivo
    query = db.query(
        models.CorporateKnowledge.source_filename,
        models.CorporateKnowledge.brand_id,
        models.CorporateKnowledge.is_public
    ).distinct(models.CorporateKnowledge.source_filename)
    
    if brand_id:
        query = query.filter(models.CorporateKnowledge.brand_id == brand_id)
    
    knowledge = query.all()
    return [{
        "id": i, # Usamos el índice como ID temporal para el frontend
        "filename": k.source_filename, 
        "is_public": k.is_public == 1,
        "brand_id": k.brand_id
    } for i, k in enumerate(knowledge)]

@app.get("/api/library/portfolios", tags=["Library"])
def list_library_portfolios(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista las presentaciones generadas en la librería."""
    query = db.query(models.GenerationJob).filter(models.GenerationJob.status == "completed")
    if brand_id:
        query = query.filter(models.GenerationJob.brand_id == brand_id)
    
    jobs = query.all()
    return [{
        "id": j.id, 
        "filename": os.path.basename(j.pptx_path) if j.pptx_path else f"Presentation_{j.id}.pptx",
        "created_at": j.created_at,
        "brand_id": j.brand_id
    } for j in jobs]

# ──────────────────────────────────────────────
# ENDPOINTS — GENERATION PIPELINE (Synthesis Studio)
# ──────────────────────────────────────────────

@app.get("/api/available-styles", tags=["Generation"])
def list_available_styles(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista los blueprints de estilo con lógica de visibilidad escalonada."""
    query = db.query(models.BrandVisualDna)
    
    if brand_id == -1:
        # SUPERUSER: Ver todo
        pass
    elif brand_id is None:
        # PUBLIC: Ver solo lo público
        query = query.filter(models.BrandVisualDna.is_public == 1)
    else:
        # BRAND: Ver lo de la marca + lo público
        query = query.filter((models.BrandVisualDna.brand_id == brand_id) | (models.BrandVisualDna.is_public == 1))
    
    blueprints = query.all()
    return {"styles": [{"id": b.id, "filename": b.source_filename} for b in blueprints]}

@app.get("/api/available-knowledge", tags=["Generation"])
def list_available_knowledge(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista los paquetes de conocimiento con lógica de visibilidad escalonada."""
    query = db.query(models.CorporateKnowledge.source_filename).distinct()
    
    if brand_id == -1:
        # SUPERUSER: Ver todo
        pass
    elif brand_id is None:
        # PUBLIC: Ver solo lo público
        query = query.filter(models.CorporateKnowledge.is_public == 1)
    else:
        # BRAND: Ver lo de la marca + lo público
        query = query.filter((models.CorporateKnowledge.brand_id == brand_id) | (models.CorporateKnowledge.is_public == 1))
    
    sources = query.all()
    return {"sources": [s[0] for s in sources]}

@app.get("/api/available-dialects", tags=["Generation"])
def list_dialects(db: Session = Depends(get_db)):
    """Lista las regiones/idiomas disponibles (antes llamados dialectos)."""
    languages = db.query(models.Language).filter(models.Language.is_active == True).all()
    return [{"id": l.id, "code": l.code, "name": l.name} for l in languages]

@app.post("/api/presentations/generate", tags=["Generation"])
async def generate_presentation(
    request: PresentationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Dispara el motor de síntesis para generar una nueva presentación."""
    # Buscar el ID del Style (Blueprint) para la jerarquía de activos v23.0
    style_dna = db.query(models.BrandVisualDna).filter(
        models.BrandVisualDna.source_filename == request.style_filename
    ).first()
    
    job = models.GenerationJob(
        brand_id=request.brand_id,
        style_id=style_dna.id if style_dna else None,
        status="pending",
        progress=0,
        current_step="Initializing isolated synthesis engine v23.0...",
        allow_ai_images=request.allow_ai_images
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Disparar orquestación con el nuevo formato de mensaje
    req_payload = {
        "style_filename": request.style_filename,
        "knowledge_filename": request.knowledge_filename,
        "prompt": request.prompt,
        "region": request.region,
        "allow_ai_images": request.allow_ai_images,
        "output_format": request.output_format,
        "tier": request.tier
    }
    
    background_tasks.add_task(
        task_generate_presentation,
        job.id,
        req_payload
    )

    return {"job_id": job.id, "status": "pending"}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
