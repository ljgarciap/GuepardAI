import json
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger("observability")

def log_performance_metric(event_name: str, duration: float, metadata: Optional[Dict[str, Any]] = None) -> None:
    """
    Log a performance metric structured event to the database.

    Args:
        event_name: Unique identifier for the measured event (e.g. 'agent_tool.generate_layout', 'llm_api.generate_json')
        duration: Elapsed time in seconds
        metadata: Optional dictionary with context metadata (e.g. prompt lengths, status, etc.)
    """
    try:
        from database import engine
        from sqlalchemy import text

        # Raw SQL avoids SA ORM RETURNING + psycopg[binary] + JSONB incompatibility
        # that causes ResourceClosedError on INSERT for models with JSONB columns.
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO performance_metrics (event_name, duration_seconds, metadata_json, timestamp)
                    VALUES (:event_name, :duration, CAST(:meta AS JSONB), NOW())
                """),
                {
                    "event_name": event_name,
                    "duration": duration,
                    "meta": json.dumps(metadata or {}),
                }
            )

    except Exception as e:
        # Cero impact in production: log exception locally, do not propagate to disrupt application flow
        logger.error(f"Failed to log performance metric to database: {e}")
