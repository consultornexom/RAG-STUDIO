"""RAG-INC-01b — caso de uso ExportKnowledgePackage, copia del id_scheme
firmado y prueba de arquitectura del repositorio de instantáneas."""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import re
from pathlib import Path

import pytest

from application.knowledge_package.commands.export_knowledge_package import (
    ExportKnowledgePackage,
    export_knowledge_package,
)
from domain.knowledge_package.entities import KnowledgePackageExportResult, SnapshotDescriptor
from domain.knowledge_package.exceptions import MissingTenantError, SnapshotNotFoundError
from domain.knowledge_package.ports import KnowledgePackageExporter
from domain.release.entities import ProjectSnapshot
from domain.release.ports import ProjectSnapshotRepository

from .fakes_release import InMemoryProjectSnapshotRepository

RAIZ = Path(__file__).resolve().parents[3]
ID_SCHEME_FIRMADO_SHA256 = "559847df560b8033b20a4e797ca32448320eef8d84f81cb654bcad6c1a942ba8"


class _Exportador(KnowledgePackageExporter):
    def __init__(self):
        self.llamadas: list[tuple] = []

    def export(self, snapshot, tenant, output_dir):
        self.llamadas.append((snapshot, tenant, output_dir))
        return KnowledgePackageExportResult(
            package_id="urn:nexom:package:" + "0" * 32, knowledge_base_id="kb", snapshot_id=snapshot.id,
            tenant=tenant, zip_path="x.zip", content_digest_path="x.content.sha256", content_digest="d",
            checksums_json_hash="c", zip_sha256="z",
        )


def _caso():
    repo = InMemoryProjectSnapshotRepository()
    snap = ProjectSnapshot(project_id="p", version=3, snapshot_dir="/snap/v3")
    repo.save(snap)
    exportador = _Exportador()
    return ExportKnowledgePackage(repo, exportador), exportador, snap


@pytest.mark.parametrize("tenant", ["", "   ", None])
def test_tenant_obligatorio_antes_de_todo(tenant):
    caso, exportador, snap = _caso()
    with pytest.raises(MissingTenantError):
        caso.execute("p", snap.id, tenant, "/salida")
    assert exportador.llamadas == []


def test_instantanea_inexistente_o_de_otro_proyecto():
    caso, exportador, snap = _caso()
    with pytest.raises(SnapshotNotFoundError):
        caso.execute("p", "otro-id", "t", "/salida")
    with pytest.raises(SnapshotNotFoundError):
        caso.execute("otro-proyecto", snap.id, "t", "/salida")
    assert exportador.llamadas == []


def test_descriptor_inmutable_y_tenant_normalizado():
    caso, exportador, snap = _caso()
    r = export_knowledge_package(caso, "p", snap.id, "  nexom  ", "/salida")
    descriptor, tenant, salida = exportador.llamadas[0]
    assert isinstance(descriptor, SnapshotDescriptor) and tenant == "nexom" and salida == "/salida"
    assert (descriptor.id, descriptor.version, descriptor.snapshot_dir) == (snap.id, 3, "/snap/v3")
    with pytest.raises(dataclasses.FrozenInstanceError):
        descriptor.version = 4  # type: ignore[misc]
    assert r.snapshot_id == snap.id


def test_repositorio_de_instantaneas_es_de_solo_insercion():
    """Alcance firmado, hito 01b: el registro de una instantánea es inmutable;
    el puerto no debe tener ninguna operación de actualización."""
    metodos = {n for n, m in inspect.getmembers(ProjectSnapshotRepository, inspect.isfunction) if not n.startswith("_")}
    assert metodos == {"save", "list_for_project", "get_latest", "get"}
    prohibidos = re.compile(r"update|delete|remove|replace|set_|modify|edit|upsert", re.IGNORECASE)
    assert not [n for n in metodos if prohibidos.search(n)]


def test_id_scheme_vendorizado_identico_al_firmado():
    copia = RAIZ / "contracts" / "nexom_knowledge_package" / "v1_0_0" / "common" / "id_scheme.py"
    assert hashlib.sha256(copia.read_bytes()).hexdigest() == ID_SCHEME_FIRMADO_SHA256
    sumas = RAIZ / "docs proyecto" / "NEXOM_Knowledge_Package_v1" / "contrato_v1.0.0" / "SHA256SUMS"
    if sumas.exists():
        assert f"{ID_SCHEME_FIRMADO_SHA256}  common/id_scheme.py" in sumas.read_text()


def test_package_id_determinista_y_con_formato_del_contrato():
    from infrastructure.exporters.nexom_knowledge_package import package_id_for

    a = package_id_for("5f9d5e2a-7b4a-4e1a-9c3a-1a2b3c4d5e6f", "snap", "tenant")
    assert a == package_id_for("5f9d5e2a-7b4a-4e1a-9c3a-1a2b3c4d5e6f", "snap", "tenant")
    assert re.fullmatch(r"urn:nexom:package:[0-9a-f]{32}", a)
    assert a != package_id_for("5f9d5e2a-7b4a-4e1a-9c3a-1a2b3c4d5e6f", "snap", "otro")
