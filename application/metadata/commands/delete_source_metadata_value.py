"""Caso de uso: desasociar (quitar) el valor de un campo ya guardado
para una fuente concreta (Ronda 6, punto 23 de
Validacion_observaciones_RAG_STUDIO.md).

Observación real de usuario (vídeo 3): "Valores por fuente" solo
ofrecía guardar/sobrescribir un valor (SetSourceMetadataValue, upsert)
-- no había ningún botón ni opción para quitarlo una vez asignado, ni
siquiera por error. A diferencia de DeleteFieldDefinition/
DeleteCatalogEntry, aquí no hay ningún "uso" que verificar (un valor de
metadato no es referenciado por nada más en el dominio): solo hace
falta confirmar que existe antes de borrarlo, para dar un error de
dominio claro en vez de un borrado silencioso de la nada si la fuente
ya no tenía ese valor (pudo desaparecer entre que se listó en la UI y
que se pulsó el botón).
"""
from __future__ import annotations

from domain.metadata.exceptions import SourceMetadataValueNotFoundError
from domain.metadata.ports import SourceMetadataRepository


class DeleteSourceMetadataValue:
    def __init__(self, source_metadata_repository: SourceMetadataRepository):
        self._source_metadata_repository = source_metadata_repository

    def execute(self, project_id: str, source_id: str, field_id: str) -> None:
        existing = self._source_metadata_repository.get_value(project_id, source_id, field_id)
        if existing is None:
            raise SourceMetadataValueNotFoundError(source_id, field_id)
        self._source_metadata_repository.delete_value(project_id, source_id, field_id)
