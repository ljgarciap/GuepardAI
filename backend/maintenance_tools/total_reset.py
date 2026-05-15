import os
import shutil
from sqlalchemy import create_engine, text
from database import Base, engine
import models
import subprocess

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://root:root@localhost:5432/ai_db")
engine = create_engine(DATABASE_URL)

def total_reset():
    print("\n🚀 [TOTAL RESET] Iniciando limpieza profunda del ambiente...")
    
    # 1. Limpiar Base de Datos (Drop all)
    with engine.connect() as conn:
        print("   [+] Eliminando todas las tablas existentes...")
        tables = [
            "brand_visual_dna", "brand_artistic_essence", "ingestion_jobs", 
            "generation_jobs", "corporate_knowledge", "brand_styles", 
            "presentation_slides", "brand_assets", "brands", "languages", "system_configs"
        ]
        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
            except Exception as e:
                print(f"       (!) Error al borrar {table}: {e}")
        conn.commit()

    # 2. Recrear Tablas
    print("   [+] Recreando esquema de base de datos...")
    models.Base.metadata.create_all(bind=engine)
    
    # 3. Asegurar pgvector
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()

    # 4. Ejecutar Seed (Configuraciones y Public Library)
    print("   [+] Ejecutando seed de configuraciones y marcas maestras...")
    try:
        # Corregido: Usar el binario del venv y PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = ".:" + env.get("PYTHONPATH", "")
        subprocess.run(["./venv/bin/python3", "seed.py"], check=True, env=env)
    except Exception as e:
        print(f"       (!) Error al ejecutar seed.py: {e}")

    # 5. Limpiar carpeta Uploads
    upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
    if os.path.exists(upload_dir):
        print(f"   [+] Vaciando carpeta de archivos: {upload_dir}")
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"       (!) No se pudo borrar {file_path}: {e}")
    
    # 6. Limpiar Logs
    log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server.log"))
    if os.path.exists(log_file):
        print(f"   [+] Vaciando archivo de logs: {log_file}")
        with open(log_file, "w") as f:
            f.write(f"--- LOG RESET AT {os.uname().nodename} ---\n")

    print("\n✨ [SUCCESS] Ambiente 100% limpio y listo para nuevas pruebas.\n")

if __name__ == "__main__":
    total_reset()
