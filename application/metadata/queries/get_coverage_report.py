"""Reporte de cobertura de metadatos.

Operacionaliza el criterio de aceptación de A1 (RAG STUDIO
INVESTIGACION.odt): "la especificación se considera completa cuando
puede describir al menos el 95% de las fuentes de prueba sin recurrir
a campos genéricos o texto libre no controlado".

Interpretación explícita (declarada, no es texto literal de la
fuente): coverage_ratio = proporción de fuentes con TODOS los campos
obligatorios del esquema activo con un valor asignado.
controlled_value_ratio = de todos los valores de metadatos guardados
para el proyecto, qué fracción corresponde a campos NO de texto libre
(catálogo, fecha, número, booleano, etc.) frente a TEXTO/TEXTO_LARGO.
Ambas métricas son complementarias; el umbral de aceptación (≥95%) se
aplica aquí a coverage_ratio.

coverage_ratio ya considera document_type_code (ver
domain.metadata.entities.fields_applicable_to, punto 10 de
Validacion_observaciones_RAG_STUDIO.md): un campo obligatorio de un
tipo de documento distinto al de la fuente no se exige para esa
fuente. controlled_value_ratio no necesita este filtro -- solo mira
los valores que de hecho ya se guardaron, nunca "campos que deberían
tener valor pero no aplican".
"""
from __future__ import annotations

from typing import Optional

from domain.documents.ports import SourceRepository
from domain.metadata.entities import FREE_TEXT_TYPES, fields_applicable_to
from domain.metadata.exceptions import MetadataDomainError
from domain.metadata.ports import MetadataSchemaRepository, SourceMetadataRepository

ACCEPTANCE_THRESHOLD = 0.95


class GetSourceMetadataCoverageReport:
    def __init__(
        self,
        source_repository: SourceRepository,
        schema_repository: MetadataSchemaRepository,
        source_metadata_repository: SourceMetadataRepository,
    ):
        self._source_repository = source_repository
        self._schema_repository = schema_repository
        self._source_metadata_repository = source_metadata_repository

    def execute(self, project_id: str) -> dict:
        schema = self._schema_repository.get_active_schema(project_id)
        if schema is None:
            raise MetadataDomainError(f"No hay esquema de metadatos activo para {project_id!r}")

        fields = self._schema_repository.list_fields(project_id, schema.id)
        field_by_id = {f.field_id: f for f in fields}

        sources = self._source_repository.list_for_project(project_id)
        if not sources:
            return {
                "total_sources": 0, "sources_fully_described": 0,
                "coverage_ratio": None, "controlled_value_ratio": None,
                "meets_acceptance_threshold": False,
            }

        fully_described = 0
        total_values = 0
        controlled_values = 0
        for source in sources:
            # Punto 10 de Validacion_observaciones_RAG_STUDIO.md: un campo
            # obligatorio solo cuenta contra una fuente si de verdad le
            # aplica (genérico, o de su mismo document_type_code) -- sin
            # este filtro, una fuente de "contactos" nunca podría quedar
            # "completa" mientras existiera un campo obligatorio propio
            # de otro tipo de documento (p. ej. "requisitos de admisión").
            applicable_required_ids = {
                f.field_id for f in fields_applicable_to(fields, source.document_type_code) if f.required
            }
            values = self._source_metadata_repository.list_values_for_source(project_id, source.id)
            present_field_ids = {v.field_id for v in values}
            if applicable_required_ids.issubset(present_field_ids):
                fully_described += 1
            for v in values:
                total_values += 1
                field = field_by_id.get(v.field_id)
                if field is not None and field.data_type not in FREE_TEXT_TYPES:
                    controlled_values += 1

        coverage_ratio = fully_described / len(sources)
        controlled_ratio: Optional[float] = (controlled_values / total_values) if total_values else None

        return {
            "total_sources": len(sources),
            "sources_fully_described": fully_described,
            "coverage_ratio": coverage_ratio,
            "controlled_value_ratio": controlled_ratio,
            "meets_acceptance_threshold": coverage_ratio >= ACCEPTANCE_THRESHOLD,
        }
