"""
brand_service.py — PowerAI
Servicio de gestión de marcas (v21.0).
Encapsula la creación y actualización de perfiles de marca.
"""
import os
import time
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import UploadFile
import models
from services.assets.asset_library_service import register_asset

UPLOAD_DIR = "uploads"

async def create_brand_logic(db: Session, name: str, about: Optional[str], core_value: Optional[str], logo: Optional[UploadFile] = None):
    """Lógica integral: Crea marca, guarda logo físicamente y lo registra con IA."""
    # 1. Registro Base
    new_brand = models.Brand(name=name, about=about, core_value=core_value)
    db.add(new_brand)
    db.commit()
    db.refresh(new_brand)

    # 2. Procesamiento de Logo (IA)
    if logo:
        try:
            safe_name = f"logo_{int(time.time())}_{logo.filename}"
            temp_path = os.path.join(UPLOAD_DIR, safe_name)
            
            # Guardado físico
            content = await logo.read()
            with open(temp_path, "wb") as f:
                f.write(content)
            
            # Asignar ruta a la base de datos PRIMERO
            new_brand.logo_path = f"uploads/{safe_name}"
            db.commit()
            
            # Registro en Biblioteca (IA) - Separado para que un error no borre el logo
            try:
                register_asset(
                    db, 
                    brand_id=new_brand.id, 
                    file_path=temp_path, 
                    category="logo", 
                    source_doc=f"Initial Brand Identity: {name}",
                    manual_tags=["official-logo", "identity"],
                    force_tagging=True
                )
                db.commit() # ¡CRÍTICO! Commit para guardar el asset en la DB
            except Exception as ai_e:
                db.rollback() # Limpiar la transacción si falló la IA
                print(f"  [BrandService] Advertencia: Logo guardado pero falló el análisis IA: {ai_e}")
                
        except Exception as e:
            print(f"  [BrandService] Error crítico al guardar archivo: {e}")

    return new_brand

async def update_brand_logic(db: Session, brand_id: int, name: str, about: Optional[str], core_value: Optional[str], logo: Optional[UploadFile] = None):
    """Lógica integral: Actualiza marca y procesa nuevo logo si existe."""
    brand = db.query(models.Brand).get(brand_id)
    if not brand: return None
    
    brand.name = name
    brand.about = about
    brand.core_value = core_value
    
    if logo:
        try:
            safe_name = f"logo_{int(time.time())}_{logo.filename}"
            temp_path = os.path.join(UPLOAD_DIR, safe_name)
            content = await logo.read()
            with open(temp_path, "wb") as f: f.write(content)
            
            brand.logo_path = f"uploads/{safe_name}"
            db.commit()
            
            try:
                register_asset(db, brand_id=brand.id, file_path=temp_path, category="logo", source_doc=f"Brand Update: {name}", force_tagging=True)
                db.commit() # ¡CRÍTICO! Commit para guardar el asset
            except Exception as ai_e:
                db.rollback() # Limpiar la transacción si falló la IA
                print(f"  [BrandService] Advertencia: Logo actualizado pero falló el análisis IA: {ai_e}")
                
        except Exception as e:
            print(f"  [BrandService] Error crítico al actualizar archivo de logo: {e}")
            
    db.commit()
    db.refresh(brand)
    return brand
