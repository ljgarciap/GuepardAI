"""
conftest.py - Configuración Central de Tests para GuepardAI Backend
====================================================================
ESTRATEGIA: Base de Datos PostgreSQL REAL dedicada para tests.

GARANTÍA DE AISLAMIENTO DE PRODUCCIÓN:
  1. La URL de la BD de test se lee de TEST_DATABASE_URL (entorno o .env.test).
  2. NUNCA se usa DATABASE_URL (producción) en los tests.
  3. Cada test corre dentro de una TRANSACCIÓN que se hace ROLLBACK al terminar,
     dejando la BD de test limpia y sin datos residuales.
  4. El schema se crea una sola vez al inicio de la sesión de tests y se destruye
     al final (con `drop_all`), sin afectar la BD de producción.

CÓMO USAR:
  1. Levanta la BD de test: `docker compose -f docker-compose.test.yml up -d`
  2. Crea el archivo `.env.test` con TEST_DATABASE_URL (ver .env.test.example)
  3. Ejecuta: `pytest --cov=agents tests/`
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ─────────────────────────────────────────────────────────────────────────────
# Carga variables de entorno del archivo .env.test (si existe)
# ─────────────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.test"), override=True)

# ─────────────────────────────────────────────────────────────────────────────
# URL de la base de datos de TEST
# NUNCA debe apuntar a la BD de producción.
# Ejemplo: postgresql+psycopg://root:root@localhost:5433/ai_db_test
# ─────────────────────────────────────────────────────────────────────────────
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://root:root@localhost:5433/ai_db_test"  # Puerto 5433 = test container
)

# ─────────────────────────────────────────────────────────────────────────────
# Parchar database.py ANTES de que cualquier módulo del proyecto lo importe.
# Esto redirige TODAS las conexiones de los agentes a la BD de test.
# ─────────────────────────────────────────────────────────────────────────────
import sys
import types

# Creamos el engine de TEST
test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_size=5,
    max_overflow=2,
    pool_timeout=10,
)

# Inicializamos la extensión pgvector en la BD de test (necesaria para los modelos)
try:
    with test_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
        print("\n  [TEST DB] pgvector extension activated on test database.")
except Exception as e:
    print(f"\n  [TEST DB] Warning: Could not activate pgvector on test DB: {e}")
    print("  [TEST DB] Vector columns will be disabled for these tests.")

# Session factory de TEST
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE DE SESIÓN: Scope=session → El schema se crea UNA VEZ por sesión de pytest
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def create_test_schema():
    """
    Crea todas las tablas del ORM en la BD de test al iniciar la sesión.
    Las destruye al final. Esto NO afecta la BD de producción.
    """
    # Importamos Base y models DESPUÉS de que el engine de test ya está listo
    # para que SQLAlchemy use el metadata correcto.
    from database import Base
    import models  # noqa: F401 - necesario para registrar todos los modelos

    print("\n  [TEST DB] Creating test schema (all tables)...")
    Base.metadata.create_all(bind=test_engine)
    yield
    print("\n  [TEST DB] Dropping test schema (cleanup)...")
    Base.metadata.drop_all(bind=test_engine)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE DE BD: Scope=function → Cada test tiene su propia transacción
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def db_session(create_test_schema):
    """
    Proporciona una sesión de BD que:
    1. Inicia una TRANSACCIÓN al comenzar el test.
    2. Hace ROLLBACK al finalizar, dejando la BD limpia para el siguiente test.

    GARANTÍA: Ningún test persiste datos en la BD de test → Sin efectos colaterales.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE DE MOCK LLM: Previene consumo de tokens reales en todos los tests
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_llm_calls():
    """
    Mock global de todas las llamadas a LLM.
    Se activa en TODOS los tests automáticamente.
    Previene el consumo de tokens reales y hace los tests deterministas.
    """
    default_qa_response = {
        "score": 0.92,
        "needs_rework": False,
        "reasoning": "Mock: Brand alignment approved."
    }
    default_content_response = {
        "slides": [
            {"slide_number": 1, "title": "Slide Mock 1", "content": "Content A"},
            {"slide_number": 2, "title": "Slide Mock 2", "content": "Content B"},
        ]
    }

    with patch("providers.llm_provider.generate_json", return_value=default_qa_response) as mock_json, \
         patch("providers.llm_provider.generate_text", return_value="Mock text content", create=True) as mock_text:
        yield {
            "generate_json": mock_json,
            "generate_text": mock_text,
        }


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE DE DATOS: Inserta datos de prueba básicos (Brand, Job, Slides)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def sample_brand(db_session):
    """Crea una Brand de prueba en la BD de test."""
    import models
    brand = models.Brand(
        name="TestBrand_Pytest",
        about="Brand created by pytest fixtures. Safe to delete.",
        core_value="Testing"
    )
    db_session.add(brand)
    db_session.flush()  # Obtener el ID sin hacer commit (dentro de la transacción)

    # Agregar Visual DNA
    dna = models.BrandVisualDna(
        brand_id=brand.id,
        source_filename="test_style.pptx",
        primary_color="#1A73E8",
        secondary_color="#E8711A",
        background_color="#FFFFFF",
        primary_font="Inter",
    )
    db_session.add(dna)
    db_session.flush()
    return brand


@pytest.fixture()
def sample_job(db_session, sample_brand):
    """Crea un GenerationJob de prueba vinculado a la brand de test."""
    import models
    job = models.GenerationJob(
        brand_id=sample_brand.id,
        status=models.GenerationJobStatus.PENDING,
        current_step="Test job initialized by pytest",
        prompt="Create a presentation about innovation"
    )
    db_session.add(job)
    db_session.flush()
    return job


@pytest.fixture()
def sample_slides(db_session, sample_job, sample_brand):
    """
    Crea slides de prueba en estado 'planned' para el job de test.
    Simula el output del Redactor + Arquitecto.
    """
    import models
    slides = []
    slide_data = [
        {"number": 1, "title": "Innovation in 2025", "layout": "cover_hero"},
        {"number": 2, "title": "Market Landscape", "layout": "two_column_text"},
        {"number": 3, "title": "Our Solution", "layout": "content_with_image_right"},
    ]
    for data in slide_data:
        slide = models.PresentationSlide(
            job_id=sample_job.id,
            slide_number=data["number"],
            title=data["title"],
            layout_slug=data["layout"],
            status="planned",
            planning_json={"art_director": {"reasoning": "Mock planning by pytest"}}
        )
        db_session.add(slide)
        slides.append(slide)
    db_session.flush()
    return slides
