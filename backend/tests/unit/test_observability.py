import os
import json
import pytest
from unittest.mock import patch, MagicMock
from utils.observability import log_performance_metric
from fastapi.testclient import TestClient
from main import app
import models

def test_log_performance_metric_writes_to_db(db_session):
    # Parchar SessionLocal para usar db_session de test
    with patch("utils.observability.SessionLocal", return_value=db_session):
        log_performance_metric("test_event", 1.23, {"foo": "bar"})
    
    # Query database to assert
    metrics = db_session.query(models.PerformanceMetric).filter(models.PerformanceMetric.event_name == "test_event").all()
    assert len(metrics) == 1
    assert metrics[0].duration_seconds == 1.23
    assert metrics[0].metadata_json == {"foo": "bar"}
    assert metrics[0].timestamp is not None

def test_get_metrics_endpoint(db_session):
    # Clear preexisting metrics first if any
    db_session.query(models.PerformanceMetric).delete()
    db_session.commit()
    
    with patch("utils.observability.SessionLocal", return_value=db_session):
        log_performance_metric("event_1", 0.5, {"id": 1})
        log_performance_metric("event_2", 1.5, {"id": 2})
    
    client = TestClient(app)
    # Patch get_db in FastAPI app to return our test db_session
    from main import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        response = client.get("/api/admin/metrics?limit=5")
        assert response.status_code == 200
        metrics = response.json()
        assert len(metrics) == 2
        # Since it sorts desc: event_2 should be first, event_1 second
        assert metrics[0]["event_name"] == "event_2"
        assert metrics[1]["event_name"] == "event_1"
    finally:
        app.dependency_overrides.clear()

def test_tool_execution_logs_metrics(db_session, sample_job):
    from agents.arquitecto import GetSlideTypesTool
    
    db_session.query(models.PerformanceMetric).delete()
    db_session.commit()
    
    tool = GetSlideTypesTool()
    
    # We patch SessionLocal of the tool and observability utils to use our test db_session
    with patch("agents.arquitecto.SessionLocal", return_value=db_session):
        with patch("utils.observability.SessionLocal", return_value=db_session):
            result = tool()
            
    # Check that a metric was logged in DB
    metrics = db_session.query(models.PerformanceMetric).filter(models.PerformanceMetric.event_name == "agent_tool.get_slide_types").all()
    assert len(metrics) == 1
    assert metrics[0].duration_seconds > 0
