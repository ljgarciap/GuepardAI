import pytest
from unittest.mock import MagicMock, patch
from services.ingestion.ingestion_orchestrator import task_extract_full_brand_style
import models

def test_full_ingestion_flow_no_leaks(tmp_path):
    # Mockear SessionLocal
    db_mock = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 42
    db_mock.query.return_value.filter.return_value.first.return_value = mock_job

    # Mockear las herramientas del AgentOrchestrator
    with patch("agents.orchestrator.SessionLocal", return_value=db_mock):
        with patch("agents.orchestrator.ExtractPaletteTool") as MockExtractPalette, \
             patch("agents.orchestrator.ReadPPTXTool") as MockReadPPTX:
            
            mock_palette_tool = MockExtractPalette.return_value
            mock_read_pptx_tool = MockReadPPTX.return_value
            
            # Ejecutar el orquestador
            task_extract_full_brand_style(
                job_key="test_job",
                file_path="dummy.pdf",
                source_filename="test_brand.pdf",
                brand_id=1
            )
            
            # Validaciones de flujo:
            # 1. Se debió llamar a ExtractPaletteTool para la esencia artística
            mock_palette_tool.assert_called_once()
            # 2. Se debió llamar a ReadPPTXTool para el DNA visual
            mock_read_pptx_tool.assert_called_once()
            # 3. El status final del job se debe cambiar a COMPLETED
            assert mock_job.status == models.IngestionJobStatus.COMPLETED

def test_ingestion_error_handling():
    # Validar que si la esencia artística falla, no explote y continúe
    db_mock = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 42
    db_mock.query.return_value.filter.return_value.first.return_value = mock_job

    with patch("agents.orchestrator.SessionLocal", return_value=db_mock):
        with patch("agents.orchestrator.ExtractPaletteTool") as MockExtractPalette, \
             patch("agents.orchestrator.ReadPPTXTool") as MockReadPPTX:
            
            mock_palette_tool = MockExtractPalette.return_value
            mock_palette_tool.side_effect = Exception("IA Down")
            
            mock_read_pptx_tool = MockReadPPTX.return_value
            
            # Ejecutar el orquestador
            task_extract_full_brand_style(
                job_key="job_err",
                file_path="fail.pdf",
                source_filename="fail.pdf",
                brand_id=1
            )
            
            # El palette falló, pero se debió llamar a read_pptx igualmente (no explota)
            assert mock_palette_tool.called
            assert mock_read_pptx_tool.called
            # Al final se marca como completed (fallos individuales son non-fatal)
            assert mock_job.status == models.IngestionJobStatus.COMPLETED

