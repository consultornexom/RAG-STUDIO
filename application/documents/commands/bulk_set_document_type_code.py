"""Caso de uso: corregir en bloque el document_type_code de varias
fuentes ya registradas (Ronda 4, punto 4a de
Validacion_observaciones_RAG_STUDIO.md).

Observación real de usuario: al importar un lote desde RAG CONTENT
STUDIO (`RegisterSourcesFromFolder`) se etiqueta todo el lote con un
único `document_type_code` (ver docstring de ese comando) -- pero
cuando el lote resulta mixto (algunas fuentes atípicas que en realidad
son de otro tipo documental), la única forma de corregirlas antes de
esto era abrir "Editar fuente" una por una. Con lotes de decenas de
fuentes eso es poco práctico.

`document_type_code` es puramente descriptivo (ver docstring de
`Source.with_updated_details`): no participa de la regla de bloqueo
estructural de location/source_type, así que corregirlo en bloque no
necesita revisar si cada fuente ya tiene extracción -- a diferencia de
`UpdateSourceDetails`, que sí depende de `ExtractionRepository` porque
también puede tocar location/source_type.

Una fuente inexistente (pudo eliminarse entre que se armó la selección
en la UI y que se ejecuta la corrección) no debe abortar el lote
completo -- se registra como omitida y se sigue con las demás, mismo
criterio de tolerancia que `RegisterSourcesFromFolder`."""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.documents.ports import SourceRepository


@dataclass
class BulkSetDocumentTypeCodeResult:
    updated_source_ids: list[str] = field(default_factory=list)
    skipped_source_ids: list[str] = field(default_factory=list)

    @property
    def updated_count(self) -> int:
        return len(self.updated_source_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_source_ids)


class BulkSetDocumentTypeCode:
    def __init__(self, repository: SourceRepository):
        self._repository = repository

    def execute(
        self, project_id: str, source_ids: list[str], document_type_code: str,
    ) -> BulkSetDocumentTypeCodeResult:
        result = BulkSetDocumentTypeCodeResult()
        for source_id in source_ids:
            source = self._repository.get(project_id, source_id)
            if source is None:
                result.skipped_source_ids.append(source_id)
                continue
            updated = source.with_updated_details(
                title=source.title, owner_area=source.owner_area, access_level=source.access_level,
                location=source.location, source_type=source.source_type,
                valid_from=source.valid_from, valid_to=source.valid_to,
                source_authority=source.source_authority, document_type_code=document_type_code,
            )
            self._repository.save(updated)
            result.updated_source_ids.append(source_id)
        return result
