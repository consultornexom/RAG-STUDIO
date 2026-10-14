"""Puerto del contexto Pipeline. Implementado en infrastructure."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import PipelineRun, PipelineRunItem


class PipelineRunRepository(ABC):
    @abstractmethod
    def save(self, run: PipelineRun) -> None: ...

    @abstractmethod
    def get(self, project_id: str, run_id: str) -> Optional[PipelineRun]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[PipelineRun]:
        """Corridas de un proyecto, más reciente primero."""
        ...

    @abstractmethod
    def get_last_successful_item(self, project_id: str, source_id: str) -> Optional[PipelineRunItem]:
        """El PipelineRunItem con status=EXITOSO más reciente para esa
        fuente, entre todas las corridas del proyecto -- la señal que
        usa RunPipeline para decidir si una fuente puede omitirse
        (incrementalidad/reanudación). None si la fuente nunca se
        proceso con éxito."""
        ...
