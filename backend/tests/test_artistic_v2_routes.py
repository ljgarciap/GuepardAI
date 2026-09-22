"""
test_artistic_v2_routes.py — Artistic Generation Engine v2, Phase 4.
docs/specs/artistic-generation-v2.md

Covers routers/artistic_v2.py: eligible-brands listing (only brands with
mined BrandLayoutGrammar) and the generate endpoint (fails fast with 400 for
a brand with no mined grammar rather than a deep pipeline failure, sets
engine_version="v2_artistic" on the created job, dispatches the exact same
Celery task v1 uses).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import models


@pytest.fixture()
def client(db_session, superadmin_headers):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app, headers=superadmin_headers)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
class TestEligibleBrands:

    def test_lists_only_brands_with_mined_grammar(self, client, db_session, sample_brand):
        other_brand = models.Brand(name="NoGrammarBrand", about="x", core_value="x")
        db_session.add(other_brand)
        db_session.flush()
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="d.pptx", signatures_json=[{"name": "x"}],
        ))
        db_session.flush()

        resp = client.get("/api/artistic-v2/eligible-brands")
        assert resp.status_code == 200
        brand_ids = [b["id"] for b in resp.json()["brands"]]
        assert sample_brand.id in brand_ids
        assert other_brand.id not in brand_ids

    def test_brand_with_multiple_mined_files_listed_once(self, client, db_session, sample_brand):
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="a.pptx", signatures_json=[{"name": "x"}],
        ))
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="b.pdf", signatures_json=[{"name": "y"}],
        ))
        db_session.flush()

        resp = client.get("/api/artistic-v2/eligible-brands")
        brand_ids = [b["id"] for b in resp.json()["brands"]]
        assert brand_ids.count(sample_brand.id) == 1

    def test_excludes_a_brand_with_mined_grammar_but_no_visual_dna(self, client, db_session):
        # Real bug found live: a brand mined for Phase 0 testing but never
        # run through real v1 ingestion has no BrandVisualDna at all — it
        # passes compose_canvas_for_job() fine but crashes deep in the
        # shared render step. Must never be offered as a generation target.
        mining_only_brand = models.Brand(name="MiningOnlyBrand", about="x", core_value="x")
        db_session.add(mining_only_brand)
        db_session.flush()
        db_session.add(models.BrandLayoutGrammar(
            brand_id=mining_only_brand.id, source_filename="d.pptx", signatures_json=[{"name": "x"}],
        ))
        db_session.flush()

        resp = client.get("/api/artistic-v2/eligible-brands")
        brand_ids = [b["id"] for b in resp.json()["brands"]]
        assert mining_only_brand.id not in brand_ids


@pytest.mark.integration
class TestGenerateArtisticV2:

    def test_rejects_brand_with_no_mined_grammar(self, client, sample_brand):
        resp = client.post("/api/artistic-v2/generate", json={
            "brand_id": sample_brand.id, "prompt": "test prompt",
        })
        assert resp.status_code == 400
        assert "no mined layout grammar" in resp.json()["detail"]

    def test_rejects_brand_with_grammar_but_no_visual_dna(self, client, db_session):
        mining_only_brand = models.Brand(name="MiningOnlyBrand2", about="x", core_value="x")
        db_session.add(mining_only_brand)
        db_session.flush()
        db_session.add(models.BrandLayoutGrammar(
            brand_id=mining_only_brand.id, source_filename="d.pptx", signatures_json=[{"name": "x"}],
        ))
        db_session.flush()

        resp = client.post("/api/artistic-v2/generate", json={
            "brand_id": mining_only_brand.id, "prompt": "test prompt",
        })
        assert resp.status_code == 400
        assert "visual DNA" in resp.json()["detail"]

    def test_creates_job_with_engine_version_v2_artistic(self, client, db_session, sample_brand):
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="d.pptx", signatures_json=[{"name": "x"}],
        ))
        db_session.flush()

        with patch("routers.artistic_v2.celery_generate_presentation.delay") as mock_delay:
            resp = client.post("/api/artistic-v2/generate", json={
                "brand_id": sample_brand.id, "prompt": "Growth strategy for 2026",
            })

        assert resp.status_code == 201
        body = resp.json()
        assert body["engine_version"] == "v2_artistic"

        job = db_session.query(models.GenerationJob).get(body["job_id"])
        assert job.engine_version == "v2_artistic"
        assert job.brand_id == sample_brand.id
        assert job.prompt == "Growth strategy for 2026"
        mock_delay.assert_called_once_with(job.id, {
            "style_filename": "", "knowledge_filename": "", "prompt": "Growth strategy for 2026",
            "region": "LATAM", "allow_ai_images": False, "output_format": "pptx",
            "tier": "free", "interactive_mode": False,
        })

    def test_dispatches_the_same_celery_task_v1_uses(self, db_session, sample_brand):
        # Not a route-level assertion — confirms the isolation design decision
        # directly: no new Celery task was introduced for v2.
        from routers.artistic_v2 import celery_generate_presentation as v2_task
        from tasks import celery_generate_presentation as v1_task
        assert v2_task is v1_task
