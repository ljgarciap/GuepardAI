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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PowerAI API — Clean Architecture")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:3000",
        "*"
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
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", CORSStaticFiles(directory=UPLOAD_DIR), name="uploads")


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
    """Registra una nueva marca con integración total de IA para el logo."""
    existing = db.query(models.Brand).filter(models.Brand.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Brand already exists.")
    
    # 1. Crear el registro de la marca primero para obtener el ID
    new_brand = models.Brand(
        name=name, 
        about=about,
        core_value=core_value
    )
    db.add(new_brand)
    db.commit()
    db.refresh(new_brand)

    # 2. Si hay logo, procesarlo como Activo Estratégico (IA)
    if logo:
        from services.asset_library_service import register_asset
        # Guardar temporalmente para procesar
        safe_logo_name = f"logo_{int(time.time())}_{logo.filename}"
        temp_path = os.path.join(UPLOAD_DIR, safe_logo_name)
        with open(temp_path, "wb") as buffer:
            buffer.write(await logo.read())
        
        # Registrar en la biblioteca (esto dispara la IA y guarda el embedding)
        asset = register_asset(
            db, 
            brand_id=new_brand.id, 
            file_path=temp_path, 
            category="logo", 
            is_public=False,
            source_doc=f"Brand Identity: {name}",
            manual_tags=["official-logo", "identity"]
        )
        
        # Actualizar la ruta en la marca usando la ruta relativa para el frontend
        new_brand.logo_path = f"uploads/{os.path.basename(temp_path)}"
        db.commit()
        db.refresh(new_brand)

    return new_brand

@app.put("/api/brands/{brand_id}", tags=["Governance"])
async def update_brand(
    brand_id: int,
    name: str = Form(...),
    about: Optional[str] = Form(None),
    core_value: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Actualiza un dossier de marca e integra el nuevo logo en la biblioteca."""
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")
    
    brand.name = name
    brand.about = about
    brand.core_value = core_value
    
    if logo:
        from services.asset_library_service import register_asset
        # Procesar nuevo logo
        safe_logo_name = f"logo_{int(time.time())}_{logo.filename}"
        temp_path = os.path.join(UPLOAD_DIR, safe_logo_name)
        with open(temp_path, "wb") as buffer:
            buffer.write(await logo.read())
            
        # Registrar como nuevo activo (IA)
        register_asset(
            db, 
            brand_id=brand.id, 
            file_path=temp_path, 
            category="logo", 
            is_public=False,
            source_doc=f"Brand Identity Update: {name}",
            manual_tags=["official-logo", "identity", "updated"]
        )
        
        # Ruta relativa para el frontend
        brand.logo_path = f"uploads/{os.path.basename(temp_path)}"

    db.commit()
    db.refresh(brand)
    return brand


# ──────────────────────────────────────────────
# WORKER TASKS (background)
# ──────────────────────────────────────────────

def task_extract_visual_dna(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Extrae DNA Visual y persiste en brand_visual_dna."""
    logger.info(f"[Task] Visual DNA iniciado: {source_filename} (Brand: {brand_id}, Scope: {visibility_scope})")
    cb = lambda msg, p=0: update_job_step(job_key, "visual_dna", msg, p)

    try:
        dna = extract_visual_dna(file_path, UPLOAD_DIR, cb=cb)

        if "error" in dna:
            raise Exception(dna["error"])

        db = SessionLocal()
        try:
            # En v11.0 usamos brand_id formal
            # v12.0: Strategic DNA also follows visibility
            is_public = (visibility_scope == "public")
            
            record = db.query(models.BrandVisualDna).filter(
                models.BrandVisualDna.brand_id == brand_id
            ).first()
            if not record:
                record = models.BrandVisualDna(brand_id=brand_id, source_filename=source_filename, is_public=int(is_public))
                db.add(record)
            else:
                record.source_filename = source_filename
                record.is_public = int(is_public)

            record.primary_color    = dna.get("primary_color", "#333333")
            record.secondary_color  = dna.get("secondary_color", "#666666")
            record.background_color = dna.get("background_color", "#FFFFFF")
            record.text_main_color  = dna.get("text_main_color", "#111111")
            record.accent_color     = dna.get("accent_color")
            record.primary_font     = dna.get("primary_font", "Arial")
            record.secondary_font   = dna.get("secondary_font")
            record.slide_width_inches = dna.get("slide_width_inches", 13.33)
            record.slide_height_inches = dna.get("slide_height_inches", 7.5)
            record.raw_extraction   = dna.get("raw_extraction")

            # --- REGISTRO EN BIBLIOTECA DE ACTIVOS (v11.0 - Governance Pass) ---
            from services.asset_library_service import register_asset
            final_library_assets = {"photos": [], "logos": [], "icons": []}
            is_public = (visibility_scope == "public")
            
            raw_assets = dna.get("extracted_assets", {})
            for cat, items in raw_assets.items():
                for item in items:
                    raw_path = os.path.join(UPLOAD_DIR, item["path"])
                    if os.path.exists(raw_path):
                        # Registramos con visibilidad, marca formal y tags manuales
                        asset_record = register_asset(
                            db, 
                            brand_id, 
                            raw_path, 
                            category=cat,
                            is_public=is_public,
                            source_doc=source_filename,
                            manual_tags=manual_tags
                        )
                        final_library_assets[cat].append({
                            "id": asset_record.id,
                            "path": os.path.basename(asset_record.local_path),
                            "tags": asset_record.tags,
                            "manual_tags": asset_record.manual_tags,
                            "description": asset_record.description,
                            "is_public": asset_record.is_public
                        })
            
            record.extracted_assets = final_library_assets

            # --- SINCRONIZACIÓN LEGACY ---
            legacy = db.query(models.BrandStyle).filter(
                models.BrandStyle.client_name == source_filename
            ).first()
            if not legacy:
                legacy = models.BrandStyle(client_name=source_filename)
                db.add(legacy)
            
            legacy.primary_color    = record.primary_color
            legacy.secondary_color  = record.secondary_color
            legacy.background_color = record.background_color
            legacy.font_family      = record.primary_font
            legacy.extracted_assets = record.extracted_assets

            db.commit()
        finally:
            db.close()

        update_job_step(job_key, "visual_dna", "Visual DNA completed.", 100)
        set_job_status(job_key, "visual_dna", "completed")

    except Exception as e:
        logger.error(f"[Task] Visual DNA error: {e}")
        update_job_step(job_key, "visual_dna", f"Error: {str(e)}", 0)
        set_job_status(job_key, "visual_dna", "error")


def task_extract_artistic_essence(job_key: str, file_path: str, source_filename: str, brand_id: int = None, visibility_scope: str = "exclusive"):
    """Extrae Esencia Artística (layouts/gestos) vía Vision LLM (v12.0)."""
    logger.info(f"[Task] Artistic Essence started: {source_filename} (Brand: {brand_id}, Scope: {visibility_scope})")
    cb = lambda msg, p=0: update_job_step(job_key, "artistic", msg, p)

    try:
        brand_essence = extract_artistic_essence(file_path, UPLOAD_DIR, cb=cb)

        # VALIDACIÓN CRÍTICA: No permitir éxitos vacíos
        if "error" in brand_essence:
            raise Exception(f"Extraction failed: {brand_essence['error']}")
        
        # Si todos los campos clave están vacíos, es un fallo de visión
        if not brand_essence.get("structural_archetypes") and not brand_essence.get("design_gestures"):
            raise Exception("Vision LLM returned empty data. Check API quota or image quality.")

        db = SessionLocal()
        try:
            # v12.0: Ahora permitimos múltiples esencias por marca (unique=False)
            # Buscamos si ya existe para este archivo EXACTO
            record = db.query(models.BrandArtisticEssence).filter(
                models.BrandArtisticEssence.source_filename == source_filename,
                models.BrandArtisticEssence.brand_id == brand_id
            ).first()
            
            is_public = (visibility_scope == "public")
            
            if not record:
                record = models.BrandArtisticEssence(source_filename=source_filename, brand_id=brand_id, is_public=int(is_public))
                db.add(record)
            else:
                record.is_public = int(is_public)

            # Sincronización
            record.brand_id              = brand_id
            record.slide_archetypes      = brand_essence.get("slide_archetypes", {})
            record.structural_archetypes = brand_essence.get("structural_archetypes", {})
            record.design_gestures        = brand_essence.get("design_gestures", {})
            record.composition_rules      = brand_essence.get("composition_rules", {})
            record.art_direction_note     = brand_essence.get("art_direction_note", "")
            record.raw_vision_response    = brand_essence.get("raw_vision_response")

            # --- SINCRONIZACIÓN LEGACY (v17.0) ---
            legacy = db.query(models.BrandStyle).filter(
                models.BrandStyle.client_name == source_filename
            ).first()
            if legacy:
                legacy.visual_patterns  = brand_essence.get("visual_patterns", [])
                legacy.visual_strategy  = brand_essence.get("visual_strategy", "")
                legacy.tone_description = record.art_direction_note
                legacy.raw_style_json   = brand_essence # Captura completa

            db.commit()
        finally:
            db.close()

        update_job_step(job_key, "artistic", "Artistic Essence completed.", 100)
        set_job_status(job_key, "artistic", "completed")

    except Exception as e:
        logger.error(f"[Task] Artistic Essence error: {e}")
        update_job_step(job_key, "artistic", f"Critical Error: {str(e)}", 0)
        set_job_status(job_key, "artistic", "error")


def task_ingest_knowledge(job_key: str, file_path: str, source_filename: str, brand_id: int = None, visibility_scope: str = "exclusive", document_type: str = "company_knowledge"):
    """Ingesta RAG con Soberanía, Visibilidad y Taxonomía (v12.0)."""
    logger.info(f"[Task] Knowledge Ingest started: {source_filename} (Brand: {brand_id}, Type: {document_type})")
    cb = lambda msg, p=0: update_job_step(job_key, "knowledge", msg, p)

    try:
        is_public = (visibility_scope == "public")
        ingest_rag(file_path, client_name=source_filename, update_callback=cb, brand_id=brand_id, is_public=is_public)
        set_job_status(job_key, "knowledge", "completed")
    except Exception as e:
        logger.error(f"[Task] Knowledge error: {e}")
        update_job_step(job_key, "knowledge", f"Error: {str(e)}", 0)
        set_job_status(job_key, "knowledge", "error")


def task_extract_pure_assets(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """
    Cosecha pura de activos. Extrae imágenes y las registra en la biblioteca.
    """
    logger.info(f"[Task] Asset Treasury Harvest started: {source_filename} (Brand: {brand_id}, Scope: {visibility_scope})")
    cb = lambda msg, p=0: update_job_step(job_key, "pure_assets", msg, p)

    try:
        ext = os.path.splitext(file_path)[1].lower()
        db = SessionLocal()
        is_public = (visibility_scope == "public")
        from services.asset_library_service import register_asset
        
        # SI YA ES UNA IMAGEN: Registro directo
        if ext in [".png", ".jpg", ".jpeg", ".webp", ".svg"]:
            cb("Registering direct asset...", 50)
            register_asset(
                db, 
                brand_id, 
                file_path, 
                category="photos", # Categoría base para carga directa
                is_public=is_public,
                source_doc=source_filename,
                manual_tags=manual_tags
            )
            db.commit()
            db.close()
            cb(f"Treasury update complete. 1 asset harvested.", 100)
            set_job_status(job_key, "pure_assets", "completed")
            return

        # SI ES PDF/PPTX: Extracción normal
        dna = extract_visual_dna(file_path, UPLOAD_DIR, cb=cb)
        
        try:
            raw_assets = dna.get("extracted_assets", {})
            count = 0
            for cat, items in raw_assets.items():
                for item in items:
                    raw_path = os.path.join(UPLOAD_DIR, item["path"])
                    if os.path.exists(raw_path):
                        register_asset(
                            db, 
                            brand_id, 
                            raw_path, 
                            category=cat,
                            is_public=is_public,
                            source_doc=source_filename,
                            manual_tags=manual_tags
                        )
                        count += 1
            
            db.commit()
            cb(f"Treasury update complete. {count} assets harvested.", 100)
        finally:
            db.close()

        set_job_status(job_key, "pure_assets", "completed")

    except Exception as e:
        logger.error(f"[Task] Pure Asset error: {e}")
        update_job_step(job_key, "pure_assets", f"Error: {str(e)}", 0)
        set_job_status(job_key, "pure_assets", "error")


def task_extract_full_brand_style(job_key: str, file_path: str, source_filename: str, visibility_scope: str = "exclusive", brand_id: int = None, manual_tags: List[str] = None):
    """Combines DNA and Essence extraction for a unified workflow."""
    logger.info(f"[Task] Full Brand Style initiated: {source_filename} (Brand: {brand_id})")
    cb = lambda msg, p=0: update_job_step(job_key, "brand_style", msg, p)

    try:
        # Step 1: Visual DNA
        cb("Extracting Visual DNA (Colors, Fonts)...", 10)
        task_extract_visual_dna(job_key, file_path, source_filename, visibility_scope=visibility_scope, brand_id=brand_id, manual_tags=manual_tags)
        
        # Step 2: Artistic Essence
        cb("Analyzing Artistic Essence (Vision LLM)...", 50)
        task_extract_artistic_essence(job_key, file_path, source_filename, brand_id=brand_id, visibility_scope=visibility_scope)

        update_job_step(job_key, "brand_style", "Full Brand Identity extraction complete.", 100)
        set_job_status(job_key, "brand_style", "completed")
    except Exception as e:
        logger.error(f"[Task] Full Brand Style error: {e}")
        update_job_step(job_key, "brand_style", f"Error: {str(e)}", 0)
        set_job_status(job_key, "brand_style", "error")


# ──────────────────────────────────────────────
# ENDPOINTS — INGESTA
# ──────────────────────────────────────────────

@app.post("/api/brand/upload", tags=["Ingestion"])
async def upload_asset(
    background_tasks: BackgroundTasks,
    ingestion_type: str = Form(...),   
    visibility_scope: str = Form("exclusive"), 
    brand_id: Optional[int] = Form(None),       # v11.0: Mandatory for exclusive
    manual_tags: Optional[str] = Form(None),    # v11.0: "logo, office, primary"
    document_type: str = Form("company_knowledge"), # v12.0: brand_identity, case_study, etc
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Endpoint unificado de ingesta con gobernanza de marca.
    """
    valid_types = {"brand_style", "visual_dna", "artistic", "knowledge", "pure_assets"}
    if ingestion_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"ingestion_type debe ser uno de: {valid_types}")

    if visibility_scope == "exclusive" and not brand_id:
        raise HTTPException(status_code=400, detail="brand_id is required for exclusive ingestion.")

    # Parse manual tags
    tag_list = [t.strip() for t in manual_tags.split(",")] if manual_tags else []

    source_filename = file.filename
    job_key = source_filename 

    # Guardar archivo
    safe_name = f"{ingestion_type}_{source_filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Crear / resetear job
    existing_job = db.query(models.IngestionJob).filter(
        models.IngestionJob.client_name == job_key,
        models.IngestionJob.ingestion_type == ingestion_type
    ).first()

    if not existing_job:
        existing_job = models.IngestionJob(
            client_name=job_key,
            ingestion_type=ingestion_type,
            visibility_scope=visibility_scope
        )
        db.add(existing_job)
    else:
        existing_job.visibility_scope = visibility_scope

    existing_job.status = "processing"
    existing_job.current_step = f"Starting {ingestion_type} ({visibility_scope})..."
    existing_job.progress = 2
    db.commit()

    # Disparar tarea en background
    if ingestion_type == "brand_style":
        background_tasks.add_task(task_extract_full_brand_style, job_key, file_path, source_filename, visibility_scope, brand_id, tag_list)
    elif ingestion_type == "visual_dna":
        background_tasks.add_task(task_extract_visual_dna, job_key, file_path, source_filename, visibility_scope, brand_id, tag_list)
    elif ingestion_type == "artistic":
        background_tasks.add_task(task_extract_artistic_essence, job_key, file_path, source_filename)
    elif ingestion_type == "pure_assets":
        background_tasks.add_task(task_extract_pure_assets, job_key, file_path, source_filename, visibility_scope, brand_id, tag_list)
    else:
        # v11.0: Knowledge Bank now follows Brand Governance & Visibility
        background_tasks.add_task(task_ingest_knowledge, job_key, file_path, source_filename, brand_id, visibility_scope, document_type=document_type)

    return {
        "status": "accepted",
        "ingestion_type": ingestion_type,
        "visibility_scope": visibility_scope,
        "source_filename": source_filename,
        "job_key": job_key,
    }


@app.get("/api/ingestion/status/{job_key}", tags=["Ingestion"])
def get_ingestion_status(
    job_key: str,
    ingestion_type: str = "visual_dna",
    db: Session = Depends(get_db)
):
    """Estado del job de ingesta. ingestion_type: visual_dna | artistic | knowledge"""
    job = db.query(models.IngestionJob).filter(
        models.IngestionJob.client_name == job_key,
        models.IngestionJob.ingestion_type == ingestion_type
    ).first()

    if not job:
        return {"status": "none", "current_step": "No records found.", "progress": 0}

    return {
        "status": job.status,
        "current_step": job.current_step,
        "progress": job.progress,
        "updated_at": job.updated_at,
    }


# ──────────────────────────────────────────────
# ENDPOINTS — METADATA (dropdowns)
# ──────────────────────────────────────────────

@app.get("/api/available-styles", tags=["Metadata"])
def get_available_styles(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Lista los estilos disponibles para el dropdown con filtrado por marca.
    """
    # Lógica de Soberanía v12.0
    query = db.query(models.BrandVisualDna.source_filename)
    
    if brand_id == -1:
        # SUPERUSER: All Access
        pass
    elif brand_id is None:
        # GENERIC: Only Public
        query = query.filter(models.BrandVisualDna.is_public == 1)
    else:
        # BRAND SPECIFIC: Own + Public
        query = query.filter(
            (models.BrandVisualDna.brand_id == brand_id) | 
            (models.BrandVisualDna.is_public == 1)
        )
    
    dna_files = {row[0] for row in query.all()}
    essence_files = {
        row[0] for row in db.query(models.BrandArtisticEssence.source_filename).all()
    }

    styles = []
    for fname in dna_files:
        styles.append({
            "filename": fname,
            "has_dna": True,
            "has_essence": fname in essence_files,
            "is_complete": fname in essence_files,
        })

    return {"styles": styles}


@app.get("/api/available-dialects", tags=["Metadata"])
def get_available_dialects(db: Session = Depends(get_db)):
    """Lista los dialectos disponibles ordenados por prioridad estratégica (v12.0)."""
    # Auto-seed if empty
    count = db.query(models.Language).count()
    if count == 0:
        seeds = [
            models.Language(code="UK", name="English (UK)", priority=1),
            models.Language(code="USA", name="English (USA)", priority=2),
            models.Language(code="LATAM", name="Spanish (LATAM)", priority=3),
            models.Language(code="ES", name="Spanish (Spain)", priority=4),
        ]
        db.add_all(seeds)
        db.commit()
    
    langs = db.query(models.Language).filter(models.Language.is_active == True).order_by(models.Language.priority).all()
    return [{"code": l.code, "name": l.name} for l in langs]
    
@app.get("/api/available-knowledge", tags=["Metadata"])
def get_available_knowledge(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista las fuentes RAG disponibles con filtrado soberano."""
    try:
        sql = "SELECT DISTINCT source_filename FROM corporate_knowledge"
        params = {}
        if brand_id == -1:
            # SUPERUSER: No filter
            pass
        elif brand_id is None:
            # GENERIC: Only public
            sql += " WHERE is_public = 1"
        else:
            # BRAND SPECIFIC: Own + Public
            sql += " WHERE (brand_id = :brand_id OR is_public = 1)"
            params["brand_id"] = brand_id
        
        sql += " ORDER BY 1"
        result = db.execute(text(sql), params)
        return {"sources": [row[0] for row in result]}
    except Exception as e:
        logger.error(f"Error fetching knowledge sources: {e}")
        return {"sources": []}


# ──────────────────────────────────────────────
# ENDPOINT — GENERACIÓN
# ──────────────────────────────────────────────

def task_generate_presentation(job_id: int, req: PresentationRequest, pptx_path: str):
    """
    Background worker for strategic generation (v12.0).
    """
    db = SessionLocal()
    try:
        def update_step(msg: str, p: int):
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.current_step = msg
                job.progress = p
                db.commit()
            logger.info(f"[Job {job_id}] {msg} ({p}%)")

        update_step("Orchestrating Narrative Architecture...", 10)
        
        # 1. Fetch DNA
        dna = db.query(models.BrandVisualDna).filter(
            models.BrandVisualDna.source_filename == req.style_filename
        ).first()
        
        # 2. Fetch Essence
        brand_essence = db.query(models.BrandArtisticEssence).filter(
            models.BrandArtisticEssence.source_filename == req.style_filename
        ).first()

        # 3. Content Synthesis (RAG)
        update_step("Synthesizing Strategic Content (RAG Analysis)...", 30)
        target_brand_id = req.brand_id if req.brand_id is not None else dna.brand_id
        
        content_manifest, full_prompt = synthesize_strategic_content(
            req.prompt,
            target_brand_id,
            region=req.region
        )
        
        # Audit update
        job = db.query(models.GenerationJob).get(job_id)
        job.full_llm_prompt = full_prompt
        job.llm_response_json = content_manifest
        db.commit()

        update_step("Structuring Visual Coherence...", 50)
        from services.layout_engine import orchestrate_visual_coherence
        content_manifest = orchestrate_visual_coherence(content_manifest, dna, brand_essence)
        
        update_step("Curating Brand Assets...", 65)
        asset_map = orchestrate_assets(content_manifest, brand=dna, db=db)

        update_step("Applying Design Archetypes...", 80)
        design_manifest = apply_design_policy(content_manifest, dna, brand_essence)

        # Art Director Pass
        update_step("Art Director: Refining Visual Fidelity...", 90)
        try:
            from services.design_refiner import refine_manifest
            dna_dict = {
                "primary_color": dna.primary_color,
                "secondary_color": dna.secondary_color,
                "background_color": dna.background_color,
                "text_main_color": dna.text_main_color,
                "primary_font": dna.primary_font
            }
            essence_dict = {
                "structural_archetypes": brand_essence.structural_archetypes if brand_essence else {},
                "design_gestures": brand_essence.design_gestures if brand_essence else {},
                "composition_rules": brand_essence.composition_rules if brand_essence else {}
            }
            design_manifest = refine_manifest(design_manifest, dna_dict, essence_dict)
        except Exception as ref_err:
            logger.error(f"Art Director pass failed: {ref_err}")

        update_step("Rendering High-Fidelity PPTX...", 95)
        render_pptx_manifest(design_manifest, asset_map, pptx_path)

        # Finalize
        job = db.query(models.GenerationJob).get(job_id)
        job.status = "completed"
        job.pptx_path = pptx_path
        job.current_step = "Presentation Ready for Download"
        job.progress = 100
        db.commit()
        
    except Exception as e:
        logger.error(f"[Task Error] {e}")
        job = db.query(models.GenerationJob).get(job_id)
        if job:
            job.status = "error"
            job.current_step = f"Critical Error: {str(e)}"
            db.commit()
    finally:
        db.close()

@app.post("/api/presentations/generate", tags=["Generation"])
async def generate_presentation(
    req: PresentationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger a new generation job with real-time tracking.
    """
    dna = db.query(models.BrandVisualDna).filter(
        models.BrandVisualDna.source_filename == req.style_filename
    ).first()
    
    if not dna:
        raise HTTPException(status_code=404, detail="Visual DNA not found.")

    gen_job = models.GenerationJob(
        client_name=req.style_filename,
        brand_id=dna.brand_id,
        prompt=req.prompt,
        status="processing",
        current_step="Initializing neural synthesis...",
        progress=5
    )
    db.add(gen_job)
    db.commit()
    db.refresh(gen_job)

    timestamp = int(time.time())
    pptx_path = os.path.join(UPLOAD_DIR, f"presentation_{gen_job.id}_{timestamp}.pptx")
    
    background_tasks.add_task(task_generate_presentation, gen_job.id, req, pptx_path)

    return {
        "status": "accepted",
        "job_id": gen_job.id,
        "message": "Strategic generation initiated."
    }

@app.get("/api/generation/status/{job_id}", tags=["Generation"])
def get_generation_status(job_id: int, db: Session = Depends(get_db)):
    """
    Check the status of a generation job (v12.0).
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "download_url": f"/api/generation/download/{job.id}" if job.status == "completed" else None
    }

@app.get("/api/generation/download/{job_id}", tags=["Generation"])
def download_presentation(job_id: int, db: Session = Depends(get_db)):
    """
    Download the finalized PPTX.
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job or job.status != "completed" or not job.pptx_path:
        raise HTTPException(status_code=404, detail="File not ready or job not found.")
    
    return FileResponse(
        job.pptx_path,
        filename=os.path.basename(job.pptx_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

@app.get("/api/library/portfolios", tags=["Library"])
def get_library_portfolios(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Lista las generaciones exitosas (v12.0: Portfolio History).
    """
    query = db.query(models.GenerationJob).filter(models.GenerationJob.status == "completed")
    if brand_id:
        # Nota: En v12.0 esto requiere que el job tenga brand_id guardado.
        # Por ahora listamos todos para la marca o generales si es nulo.
        pass 
        
    jobs = query.order_by(models.GenerationJob.id.desc()).all()
    return [{
        "id": j.id,
        "pptx_path": j.pptx_path,
        "filename": os.path.basename(j.pptx_path) if j.pptx_path else f"Generation_{j.id}.pptx",
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "step": j.current_step
    } for j in jobs]

def _build_brand_context(dna: models.BrandVisualDna,
                          brand_essence: Optional[models.BrandArtisticEssence]) -> dict:
    """Construye un dict unificado de contexto de marca para el pipeline."""
    ctx = {
        "primary_color":    dna.primary_color,
        "secondary_color":  dna.secondary_color,
        "background_color": dna.background_color,
        "text_main_color":  dna.text_main_color,
        "accent_color":     dna.accent_color,
        "primary_font":     dna.primary_font,
        "secondary_font":   dna.secondary_font,
        "extracted_assets": dna.extracted_assets or [],
    }
    if brand_essence:
        ctx["slide_archetypes"]   = brand_essence.slide_archetypes or {}
        ctx["design_gestures"]    = brand_essence.design_gestures or {}
        ctx["composition_rules"]  = brand_essence.composition_rules or {}
        ctx["art_direction_note"] = brand_essence.art_direction_note or ""
    return ctx


# ──────────────────────────────────────────────
# LIBRARY ENDPOINTS (Bóveda de Activos)
# ──────────────────────────────────────────────

@app.get("/api/library/images", tags=["Library"])
def get_library_images(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista imágenes/assets filtrados por marca. Excluye embeddings por eficiencia (v12.0)."""
    query = db.query(
        models.BrandAsset.id,
        models.BrandAsset.brand_id,
        models.BrandAsset.local_path,
        models.BrandAsset.category,
        models.BrandAsset.tags,
        models.BrandAsset.manual_tags,
        models.BrandAsset.description,
        models.BrandAsset.is_public,
        models.BrandAsset.source_doc,
        models.BrandAsset.created_at
    )
    if brand_id:
        query = query.filter(models.BrandAsset.brand_id == brand_id)
    
    assets = query.all()
    # Mapear a diccionarios para mantener compatibilidad con el contrato del Frontend
    # El Frontend ya añade http://localhost:8000/ por su cuenta, así que enviamos solo la subruta uploads/
    return [
        {
            "id": a[0], "brand_id": a[1], 
            "local_path": f"uploads/{os.path.basename(a[2])}", 
            "category": a[3], "tags": a[4], "manual_tags": a[5],
            "description": a[6], "is_public": a[7], 
            "source_doc": a[8], "created_at": a[9]
        } for a in assets
    ]

@app.get("/api/library/blueprints", tags=["Library"])
def get_library_blueprints(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista estilos (DNA Visual) filtrados por marca."""
    query = db.query(models.BrandVisualDna)
    if brand_id:
        query = query.filter(models.BrandVisualDna.brand_id == brand_id)
    return query.all()

@app.get("/api/library/knowledge", tags=["Library"])
def get_library_knowledge(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lista documentos de conocimiento filtrados por marca."""
    sql = "SELECT DISTINCT source_filename, is_public, brand_id FROM corporate_knowledge"
    params = {}
    if brand_id:
        sql += " WHERE brand_id = :brand_id"
        params["brand_id"] = brand_id
    
    result = db.execute(text(sql), params)
    return [{"filename": row[0], "is_public": row[1], "brand_id": row[2]} for row in result]


# ──────────────────────────────────────────────
# ENDPOINTS — ADMIN
# ──────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "version": "11.0", "architecture": "clean"}


@app.delete("/api/admin/reset-db", tags=["Admin"])
def reset_database(db: Session = Depends(get_db)):
    """Limpia y RECONSTRUYE físicamente la base de datos para aplicar cambios de esquema."""
    try:
        # 1. Borrado físico de tablas para aplicar nuevos esquemas
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        # 2. Limpieza de archivos
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "reset_complete"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
