"""Fixtures compartidos. El paquete se instala en modo editable
(pyproject.toml) así que domain/application/infrastructure/workers/app
se importan directamente sin manipular sys.path."""
import pytest

from app.lifecycle import shutdown, start
from infrastructure.filesystem.paths import InstallationPaths


@pytest.fixture
def installation_paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


@pytest.fixture
def app_context(tmp_path):
    context = start(base_dir=tmp_path / "agent_studio")
    yield context
    shutdown(context)
