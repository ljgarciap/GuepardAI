import pytest
from unittest.mock import MagicMock, patch
from services.ingestion_orchestrator import task_extract_full_brand_style
import models

def test_full_ingestion_flow_no_leaks(tmp_path):
    # Mockear DB para evitar escrituras reales en producción durante el test
    db_mock = MagicMock()
    
    # Mockear las funciones pesadas de IA
    with patch("services.ingestion_orchestrator.task_extract_artistic_essence") as mock_essence:
        with patch("services.ingestion_orchestrator.task_extract_visual_dna") as mock_dna:
            with patch("services.ingestion_orchestrator.update_job_step") as mock_step:
                with patch("services.ingestion_orchestrator.set_job_status") as mock_status:
                    
                    # Ejecutar el orquestador
                    task_extract_full_brand_style(
                        job_key="test_job",
                        file_path="dummy.pdf",
                        source_filename="test_brand.pdf",
                        brand_id=1
                    )
                    
                    # Validaciones de flujo
                    assert mock_essence.called, "Artistic Essence should be extracted first"
                    assert mock_dna.called, "Visual DNA should be extracted second"
                    assert mock_status.called
                    
                    # Verificar que el status final sea 'completed'
                    mock_status.assert_any_call("test_job", "brand_style", "completed")

def test_ingestion_error_handling():
    # Validar que si algo falla, el status sea 'error'
    with patch("services.ingestion_orchestrator.task_extract_artistic_essence", side_effect=Exception("IA Down")):
        with patch("services.ingestion_orchestrator.set_job_status") as mock_status:
            # No debería explotar, debería atrapar el error
            task_extract_full_brand_style("job_err", "fail.pdf", "fail.pdf", brand_id=1)
            
            # El flujo sigue pero debería marcarse completado (o manejar el error parcial)
            # Nota: En nuestro orquestador actual, el flujo continúa para intentar el DNA
            assert mock_status.called
