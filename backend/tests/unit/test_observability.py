import json
import pytest
from unittest.mock import patch, MagicMock, call
from utils.observability import log_performance_metric


def _make_engine_mock():
    """Returns a mock engine whose begin() context manager captures execute calls."""
    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_ctx
    return mock_engine, mock_conn


def test_log_performance_metric_calls_correct_sql():
    mock_engine, mock_conn = _make_engine_mock()

    with patch("database.engine", mock_engine):
        log_performance_metric("test_event", 1.23, {"foo": "bar"})

    mock_engine.begin.assert_called_once()
    mock_conn.execute.assert_called_once()
    _, params = mock_conn.execute.call_args[0]
    assert params["event_name"] == "test_event"
    assert params["duration"] == 1.23
    assert json.loads(params["meta"]) == {"foo": "bar"}


def test_log_performance_metric_empty_metadata():
    mock_engine, mock_conn = _make_engine_mock()

    with patch("database.engine", mock_engine):
        log_performance_metric("event_no_meta", 0.5)

    _, params = mock_conn.execute.call_args[0]
    assert json.loads(params["meta"]) == {}


def test_log_performance_metric_does_not_propagate_errors():
    mock_engine = MagicMock()
    mock_engine.begin.side_effect = Exception("DB connection failed")

    # Must not raise — failures are silenced
    with patch("database.engine", mock_engine):
        log_performance_metric("test_event", 1.0, {"k": "v"})


def test_log_performance_metric_multiple_calls():
    mock_engine, mock_conn = _make_engine_mock()

    with patch("database.engine", mock_engine):
        log_performance_metric("event_1", 0.5, {"id": 1})
        log_performance_metric("event_2", 1.5, {"id": 2})

    assert mock_engine.begin.call_count == 2
    assert mock_conn.execute.call_count == 2
    first_params = mock_conn.execute.call_args_list[0][0][1]
    second_params = mock_conn.execute.call_args_list[1][0][1]
    assert first_params["event_name"] == "event_1"
    assert second_params["event_name"] == "event_2"


def test_tool_execution_logs_metrics(db_session, sample_job):
    from agents.architect import GetSlideTypesTool

    mock_engine, mock_conn = _make_engine_mock()
    tool = GetSlideTypesTool()

    with patch("database.engine", mock_engine):
        result = tool()

    # Tool ran and called log_performance_metric at least once
    assert mock_engine.begin.call_count >= 1
    executed_event_names = [
        mock_conn.execute.call_args_list[i][0][1]["event_name"]
        for i in range(mock_conn.execute.call_count)
    ]
    assert any("agent_tool" in name for name in executed_event_names)
