import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from pptx.dml.color import RGBColor
import os

import models
from services.rendering.painter import GammaPainter

def test_footer_contrast_logic():
    class MockBrand:
        primary_color = "#0052A3"     # Dark blue
        secondary_color = "#EE1C2E"
        background_color = "#FFFFFF"   # Light bg
        font_family = "Arial"

    brand = MockBrand()
    painter = GammaPainter(brand)
    
    # 1. Dark slide background (like composition_hero or dark color primary)
    # Background color has low luminance
    dark_bg = RGBColor(0, 82, 163) 
    
    # 2. Light slide background
    light_bg = RGBColor(255, 255, 255)
    
    # Verify Luminance of dark_bg is low
    from services.rendering.painter import get_luminance
    assert get_luminance(dark_bg) < 0.5
    assert get_luminance(light_bg) >= 0.5
    
    # Verify get_contrast_text_color works
    from services.rendering.painter import get_contrast_text_color
    assert get_contrast_text_color(dark_bg) == RGBColor(255, 255, 255) # White text
    assert get_contrast_text_color(light_bg) == RGBColor(20, 20, 20)     # Dark text

@pytest.mark.integration
def test_footer_api_endpoints(db_session, superadmin_headers):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        client = TestClient(app, headers=superadmin_headers)
        
        # 1. List footers (should contain default seeded config)
        response = client.get("/api/footers")
        assert response.status_code == 200
        data = response.json()
        assert "is_footer_enabled" in data
        assert len(data["footers"]) >= 1
        
        # Find default seeded config
        seeded = next(f for f in data["footers"] if "Default" in f["name"])
        assert seeded["is_selected"] is True
        
        # 2. Create new footer configuration without logos
        create_payload = {
            "name": "Custom Test Footer",
            "text": "L - custom test footer details"
        }
        response = client.post("/api/footers", data=create_payload)
        assert response.status_code == 200
        new_footer = response.json()
        assert new_footer["name"] == "Custom Test Footer"
        assert new_footer["text"] == "L - custom test footer details"
        assert new_footer["is_selected"] is False
        
        # 3. Select new footer
        response = client.put(f"/api/footers/{new_footer['id']}/select")
        assert response.status_code == 200
        selected = response.json()
        assert selected["is_selected"] is True
        
        # Ensure others are deselected
        response = client.get("/api/footers")
        footers = response.json()["footers"]
        for f in footers:
            if f["id"] == new_footer["id"]:
                assert f["is_selected"] is True
            else:
                assert f["is_selected"] is False
                
        # 4. Toggle global footer activation
        response = client.put("/api/footers/toggle?enabled=false")
        assert response.status_code == 200
        assert response.json()["is_footer_enabled"] is False
        
        response = client.get("/api/footers")
        assert response.json()["is_footer_enabled"] is False
        
        # Toggle back
        client.put("/api/footers/toggle?enabled=true")

        # 5. Delete footer
        response = client.delete(f"/api/footers/{new_footer['id']}")
        assert response.status_code == 200
        
        # Verify it is deleted
        response = client.get("/api/footers")
        footers = response.json()["footers"]
        assert not any(f["id"] == new_footer["id"] for f in footers)

    finally:
        app.dependency_overrides.clear()
