"""Compuertas de avance (RAG STUDIO.odt: "Debe existir..." por etapa)
evaluadas antes de permitir una liberación.

Alcance (ver domain/release/entities.py y README): compuertas para las
etapas 2-6 (metadatos, fragmentación, pipeline, índice, diseño
conversacional, calidad). No hay compuerta de etapa 1 (Objetivo/
Usuarios/Alcance/Fuentes iniciales/Riesgo) porque `Project` no tiene
esos campos."""
from __future__ import annotations

from typing import Optional

from application.conversational.service import ConversationalService
from application.ingestion.service import IngestionService
from application.metadata.service import MetadataService
from application.pipeline.service import PipelineService
from application.quality.options import DEFAULT_QUALITY_REGRESSION_THRESHOLD
from application.quality.service import QualityService
from application.rag.service import RagService
from domain.metadata.exceptions import MetadataDomainError
from domain.projects.ports import ProjectRepository
from domain.quality.entities import RetrievalRegressionStatus, compare_retrieval_regression
from domain.release.entities import GateResult, ReleaseChecklist


class EvaluateReleaseGates:
    def __init__(
        self, metadata_service: MetadataService, ingestion_service: IngestionService,
        pipeline_service: PipelineService, rag_service: RagService,
        conversational_service: ConversationalService, quality_service: QualityService,
        project_repository: Optional[ProjectRepository] = None,
    ):
        self._metadata = metadata_service
        self._ingestion = ingestion_service
        self._pipeline = pipeline_service
        self._rag = rag_service
        self._conversational = conversational_service
        self._quality = quality_service
        # project_repository es opcional (mismo patrón que en
        # ReleaseService/QualityService): sin él, la compuerta de
        # regresión de recuperación (Ronda 53) sigue funcionando, solo
        # que siempre con el umbral por defecto de la instalación --
        # nunca deja de evaluarse por falta de este parámetro.
        self._projects = project_repository

    def execute(self, project_id: str) -> ReleaseChecklist:
        gates = [
            self._metadata_gate(project_id),
            self._fragmentation_gate(project_id),
            self._pipeline_gate(project_id),
            self._index_gate(project_id),
            self._conversational_gate(project_id),
            self._quality_gate(project_id),
            self._retrieval_regression_gate(project_id),
        ]
        return ReleaseChecklist(gates=gates)

    def _metadata_gate(self, project_id: str) -> GateResult:
        try:
            _schema, fields = self._metadata.get_schema(project_id)
        except MetadataDomainError:
            return GateResult(
                name="Metadatos", passed=False,
                reason="No hay un esquema de metadatos activo para el proyecto.",
            )
        if not fields:
            return GateResult(
                name="Metadatos", passed=False,
                reason="El esquema de metadatos activo no tiene campos definidos.",
            )
        return GateResult(
            name="Metadatos", passed=True, reason=f"Esquema activo con {len(fields)} campo(s) definido(s).",
        )

    def _fragmentation_gate(self, project_id: str) -> GateResult:
        policies = self._ingestion.list_fragmentation_policies(project_id)
        if not policies:
            return GateResult(
                name="Fragmentación", passed=False,
                reason="No hay ninguna política de fragmentación configurada.",
            )
        return GateResult(
            name="Fragmentación", passed=True,
            reason=f"{len(policies)} política(s) de fragmentación configurada(s).",
        )

    def _pipeline_gate(self, project_id: str) -> GateResult:
        runs = self._pipeline.list_runs(project_id)
        last_run = runs[0] if runs else None
        if last_run is None:
            return GateResult(
                name="Pipeline reproducible", passed=False,
                reason="No se ha ejecutado ninguna corrida del pipeline.",
            )
        if not last_run.is_usable_as_index_base:
            return GateResult(
                name="Pipeline reproducible", passed=False,
                reason="La última corrida del pipeline no terminó en un estado utilizable como base del índice.",
            )
        return GateResult(
            name="Pipeline reproducible", passed=True,
            reason="La última corrida del pipeline es utilizable como base del índice.",
        )

    def _index_gate(self, project_id: str) -> GateResult:
        info = self._rag.get_index_info(project_id)
        if info is None or info.points_count <= 0:
            return GateResult(
                name="Índice y recuperación", passed=False,
                reason="No existe un índice con fragmentos indexados.",
            )
        return GateResult(
            name="Índice y recuperación", passed=True,
            reason=f"Índice con {info.points_count} fragmento(s) indexado(s).",
        )

    def _conversational_gate(self, project_id: str) -> GateResult:
        intents = self._conversational.list_intents(project_id)
        guardrails = self._conversational.list_guardrail_rules(project_id)
        has_active_intent = any(intent.active for intent in intents)
        has_active_guardrail = any(rule.active for rule in guardrails)
        if not has_active_intent or not has_active_guardrail:
            missing = []
            if not has_active_intent:
                missing.append("ninguna intención activa")
            if not has_active_guardrail:
                missing.append("ningún guardrail activo")
            return GateResult(
                name="Diseño conversacional", passed=False,
                reason=f"Falta configuración mínima: {', '.join(missing)}.",
            )
        return GateResult(
            name="Diseño conversacional", passed=True,
            reason="Hay al menos una intención activa y un guardrail activo.",
        )

    def _quality_gate(self, project_id: str) -> GateResult:
        cases = self._quality.list_test_cases(project_id)
        if not cases:
            return GateResult(
                name="Calidad", passed=False, reason="No hay ningún caso de prueba en el banco de pruebas.",
            )
        runs = self._quality.list_evaluation_runs(project_id)
        last_run = runs[0] if runs else None
        if last_run is None:
            return GateResult(
                name="Calidad", passed=False, reason="No se ha ejecutado ninguna corrida de evaluación.",
            )
        if last_run.has_blocking_failures:
            return GateResult(
                name="Calidad", passed=False,
                reason="La última corrida de evaluación tiene al menos un hallazgo en rojo (bloqueo).",
            )
        return GateResult(
            name="Calidad", passed=True,
            reason=f"{len(cases)} caso(s) de prueba, última corrida sin bloqueos.",
        )

    def _retrieval_regression_gate(self, project_id: str) -> GateResult:
        """Ronda 53 (Propuesta de evaluación continua reforzada,
        opción B' confirmada por el consultor): compuerta nueva,
        separada de "Calidad" (que solo bloquea por casos individuales
        en ROJO) -- bloquea si Recall@3 o MRR cayeron más del umbral
        configurado respecto de la corrida "completa" de referencia
        (la inmediatamente anterior a la más reciente, ambas del mismo
        alcance -- comparar contra una corrida "individual" o "por
        categoría" no sería significativo, ver ListCompleteEvaluationRuns).

        Deliberadamente NUNCA bloquea por falta de datos (menos de dos
        corridas "completa", o sin una base comparable) -- esa
        responsabilidad ya es de la compuerta "Calidad" (banco de
        pruebas vacío / ninguna corrida ejecutada). Esta compuerta solo
        bloquea ante una regresión medible de verdad.

        Ronda 84 (hallazgo real de usuario, ver bitácora): la
        clasificación de qué corridas tienen métricas vive en
        domain.quality.entities.compare_retrieval_regression (Ronda 83
        seguía un `if ... or ...` que confundía "ninguna corrida tiene
        fuente esperada" con "solo la corrida de referencia no la
        tiene" -- un caso muy distinto y engañoso para el usuario, que
        ya había calculado métricas reales en la corrida más reciente)."""
        complete_runs = self._quality.list_complete_evaluation_runs(project_id)
        if len(complete_runs) < 2:
            return GateResult(
                name="Regresión de recuperación", passed=True,
                reason="Menos de dos corridas \"completa\" registradas todavía -- nada que comparar.",
            )
        current, reference = complete_runs[0], complete_runs[1]
        comparison = compare_retrieval_regression(current, reference)

        if comparison.status is RetrievalRegressionStatus.SIN_METRICAS_EN_LA_MAS_RECIENTE:
            return GateResult(
                name="Regresión de recuperación", passed=True,
                reason=(
                    "La corrida \"completa\" más reciente no tiene casos con fuente esperada "
                    "declarada -- no hay Recall@3/MRR que comparar."
                ),
            )
        if comparison.status is RetrievalRegressionStatus.SIN_CORRIDA_ANTERIOR_COMPARABLE:
            return GateResult(
                name="Regresión de recuperación", passed=True,
                reason=(
                    "La corrida \"completa\" más reciente contiene casos con fuente esperada, pero "
                    "la corrida \"completa\" anterior no tiene métricas Recall@3/MRR disponibles; "
                    "todavía no existe una base comparable para evaluar regresión."
                ),
            )

        threshold = self._regression_threshold(project_id)
        assert comparison.current_recall is not None and comparison.reference_recall is not None
        assert comparison.current_mrr is not None and comparison.reference_mrr is not None
        assert comparison.worst_drop is not None
        if comparison.worst_drop > threshold:
            return GateResult(
                name="Regresión de recuperación", passed=False,
                reason=(
                    f"Recall@3 cayó de {comparison.reference_recall:.0%} a {comparison.current_recall:.0%} y "
                    f"MRR de {comparison.reference_mrr:.2f} a {comparison.current_mrr:.2f} respecto de la "
                    f"corrida \"completa\" de referencia -- caída de {comparison.worst_drop:.0%}, por encima "
                    f"del umbral configurado ({threshold:.0%})."
                ),
            )
        return GateResult(
            name="Regresión de recuperación", passed=True,
            reason=(
                f"Recall@3: {comparison.current_recall:.0%} (referencia: {comparison.reference_recall:.0%}), "
                f"MRR: {comparison.current_mrr:.2f} (referencia: {comparison.reference_mrr:.2f}) -- sin caída "
                f"por encima del umbral configurado ({threshold:.0%})."
            ),
        )

    def _regression_threshold(self, project_id: str) -> float:
        """Umbral configurado por el proyecto (Project.quality_
        regression_threshold), o el de la instalación si el proyecto no
        configuró uno propio, o si esta instancia no tiene acceso al
        repositorio de proyectos (ver __init__)."""
        if self._projects is not None:
            project = self._projects.get(project_id)
            if project is not None and project.quality_regression_threshold is not None:
                return project.quality_regression_threshold
        return DEFAULT_QUALITY_REGRESSION_THRESHOLD
