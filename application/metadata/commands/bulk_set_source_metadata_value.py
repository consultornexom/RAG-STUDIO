"""Caso de uso: asignar el mismo valor de un campo a varias fuentes a
la vez (Ronda 5, punto 21 de Validacion_observaciones_RAG_STUDIO.md).

Observación real de usuario (vídeo 2): describir metadatos fuente por
fuente es tedioso cuando muchas fuentes de un mismo tipo comparten el
mismo valor en un campo (p. ej. "plantel = Campus Norte" para todas las
fuentes de un lote). El mismo patrón de selección múltiple que ya
existe en Fuentes (ver BulkSetDocumentTypeCode) se extiende aquí a
"Valores por fuente".

La validación de campo/valor (existe el campo, respeta obligatoriedad y
multiplicidad, el valor pertenece al catálogo si aplica) es la MISMA
para todas las fuentes del lote -- a diferencia de una fuente
inexistente, un valor inválido no es un problema de una fuente
puntual, sino un error de diseño del lote completo. Se valida con
SetSourceMetadataValue.validate() ANTES del bucle, sin depender de
ninguna fuente concreta: si el campo/valor es inválido, falla ahí,
antes de haber escrito nada.

Corrección post-Ronda 5 (auditoría de la Ronda 6): validar dentro del
bucle, condicionado a que la fuente exista (versión original), dejaba
un hueco -- si TODAS las fuentes del lote habían dejado de existir (o
`source_ids` llegaba vacío), la validación nunca se ejecutaba y el
método devolvía un resultado vacío en silencio en vez de señalar el
field_id/valor inválido. Validar antes del bucle, independientemente de
qué fuentes existan, cierra ese hueco.

Una fuente que ya no existe (pudo eliminarse entre que se armó la
selección en la UI y que se ejecuta la asignación) no aborta el lote:
se registra como omitida y se continúa con las demás -- mismo criterio
de tolerancia que BulkSetDocumentTypeCode. `source_ids` se depura
(se preservan solo apariciones únicas, en orden) para que un id
repetido no infle `updated_count` ni se procese dos veces.

Ronda 97 (hallazgo real de NEXOM, AGENTE UDL): `mode` se pasa tal cual a
SetSourceMetadataValue. Con `mode="agregar"` (solo campos de varios
valores) cada fuente CONSERVA los valores que ya tenía y se le suman los
nuevos -- p. ej. aplicar `campus=torres_landa` a varias fuentes sin
borrar el `hilario_medina` que algunas ya tenían. Con `"reemplazar"` (por
defecto, comportamiento de siempre) cada fuente queda exactamente con la
lista indicada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from domain.documents.ports import SourceRepository
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository

from .set_source_metadata_value import SetSourceMetadataValue, ValueAssignmentMode, parse_mode


@dataclass
class BulkSetSourceMetadataValueResult:
    updated_source_ids: list[str] = field(default_factory=list)
    skipped_source_ids: list[str] = field(default_factory=list)

    @property
    def updated_count(self) -> int:
        return len(self.updated_source_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_source_ids)


class BulkSetSourceMetadataValue:
    def __init__(
        self,
        schema_repository: MetadataSchemaRepository,
        catalog_repository: CatalogRepository,
        source_metadata_repository: SourceMetadataRepository,
        source_repository: SourceRepository,
    ):
        self._source_repository = source_repository
        self._set_value = SetSourceMetadataValue(schema_repository, catalog_repository, source_metadata_repository)

    def execute(
        self,
        project_id: str,
        schema_id: str,
        source_ids: list[str],
        field_id: str,
        raw_value: Union[str, list[str]],
        mode: object = ValueAssignmentMode.REEMPLAZAR,
    ) -> BulkSetSourceMetadataValueResult:
        # Deja que FieldDefinitionNotFoundError/InvalidMetadataValueError se
        # propaguen sin capturarlas: son errores de diseño del lote
        # (campo/valor), no de una fuente puntual -- deben abortar toda la
        # operación antes de tocar ninguna fuente, incluso si source_ids
        # viene vacío o ninguna fuente listada sigue existiendo.
        modo = parse_mode(mode)
        self._set_value.validate(project_id, schema_id, field_id, raw_value, modo)

        result = BulkSetSourceMetadataValueResult()
        for source_id in dict.fromkeys(source_ids):  # depura duplicados, conserva el orden
            if self._source_repository.get(project_id, source_id) is None:
                result.skipped_source_ids.append(source_id)
                continue
            self._set_value.execute(project_id, schema_id, source_id, field_id, raw_value, modo)
            result.updated_source_ids.append(source_id)
        return result
