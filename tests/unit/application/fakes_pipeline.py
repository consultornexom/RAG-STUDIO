"""Doble de prueba en memoria para el contexto Pipeline."""
from __future__ import annotations

from typing import Optional

from domain.pipeline.entities import PipelineItemStatus, PipelineRun, PipelineRunItem
from domain.pipeline.ports import PipelineRunRepository


class InMemoryPipelineRunRepository(PipelineRunRepository):
    def __init__(self):
        self._runs: list[PipelineRun] = []

    def save(self, run: PipelineRun) -> None:
        self._runs.append(run)

    def get(self, project_id: str, run_id: str) -> Optional[PipelineRun]:
        return next((r for r in self._runs if r.project_id == project_id and r.id == run_id), None)

    def list_for_project(self, project_id: str) -> list[PipelineRun]:
        return sorted(
            (r for r in self._runs if r.project_id == project_id),
            key=lambda r: r.started_at, reverse=True,
        )

    def get_last_successful_item(self, project_id: str, source_id: str) -> Optional[PipelineRunItem]:
        candidates = [
            item for run in self._runs if run.project_id == project_id
            for item in run.items
            if item.source_id == source_id and item.status == PipelineItemStatus.EXITOSO
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.started_at)

    def get_last_processed_item(self, project_id: str, source_id: str) -> Optional[PipelineRunItem]:
        candidates = [
            item for run in self._runs if run.project_id == project_id
            for item in run.items
            if item.source_id == source_id and item.status != PipelineItemStatus.OMITIDO
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.started_at)
