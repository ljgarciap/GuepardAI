"""
test_portfolios.py — Tests de Gestión de Portfolios.

Cubre: orden descendente, búsqueda (display_name y filename, escapado de
comodines), rango de fechas, paginación, renombrado (validaciones) y
eliminación con limpieza completa.

Spec: docs/specs/gestion-portfolios.md
"""
import datetime
import os
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


def _make_job(db, brand_id, *, days_ago=0, display_name=None, filename=None,
              status=models.GenerationJobStatus.COMPLETED, pptx_path=None):
    job = models.GenerationJob(
        client_name="pytest",
        brand_id=brand_id,
        prompt="test",
        status=status,
        display_name=display_name,
        pptx_path=pptx_path if pptx_path is not None else (f"outputs/{filename}" if filename else None),
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=days_ago),
    )
    db.add(job)
    db.flush()
    return job


# ─────────────────────────────────────────────────────────────────────────────
# LISTADO: orden, búsqueda, fechas, paginación
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestPortfolioListing:

    def test_ordered_newest_first(self, client, db_session, sample_brand):
        _make_job(db_session, sample_brand.id, days_ago=5, filename="old.pptx")
        _make_job(db_session, sample_brand.id, days_ago=0, filename="newest.pptx")
        _make_job(db_session, sample_brand.id, days_ago=2, filename="middle.pptx")

        res = client.get("/api/library/portfolios")
        assert res.status_code == 200
        body = res.json()
        names = [i["filename"] for i in body["items"]]
        assert names == ["newest.pptx", "middle.pptx", "old.pptx"]
        assert body["total"] == 3
        assert body["page"] == 1

    def test_search_matches_display_name_and_filename(self, client, db_session, sample_brand):
        _make_job(db_session, sample_brand.id, display_name="Tesco Clubcard Pitch", filename="Presentation_1.pptx")
        _make_job(db_session, sample_brand.id, filename="tesco_keynote.pptx")
        _make_job(db_session, sample_brand.id, filename="other_brand.pptx")

        res = client.get("/api/library/portfolios", params={"search": "tesco"})
        body = res.json()
        assert body["total"] == 2
        display_names = {i["display_name"] for i in body["items"]}
        assert display_names == {"Tesco Clubcard Pitch", "tesco_keynote.pptx"}

    def test_search_escapes_like_wildcards(self, client, db_session, sample_brand):
        _make_job(db_session, sample_brand.id, display_name="100% Loyalty", filename="a.pptx")
        _make_job(db_session, sample_brand.id, display_name="Loyalty Deck", filename="b.pptx")

        # '%' literal: solo debe coincidir el que realmente contiene el carácter
        res = client.get("/api/library/portfolios", params={"search": "100%"})
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["display_name"] == "100% Loyalty"

    def test_date_range_inclusive(self, client, db_session, sample_brand):
        _make_job(db_session, sample_brand.id, days_ago=10, filename="too_old.pptx")
        target = _make_job(db_session, sample_brand.id, days_ago=3, filename="in_range.pptx")
        _make_job(db_session, sample_brand.id, days_ago=0, filename="too_new.pptx")

        # created_at se sella con utcnow(); el rango debe derivarse de la MISMA
        # base UTC, no de date.today() (local). En UTC-5 por la tarde difieren un
        # día y el rango inclusivo dejaba fuera al target (test timezone-frágil).
        today_utc = datetime.datetime.utcnow().date()
        d_from = (today_utc - datetime.timedelta(days=4)).isoformat()
        d_to = (today_utc - datetime.timedelta(days=3)).isoformat()
        res = client.get("/api/library/portfolios", params={"date_from": d_from, "date_to": d_to})
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == target.id

    def test_inverted_date_range_returns_422(self, client):
        res = client.get("/api/library/portfolios", params={
            "date_from": "2026-06-11", "date_to": "2026-06-01"
        })
        assert res.status_code == 422

    def test_pagination_and_out_of_range_page(self, client, db_session, sample_brand):
        for i in range(5):
            _make_job(db_session, sample_brand.id, days_ago=i, filename=f"deck_{i}.pptx")

        res = client.get("/api/library/portfolios", params={"page": 2, "page_size": 2})
        body = res.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["items"][0]["filename"] == "deck_2.pptx"  # tercero más reciente

        # Página fuera de rango: items vacíos, total correcto, sin error
        res = client.get("/api/library/portfolios", params={"page": 99, "page_size": 2})
        body = res.json()
        assert res.status_code == 200
        assert body["items"] == []
        assert body["total"] == 5

    def test_only_completed_jobs_listed(self, client, db_session, sample_brand):
        _make_job(db_session, sample_brand.id, filename="done.pptx")
        _make_job(db_session, sample_brand.id, filename="wip.pptx", status=models.GenerationJobStatus.PROCESSING)

        body = client.get("/api/library/portfolios").json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "done.pptx"


