"""Fachada de application para el contexto Pipeline (Etapa 3, "pipeline
reproducible")."""
from __future__ import annotations

from typing import Callable, Optional

from domain.documents.ports import SourceRepository
from domain.pipeline.entities import PipelineRun
from domain.pipeline.ports import PipelineRunRepository

from .commands.run_pipeline import RunPipeline


class PipelineService:
    def __init__(
        self,
        source_repository: SourceRepository,
        ingestion_service,
        rag_service,
        pipeline_run_repository: PipelineRunRepository,
    ):
        self._run_pipeline = RunPipeline(source_repository, ingestion_service, rag_service, pipeline_run_repository)
        self._runs = pipeline_run_repository

    def run(
        self, project_id: str, document_type_code: str = "default",
        schema_id: Optional[str] = None, is_cancelled: Callable[[], bool] = lambda: False,
    ) -> PipelineRun:
        return self._run_pipeline.execute(
            project_id, document_type_code=document_type_code, schema_id=schema_id, is_cancelled=is_cancelled,
        )

    def get_run(self, project_id: str, run_id: str) -> Optional[PipelineRun]:
        return self._runs.get(project_id, run_id)

    def list_runs(self, project_id: str) -> list[PipelineRun]:
        return self._runs.list_for_project(project_id)
