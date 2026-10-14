"""Pruebas de integración reales (sistema de archivos + SQLite vía
Alembic) del ítem 4 de la evaluación de madurez post-8-etapas: copiar
el archivo original de una fuente a sources/original/ del proyecto."""
from __future__ import annotations

from pathlib import Path

from application.documents.service import DocumentService
from domain.documents.entities import SourceType
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyExtractionRepository
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.source_file_store import FilesystemSourceFileStore


def _paths(tmp_path: Path) -> InstallationPaths:
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_filesystem_source_file_store_copies_file_into_project(tmp_path):
    paths = _paths(tmp_path)
    external_dir = tmp_path / "externo"
    external_dir.mkdir()
    original_file = external_dir / "reglamento.pdf"
    original_file.write_bytes(b"%PDF-1.4 contenido de prueba")

    store = FilesystemSourceFileStore(paths)
    paths.ensure_project_layout("p1")
    copy_path = store.store_original("p1", "source-1", str(original_file))

    copied = Path(copy_path)
    assert copied.exists()
    assert copied.read_bytes() == b"%PDF-1.4 contenido de prueba"
    assert copied.parent == paths.project_dir("p1") / "sources" / "original"
    assert copied.suffix == ".pdf"


def test_filesystem_source_file_store_propagates_missing_file(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure_project_layout("p1")
    store = FilesystemSourceFileStore(paths)

    try:
        store.store_original("p1", "source-1", str(tmp_path / "no-existe.pdf"))
        raise AssertionError("debía propagar el error de archivo no encontrado")
    except OSError:
        pass


def test_register_source_end_to_end_copies_and_persists_original_copy_path(tmp_path):
    paths = _paths(tmp_path)
    external_file = tmp_path / "externo" / "manual.docx"
    external_file.parent.mkdir()
    external_file.write_bytes(b"contenido real del manual")

    source_repository = SqlAlchemySourceRepository(paths)
    document_service = DocumentService(
        source_repository, SqlAlchemyExtractionRepository(paths),
        file_store=FilesystemSourceFileStore(paths),
    )

    source = document_service.register_source(
        "p1", "Manual de usuario", SourceType.DOCX, location=str(external_file),
    )

    assert source.original_copy_path is not None
    assert Path(source.original_copy_path).read_bytes() == b"contenido real del manual"

    # El campo se persiste de verdad en project.db, no solo en el
    # objeto en memoria devuelto por register_source.
    fetched = document_service.get_source("p1", source.id)
    assert fetched.original_copy_path == source.original_copy_path

    # Si el archivo externo original desaparece después, la copia local
    # sigue intacta -- exactamente el problema que este ítem resuelve
    # (ver README, "Limitaciones conocidas").
    external_file.unlink()
    assert Path(source.original_copy_path).exists()
