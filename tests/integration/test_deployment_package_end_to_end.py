"""Prueba de integración real de punta a punta del paquete de entrega
al cliente (Ronda 10, ver Validacion_observaciones_RAG_STUDIO.md):
publica una instantánea real (FilesystemProjectSnapshotPublisher,
project.db real -- sin dobles), exporta el paquete de entrega con
ExportDeploymentPackage contra repositorios SQLAlchemy reales y
FilesystemDeploymentPackager real, y verifica el contenido del .zip
resultante en disco -- ningún componente de esta cadena es un doble."""
from __future__ import annotations

import json
import zipfile

from application.release.commands.export_deployment_package import ExportDeploymentPackage
from domain.projects.entities import Project
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.database.runtime_repositories import SqlAlchemyWidgetTokenRepository
from infrastructure.filesystem.deployment_packager import FilesystemDeploymentPackager
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher

_PROJECT_ID = "p1"


def _publish_sample_project(paths: InstallationPaths) -> None:
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)

    # save() ya crea project.db real (vía migración Alembic, ver
    # ensure_project_db) -- no hace falta (ni se debe) escribirlo a
    # mano: la instantánea copia lo que sea que haya ahí de verdad.
    project_repository = SqlAlchemyProjectRepository(paths)
    project_repository.save(Project(id=_PROJECT_ID, name="Horarios de atención"))

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 1)
    from domain.release.entities import ProjectSnapshot
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=1, snapshot_dir=snapshot_dir),
    )


def test_export_deployment_package_bundles_the_real_snapshot_and_documents(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    _publish_sample_project(paths)

    command = ExportDeploymentPackage(
        SqlAlchemyProjectRepository(paths),
        SqlAlchemyProjectSnapshotRepository(paths),
        SqlAlchemyWidgetTokenRepository(paths.runtime_db_path()),
        FilesystemDeploymentPackager(),
    )
    destination = tmp_path / "entrega.zip"
    result_path = command.execute(_PROJECT_ID, str(destination))

    assert result_path == str(destination)
    assert destination.exists()

    with zipfile.ZipFile(destination) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "INFORME_ENTREGA.md" in names
        assert "GUIA_DESPLIEGUE.md" in names
        assert "CONTRATO_INTEGRACION.md" in names
        assert ".env.example" in names
        assert "widget-embed.html" in names
        assert "instantanea/project.db" in names

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["project_id"] == _PROJECT_ID
        assert manifest["project_name"] == "Horarios de atención"
        assert manifest["snapshot_version"] == 1

        informe = zf.read("INFORME_ENTREGA.md").decode("utf-8")
        assert "Horarios de atención" in informe

        # Ronda 19: el contrato de integración es para quien construye el
        # agente conversacional externo -- debe mencionar el proyecto y
        # los conceptos centrales del contrato HTTP real (conversation_id,
        # los cuatro valores de "action").
        contrato = zf.read("CONTRATO_INTEGRACION.md").decode("utf-8")
        assert "Horarios de atención" in contrato
        assert "conversation_id" in contrato
        assert "responder" in contrato and "aclarar" in contrato
        assert "abstenerse" in contrato and "canalizar" in contrato
        # Pista C.4a del ADR-003 -- captura de señal de relevancia:
        # endpoint opcional documentado en el contrato del agente (no en
        # GUIA_DESPLIEGUE.md, a diferencia de /metrics -- este sí lo
        # llama el agente conversacional externo, no un operador).
        assert "/feedback" in contrato
        assert "citado_en_respuesta" in contrato
        # Pista C.5 del ADR-003 (roadmap de pendientes de RAG 5, Ronda
        # 43/44): page_start/page_end ahora documentados en 'sources'.
        assert "page_start" in contrato and "page_end" in contrato
        # Ronda 58: section_title ahora documentado en 'sources' -- ya
        # no dice que "no hay todavía un título de sección" ahí.
        assert "section_title" in contrato
        # Ronda 59 (roadmap de preparación RAG 3-5): GET /quality (doble
        # validación de calidad) y el flujo de ambiente de pruebas
        # pre-liberación, ambos documentados en el contrato del agente.
        assert "/quality" in contrato and "regression_gate_passed" in contrato
        assert "Ambiente de pruebas pre-liberación" in contrato
        # Ronda 69 (Fase 5 de RAG 3, cierre de documentación): image_results
        # -- tercer canal de evidencia (Fase 3 de multimodalidad nativa),
        # incluida la limitación conocida de no exponer un endpoint HTTP
        # para descargar el archivo de imagen.
        assert "image_results" in contrato and "image_relative_path" in contrato
        assert "Limitación conocida" in contrato

        widget_html = zf.read("widget-embed.html").decode("utf-8")
        assert f'data-project-id="{_PROJECT_ID}"' in widget_html

        # Pista C.1 del ADR-003 -- GUIA_DESPLIEGUE.md documenta el
        # endpoint opcional de métricas (observabilidad básica), en la
        # misma guía operativa que ya documenta widget-tokens (ambas
        # son capacidades administrativas, protegidas por API key).
        guia = zf.read("GUIA_DESPLIEGUE.md").decode("utf-8")
        assert "/metrics" in guia
        assert "X-API-Key" in guia
        # Pista C.5 del ADR-003 (roadmap de pendientes de RAG 5, Ronda
        # 44): percentiles documentados junto al resto de /metrics.
        assert "p95_latency_ms" in guia and "p99_latency_ms" in guia

        # La instantánea copiada dentro del paquete debe ser un archivo
        # real (no vacío) idéntico byte a byte al project.db publicado --
        # mismo criterio de "es una copia real" que ya prueba
        # test_project_snapshot_qdrant_isolation.py.
        bundled_project_db = zf.read("instantanea/project.db")
        assert len(bundled_project_db) > 0
        published_project_db = (
            paths.snapshot_version_dir(_PROJECT_ID, 1) / "project.db"
        ).read_bytes()
        assert bundled_project_db == published_project_db

    # El token de widget emitido para esta entrega debe quedar
    # persistido de verdad en runtime.db (no solo en el zip) -- para que
    # pueda revocarse después vía POST/DELETE /projects/{id}/widget-tokens
    # (ver GUIA_DESPLIEGUE.md dentro del paquete).
    widget_snippet = None
    with zipfile.ZipFile(destination) as zf:
        widget_snippet = zf.read("widget-embed.html").decode("utf-8")
    token_repository = SqlAlchemyWidgetTokenRepository(paths.runtime_db_path())
    tokens = token_repository.list_for_project(_PROJECT_ID)
    assert len(tokens) == 1
    assert tokens[0].token in widget_snippet


def test_export_deployment_package_raises_without_a_published_snapshot(tmp_path):
    from domain.release.exceptions import NoPublishedSnapshotError

    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)
    SqlAlchemyProjectRepository(paths).save(Project(id=_PROJECT_ID, name="Sin instantánea"))

    command = ExportDeploymentPackage(
        SqlAlchemyProjectRepository(paths),
        SqlAlchemyProjectSnapshotRepository(paths),
        SqlAlchemyWidgetTokenRepository(paths.runtime_db_path()),
        FilesystemDeploymentPackager(),
    )
    try:
        command.execute(_PROJECT_ID, str(tmp_path / "entrega.zip"))
        raise AssertionError("debía fallar sin ninguna instantánea publicada")
    except NoPublishedSnapshotError:
        pass
    assert not (tmp_path / "entrega.zip").exists()
