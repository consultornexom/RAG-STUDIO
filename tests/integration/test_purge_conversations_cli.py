"""Prueba de integración real (subproceso real, `python -m
interfaces.api.purge_conversations`, contra un runtime.db real -- no
una llamada directa a la función) del script de mantenimiento de
Ronda 12 (ver Validacion_observaciones_RAG_STUDIO.md)."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from domain.runtime.entities import ConversationLogEntry
from infrastructure.database.runtime_repositories import SqlAlchemyConversationLogRepository
from infrastructure.filesystem.paths import InstallationPaths

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _seed(base_dir: Path) -> InstallationPaths:
    paths = InstallationPaths(base_dir)
    paths.ensure_installation_layout()
    repository = SqlAlchemyConversationLogRepository(paths.runtime_db_path())
    now = datetime.now(timezone.utc)
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="vieja", action="responder",
        created_at=now - timedelta(days=100),
    ))
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="reciente", action="responder",
        created_at=now - timedelta(days=1),
    ))
    return paths


def _run_cli(base_dir: Path, *extra_args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["RAGSTUDIO_HOME"] = str(base_dir)
    return subprocess.run(
        [sys.executable, "-m", "interfaces.api.purge_conversations", *extra_args],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=30,
    )


def test_dry_run_reports_the_count_without_deleting_anything(tmp_path):
    paths = _seed(tmp_path / "agent_studio")

    result = _run_cli(paths.base_dir, "--retention-days", "90", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Se borrarían 1" in result.stdout
    reader = SqlAlchemyConversationLogRepository(paths.runtime_db_path())
    assert reader.count_older_than(datetime.now(timezone.utc)) == 2  # nada se borró


def test_running_for_real_deletes_only_the_eligible_rows(tmp_path):
    paths = _seed(tmp_path / "agent_studio")

    result = _run_cli(paths.base_dir, "--retention-days", "90")

    assert result.returncode == 0, result.stderr
    assert "Se borraron 1" in result.stdout
    reader = SqlAlchemyConversationLogRepository(paths.runtime_db_path())
    remaining = reader.list_for_project("p1")
    assert len(remaining) == 1
    assert remaining[0].message == "reciente"
    assert (paths.logs_dir() / "ragstudio-api.log").exists()


def test_rejects_a_non_positive_retention_window(tmp_path):
    paths = _seed(tmp_path / "agent_studio")

    result = _run_cli(paths.base_dir, "--retention-days", "0")

    assert result.returncode == 2
    assert "Error" in result.stdout
