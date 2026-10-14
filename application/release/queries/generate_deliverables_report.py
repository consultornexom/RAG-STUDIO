"""Genera los 8 entregables formales que el documento maestro exige
("A y B" -- especificación de metadatos, diseño de fragmentación,
pipeline reproducible, índice y reporte de recuperación, catálogo de
reglas, esquema de canalización, banco de pruebas, matriz de
resultados esperados), compilados a partir de los seis contextos ya
existentes.

Decisión de alcance: el reporte se compila como un dict serializable a
JSON y se guarda inline en `ReleaseRecord.deliverables_report` -- ese
sigue siendo el registro auditable de verdad, consultado en el
historial de liberaciones. Para compartirlo fuera de la app como
archivos reales (ítem 6 de la evaluación de madurez post-8-etapas, ver
README/bitácora), `ReleaseService.export_deliverables_package` toma un
`ReleaseRecord` ya generado y lo serializa a un `.zip` -- un archivo
JSON por entregable, más manifest/dictamen/checklist -- sin volver a
calcular nada de lo que ya está aquí."""
from __future__ import annotations

from typing import Any

from application.conversational.service import ConversationalService
from application.ingestion.service import IngestionService
from application.metadata.service import MetadataService
from application.pipeline.service import PipelineService
from application.quality.service import QualityService
from application.rag.service import RagService
from domain.metadata.exceptions import MetadataDomainError


class GenerateDeliverablesReport:
    def __init__(
        self, metadata_service: MetadataService, ingestion_service: IngestionService,
        pipeline_service: PipelineService, rag_service: RagService,
        conversational_service: ConversationalService, quality_service: QualityService,
    ):
        self._metadata = metadata_service
        self._ingestion = ingestion_service
        self._pipeline = pipeline_service
        self._rag = rag_service
        self._conversational = conversational_service
        self._quality = quality_service

    def execute(self, project_id: str) -> dict[str, Any]:
        return {
            "especificacion_metadatos": self._especificacion_metadatos(project_id),
            "diseno_fragmentacion": self._diseno_fragmentacion(project_id),
            "pipeline_reproducible": self._pipeline_reproducible(project_id),
            "indice_y_recuperacion": self._indice_y_recuperacion(project_id),
            "catalogo_reglas": self._catalogo_reglas(project_id),
            "esquema_canalizacion": self._esquema_canalizacion(project_id),
            "banco_de_pruebas": self._banco_de_pruebas(project_id),
            "matriz_resultados_esperados": self._matriz_resultados_esperados(project_id),
        }

    def _especificacion_metadatos(self, project_id: str) -> dict[str, Any]:
        try:
            schema, fields = self._metadata.get_schema(project_id)
        except MetadataDomainError:
            return {"esquema_activo": None, "campos": []}
        catalogs = self._metadata.list_catalogs(project_id)
        return {
            "esquema_activo": schema.id,
            "campos": [
                {
                    "field_id": f.field_id, "nombre": f.display_name, "tipo": f.data_type.value,
                    "obligatorio": f.required, "filtrable": f.filterable, "catalogo_id": f.catalog_id,
                    # Ronda 3/4 (punto 12): sin esto, el entregable formal
                    # no reflejaba que un campo solo aplica a un tipo de
                    # documento concreto (None = genérico, aplica a
                    # todas las fuentes -- ver fields_applicable_to).
                    "document_type_code": f.document_type_code,
                }
                for f in fields
            ],
            "catalogos": [{"id": c.id, "nombre": c.name} for c in catalogs],
        }

    def _diseno_fragmentacion(self, project_id: str) -> dict[str, Any]:
        policies = self._ingestion.list_fragmentation_policies(project_id)
        return {
            "politicas": [
                {
                    "tipo_documental": p.document_type_code, "estrategia": p.strategy.value,
                    "tamano_objetivo": p.target_tokens, "solapamiento": p.overlap_tokens,
                    "minimo": p.min_tokens,
                }
                for p in policies
            ],
        }

    def _pipeline_reproducible(self, project_id: str) -> dict[str, Any]:
        runs = self._pipeline.list_runs(project_id)
        last_run = runs[0] if runs else None
        return {
            "total_corridas": len(runs),
            "ultima_corrida": None if last_run is None else {
                "id": last_run.id, "estado": last_run.status.value,
                "utilizable_como_base_de_indice": last_run.is_usable_as_index_base,
                "tiene_errores_criticos": last_run.has_critical_errors,
                "iniciada": last_run.started_at.isoformat(),
            },
        }

    def _indice_y_recuperacion(self, project_id: str) -> dict[str, Any]:
        info = self._rag.get_index_info(project_id)
        if info is None:
            return {"existe": False}
        return {
            "existe": True, "proveedor": info.embedding_provider, "modelo": info.embedding_model,
            "dimensiones": info.dimensions, "fragmentos_indexados": info.points_count,
        }

    def _catalogo_reglas(self, project_id: str) -> dict[str, Any]:
        rules = self._conversational.list_guardrail_rules(project_id)
        return {
            "reglas": [
                {
                    "nombre": r.name, "tipo": r.rule_type.value, "accion": r.action.value,
                    "prioridad": r.priority, "activa": r.active, "condiciones": len(r.conditions),
                }
                for r in rules
            ],
        }

    def _esquema_canalizacion(self, project_id: str) -> dict[str, Any]:
        schemes = self._conversational.list_channeling_schemes(project_id)
        return {
            "esquemas": [
                {
                    "codigo": s.code, "nombre": s.name, "motivo": s.reason, "medio": s.medium.value,
                    "area_destino": s.target_area, "activo": s.active,
                }
                for s in schemes
            ],
        }

    def _banco_de_pruebas(self, project_id: str) -> dict[str, Any]:
        cases = self._quality.list_test_cases(project_id)
        return {
            "casos": [
                {
                    "codigo": c.code, "categoria": c.category.value, "severidad": c.severity.value,
                    "activo": c.active,
                }
                for c in cases
            ],
        }

    def _matriz_resultados_esperados(self, project_id: str) -> dict[str, Any]:
        runs = self._quality.list_evaluation_runs(project_id)
        last_run = runs[0] if runs else None
        if last_run is None:
            return {"ultima_corrida": None}
        verdes = sum(1 for item in last_run.items if item.verdict.value == "verde")
        return {
            "ultima_corrida": {
                "id": last_run.id, "total_pruebas": len(last_run.items), "aprobadas": verdes,
                "fallidas": len(last_run.items) - verdes, "bloqueos": last_run.has_blocking_failures,
                "dictamen": last_run.overall_verdict.value,
            },
        }
