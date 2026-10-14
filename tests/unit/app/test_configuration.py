"""Pruebas unitarias de default_base_dir (tercera ronda de madurez
post-8-etapas, ver bitácora en README): por defecto, los datos de la
instalación deben vivir dentro de la propia carpeta de la aplicación
(subcarpeta data/), no dispersos en una carpeta de perfil del sistema
operativo -- y sin romper el caso empaquetado con PyInstaller, donde la
carpeta correcta es la del ejecutable real, no sys._MEIPASS."""
from __future__ import annotations

import sys
from pathlib import Path

import app.configuration as configuration


def test_default_base_dir_lives_inside_the_source_installation(monkeypatch):
    monkeypatch.delenv("RAGSTUDIO_HOME", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    result = configuration.default_base_dir()

    project_root = Path(configuration.__file__).resolve().parent.parent
    assert result == project_root / "data"


def test_default_base_dir_uses_executable_directory_when_frozen(monkeypatch, tmp_path):
    monkeypatch.delenv("RAGSTUDIO_HOME", raising=False)
    fake_dist_dir = tmp_path / "dist" / "RAGStudio"
    fake_dist_dir.mkdir(parents=True)
    fake_executable = fake_dist_dir / "RAGStudio"
    fake_executable.write_text("")  # no necesita ser un binario real para la prueba

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_executable))

    result = configuration.default_base_dir()

    assert result == fake_dist_dir / "data"


def test_default_base_dir_respects_env_override_even_when_frozen(monkeypatch, tmp_path):
    custom_home = tmp_path / "donde-yo-quiera"
    monkeypatch.setenv("RAGSTUDIO_HOME", str(custom_home))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dist" / "RAGStudio" / "RAGStudio"))

    result = configuration.default_base_dir()

    assert result == custom_home


def test_load_settings_without_explicit_base_dir_uses_default_base_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("RAGSTUDIO_HOME", str(tmp_path / "instalacion-portatil"))

    settings = configuration.load_settings()

    assert settings.base_dir == tmp_path / "instalacion-portatil"


def test_load_settings_explicit_base_dir_wins_over_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("RAGSTUDIO_HOME", str(tmp_path / "no-deberia-usarse"))

    settings = configuration.load_settings(base_dir=tmp_path / "explicito")

    assert settings.base_dir == tmp_path / "explicito"
