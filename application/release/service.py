"""Fachada de application para el contexto Liberación (Etapa 7).
Depende de los seis facades previos, siguiendo el mismo precedente que
QualityService (que depende de ConversationalService) y
ConversationalService (que depende de RagService)."""
from __future__ import annotations

from typing import Optional

from application.conversational.service import ConversationalService
from application.ingestion.service import IngestionService
from application.metadata.service import MetadataService
from application.pipeline.service import PipelineService
from application.quality.service import QualityService
from application.rag.service import RagService
from domain.projects.ports import ProjectRepository
from domain.release.entities import ProjectSnapshot, ReleaseChecklist, ReleaseRecord
from domain.release.ports import (
    DeploymentPackager,
    ProjectSnapshotPublisher,
    ProjectSnapshotRepository,
    ReleasePackager,
    ReleaseRecordRepository,
)
from domain.runtime.ports import WidgetTokenRepository

from .commands.export_deliverables_package import ExportDeliverablesPackage
from .commands.export_deployment_package import ExportDeploymentPackage
from .commands.publish_project_snapshot import PublishProjectSnapshot
from .commands.request_release import RequestRelease
from .queries.evaluate_release_gates import EvaluateReleaseGates
from .queries.generate_deliverables_report import GenerateDeliverablesReport
from .queries.get_release_record import GetReleaseRecord
from .queries.list_project_snapshots import ListProjectSnapshots
from .queries.list_release_records import ListReleaseRecords


class ReleaseService:
    def __init__(
        self, release_record_repository: ReleaseRecordRepository, metadata_service: MetadataService,
        ingestion_service: IngestionService, pipeline_service: PipelineService, rag_service: RagService,
        conversational_service: ConversationalService, quality_service: QualityService,
        release_packager: Optional[ReleasePackager] = None,
        project_repository: Optional[ProjectRepository] = None,
        snapshot_repository: Optional[ProjectSnapshotRepository] = None,
        snapshot_publisher: Optional[ProjectSnapshotPublisher] = None,
        widget_token_repository: Optional[WidgetTokenRepository] = None,
        deployment_packager: Optional[DeploymentPackager] = None,
    ):
        self._evaluate_gates = EvaluateReleaseGates(
            metadata_service, ingestion_service, pipeline_service, rag_service, conversational_service,
            quality_service, project_repository=project_repository,
        )
        self._generate_report = GenerateDeliverablesReport(
            metadata_service, ingestion_service, pipeline_service, rag_service, conversational_service,
            quality_service,
        )
        self._request_release = RequestRelease(release_record_repository, self._evaluate_gates, self._generate_report)
        self._list_records = ListReleaseRecords(release_record_repository)
        self._get_record = GetReleaseRecord(release_record_repository)
        # release_packager es opcional (igual patrón que
        # embedding_provider_factory/ocr_engine/source_file_store):
        # solo lo necesita export_deliverables_package, ver bootstrap.
        self._export_package = (
            ExportDeliverablesPackage(release_record_repository, release_packager)
            if release_packager is not None else None
        )
        # project_repository/snapshot_repository/snapshot_publisher: igual
        # patrón opcional -- solo los necesita publish_snapshot (ADR-002,
        # Fase 1). Ninguno de los tres es requerido por el resto del
        # panel de Liberación (evaluar compuertas, solicitar liberación,
        # exportar entregables ya funcionan sin instantáneas).
        self._publish_snapshot = (
            PublishProjectSnapshot(project_repository, snapshot_repository, snapshot_publisher)
            if project_repository is not None and snapshot_repository is not None
            and snapshot_publisher is not None else None
        )
        self._list_snapshots = (
            ListProjectSnapshots(snapshot_repository) if snapshot_repository is not None else None
        )
        # deployment_packager (Ronda 10, ver Validacion_observaciones_
        # RAG_STUDIO.md): paquete de entrega al cliente -- igual patrón
        # opcional que el resto de dependencias de esta fachada. Requiere
        # project_repository/snapshot_repository (ya construidos arriba
        # para publish_snapshot) más widget_token_repository, que ningún
        # otro método de este servicio necesitaba hasta ahora.
        self._export_deployment_package = (
            ExportDeploymentPackage(
                project_repository, snapshot_repository, widget_token_repository, deployment_packager,
            )
            if project_repository is not None and snapshot_repository is not None
            and widget_token_repository is not None and deployment_packager is not None else None
        )

    def evaluate_gates(self, project_id: str) -> ReleaseChecklist:
        return self._evaluate_gates.execute(project_id)

    def generate_deliverables_report(self, project_id: str) -> dict:
        return self._generate_report.execute(project_id)

    def request_release(self, project_id: str) -> ReleaseRecord:
        return self._request_release.execute(project_id)

    def list_release_records(self, project_id: str) -> list[ReleaseRecord]:
        return self._list_records.execute(project_id)

    def get_release_record(self, project_id: str, record_id: str) -> Optional[ReleaseRecord]:
        return self._get_record.execute(project_id, record_id)

    def export_deliverables_package(self, project_id: str, record_id: str, destination_path: str) -> str:
        if self._export_package is None:
            raise RuntimeError(
                "Esta instalación no tiene configurado un empaquetador de entregables "
                "(release_packager); no se puede exportar el paquete."
            )
        return self._export_package.execute(project_id, record_id, destination_path)

    def publish_snapshot(self, project_id: str, source_release_id: Optional[str] = None) -> ProjectSnapshot:
        """ADR-002, Fase 1: publica una instantánea de solo lectura del
        proyecto, separada de los archivos en edición."""
        if self._publish_snapshot is None:
            raise RuntimeError(
                "Esta instalación no tiene configurado el mecanismo de instantáneas "
                "(project_repository/snapshot_repository/snapshot_publisher); no se puede publicar."
            )
        return self._publish_snapshot.execute(project_id, source_release_id)

    def list_snapshots(self, project_id: str) -> list[ProjectSnapshot]:
        if self._list_snapshots is None:
            return []
        return self._list_snapshots.execute(project_id)

    def export_deployment_package(self, project_id: str, destination_path: str) -> str:
        """Ronda 10: exporta el paquete de entrega al cliente (instantánea
        publicada + token de widget + guía de despliegue + informe formal)
        -- ver ExportDeploymentPackage. Requiere una instantánea publicada
        (NoPublishedSnapshotError si no hay ninguna)."""
        if self._export_deployment_package is None:
            raise RuntimeError(
                "Esta instalación no tiene configurado el empaquetador de entrega al cliente "
                "(project_repository/snapshot_repository/widget_token_repository/"
                "deployment_packager); no se puede exportar el paquete."
            )
        return self._export_deployment_package.execute(project_id, destination_path)
