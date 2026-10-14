"""Solicita una liberación: evalúa las compuertas, compila los
entregables y persiste el veredicto (RAG STUDIO.odt: "la aplicación
debe bloquear una liberación cuando exista..." -- aquí, cuando
cualquier compuerta falle)."""
from __future__ import annotations

from domain.release.entities import ReleaseChecklist, ReleaseRecord, ReleaseStatus
from domain.release.ports import ReleaseRecordRepository

from ..queries.evaluate_release_gates import EvaluateReleaseGates
from ..queries.generate_deliverables_report import GenerateDeliverablesReport


class RequestRelease:
    def __init__(
        self, release_record_repository: ReleaseRecordRepository, evaluate_gates: EvaluateReleaseGates,
        generate_deliverables_report: GenerateDeliverablesReport,
    ):
        self._repository = release_record_repository
        self._evaluate_gates = evaluate_gates
        self._generate_report = generate_deliverables_report

    def execute(self, project_id: str) -> ReleaseRecord:
        checklist = self._evaluate_gates.execute(project_id)
        deliverables_report = self._generate_report.execute(project_id)
        status = ReleaseStatus.APROBADA if checklist.all_passed else ReleaseStatus.BLOQUEADA
        dictamen = self._build_dictamen(checklist)
        evidence = self._build_evidence(deliverables_report)
        record = ReleaseRecord(
            project_id=project_id, status=status, checklist=checklist, dictamen=dictamen,
            evidence=evidence, deliverables_report=deliverables_report,
        )
        self._repository.save(record)
        return record

    @staticmethod
    def _build_dictamen(checklist: ReleaseChecklist) -> str:
        if checklist.all_passed:
            return f"Liberación aprobada: las {len(checklist.gates)} compuertas evaluadas se cumplieron."
        failed_names = ", ".join(gate.name for gate in checklist.failed_gates)
        return f"Liberación bloqueada: no se cumplieron las siguientes compuertas: {failed_names}."

    @staticmethod
    def _build_evidence(deliverables_report: dict) -> dict[str, str | None]:
        pipeline_info = deliverables_report.get("pipeline_reproducible", {}).get("ultima_corrida")
        matriz_info = deliverables_report.get("matriz_resultados_esperados", {}).get("ultima_corrida")
        schema_info = deliverables_report.get("especificacion_metadatos", {}).get("esquema_activo")
        return {
            "esquema_metadatos_id": schema_info,
            "pipeline_run_id": pipeline_info.get("id") if pipeline_info else None,
            "evaluation_run_id": matriz_info.get("id") if matriz_info else None,
        }
