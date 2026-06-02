import abc
from typing import Any, Dict, Type
from pydantic import BaseModel, Field

class BaseAgentTool(abc.ABC):
    """
    Clase base para todas las herramientas (tools) de los agentes.
    Define el contrato estricto de entradas y salidas.
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
        # Valida los inputs usando el schema de Pydantic antes de correr la herramienta
        validated_args = self.args_schema(**kwargs)
        return self.run(**validated_args.dict())
