"""Caso de uso: revocar un token de widget (ADR-002, Fase 4). Revocar
es idempotente en el sentido de "el token queda inválido"; volver a
revocar uno ya revocado no es un error, solo no cambia nada."""
from __future__ import annotations

from datetime import datetime, timezone

from domain.runtime.ports import WidgetTokenRepository


class WidgetTokenNotFoundError(Exception):
    def __init__(self, token_id: str):
        super().__init__(f"No existe ningún token de widget con id {token_id!r}.")
        self.token_id = token_id


class RevokeWidgetToken:
    def __init__(self, repository: WidgetTokenRepository):
        self._repository = repository

    def execute(self, token_id: str) -> None:
        token = self._repository.get_by_id(token_id)
        if token is None:
            raise WidgetTokenNotFoundError(token_id)
        if token.revoked_at is not None:
            return  # ya estaba revocado -- idempotente, no es un error.
        token.revoked_at = datetime.now(timezone.utc)
        self._repository.save(token)
