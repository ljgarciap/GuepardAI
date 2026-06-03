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
        from database import SessionLocal
        import models
        
        db = SessionLocal()
        try:
            metric = models.PerformanceMetric(
                event_name=event_name,
                duration_seconds=duration,
                metadata_json=metadata or {}
            )
            db.add(metric)
            db.commit()
        finally:
            db.close()
            
    except Exception as e:
        # Cero impact in production: log exception locally, do not propagate to disrupt application flow
        logger.error(f"Failed to log performance metric to database: {e}")
