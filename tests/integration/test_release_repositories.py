"""Pruebas de integración reales (SQLite vía Alembic) del repositorio
del contexto Liberación (Etapa 7), del empaquetador de entregables
(ítem 6 de la evaluación de madurez post-8-etapas), y de las
instantáneas publicadas de proyecto (ADR-002, Fase 1)."""
import json
import zipfile

from domain.release.entities import GateResult, ProjectSnapshot, ReleaseChecklist, ReleaseRecord, ReleaseStatus
from infrastructure.database.release_repositories import (
    SqlAlchemyProjectSnapshotRepository,
    SqlAlchemyReleaseRecordRepository,
)
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.filesystem.release_packager import FilesystemReleasePackager


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_release_record_round_trip_preserves_all_fields(tmp_path):
    repo = SqlAlchemyReleaseRecordRepository(_paths(tmp_path))
    checklist = ReleaseChecklist(gates=[
        GateResult(name="Metadatos", passed=True, reason="esquema con 2 campos"),
        GateResult(name="Calidad", passed=False, reason="sin casos de prueba"),
    ])
    record = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.BLOQUEADA, checklist=checklist,
        dictamen="Liberación bloqueada: no se cumplieron las siguientes compuertas: Calidad.",
        evidence={"pipeline_run_id": "run-1", "evaluation_run_id": None},
        deliverables_report={"especificacion_metadatos": {"campos": ["titulo"]}},
    )
    repo.save(record)

    fetched = repo.get("p1", record.id)
    assert fetched is not None
    assert fetched.status == ReleaseStatus.BLOQUEADA
    assert fetched.checklist.all_passed is False
    assert [g.name for g in fetched.checklist.failed_gates] == ["Calidad"]
    assert fetched.dictamen == record.dictamen
    assert fetched.evidence == {"pipeline_run_id": "run-1", "evaluation_run_id": None}
    assert fetched.deliverables_report == {"especificacion_metadatos": {"campos": ["titulo"]}}


def test_release_record_get_returns_none_for_wrong_project(tmp_path):
    repo = SqlAlchemyReleaseRecordRepository(_paths(tmp_path))
    record = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.APROBADA, checklist=ReleaseChecklist(gates=[]), dictamen="ok",
    )
    repo.save(record)
    assert repo.get("p2", record.id) is None


def test_release_record_list_for_project_orders_most_recent_first(tmp_path):
    from datetime import datetime, timedelta, timezone
    repo = SqlAlchemyReleaseRecordRepository(_paths(tmp_path))
    older = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.BLOQUEADA, checklist=ReleaseChecklist(gates=[]), dictamen="bloqueada",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    newer = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.APROBADA, checklist=ReleaseChecklist(gates=[]), dictamen="aprobada",
        created_at=datetime.now(timezone.utc),
    )
    repo.save(older)
    repo.save(newer)

    records = repo.list_for_project("p1")
    assert [r.id for r in records] == [newer.id, older.id]


def test_release_record_get_last_record_returns_most_recent(tmp_path):
    from datetime import datetime, timedelta, timezone
    repo = SqlAlchemyReleaseRecordRepository(_paths(tmp_path))
    older = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.BLOQUEADA, checklist=ReleaseChecklist(gates=[]), dictamen="bloqueada",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    newer = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.APROBADA, checklist=ReleaseChecklist(gates=[]), dictamen="aprobada",
        created_at=datetime.now(timezone.utc),
    )
    repo.save(older)
    repo.save(newer)

    assert repo.get_last_record("p1").id == newer.id


def test_release_record_get_last_record_returns_none_when_no_records(tmp_path):
    repo = SqlAlchemyReleaseRecordRepository(_paths(tmp_path))
    assert repo.get_last_record("p1") is None


# ---------- paquete exportable de entregables (ítem 6 de la
# evaluación de madurez post-8-etapas) ----------

def test_filesystem_release_packager_writes_a_real_zip_with_all_deliverables(tmp_path):
    checklist = ReleaseChecklist(gates=[
        GateResult(name="Metadatos", passed=True, reason="esquema con 2 campos"),
        GateResult(name="Calidad", passed=False, reason="sin casos de prueba"),
    ])
    record = ReleaseRecord(
        project_id="p1", status=ReleaseStatus.BLOQUEADA, checklist=checklist,
        dictamen="Liberación bloqueada: no se cumplieron las siguientes compuertas: Calidad.",
        evidence={"pipeline_run_id": "run-1"},
        deliverables_report={
            "especificacion_metadatos": {"campos": ["titulo"]},
            "banco_de_pruebas": {"casos": []},
        },
    )

    destination = tmp_path / "salida" / "release.zip"
    packager = FilesystemReleasePackager()
    result_path = packager.export(record, str(destination))

    assert result_path == str(destination)
    assert destination.exists()

    with zipfile.ZipFile(destination) as zf:
        names = set(zf.namelist())
        assert names == {
            "manifest.json", "dictamen.txt", "checklist.json",
            "entregables/especificacion_metadatos.json", "entregables/banco_de_pruebas.json",
        }

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["release_id"] == record.id
        assert manifest["project_id"] == "p1"
        assert manifest["status"] == "bloqueada"
        assert manifest["compuertas_cumplidas"] is False
        assert manifest["evidence"] == {"pipeline_run_id": "run-1"}

        assert zf.read("dictamen.txt").decode("utf-8") == record.dictamen

        checklist_payload = json.loads(zf.read("checklist.json"))
        assert checklist_payload["compuertas"] == [
            {"nombre": "Metadatos", "cumplida": True, "motivo": "esquema con 2 campos"},
            {"nombre": "Calidad", "cumplida": False, "motivo": "sin casos de prueba"},
        ]

        assert json.loads(zf.read("entregables/especificacion_metadatos.json")) == {"campos": ["titulo"]}
        assert json.loads(zf.read("entregables/banco_de_pruebas.json")) == {"casos": []}


