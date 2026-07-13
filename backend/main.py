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
from sqlalchemy.orm import Session, joinedload
import models
from database import SessionLocal, engine, Base, reconcile_additive_columns, get_db
from tasks import (
    celery_extract_full_brand_style,
    celery_ingest_knowledge,
    celery_extract_pure_assets,
    celery_generate_presentation,
    celery_resume_generation_pipeline
)
from services.core.brand_service import create_brand_logic, update_brand_logic
from auth.dependencies import (
    get_current_user,
    require_role,
    require_tenant_access,
    check_brand_tenant_access,
    check_job_tenant_access,
    tenant_brand_ids_filter,
)
import uuid
from datetime import datetime, date
from sqlalchemy import JSON

# ── PIPELINE SERVICES ──
from services.generation.content_engine import synthesize_strategic_content
from services.assets.asset_engine import orchestrate_assets
from services.rendering.layout_engine import apply_design_policy
from services.rendering.pptx_renderer import render_pptx_manifest

# ── INGESTION SERVICES (nuevos) ──
from services.ingestion.visual_dna_service import extract_visual_dna
from services.ingestion.artistic_essence_service import extract_artistic_essence

# ── INGESTION SERVICES (legacy RAG — sin cambios) ──
from services.ingestion.ingest_knowledge import ingest_document as ingest_rag

# Actualizar caché de fuentes por si se subieron fuentes personalizadas
print("[System] Updating font cache for LibreOffice...", flush=True)
os.system("fc-cache -f")

