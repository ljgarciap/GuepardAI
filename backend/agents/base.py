import abc
import json
import logging
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class BaseAgentTool(abc.ABC):
    """
    Clase base para todas las herramientas (tools) de los agentes.
    Define el contrato estricto de entradas y salidas, y provee
    trazabilidad automática de decisiones via ArtDirectorDecision.
    """
    name: str
    description: str
    args_schema: Type[BaseModel]

    @abc.abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Ejecuta la herramienta de forma síncrona.
        Debe ser sobrescrito por las herramientas específicas.
        """
        pass

    @abc.abstractmethod
    async def arun(self, **kwargs) -> Any:
        """
        Ejecuta la herramienta de forma asíncrona.
        Debe ser sobrescrito por las herramientas específicas.
        """
        pass

    def __call__(self, *args, **kwargs):
        import time
        from utils.observability import log_performance_metric

        # Valida los inputs usando el schema de Pydantic antes de correr la herramienta
        validated_args = self.args_schema(**kwargs)
        self._last_start_time = time.perf_counter()
        
        job_id = kwargs.get("job_id") or getattr(validated_args, "job_id", None)
        
        try:
            result = self.run(**validated_args.dict())
            duration = time.perf_counter() - self._last_start_time
            
            metadata = {}
            if job_id is not None:
                metadata["job_id"] = job_id
            
            log_performance_metric(
                event_name=f"agent_tool.{self.name}",
                duration=duration,
                metadata=metadata
            )
            return result
        except Exception as e:
            duration = time.perf_counter() - self._last_start_time
            metadata = {"error": str(e)}
            if job_id is not None:
                metadata["job_id"] = job_id
            
            log_performance_metric(
                event_name=f"agent_tool.{self.name}",
                duration=duration,
                metadata=metadata
            )
            raise e

    def log_decision(
        self,
        db,
        job_id: int,
        decision_type: str,
        summary: str,
        reasoning: str = "",
        slide_number: Optional[int] = None,
        prompt_used: Optional[str] = None,
        response_raw: Optional[Any] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Escribe una traza auditable en la tabla ArtDirectorDecision.

        Debe llamarse al final de cualquier decisión significativa de un agente:
          - Elección de layout por el Arquitecto.
          - Score y veredicto del QA Validator.
          - Violaciones detectadas por ValidateBrandTool.
          - Resumen del contenido generado por el Redactor.
          - Confirmación del render por el RenderAgent.

        Args:
            db:             Sesión de SQLAlchemy (la que el Tool ya tiene abierta).
            job_id:         ID del GenerationJob al que pertenece esta decisión.
            decision_type:  Categoría de la decisión ('layout', 'qa_score',
                            'brand_violation', 'content_synthesis', 'render').
            summary:        Descripción corta legible por humanos (máx ~200 chars).
            reasoning:      Explicación detallada del razonamiento del agente/LLM.
            slide_number:   Número de diapositiva afectada (None si aplica al job).
            prompt_used:    El prompt enviado al LLM (para auditoría y reentrenamiento).
            response_raw:   La respuesta cruda del LLM (dict, list o string).
            metadata:       Datos adicionales estructurados (scores, flags, etc.).
        """
        try:
            import models  # Import local para evitar circular imports
            import time
            
            metadata_dict = dict(metadata) if metadata is not None else {}
            if hasattr(self, "_last_start_time"):
                metadata_dict["duration_seconds"] = time.perf_counter() - self._last_start_time

            decision = models.ArtDirectorDecision(
                job_id=job_id,
                slide_number=slide_number,
                decision_type=decision_type,
                summary=summary,
                reasoning=reasoning,
                prompt_used=prompt_used,
                response_raw=json.dumps(response_raw, default=str) if response_raw is not None else None,
                metadata_json=metadata_dict,
            )
            db.add(decision)
            db.flush()  # flush sin commit: respeta la transacción del Tool que llama
            logger.debug(f"[{self.name}] Decision logged: type={decision_type}, job={job_id}, slide={slide_number}")
        except Exception as e:
            # Nunca debe romper el flujo principal por un error de logging
            logger.warning(f"[{self.name}] Could not log decision (non-fatal): {e}")

