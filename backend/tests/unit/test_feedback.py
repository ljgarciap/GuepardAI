import pytest
from fastapi.testclient import TestClient
import models


@pytest.mark.integration
def test_submit_and_get_feedback(db_session, sample_job, superadmin_headers):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        client = TestClient(app, headers=superadmin_headers)
        
        # Check that initially get feedback returns empty list
        response = client.get(f"/api/presentations/{sample_job.id}/feedback")
        assert response.status_code == 200
        assert response.json() == []
        
        # Submit valid feedback
        feedback_payload = {
            "question_key": "presentation_satisfaction",
            "rating": 5,
            "comment": "Excellent presentation quality!"
        }
        
        response = client.post(
            f"/api/presentations/{sample_job.id}/feedback",
            json=feedback_payload
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["rating"] == 5
        assert response.json()["comment"] == "Excellent presentation quality!"
        
        # Retrieve feedback and check values
        response = client.get(f"/api/presentations/{sample_job.id}/feedback")
        assert response.status_code == 200
        feedbacks = response.json()
        assert len(feedbacks) == 1
        assert feedbacks[0]["question_key"] == "presentation_satisfaction"
        assert feedbacks[0]["rating"] == 5
        assert feedbacks[0]["comment"] == "Excellent presentation quality!"
        
        # Submit invalid rating (e.g. 6)
        invalid_payload = {
            "question_key": "presentation_satisfaction",
            "rating": 6,
            "comment": "Too high!"
        }
        response = client.post(
            f"/api/presentations/{sample_job.id}/feedback",
            json=invalid_payload
        )
        assert response.status_code == 400
        
        # Submit feedback for non-existing job
        response = client.post(
            "/api/presentations/99999/feedback",
            json=feedback_payload
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
