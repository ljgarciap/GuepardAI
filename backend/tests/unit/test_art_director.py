import pytest
from services.art_director_service import plan_presentation_design
from unittest.mock import MagicMock, patch

def test_safe_int_id_handling():
    # Este test valida que el parche anti-hallucinación funcione
    # Necesitamos acceder a la función interna o simular el flujo
    from services.art_director_service import plan_presentation_design
    
    # Creamos un mock de la decisión de la IA con basura en los IDs
    mock_decision = {
        "layout_slug": "split-right",
        "primary_asset_id": "None (custom image required)", # El culpable del error anterior
        "accent_id": "hallucinated_string",
        "reasoning": "Test reasoning"
    }
    
    with patch("services.art_director_service.generate_json", return_value=mock_decision):
        with patch("services.art_director_service.ensure_brand_fonts"):
            db = MagicMock()
            # Simular que el job existe
            job = MagicMock(style_id=1, brand_id=1)
            db.query.return_value.get.return_value = job
            
            # Simular una slide
            slide = MagicMock(slide_number=1, title="Test", content_json={})
            db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slide]
            
            # Mock de Brand record
            brand = MagicMock(name="Tesco")
            db.query.return_value.get.return_value = brand
            
            # Debería ejecutar sin explotar
            try:
                plan_presentation_design(db, 1)
                assert True
            except Exception as e:
                pytest.fail(f"Art Director failed to handle string IDs: {e}")