# ---------- instantáneas publicadas de proyecto (ADR-002, Fase 1) ----------

def test_project_snapshot_round_trip_preserves_all_fields(tmp_path):
    repo = SqlAlchemyProjectSnapshotRepository(_paths(tmp_path))
    snapshot = ProjectSnapshot(
        project_id="p1", version=1, source_release_id="rel-1", snapshot_dir="/agent_studio/snapshots/p1/v1",
    )
    repo.save(snapshot)

    fetched = repo.get_latest("p1")
    assert fetched is not None
    assert fetched.id == snapshot.id
    assert fetched.version == 1
    assert fetched.source_release_id == "rel-1"
    assert fetched.snapshot_dir == "/agent_studio/snapshots/p1/v1"


def test_project_snapshot_list_for_project_orders_most_recent_version_first(tmp_path):
    repo = SqlAlchemyProjectSnapshotRepository(_paths(tmp_path))
    v1 = ProjectSnapshot(project_id="p1", version=1, snapshot_dir="/a/v1")
    v2 = ProjectSnapshot(project_id="p1", version=2, snapshot_dir="/a/v2")
    repo.save(v1)
    repo.save(v2)

    snapshots = repo.list_for_project("p1")
    assert [s.version for s in snapshots] == [2, 1]
    assert repo.get_latest("p1").version == 2


def test_project_snapshot_get_latest_returns_none_when_no_snapshots(tmp_path):
    repo = SqlAlchemyProjectSnapshotRepository(_paths(tmp_path))
    assert repo.get_latest("p1") is None


def test_project_snapshot_list_for_project_does_not_mix_other_projects(tmp_path):
    repo = SqlAlchemyProjectSnapshotRepository(_paths(tmp_path))
    repo.save(ProjectSnapshot(project_id="p1", version=1, snapshot_dir="/a/v1"))
    repo.save(ProjectSnapshot(project_id="p2", version=1, snapshot_dir="/b/v1"))
    assert [s.project_id for s in repo.list_for_project("p1")] == ["p1"]


def test_filesystem_publisher_copies_project_dir_to_a_new_versioned_folder(tmp_path):
    paths = _paths(tmp_path)
    project_dir = paths.ensure_project_layout("p1")
    (project_dir / "manifest.json").write_text('{"ok": true}', encoding="utf-8")
    (project_dir / "sources" / "original" / "doc1.pdf").write_bytes(b"contenido de prueba")

    publisher = FilesystemProjectSnapshotPublisher(paths)
    snapshot_dir = publisher.publish("p1", 1)

    from pathlib import Path
    snapshot_path = Path(snapshot_dir)
    assert snapshot_path == paths.snapshot_version_dir("p1", 1)
    assert (snapshot_path / "manifest.json").read_text(encoding="utf-8") == '{"ok": true}'
    assert (snapshot_path / "sources" / "original" / "doc1.pdf").read_bytes() == b"contenido de prueba"
    # El directorio original de edición sigue intacto y sin tocar.
    assert (project_dir / "manifest.json").exists()


def test_filesystem_publisher_does_not_include_the_project_still_being_edited(tmp_path):
    """La instantánea vive fuera de projects/<project_id> -- editar el
    proyecto después de publicar no debe afectar la copia ya hecha."""
    paths = _paths(tmp_path)
    project_dir = paths.ensure_project_layout("p1")
    (project_dir / "manifest.json").write_text("v1", encoding="utf-8")

    publisher = FilesystemProjectSnapshotPublisher(paths)
    snapshot_dir = publisher.publish("p1", 1)

    (project_dir / "manifest.json").write_text("v2 -- edición posterior", encoding="utf-8")

    from pathlib import Path
    assert (Path(snapshot_dir) / "manifest.json").read_text(encoding="utf-8") == "v1"


def test_filesystem_publisher_rejects_publishing_the_same_version_twice(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure_project_layout("p1")
    publisher = FilesystemProjectSnapshotPublisher(paths)
    publisher.publish("p1", 1)

    import pytest
    with pytest.raises(FileExistsError):
        publisher.publish("p1", 1)


def test_filesystem_publisher_checkpoints_a_real_project_db_before_copying(tmp_path):
    """project.db real (creado y migrado vía ensure_project_db, no un
    archivo cualquiera) -- confirma que el checkpoint del WAL no falla
    contra una base real y que el archivo copiado es consultable."""
    import sqlite3

    from infrastructure.database.migrations import ensure_project_db

    paths = _paths(tmp_path)
    db_path = ensure_project_db(paths, "p1")
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.commit()
    finally:
        connection.close()

    publisher = FilesystemProjectSnapshotPublisher(paths)
    snapshot_dir = publisher.publish("p1", 1)

    from pathlib import Path
    copied_db = Path(snapshot_dir) / "project.db"
    assert copied_db.exists()
    verify = sqlite3.connect(str(copied_db))
    try:
        verify.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1;")
    finally:
        verify.close()
