"""Pruebas de integración reales (sistema de archivos real) del
exportador de diagnóstico (ítem 5 de la segunda evaluación de madurez
post-8-etapas, ver bitácora en README)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from application.diagnostics_facade import DiagnosticsFacade
from infrastructure.filesystem.diagnostics import FilesystemDiagnosticsExporter
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path: Path) -> InstallationPaths:
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_export_creates_a_zip_with_info_json(tmp_path):
    paths = _paths(tmp_path)
    exporter = FilesystemDiagnosticsExporter(paths)
    destination = tmp_path / "diagnostico.zip"

    result_path = exporter.export(str(destination))

    assert result_path == str(destination)
    assert destination.exists()
    with zipfile.ZipFile(destination) as zf:
        names = zf.namelist()
        assert "info.json" in names
        info = json.loads(zf.read("info.json"))
        assert "ragstudio_version" in info
        assert "python_version" in info
        assert "plataforma" in info
        assert "generado_en" in info


def test_export_includes_log_files_when_present(tmp_path):
    paths = _paths(tmp_path)
    (paths.logs_dir() / "ragstudio.log").write_text("2026-07-27 | INFO | prueba\n", encoding="utf-8")
    exporter = FilesystemDiagnosticsExporter(paths)
    destination = tmp_path / "diagnostico.zip"

    exporter.export(str(destination))

    with zipfile.ZipFile(destination) as zf:
        assert "logs/ragstudio.log" in zf.namelist()
        assert "prueba" in zf.read("logs/ragstudio.log").decode("utf-8")


def test_export_does_not_fail_when_logs_dir_is_empty(tmp_path):
    paths = _paths(tmp_path)
    exporter = FilesystemDiagnosticsExporter(paths)
    destination = tmp_path / "diagnostico.zip"

    exporter.export(str(destination))
    assert destination.exists()


def test_export_creates_destination_parent_directories(tmp_path):
    paths = _paths(tmp_path)
    exporter = FilesystemDiagnosticsExporter(paths)
    destination = tmp_path / "subcarpeta" / "otra" / "diagnostico.zip"

    exporter.export(str(destination))
    assert destination.exists()


def test_diagnostics_facade_delegates_to_the_exporter(tmp_path):
    paths = _paths(tmp_path)
    facade = DiagnosticsFacade(FilesystemDiagnosticsExporter(paths))
    destination = tmp_path / "diagnostico.zip"

    result_path = facade.export_diagnostics_package(str(destination))

    assert result_path == str(destination)
    assert destination.exists()