# ─────────────────────────────────────────────────────────────────────────────
# RENOMBRADO
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestPortfolioRename:

    def test_rename_persists_and_search_finds_new_name(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, filename="Presentation_X.pptx")

        res = client.patch(f"/api/library/portfolios/{job.id}", json={"display_name": "  Pitch Q3 Tesco  "})
        assert res.status_code == 200
        assert res.json()["display_name"] == "Pitch Q3 Tesco"  # trimmed

        body = client.get("/api/library/portfolios", params={"search": "Pitch Q3"}).json()
        assert body["total"] == 1
        assert body["items"][0]["display_name"] == "Pitch Q3 Tesco"

    def test_rename_validations(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, filename="a.pptx")

        assert client.patch(f"/api/library/portfolios/{job.id}", json={"display_name": "   "}).status_code == 422
        assert client.patch(f"/api/library/portfolios/{job.id}", json={"display_name": "x" * 121}).status_code == 422
        assert client.patch("/api/library/portfolios/999999", json={"display_name": "valid"}).status_code == 404

    def test_rename_does_not_touch_file_path(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, filename="physical_name.pptx")
        original_path = job.pptx_path

        client.patch(f"/api/library/portfolios/{job.id}", json={"display_name": "New Label"})

        db_session.refresh(job)
        assert job.pptx_path == original_path
        assert job.display_name == "New Label"


