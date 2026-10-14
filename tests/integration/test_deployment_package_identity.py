"""Ronda 95 (hallazgo de integración con NEXOM Testing Agent, proyecto
AGENTE UDL): `package_id` cambiaba en cada exportación (comportamiento
deliberado) y el consumidor lo tomaba como identidad lógica. El manifest
ahora separa explícitamente cada identidad."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from application.release.commands.export_deployment_package import ExportDeploymentPackage
from domain.projects.entities import Project
from domain.release.entities import ProjectSnapshot
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.database.runtime_repositories import SqlAlchemyWidgetTokenRepository
from infrastructure.filesystem.deployment_packager import FilesystemDeploymentPackager
from infrastructure.filesystem.import_batch_ledger import LEDGER_FILENAME
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher

_PID = "6073eda1-268d-48bd-8257-e6d3fef4f981"


def _publicar(paths: InstallationPaths, version: int) -> None:
    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PID, version)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PID, version=version, snapshot_dir=snapshot_dir),
    )


def _exportar(paths: InstallationPaths, destino: Path) -> dict:
    ExportDeploymentPackage(
        SqlAlchemyProjectRepository(paths), SqlAlchemyProjectSnapshotRepository(paths),
        SqlAlchemyWidgetTokenRepository(paths.runtime_db_path()), FilesystemDeploymentPackager(),
    ).execute(_PID, str(destino))
    with zipfile.ZipFile(destino) as zf:
        return json.loads(zf.read("manifest.json"))


def _instalacion(tmp_path: Path) -> InstallationPaths:
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PID)
    SqlAlchemyProjectRepository(paths).save(Project(id=_PID, name="AGENTE UDL"))
    # Procedencia de un lote (con una reimportación idéntica registrada dos veces).
    linea = json.dumps({
        "fingerprint": "sha256:abc", "label": "LIC_DAE/v1", "manifest_schema_version": "2",
        "imported_at": "2026-10-01T00:00:00+00:00", "relation": "lote_nuevo", "related_label": None,
        "rows": [], "complete": True,
    })
    (paths.project_dir(_PID) / LEDGER_FILENAME).write_text(linea + "\n" + linea + "\n", encoding="utf-8")
    return paths


def test_versiones_sucesivas_se_agrupan_por_project_id_y_cada_exportacion_tiene_su_id(tmp_path):
    paths = _instalacion(tmp_path)
    _publicar(paths, 2)
    v2 = _exportar(paths, tmp_path / "v2.zip")
    _publicar(paths, 3)
    _publicar(paths, 4)
    v4 = _exportar(paths, tmp_path / "v4.zip")

    for m in (v2, v4):
        assert m["manifest_version"] == 2
        assert m["package_id"] == m["deployment_package_id"] == m["identity"]["deployment_package_id"]
        assert m["identity"]["grouping_key"] == "project_id"
        assert m["identity"]["knowledge_base_id"] is None
        assert m["identity"]["source_batches"] == [{"fingerprint": "sha256:abc", "label": "LIC_DAE/v1"}]

    assert v2["identity"]["project_id"] == v4["identity"]["project_id"] == v2["project_id"] == _PID
    assert (v2["identity"]["snapshot_version"], v4["identity"]["snapshot_version"]) == (2, 4)
    assert v2["deployment_package_id"] != v4["deployment_package_id"]


def test_dos_exportaciones_de_la_misma_version_comparten_contenido_y_no_id_de_exportacion(tmp_path):
    paths = _instalacion(tmp_path)
    _publicar(paths, 4)
    a = _exportar(paths, tmp_path / "a.zip")
    b = _exportar(paths, tmp_path / "b.zip")
    assert a["identity"]["snapshot_id"] and a["identity"]["snapshot_id"] == b["identity"]["snapshot_id"]
    assert a["identity"]["content_fingerprint"] == b["identity"]["content_fingerprint"]
    assert a["deployment_package_id"] != b["deployment_package_id"]


def test_claves_de_la_version_1_del_manifest_se_conservan(tmp_path):
    paths = _instalacion(tmp_path)
    _publicar(paths, 1)
    m = _exportar(paths, tmp_path / "e.zip")
    for clave in ("package_id", "project_id", "project_name", "snapshot_version", "widget_token_id",
                  "created_at", "instantanea_incluida", "instantanea_archivos"):
        assert clave in m


def test_contrato_y_guia_documentan_las_identidades(tmp_path):
    paths = _instalacion(tmp_path)
    _publicar(paths, 1)
    destino = tmp_path / "e.zip"
    _exportar(paths, destino)
    with zipfile.ZipFile(destino) as zf:
        contrato = zf.read("CONTRATO_INTEGRACION.md").decode("utf-8")
        guia = zf.read("GUIA_DESPLIEGUE.md").decode("utf-8")
        informe = zf.read("INFORME_ENTREGA.md").decode("utf-8")
    # Ronda 96: el informe al cliente también distingue ambas identidades, y el
    # contrato trata manifiestos anteriores como advertencia, no como rechazo.
    assert "deployment_package_id" in informe
    assert "advertencia para revisión del operador" in contrato
    assert "AGENTE UDL -> [su package lógico] -> v2, v4" in contrato
    for texto in ("deployment_package_id", "knowledge_base_id", "Agrupar versiones sucesivas por `project_id`",
                  "No usar `package_id` ni `deployment_package_id` como identidad"):
        assert texto in contrato
    assert "deployment_package_id" in guia


def test_instantanea_antigua_se_identifica_una_vez_y_conserva_su_huella(tmp_path):
    """Auditoría Ronda 95: una instantánea sin snapshot_identity.json (anterior a
    la Ronda 92) recibía una huella recalculada en cada exportación."""
    from infrastructure.filesystem.snapshot_identity import IDENTITY_FILENAME

    paths = _instalacion(tmp_path)
    _publicar(paths, 1)
    (paths.snapshot_version_dir(_PID, 1) / IDENTITY_FILENAME).unlink()
    a = _exportar(paths, tmp_path / "a.zip")
    assert (paths.snapshot_version_dir(_PID, 1) / IDENTITY_FILENAME).exists()
    (paths.snapshot_version_dir(_PID, 1) / "indexes" / "cambio_interno.bin").parent.mkdir(parents=True, exist_ok=True)
    (paths.snapshot_version_dir(_PID, 1) / "indexes" / "cambio_interno.bin").write_bytes(b"x")
    b = _exportar(paths, tmp_path / "b.zip")
    assert a["identity"]["content_fingerprint"] == b["identity"]["content_fingerprint"]
