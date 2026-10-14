"""Caso de uso: eliminar un campo del esquema, bloqueado si alguna
fuente del proyecto ya tiene un valor asignado para ese campo.

Observación real de usuario (docs proyecto/Validacion_observaciones_RAG_STUDIO.md,
punto 11): "Editar campo" solo permite corregir la etiqueta -- field_id
y tipo de dato quedan bloqueados a propósito (ver update_field_definition.py),
pero hasta ahora no existía ninguna forma de deshacer un campo dado de
alta por error. Mismo patrón que DeleteCatalogEntry: se verifica que
ningún SourceMetadataValue ya referencie el campo antes de borrarlo,
para no dejar valores huérfanos.

Ronda 3/4 (punto 12): la primera versión de este comando hacía esa
verificación recorriendo `source_repository.list_for_project` +
`source_metadata_repository.list_values_for_source` fuente por fuente
-- cada llamada abría una conexión/engine de base de datos nueva (ver
infrastructure.database.engine.make_sqlite_engine), así que un
proyecto con muchas fuentes pagaba ese costo N veces solo para
responder una pregunta de sí/no. `is_field_in_use` resuelve la misma
pregunta con una sola consulta -- ya no depende de SourceRepository."""
from __future__ import annotations

from domain.metadata.exceptions import FieldDefinitionNotFoundError, FieldInUseError
from domain.metadata.ports import MetadataSchemaRepository, SourceMetadataRepository


class DeleteFieldDefinition:
    def __init__(
        self,
        schema_repository: MetadataSchemaRepository,
        source_metadata_repository: SourceMetadataRepository,
    ):
        self._schema_repository = schema_repository
        self._source_metadata_repository = source_metadata_repository

    def execute(self, project_id: str, schema_id: str, field_id: str) -> None:
        existing = self._schema_repository.get_field(project_id, schema_id, field_id)
        if existing is None:
            raise FieldDefinitionNotFoundError(field_id)

        if self._source_metadata_repository.is_field_in_use(project_id, field_id):
            raise FieldInUseError(field_id)

        self._schema_repository.delete_field(project_id, schema_id, field_id)
