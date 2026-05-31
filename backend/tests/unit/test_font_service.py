import pytest
from unittest.mock import MagicMock, patch
from services.rendering.font_service import install_font, ensure_brand_fonts

def test_install_font_already_exists(tmp_path):
    # Mockear el directorio de fuentes para usar uno temporal
    with patch("services.rendering.font_service.FONT_DIR", str(tmp_path)):
        # Crear un archivo de fuente ficticio
        font_file = tmp_path / "Inter.ttf"
        font_file.write_text("dummy font content")
        
        # Debería devolver el nombre sin intentar descargar
        result = install_font("Inter")
        assert result == "Inter"

def test_install_font_download_fail():
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 404
        result = install_font("NonExistentFont")
        assert result is None

def test_ensure_brand_fonts_updates_db():
    db = MagicMock()
    visual_dna = {"primary_font": "Inter", "secondary_font": "Roboto"}
    brand_id = 1
    
    # Simular que install_font devuelve un nombre diferente (sincronizado)
    with patch("services.rendering.font_service.install_font") as mock_install:
        mock_install.side_effect = ["Inter", "Roboto Slab"]
        
        ensure_brand_fonts(db, brand_id, visual_dna)
        
        # Verificar que el diccionario se actualizó
        assert visual_dna["secondary_font"] == "Roboto Slab"
        
        # Verificar que se intentó guardar en la DB
        assert db.commit.called
