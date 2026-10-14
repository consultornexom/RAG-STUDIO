"""Pruebas unitarias de domain.projects.packaging (auditoría Ronda 46,
hallazgo crítico -- Zip Slip en la importación de paquetes .agentproj):
FileEntry.relative_path debe rechazar cualquier ruta que no sea una
ruta relativa segura, en el momento en que se construye el objeto de
dominio."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.projects.packaging import FileEntry


def _entry(relative_path: str) -> FileEntry:
    return FileEntry(relative_path=relative_path, sha256="a" * 64, size_bytes=1)


@pytest.mark.parametrize(
    "relative_path",
    [
        "project.db",
        "sources/original/politica.txt",
        "a/b/c/d.txt",
    ],
)
def test_relative_path_acepta_rutas_relativas_reales(relative_path):
    entry = _entry(relative_path)

    assert entry.relative_path == relative_path


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        "   ",
        "../etc/passwd",
        "../../etc/passwd",
        "sources/../../../etc/passwd",
        "/etc/passwd",
        "~/.bashrc",
        "C:/Windows/System32/algo.dll",
        "sources\\original\\politica.txt",
        "..",
    ],
)
def test_relative_path_rechaza_rutas_inseguras(relative_path):
    with pytest.raises(ValidationError):
        _entry(relative_path)
