"""
portfolio_service.py — helpers compartidos entre main.py (listado/rename/
delete, legacy) y routers/portfolios.py (detalle, nuevo) para no duplicar
lógica de biblioteca de presentaciones.
"""
import os

import models


def portfolio_display_name(job: models.GenerationJob) -> str:
    """Nombre visible: etiqueta editable > basename del archivo > fallback."""
    if job.display_name:
        return job.display_name
    if job.pptx_path:
        return os.path.basename(job.pptx_path)
    return f"Presentation_{job.id}.pptx"
