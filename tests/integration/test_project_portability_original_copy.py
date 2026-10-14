"""Ronda 92 (SOLICITUD NEXOM, documento 03 "Equipo B debe continuar el
procesamiento"): un proyecto exportado (.agentproj) en el equipo A e
importado en el equipo B, con otra carpeta de instalación, debe poder
re-extraer sus fuentes. Antes, `Source.original_copy_path` guardaba la
ruta ABSOLUTA del equipo A y la re-extracción fallaba con "no se pudo
leer" aunque la copia de respaldo sí viajó dentro del paquete."""
from __future__ import annotations

import shutil

from application.ingestion.commands.extract_source_text import ExtractSourceText
from application.documents.commands.register_source import RegisterSource
from domain.documents.entities import SourceType
from domain.projects.entities import Project
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyExtractionRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.extraction.text_extractors import TxtExtractor
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.source_file_store import FilesystemSourceFileStore


def test_reextraccion_en_otro_equipo_usa_la_copia_que_viajo_en_el_paquete(tmp_path):
    equipo_a = InstallationPaths(tmp_path / "equipo_a" / "agent_studio")
    equipo_a.ensure_installation_layout()
    equipo_a.ensure_project_layout("p1")
    SqlAlchemyProjectRepository(equipo_a).save(Project(id="p1", name="Portabilidad"))
    externo = tmp_path / "equipo_a" / "documentos" / "reglamento.txt"
    externo.parent.mkdir(parents=True)
    externo.write_text("Artículo 1. Texto del reglamento.", encoding="utf-8")
    fuente = RegisterSource(
        SqlAlchemySourceRepository(equipo_a), file_store=FilesystemSourceFileStore(equipo_a),
    ).execute("p1", "Reglamento", SourceType.TXT, location=str(externo))
    assert fuente.original_copy_path and str(tmp_path / "equipo_a") in fuente.original_copy_path

    paquete = tmp_path / "p1.agentproj"
    FilesystemProjectPackager(equipo_a).export("p1", str(paquete))
    shutil.rmtree(tmp_path / "equipo_a")  # el equipo A ya no existe para el equipo B

    equipo_b = InstallationPaths(tmp_path / "equipo_b" / "otra" / "carpeta")
    equipo_b.ensure_installation_layout()
    FilesystemProjectPackager(equipo_b).import_project(str(paquete))

    repo_b = SqlAlchemySourceRepository(equipo_b)
    vista = repo_b.get("p1", fuente.id)
    assert vista is not None and vista.original_copy_path
    assert vista.original_copy_path.startswith(str(equipo_b.base_dir))

    registro = ExtractSourceText(repo_b, TxtExtractor(), SqlAlchemyExtractionRepository(equipo_b)).execute(
        "p1", fuente.id,
    )
    assert registro is not None and "Artículo 1" in registro.text