# ─────────────────────────────────────────────────────────────────────────────
# ELIMINACIÓN
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestPortfolioDelete:

    def test_delete_cleans_everything(self, client, db_session, sample_brand, tmp_path):
        # Archivo físico real para verificar su eliminación
        pptx_file = tmp_path / "to_delete.pptx"
        pptx_file.write_bytes(b"fake pptx")
        job = _make_job(db_session, sample_brand.id, pptx_path=str(pptx_file))

        slide = models.PresentationSlide(job_id=job.id, slide_number=1, title="S1", status="rendered")
        decision = models.ArtDirectorDecision(job_id=job.id, slide_number=1, decision_type="layout", summary="x")
        question = db_session.query(models.SurveyQuestion).filter(
            models.SurveyQuestion.key == "presentation_satisfaction").first()
        if not question:
            question = models.SurveyQuestion(key="presentation_satisfaction", question_text="?", is_active=True)
            db_session.add(question)
            db_session.flush()
        feedback = models.GenerationJobFeedback(job_id=job.id, question_id=question.id, rating=5)
        db_session.add_all([slide, decision, feedback])
        db_session.flush()
        job_id = job.id

        res = client.delete(f"/api/library/portfolios/{job_id}")
        assert res.status_code == 200
        assert res.json() == {"deleted": True, "id": job_id}

        assert db_session.query(models.GenerationJob).get(job_id) is None
        assert db_session.query(models.PresentationSlide).filter_by(job_id=job_id).count() == 0
        assert db_session.query(models.ArtDirectorDecision).filter_by(job_id=job_id).count() == 0
        assert db_session.query(models.GenerationJobFeedback).filter_by(job_id=job_id).count() == 0
        assert not os.path.exists(str(pptx_file))

    def test_delete_tolerates_missing_file(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, pptx_path="outputs/ghost_file.pptx")

        res = client.delete(f"/api/library/portfolios/{job.id}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

    def test_delete_blocked_while_pipeline_active(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, filename="wip.pptx",
                        status=models.GenerationJobStatus.PROCESSING)

        res = client.delete(f"/api/library/portfolios/{job.id}")
        assert res.status_code == 409
        assert db_session.query(models.GenerationJob).get(job.id) is not None

    def test_delete_error_status_allowed(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, filename="failed.pptx",
                        status=models.GenerationJobStatus.ERROR)

        assert client.delete(f"/api/library/portfolios/{job.id}").status_code == 200

    def test_delete_twice_returns_404(self, client, db_session, sample_brand):
        job = _make_job(db_session, sample_brand.id, filename="once.pptx")
        job_id = job.id

        assert client.delete(f"/api/library/portfolios/{job_id}").status_code == 200
        assert client.delete(f"/api/library/portfolios/{job_id}").status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# RATING AGREGADO (PresentationReview) EN EL LISTADO
# Modelo unificado (confirmado 2026-07-13): el rating del creador es su review
# individual; la tarjeta muestra el promedio del team. 'hidden' y borradas
# quedan fuera del promedio; 'flagged' (auto-tag pendiente) cuenta.
# ─────────────────────────────────────────────────────────────────────────────
import uuid

from auth import security


def _make_user(db, tenant_id=None, role=models.UserRole.CLIENTE.value):
    user = models.User(
        email=f"user_{uuid.uuid4().hex}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=1,
    )
    db.add(user)
    db.flush()
    return user


def _headers(user):
    return {"Authorization": f"Bearer {security.create_access_token(user.id, user.role, user.tenant_id)}"}


def _add_review(db, job_id, user_id, rating, moderation_status="visible", is_deleted=False):
    review = models.PresentationReview(
        job_id=job_id, user_id=user_id, rating=rating,
        moderation_status=moderation_status, is_deleted=is_deleted,
    )
    db.add(review)
    db.flush()
    return review


@pytest.mark.integration
class TestPortfolioRatingAggregates:

    def _scenario(self, db):
        tenant = models.Tenant(name=f"Tenant_{uuid.uuid4().hex}")
        db.add(tenant)
        db.flush()
        brand = models.Brand(name=f"Brand_{uuid.uuid4().hex}", tenant_id=tenant.id)
        db.add(brand)
        db.flush()
        owner = _make_user(db, tenant_id=tenant.id)
        job = _make_job(db, brand.id, filename="team_rated.pptx")
        job.owner_id = owner.id
        db.flush()
        return tenant, brand, owner, job

    def test_average_count_and_my_rating(self, client, db_session):
        tenant, brand, owner, job = self._scenario(db_session)
        teammate = _make_user(db_session, tenant_id=tenant.id)
        _add_review(db_session, job.id, owner.id, 5)
        _add_review(db_session, job.id, teammate.id, 3, moderation_status="flagged")  # flagged cuenta

        item = client.get("/api/library/portfolios", headers=_headers(owner)).json()["items"][0]
        assert item["rating_average"] == 4.0
        assert item["rating_count"] == 2
        assert item["my_rating"] == 5  # habilita/oculta el RATE IT de la tarjeta

        item = client.get("/api/library/portfolios", headers=_headers(teammate)).json()["items"][0]
        assert item["my_rating"] == 3

    def test_hidden_and_deleted_excluded_from_average(self, client, db_session):
        tenant, brand, owner, job = self._scenario(db_session)
        hidden_user = _make_user(db_session, tenant_id=tenant.id)
        deleted_user = _make_user(db_session, tenant_id=tenant.id)
        _add_review(db_session, job.id, owner.id, 4)
        _add_review(db_session, job.id, hidden_user.id, 1, moderation_status="hidden")
        _add_review(db_session, job.id, deleted_user.id, 1, is_deleted=True)

        item = client.get("/api/library/portfolios", headers=_headers(owner)).json()["items"][0]
        assert item["rating_average"] == 4.0
        assert item["rating_count"] == 1

        # La review propia hidden sigue contando como "ya calificó" (no re-mostrar RATE IT);
        # la borrada no — el usuario decidió retirarla y puede volver a calificar.
        assert client.get("/api/library/portfolios", headers=_headers(hidden_user)).json()["items"][0]["my_rating"] == 1
        assert client.get("/api/library/portfolios", headers=_headers(deleted_user)).json()["items"][0]["my_rating"] is None

    def test_job_without_reviews(self, client, db_session):
        tenant, brand, owner, job = self._scenario(db_session)

        item = client.get("/api/library/portfolios", headers=_headers(owner)).json()["items"][0]
        assert item["rating_average"] is None
        assert item["rating_count"] == 0
        assert item["my_rating"] is None
