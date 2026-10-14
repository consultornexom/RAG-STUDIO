"""Consulta: listar los tokens de widget de un proyecto (ADR-002, Fase
4), incluidos los ya revocados -- quien llama decide si los oculta."""
from __future__ import annotations

from domain.runtime.entities import WidgetToken
from domain.runtime.ports import WidgetTokenRepository


class ListWidgetTokens:
    def __init__(self, repository: WidgetTokenRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[WidgetToken]:
        return self._repository.list_for_project(project_id)