print("[System] PowerAI Engine v11.0 (Clean Architecture) IS LIVE.", flush=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from utils.seed import seed_data

Base.metadata.create_all(bind=engine)
# Capa de schema: tras crear tablas nuevas, poner al día las ya existentes con
# las columnas aditivas que el modelo declara y la BD desplegada aún no tiene.
# Evita que cada columna nueva rompa la ingesta/generación en bases viejas.
try:
    reconcile_additive_columns()
except Exception as e:
    print(f"  [System] Warning: Schema reconcile failed: {e}")
try:
    seed_data()
except Exception as e:
    print(f"  [System] Warning: Seeding failed: {e}")
try:
    from utils.seed_superadmin import seed_superadmin, seed_default_tenant
    seed_superadmin()
    seed_default_tenant()
except Exception as e:
    print(f"  [System] Warning: Superadmin/default tenant seeding failed: {e}")
try:
    from utils.seed_test_users import seed_test_users
    seed_test_users()
except Exception as e:
    print(f"  [System] Warning: Test user seeding failed: {e}")

# Alineaciones de datos (tercera capa, junto a esquema y config) — nunca bloquea el boot
try:
    from services.core.data_alignment_service import dispatch_pending_alignments
    dispatch_pending_alignments()
except Exception as e:
    print(f"  [System] Warning: Data alignment dispatch failed: {e}")


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

# Storage v1: SOLO el árbol público se sirve por HTTP. private/ y tmp/ jamás se montan.
from services.core.storage_service import PUBLIC_ROOT as STORAGE_PUBLIC_ROOT, cleanup_tmp
os.makedirs(STORAGE_PUBLIC_ROOT, exist_ok=True)
app.mount("/files", CORSStaticFiles(directory=STORAGE_PUBLIC_ROOT), name="files")
cleanup_tmp()  # housekeeping de temporales >24h (tolerante, nunca bloquea)

# Autenticación / Multi-tenant (B4-B5) — routers propios, no inline en este archivo.
from routers.auth import router as auth_router
from routers.users import router as users_router
from routers.template_merge import router as template_merge_router
from routers.collaborators import router as collaborators_router
from routers.reviews import router as reviews_router
from routers.portfolios import router as portfolios_router
from routers.departments import router as departments_router
from routers.analytics import router as analytics_router
from routers.badges import router as badges_router
from routers.config import router as config_router
from routers.prompt_favorites import router as prompt_favorites_router
from routers.tenants import router as tenants_router
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(template_merge_router)
app.include_router(collaborators_router)
app.include_router(reviews_router)
app.include_router(portfolios_router)
app.include_router(departments_router)
app.include_router(analytics_router)
app.include_router(badges_router)
app.include_router(config_router)
app.include_router(prompt_favorites_router)
app.include_router(tenants_router)


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
    interactive_mode: bool = False
    # Selección estructurada del compositor guiado (soporte-indicaciones), si el
    # frontend lo usó. Se persiste tal cual en el job — el backend no la interpreta,
    # `prompt` sigue siendo la única entrada real al pipeline.
    prompt_metadata: Optional[dict] = None


# ──────────────────────────────────────────────
# DB HELPER — importado de database.py (get_db), no redefinido acá.
# Antes de Autenticación/Multi-tenant (B4-B6) este archivo tenía su propia
# copia local de get_db(); al tener dos objetos de función distintos con el
# mismo comportamiento, un test que overridea uno no afecta al otro, y las
# nuevas dependencias de auth (auth/dependencies.py) usan la de database.py.
# ──────────────────────────────────────────────


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

def _serialize_brand(brand: models.Brand) -> dict:
    """Storage v1: logo_path servible real resuelto en lectura (nuevo → files/, legacy → uploads/)."""
    from services.core.storage_service import resolve as resolve_storage, public_url
    logo_url = None
    if brand.logo_path:
        physical = resolve_storage(brand.logo_path, brand_id=brand.id)
        url = public_url(physical) if physical else None
        logo_url = url.lstrip("/") if url else None
    return {
        "id": brand.id,
        "name": brand.name,
        "logo_path": logo_url,
        "about": brand.about,
        "core_value": brand.core_value,
        "tenant_id": brand.tenant_id,
        "tenant_name": brand.tenant.name if brand.tenant else None,
        "created_at": brand.created_at.isoformat() if brand.created_at else None,
    }


@app.get("/api/brands", tags=["Governance"])
def list_brands(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lista el Directorio Oficial de Marcas (scopeado al tenant del usuario; superadmin ve todas,
    o filtra por tenant_id si lo pasa explícito — mismo criterio que departments.py/users.py)."""
    query = db.query(models.Brand).options(joinedload(models.Brand.tenant))
    if current_user.role != models.UserRole.SUPERADMIN.value:
        query = query.filter(models.Brand.tenant_id == current_user.tenant_id)
    elif tenant_id is not None:
        query = query.filter(models.Brand.tenant_id == tenant_id)
    return [_serialize_brand(b) for b in query.all()]

@app.post("/api/brands", tags=["Governance"])
async def create_brand(
    name: str = Form(...),
    about: Optional[str] = Form(None),
    core_value: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    tenant_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Registra una nueva marca (Delegado a BrandService). Se asigna al tenant del usuario
    (admin/cliente); `tenant_id` explícito lo requiere un superadmin (mismo criterio que
    POST /api/admin/departments — sin esto la Brand queda "unaligned", invisible para el
    tenant que se buscaba armar)."""
    if current_user.role == models.UserRole.SUPERADMIN.value and tenant_id is None:
        raise HTTPException(status_code=422, detail="tenant_id is required for superadmin")

    existing = db.query(models.Brand).filter(models.Brand.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Brand already exists.")

    brand = await create_brand_logic(db, name, about, core_value, logo)
    if current_user.role == models.UserRole.SUPERADMIN.value:
        brand.tenant_id = tenant_id
    else:
        brand.tenant_id = current_user.tenant_id
    db.commit()
    db.refresh(brand)
    return _serialize_brand(brand)

@app.put("/api/brands/{brand_id}", tags=["Governance"])
async def update_brand(
    brand_id: int,
    name: str = Form(...),
    about: Optional[str] = Form(None),
    core_value: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_tenant_access)
):
    """Actualiza una marca (Delegado a BrandService)."""
    brand = await update_brand_logic(db, brand_id, name, about, core_value, logo)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")

    return _serialize_brand(brand)


@app.get("/api/footers", tags=["Governance"])
def list_footers(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista todas las configuraciones de footer."""
    is_enabled_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "is_footer_enabled").first()
    is_enabled = (is_enabled_config.value == "true") if is_enabled_config else True
    
    footers = db.query(models.FooterConfig).order_by(models.FooterConfig.created_at.desc()).all()
    return {
        "is_footer_enabled": is_enabled,
        "footers": footers
    }

@app.post("/api/footers", tags=["Governance"])
async def create_footer(
    id: Optional[int] = Form(None),
    name: str = Form(...),
    text: Optional[str] = Form(None),
    disclaimer: Optional[str] = Form(None),
    logo_light: Optional[UploadFile] = File(None),
    logo_dark: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Crea o actualiza una configuración de footer y procesa logos opcionales."""
    logo_light_path = None
    logo_dark_path = None
    
    if logo_light:
        try:
            safe_name = f"footer_light_{int(time.time())}_{logo_light.filename}"
            path = os.path.join(UPLOAD_DIR, safe_name)
            content = await logo_light.read()
            with open(path, "wb") as f:
                f.write(content)
            logo_light_path = f"uploads/{safe_name}"
        except Exception as e:
            print(f"  [FooterService] Error saving logo_light: {e}")
            
    if logo_dark:
        try:
            safe_name = f"footer_dark_{int(time.time())}_{logo_dark.filename}"
            path = os.path.join(UPLOAD_DIR, safe_name)
            content = await logo_dark.read()
            with open(path, "wb") as f:
                f.write(content)
            logo_dark_path = f"uploads/{safe_name}"
        except Exception as e:
            print(f"  [FooterService] Error saving logo_dark: {e}")

    if id is not None:
        footer = db.query(models.FooterConfig).filter(models.FooterConfig.id == id).first()
        if not footer:
            raise HTTPException(status_code=404, detail="Footer configuration not found")
        footer.name = name
        footer.text = text
        footer.disclaimer = disclaimer
        if logo_light_path:
            footer.logo_light_path = logo_light_path
        if logo_dark_path:
            footer.logo_dark_path = logo_dark_path
        db.commit()
        db.refresh(footer)
        return footer

    # Si es el primer footer, lo dejamos seleccionado por defecto
    first_count = db.query(models.FooterConfig).count()
    should_select = (first_count == 0)

    footer = models.FooterConfig(
        name=name,
        text=text,
        disclaimer=disclaimer,
        logo_light_path=logo_light_path,
        logo_dark_path=logo_dark_path,
        is_active=True,
        is_selected=should_select
    )
    db.add(footer)
    db.commit()
    db.refresh(footer)
    return footer

@app.put("/api/footers/{footer_id}/select", tags=["Governance"])
def select_footer(footer_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Selecciona un footer específico (desmarcando los demás)."""
    # Si footer_id es 0, deseleccionamos todos (sin footer)
    if footer_id == 0:
        db.query(models.FooterConfig).update({models.FooterConfig.is_selected: False})
        db.commit()
        return {"status": "success", "selected_id": None}
        
    footer = db.query(models.FooterConfig).get(footer_id)
    if not footer:
        raise HTTPException(status_code=404, detail="Footer configuration not found")
        
    db.query(models.FooterConfig).update({models.FooterConfig.is_selected: False})
    footer.is_selected = True
    db.commit()
    db.refresh(footer)
    return footer

@app.delete("/api/footers/{footer_id}", tags=["Governance"])
def delete_footer(footer_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Elimina una configuración de footer."""
    footer = db.query(models.FooterConfig).get(footer_id)
    if not footer:
        raise HTTPException(status_code=404, detail="Footer configuration not found")
        
    db.delete(footer)
    db.commit()
    return {"status": "success", "message": "Footer deleted"}

@app.put("/api/footers/toggle", tags=["Governance"])
def toggle_footer_global(enabled: bool, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Habilita o deshabilita globalmente el footer."""
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "is_footer_enabled").first()
    val_str = "true" if enabled else "false"
    if cfg:
        cfg.value = val_str
    else:
        cfg = models.SystemConfig(key="is_footer_enabled", value=val_str, description="Global footer activation toggle")
        db.add(cfg)
    db.commit()
    return {"status": "success", "is_footer_enabled": enabled}


# ──────────────────────────────────────────────
# WORKER TASKS (background)
# ──────────────────────────────────────────────
@app.get("/api/library/images", tags=["Library"])
def list_images(brand_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista activos excluyendo datos binarios/vectores para evitar errores de serialización."""
    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)
    query = db.query(models.BrandAsset)
    if brand_id:
        query = query.filter(models.BrandAsset.brand_id == brand_id)
    else:
        tenant_ids = tenant_brand_ids_filter(db, current_user)
        if tenant_ids is not None:
            query = query.filter(models.BrandAsset.brand_id.in_(tenant_ids))

    assets = query.all()
    # v21.5: Conversión manual para evitar fallos con pgvector/embeddings
    from services.core.storage_service import resolve as resolve_storage, public_url
    safe_assets = []
    for a in assets:
        # Storage v1: URL servible real (jerarquía nueva → /files, legacy → /uploads)
        filename = os.path.basename(a.local_path)
        physical = resolve_storage(a.local_path, brand_id=a.brand_id)
        url = public_url(physical) if physical else None
        safe_assets.append({
            "id": a.id,
            "brand_id": a.brand_id,
            "category": a.category,
            "local_path": url.lstrip("/") if url else f"uploads/{filename}",
            "tags": a.tags,
            "description": a.description,
            "source_doc": a.source_doc,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })
    return safe_assets

@app.get("/api/generation/status/{job_id}", tags=["Generation"])
def get_generation_status(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    return {
        "id": job.id, "status": job.status, "progress": job.progress,
        "current_step": job.current_step,
        "qa_forced": bool(job.qa_forced),
        "download_url": f"/api/generation/download/{job.id}" if job.status == models.GenerationJobStatus.COMPLETED else None
    }

@app.get("/api/generation/download/{job_id}", tags=["Generation"])
def download_presentation(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    if job.status != models.GenerationJobStatus.COMPLETED: raise HTTPException(status_code=404, detail="File not ready.")
    from services.core.storage_service import resolve as resolve_storage
    physical = resolve_storage(job.pptx_path)
    if not physical: raise HTTPException(status_code=404, detail="File not found on disk.")
    return FileResponse(physical, filename=os.path.basename(job.pptx_path))


# ──────────────────────────────────────────────
# ENDPOINTS — INGESTION (v11.0)
# ──────────────────────────────────────────────

@app.post("/api/brand/upload", tags=["Ingestion"])
async def upload_asset(
    ingestion_type: str = Form(...),
    visibility_scope: str = Form("exclusive"),
    brand_id: Optional[int] = Form(None),
    manual_tags: Optional[str] = Form(None),
    document_type: str = Form("company_knowledge"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Punto de entrada para la ingesta de conocimiento y estilo."""
    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)
    job_key = file.filename
    safe_tags = [t.strip() for t in manual_tags.split(",")] if manual_tags else []

    # Guardar el documento fuente en el árbol PRIVADO de la marca (storage v1)
    from services.core.storage_service import brand_sources_dir
    file_path = os.path.join(brand_sources_dir(brand_id), job_key)
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
            status=models.IngestionJobStatus.PROCESSING,
            progress=0,
            visibility_scope=visibility_scope
        )
        db.add(job)
    else:
        job.status = models.IngestionJobStatus.PROCESSING
        job.progress = 0
        job.visibility_scope = visibility_scope
    
    db.commit()
    db.close()

    # Disparar tarea en segundo plano (vía Celery/Redis)
    if ingestion_type == "brand_style":
        celery_extract_full_brand_style.delay(job_key, file_path, job_key, visibility_scope, brand_id, safe_tags)
    elif ingestion_type == "knowledge":
        celery_ingest_knowledge.delay(job_key, file_path, job_key, brand_id, visibility_scope, document_type)
    elif ingestion_type == "pure_assets":
        celery_extract_pure_assets.delay(job_key, file_path, job_key, visibility_scope, brand_id, safe_tags)

    return {"status": models.IngestionJobStatus.PROCESSING, "job_key": job_key}

@app.get("/api/ingestion/status/{job_key}", tags=["Ingestion"])
def get_ingestion_status(job_key: str, ingestion_type: str = "brand_style", db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
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
def list_library_blueprints(brand_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista los blueprints de estilo en la librería (usando BrandVisualDna)."""
    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)
    query = db.query(models.BrandVisualDna)
    if brand_id:
        query = query.filter(models.BrandVisualDna.brand_id == brand_id)
    else:
        tenant_ids = tenant_brand_ids_filter(db, current_user)
        if tenant_ids is not None:
            query = query.filter(models.BrandVisualDna.brand_id.in_(tenant_ids))

    blueprints = query.all()
    return [{"id": b.id, "source_filename": b.source_filename, "brand_id": b.brand_id} for b in blueprints]

@app.get("/api/library/knowledge", tags=["Library"])
def list_library_knowledge(brand_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista los documentos de conocimiento procesados en la librería, agrupados por archivo."""
    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)
    # Usamos DISTINCT ON o GROUP BY para devolver solo una entrada por archivo
    query = db.query(
        models.CorporateKnowledge.source_filename,
        models.CorporateKnowledge.brand_id,
        models.CorporateKnowledge.is_public
    ).distinct(models.CorporateKnowledge.source_filename)

    if brand_id:
        query = query.filter(models.CorporateKnowledge.brand_id == brand_id)
    else:
        tenant_ids = tenant_brand_ids_filter(db, current_user)
        if tenant_ids is not None:
            query = query.filter(models.CorporateKnowledge.brand_id.in_(tenant_ids))

    knowledge = query.all()
    return [{
        "id": i, # Usamos el índice como ID temporal para el frontend
        "filename": k.source_filename, 
        "is_public": k.is_public == 1,
        "brand_id": k.brand_id
    } for i, k in enumerate(knowledge)]

from services.core.portfolio_service import portfolio_display_name as _portfolio_display_name
from utils.sql import escape_like as _escape_like  # compartido con routers/template_merge.py


@app.get("/api/library/portfolios", tags=["Library"])
def list_library_portfolios(
    brand_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lista paginada de presentaciones generadas (más reciente primero)."""
    from sqlalchemy import or_

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be earlier than or equal to date_to.")

    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)

    query = db.query(models.GenerationJob).filter(models.GenerationJob.status == models.GenerationJobStatus.COMPLETED)
    if brand_id:
        query = query.filter(models.GenerationJob.brand_id == brand_id)
    else:
        tenant_ids = tenant_brand_ids_filter(db, current_user)
        if tenant_ids is not None:
            query = query.filter(models.GenerationJob.brand_id.in_(tenant_ids))
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.filter(or_(
            models.GenerationJob.display_name.ilike(pattern, escape="\\"),
            models.GenerationJob.pptx_path.ilike(pattern, escape="\\"),
        ))
    if date_from:
        query = query.filter(models.GenerationJob.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        # Inclusivo: todo el día de date_to
        query = query.filter(models.GenerationJob.created_at <= datetime.combine(date_to, datetime.max.time()))

    total = query.count()
    jobs = (query.order_by(models.GenerationJob.created_at.desc())
                 .offset((page - 1) * page_size)
                 .limit(page_size)
                 .all())

    # Rating del team (PresentationReview): promedio + conteo por job, batcheado a
    # la página. Mismo criterio que GET /api/presentations/{id}/reviews — 'flagged'
    # cuenta (auto-tag pendiente), solo 'hidden' (acción de admin) queda fuera.
    aggregates_dict = {}
    my_reviews_dict = {}
    if jobs:
        job_ids = [j.id for j in jobs]
        visible_reviews = db.query(
            models.PresentationReview.job_id,
            func.avg(models.PresentationReview.rating),
            func.count(models.PresentationReview.id),
        ).filter(
            models.PresentationReview.job_id.in_(job_ids),
            models.PresentationReview.is_deleted == False,
            models.PresentationReview.moderation_status != "hidden",
        ).group_by(models.PresentationReview.job_id).all()
        aggregates_dict = {job_id: {"avg": round(float(avg), 2), "count": count} for job_id, avg, count in visible_reviews}

        # La review propia (aunque esté hidden) — habilita el "RATE IT" de la tarjeta
        my_reviews = db.query(models.PresentationReview).filter(
            models.PresentationReview.job_id.in_(job_ids),
            models.PresentationReview.user_id == current_user.id,
            models.PresentationReview.is_deleted == False,
        ).all()
        my_reviews_dict = {r.job_id: r for r in my_reviews}

    items = [{
        "id": j.id,
        "filename": os.path.basename(j.pptx_path) if j.pptx_path else f"Presentation_{j.id}.pptx",
        "display_name": _portfolio_display_name(j),
        "created_at": j.created_at,
        "brand_id": j.brand_id,
        "rating_average": aggregates_dict.get(j.id, {}).get("avg"),
        "rating_count": aggregates_dict.get(j.id, {}).get("count", 0),
        "my_rating": my_reviews_dict[j.id].rating if j.id in my_reviews_dict else None,
        "has_prompt": bool(j.prompt),
    } for j in jobs]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


class PortfolioRenameRequest(BaseModel):
    display_name: str


@app.patch("/api/library/portfolios/{job_id}", tags=["Library"])
def rename_library_portfolio(job_id: int, payload: PortfolioRenameRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Renombra la etiqueta visible de una presentación (no toca el archivo físico)."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    name = (payload.display_name or "").strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=422, detail="display_name must be between 1 and 120 characters.")

    job.display_name = name
    db.commit()
    return {"id": job.id, "display_name": job.display_name,
            "filename": os.path.basename(job.pptx_path) if job.pptx_path else f"Presentation_{job.id}.pptx"}


@app.delete("/api/library/portfolios/{job_id}", tags=["Library"])
def delete_library_portfolio(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """
    Elimina una presentación: job + slides (cascade) + feedback + decisiones de
    arte + archivo físico (tolerante). Solo estados terminales — un job en
    proceso devolvería el pipeline Celery escribiendo sobre un job borrado.
    """
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    if job.status not in [models.GenerationJobStatus.COMPLETED, models.GenerationJobStatus.ERROR]:
        raise HTTPException(status_code=409, detail=f"Cannot delete a presentation while its pipeline is active (status: {job.status}).")

    pptx_path = job.pptx_path

    db.query(models.GenerationJobFeedback).filter(
        models.GenerationJobFeedback.job_id == job_id
    ).delete(synchronize_session=False)
    db.query(models.ArtDirectorDecision).filter(
        models.ArtDirectorDecision.job_id == job_id
    ).delete(synchronize_session=False)
    # PromptFavorite.source_job_id es informativo, no una referencia viva —
    # sin esto, el FK revienta con IntegrityError al borrar el job de origen.
    db.query(models.PromptFavorite).filter(
        models.PromptFavorite.source_job_id == job_id
    ).update({"source_job_id": None}, synchronize_session=False)
    db.delete(job)  # PresentationSlide cae por cascade="all, delete-orphan"
    db.commit()

    # Limpieza física DESPUÉS del commit, tolerante a ausencia
    if pptx_path:
        try:
            from services.core.storage_service import resolve as resolve_storage
            physical = resolve_storage(pptx_path)
            if physical and os.path.exists(physical):
                os.remove(physical)
        except Exception as file_err:
            logger.warning(f"[Portfolios] Job {job_id} deleted from DB but file cleanup failed: {file_err}")

    # Storage v1: si el job tiene carpeta propia, eliminarla completa
    try:
        import shutil
        from services.core.storage_service import PUBLIC_ROOT as _public_root
        job_folder = os.path.join(_public_root, "jobs", str(job_id))
        if os.path.isdir(job_folder):
            shutil.rmtree(job_folder, ignore_errors=True)
    except Exception as dir_err:
        logger.warning(f"[Portfolios] Job {job_id} folder cleanup failed: {dir_err}")

    return {"deleted": True, "id": job_id}

# ──────────────────────────────────────────────
# ENDPOINTS — GENERATION PIPELINE (Synthesis Studio)
# ──────────────────────────────────────────────

@app.get("/api/available-styles", tags=["Generation"])
def list_available_styles(brand_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista los blueprints de estilo con lógica de visibilidad escalonada."""
    query = db.query(models.BrandVisualDna)

    if current_user.role == models.UserRole.SUPERADMIN.value:
        # superadmin: ver todo (reemplaza el sentinel legacy brand_id=-1,
        # que dejaba "ver todo" a cualquier caller sin chequeo de rol real)
        pass
    elif brand_id is None:
        # PUBLIC: Ver solo lo público
        query = query.filter(models.BrandVisualDna.is_public == 1)
    else:
        # BRAND: Ver lo de la marca (propia del tenant) + lo público
        check_brand_tenant_access(db, current_user, brand_id)
        query = query.filter((models.BrandVisualDna.brand_id == brand_id) | (models.BrandVisualDna.is_public == 1))

    blueprints = query.all()
    return {"styles": [{"id": b.id, "filename": b.source_filename} for b in blueprints]}

@app.get("/api/available-knowledge", tags=["Generation"])
def list_available_knowledge(brand_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista los paquetes de conocimiento con lógica de visibilidad escalonada."""
    query = db.query(models.CorporateKnowledge.source_filename).distinct()

    if current_user.role == models.UserRole.SUPERADMIN.value:
        # superadmin: ver todo (reemplaza el sentinel legacy brand_id=-1)
        pass
    elif brand_id is None:
        # PUBLIC: Ver solo lo público
        query = query.filter(models.CorporateKnowledge.is_public == 1)
    else:
        # BRAND: Ver lo de la marca (propia del tenant) + lo público
        check_brand_tenant_access(db, current_user, brand_id)
        query = query.filter((models.CorporateKnowledge.brand_id == brand_id) | (models.CorporateKnowledge.is_public == 1))

    sources = query.all()
    return {"sources": [s[0] for s in sources]}

@app.get("/api/available-dialects", tags=["Generation"])
def list_dialects(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista las regiones/idiomas disponibles (antes llamados dialectos)."""
    languages = db.query(models.Language).filter(models.Language.is_active == True).all()
    return [{"id": l.id, "code": l.code, "name": l.name} for l in languages]

@app.post("/api/presentations/generate", tags=["Generation"])
async def generate_presentation(
    request: PresentationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Dispara el motor de síntesis para generar una nueva presentación."""
    if request.brand_id:
        check_brand_tenant_access(db, current_user, request.brand_id)
    # Buscar el ID del Style (Blueprint) para la jerarquía de activos v23.0
    style_dna = db.query(models.BrandVisualDna).filter(
        models.BrandVisualDna.source_filename == request.style_filename
    ).first()
    
    job = models.GenerationJob(
        brand_id=request.brand_id,
        style_id=style_dna.id if style_dna else None,
        status=models.GenerationJobStatus.PENDING,
        progress=0,
        current_step="Initializing isolated synthesis engine v23.0...",
        allow_ai_images=request.allow_ai_images,
        owner_id=current_user.id,
        prompt_metadata=request.prompt_metadata,
        prompt=request.prompt,
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
        "tier": request.tier,
        "interactive_mode": request.interactive_mode
    }
    
    celery_generate_presentation.delay(
        job.id,
        req_payload
    )

    return {"job_id": job.id, "status": models.GenerationJobStatus.PENDING}

class SlideUpdate(BaseModel):
    title: Optional[str] = None
    content_json: Optional[dict] = None
    layout_slug: Optional[str] = None
    assigned_image: Optional[str] = None

class ResumeRequest(BaseModel):
    tier: Optional[str] = "standard"
    output_format: Optional[str] = "pptx"

@app.get("/api/presentations/{job_id}/slides", tags=["Generation"])
def get_presentation_slides(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Retorna los slides asociados a un job de generación."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)


    slides = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id
    ).order_by(models.PresentationSlide.slide_number.asc()).all()
    return slides

@app.put("/api/presentations/{job_id}/slides/{slide_id}", tags=["Generation"])
def update_presentation_slide(job_id: int, slide_id: int, request: SlideUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Permite a un usuario editar el contenido de un slide antes de reanudar el diseño."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    slide = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id,
        models.PresentationSlide.id == slide_id
    ).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    if request.title is not None:
        slide.title = request.title
    if request.content_json is not None:
        slide.content_json = request.content_json
    if request.layout_slug is not None:
        slide.layout_slug = request.layout_slug
    if request.assigned_image is not None:
        slide.assigned_image = request.assigned_image
    
    # Marcamos el slide de vuelta en CONTENT_READY para obligar al arquitecto a procesarlo
    slide.status = models.PresentationSlideStatus.CONTENT_READY

    # Analítica de uso (reviews-analitica-colaboracion, ítem 5): cada edición cuenta.
    db.add(models.UserActivityEvent(job_id=job_id, user_id=current_user.id, event_type="slide_edit", value=1))

    db.commit()
    db.refresh(slide)
    return slide

@app.post("/api/presentations/{job_id}/resume", tags=["Generation"])
def resume_presentation(job_id: int, request: ResumeRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Reanuda un job que estaba pausado en el checkpoint de revisión humana (CONTENT_READY)."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    if job.status != models.GenerationJobStatus.CONTENT_READY:
        raise HTTPException(status_code=400, detail=f"Job cannot be resumed from status: {job.status}")
    
    # Obtener el style_filename a partir del style_id del job
    style_dna = db.query(models.BrandVisualDna).get(job.style_id) if job.style_id else None
    style_filename = style_dna.source_filename if style_dna else ""
    
    req_payload = {
        "style_filename": style_filename,
        "knowledge_filename": "",
        "prompt": job.prompt or "",
        "region": "Global",
        "allow_ai_images": job.allow_ai_images or False,
        "output_format": request.output_format,
        "tier": request.tier
    }
    
    # Disparar la tarea Celery de reanudación
    celery_resume_generation_pipeline.delay(
        job.id,
        req_payload
    )

    return {"job_id": job.id, "status": models.GenerationJobStatus.PROCESSING}


class FeedbackSubmitRequest(BaseModel):
    question_key: str = "presentation_satisfaction"
    rating: int
    comment: Optional[str] = None


@app.post("/api/presentations/{job_id}/feedback", tags=["Generation"])
def submit_presentation_feedback(job_id: int, request: FeedbackSubmitRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Guarda o actualiza la calificación y observaciones del usuario para una diapositiva/job."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    if request.rating < 1 or request.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    # Obtener o crear la pregunta
    question = db.query(models.SurveyQuestion).filter(models.SurveyQuestion.key == request.question_key).first()
    if not question:
        question = models.SurveyQuestion(
            key=request.question_key,
            question_text=request.question_key.replace("_", " ").capitalize() + "?",
            question_type="stars"
        )
        db.add(question)
        db.flush()

    # Buscar feedback existente para este job y pregunta
    feedback = db.query(models.GenerationJobFeedback).filter(
        models.GenerationJobFeedback.job_id == job_id,
        models.GenerationJobFeedback.question_id == question.id
    ).first()

    if feedback:
        feedback.rating = request.rating
        feedback.comment = request.comment
    else:
        feedback = models.GenerationJobFeedback(
            job_id=job_id,
            question_id=question.id,
            rating=request.rating,
            comment=request.comment
        )
        db.add(feedback)

    db.commit()
    return {"status": "success", "job_id": job_id, "rating": request.rating, "comment": request.comment}


@app.get("/api/presentations/{job_id}/feedback", tags=["Generation"])
def get_presentation_feedback(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Retorna todas las calificaciones y comentarios asociados a un job."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    feedbacks = db.query(models.GenerationJobFeedback).filter(
        models.GenerationJobFeedback.job_id == job_id
    ).all()
    
    return [
        {
            "question_key": f.question.key,
            "question_text": f.question.question_text,
            "rating": f.rating,
            "comment": f.comment,
            "created_at": f.created_at
        }
        for f in feedbacks
    ]

@app.get("/api/admin/metrics", tags=["Admin"])
def get_performance_metrics(limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(require_role(models.UserRole.SUPERADMIN.value))):
    """
    Exposes the recorded performance metrics from the database.
    Returns the last `limit` recorded metrics.
    """
    try:
        metrics = db.query(models.PerformanceMetric).order_by(models.PerformanceMetric.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": m.id,
                "event_name": m.event_name,
                "duration_seconds": m.duration_seconds,
                "metadata": m.metadata_json or {},
                "timestamp": m.timestamp.isoformat() + "Z"
            }
            for m in metrics
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query metrics: {e}")

@app.delete("/api/admin/reset-db", tags=["Admin"])
def reset_database(admin_token: str = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_role(models.UserRole.SUPERADMIN.value))):
    """HARD RESET: Limpia toda la base de datos, borra archivos temporales y vuelve a sembrar las configuraciones."""
    from fastapi import HTTPException
    import os
    import shutil
    
    expected_token = os.getenv("ADMIN_TOKEN")
    if expected_token and admin_token != expected_token:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing admin token")
        
    from database import engine, Base
    
    try:
        # Drop and recreate all tables
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        # Clean uploads directory
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete upload file {file_path}: {e}")

        # Clean outputs directory
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete output file {file_path}: {e}")
        
        # Re-populate configs, then the superadmin + base tenant — otherwise the
        # very superadmin who called this endpoint would be wiped out along with
        # everything else, locking everyone out until someone reseeds by hand.
        from utils.seed import seed_data
        from utils.seed_superadmin import seed_superadmin, seed_default_tenant
        seed_data()
        seed_superadmin()
        seed_default_tenant()

        return {"status": "success", "message": "Database and temporary files reset and seeded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
