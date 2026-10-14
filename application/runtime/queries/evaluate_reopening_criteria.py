"""Ronda 56 -- computa, en vez de exigir una consulta SQL manual sobre
el project.db/runtime.db real cada ronda de consultoría (ver Rondas
43/45/50), si ya se cumplen los criterios de reapertura escritos en la
Ronda 45 (RAG_STUDIO_Propuesta_Roadmap_RAG5_Pendientes.docx, sección 9)
para los dos pendientes de RAG 5 diferidos por falta de evidencia de
uso real: alertas proactivas de observabilidad, y el ajuste automático
del retrieval (aprendizaje, Opción 3).

Vive en application (no en domain) porque orquesta cuatro puertos de
tres contextos distintos (Proyectos, Runtime -- bitácora, feedback y
tokens de widget) -- mismo criterio ya usado por
`application.release.queries.evaluate_release_gates.EvaluateReleaseGates`
para una orquestación cruzada equivalente."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.projects.entities import ProjectStatus
from domain.projects.ports import ProjectRepository
from domain.runtime.entities import ReopeningCriteriaStatus
from domain.runtime.ports import ConversationLogRepository, RetrievalFeedbackRepository, WidgetTokenRepository

from ..options import (
    REOPENING_ALERTAS_PROACTIVAS_MIN_TURNOS_30D,
    REOPENING_APRENDIZAJE_MIN_DIAS_DE_USO,
    REOPENING_APRENDIZAJE_MIN_ENTRADAS,
    REOPENING_APRENDIZAJE_MIN_FUENTES_DISTINTAS,
)


class EvaluateReopeningCriteria:
    def __init__(
        self, project_repository: ProjectRepository, widget_token_repository: WidgetTokenRepository,
        log_repository: ConversationLogRepository, feedback_repository: RetrievalFeedbackRepository,
    ):
        self._projects = project_repository
        self._widget_tokens = widget_token_repository
        self._log_repository = log_repository
        self._feedback_repository = feedback_repository

    def execute(self, project_id: str) -> ReopeningCriteriaStatus:
        now = datetime.now(timezone.utc)

        # Alertas proactivas -- condición 1: el proyecto llegó a
        # LIBERADO. Un project_id que no existe (borrado, o un error
        # de quien llama) se trata como "no liberado", no como una
        # excepción: este chequeo es un diagnóstico de solo lectura,
        # no una operación que deba fallar de forma ruidosa.
        project = self._projects.get(project_id)
        proyecto_liberado = project is not None and project.status == ProjectStatus.LIBERADO

        # Condición 2: al menos un WidgetToken activo (sin revocar).
        tokens = self._widget_tokens.list_for_project(project_id)
        token_widget_activo = any(token.is_active for token in tokens)

        # Condición 3: al menos N turnos reales en los últimos 30 días
        # naturales -- se reutiliza get_metrics_summary (agregación en
        # SQL, sin traer filas completas a memoria), mismo criterio que
        # ya usa el panel de Monitoreo.
        since_30d = now - timedelta(days=30)
        metrics = self._log_repository.get_metrics_summary(project_id, since=since_30d)
        turnos_30d = metrics.total_turns
        alertas_proactivas_reunidas = (
            proyecto_liberado
            and token_widget_activo
            and turnos_30d >= REOPENING_ALERTAS_PROACTIVAS_MIN_TURNOS_30D
        )

        # Aprendizaje del retrieval, Opción 3 -- las tres condiciones
        # se calculan sobre el historial completo (since=None): a
        # diferencia de "alertas proactivas" (una ventana reciente de
        # tráfico sostenido), aquí lo que se mide es si YA existe
        # suficiente evidencia acumulada, sin importar cuándo empezó.
        entradas = self._feedback_repository.list_for_project(project_id, since=None)
        total_entradas = len(entradas)
        fuentes_distintas = len({entry.source_id for entry in entradas})
        if entradas:
            primera_entrada = min(entry.created_at for entry in entradas)
            dias_de_uso: int | None = (now - primera_entrada).days
        else:
            dias_de_uso = None
        aprendizaje_opcion3_reunidas = (
            total_entradas >= REOPENING_APRENDIZAJE_MIN_ENTRADAS
            and fuentes_distintas >= REOPENING_APRENDIZAJE_MIN_FUENTES_DISTINTAS
            and dias_de_uso is not None
            and dias_de_uso >= REOPENING_APRENDIZAJE_MIN_DIAS_DE_USO
        )

        return ReopeningCriteriaStatus(
            project_id=project_id, checked_at=now,
            proyecto_liberado=proyecto_liberado, token_widget_activo=token_widget_activo,
            turnos_ultimos_30_dias=turnos_30d, alertas_proactivas_reunidas=alertas_proactivas_reunidas,
            entradas_feedback_totales=total_entradas, fuentes_distintas_en_feedback=fuentes_distintas,
            dias_desde_la_primera_entrada=dias_de_uso, aprendizaje_opcion3_reunidas=aprendizaje_opcion3_reunidas,
        )
