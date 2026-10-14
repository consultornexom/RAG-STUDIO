"""Caso de uso: emitir un token de widget nuevo para un proyecto
(ADR-002, Fase 4 -- resuelve el riesgo de seguridad documentado en la
Fase 3: la `X-API-Key` operativa global incrustada en un `<script>`
público solo era aceptable para un piloto de un solo sitio de
confianza). No valida que el proyecto tenga una instantánea publicada
-- un token puede aprovisionarse antes de la primera publicación, el
proyecto simplemente no respondería nada útil todavía si se usara."""
from __future__ import annotations

from typing import Optional

from domain.documents.entities import AccessLevel
from domain.runtime.entities import WidgetToken
from domain.runtime.ports import WidgetTokenRepository


class IssueWidgetToken:
    def __init__(self, repository: WidgetTokenRepository):
        self._repository = repository

    def execute(self, project_id: str, max_access_level: Optional[str] = None) -> WidgetToken:
        """max_access_level (Pista B.3 del ADR-003): opcional -- si se
        omite, WidgetToken.max_access_level usa su propio default
        ("restringido", sin techo, ver domain.runtime.entities). Si se
        pasa, debe ser uno de los cuatro valores conocidos de
        domain.documents.entities.AccessLevel; se valida aquí (no en
        domain.runtime, que a propósito no importa ese Enum) para dar
        un error claro en vez de guardar un valor arbitrario que
        is_within_access_level no sabría interpretar."""
        kwargs = {}
        if max_access_level is not None:
            try:
                kwargs["max_access_level"] = AccessLevel(max_access_level).value
            except ValueError as exc:
                valores = ", ".join(nivel.value for nivel in AccessLevel)
                raise ValueError(
                    f"max_access_level inválido: {max_access_level!r} -- valores válidos: {valores}."
                ) from exc
        token = WidgetToken(project_id=project_id, **kwargs)
        self._repository.save(token)
        return token
