"""Pruebas de integración reales (sistema de archivos real) de cómo
`infrastructure.database.migrations` ubica la carpeta `migrations/`
tanto en desarrollo como empaquetado con PyInstaller (ítem 7 de la
segunda evaluación de madurez post-8-etapas, ver bitácora en README).

Antes de este ítem, `GLOBAL_MIGRATIONS_DIR`/`PROJECT_MIGRATIONS_DIR`
solo sabían buscar `migrations/` subiendo desde este archivo hasta
encontrar `pyproject.toml` -- un ejecutable congelado con PyInstaller
no tiene ese archivo en disco, así que las migraciones nunca se habrían
encontrado fuera de un checkout de desarrollo."""
from __future__ import annotations

import sys

from infrastructure.database import migrations


def test_resolve_migrations_root_finds_the_real_dev_checkout():
    root = migrations._resolve_migrations_root()
    assert (root / "global").exists()
    assert (root / "project").exists()


def test_resolve_migrations_root_prefers_meipass_when_frozen(tmp_path, monkeypatch):
    frozen_migrations = tmp_path / "migrations"
    (frozen_migrations / "global").mkdir(parents=True)
    (frozen_migrations / "project").mkdir(parents=True)

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    root = migrations._resolve_migrations_root()
    assert root == frozen_migrations


def test_resolve_migrations_root_falls_back_to_dev_lookup_if_meipass_migrations_missing(monkeypatch, tmp_path):
    # _MEIPASS existe pero, por lo que sea, no trae migrations/ adentro
    # (paquete .spec mal armado, por ejemplo) -- no debe reventar:
    # cae de vuelta a la búsqueda de desarrollo de siempre.
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "vacio"), raising=False)

    root = migrations._resolve_migrations_root()
    assert (root / "global").exists()
    assert (root / "project").exists()
