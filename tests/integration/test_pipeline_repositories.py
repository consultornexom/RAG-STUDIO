"""Pruebas de integración reales (SQLite vía Alembic) de
SqlAlchemyPipelineRunRepository (Etapa 3: pipeline reproducible)."""
from domain.pipeline.entities import (
    PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus,
)
from infrastructure.database.pipeline_repositories import SqlAlchemyPipelineRunRepository
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def _run(project_id="p1", **kwargs) -> PipelineRun:
    return PipelineRun(project_id=project_id, **kwargs)


def test_save_and_get_round_trips_run_and_items(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyPipelineRunRepository(paths)

    run = _run(
        status=PipelineRunStatus.COMPLETO,
        items=[
            PipelineRunItem(
                source_id="s1", source_title="Fuente uno", status=PipelineItemStatus.EXITOSO,
                content_hash="abc123", steps_completed=["extraccion", "fragmentacion", "indexacion"],
                chunks_indexed=3, warnings=["ojo con esto"],
            ),
        ],
    )
    repo.save(run)

    fetched = repo.get("p1", run.id)
    assert fetched is not None
    assert fetched.status == PipelineRunStatus.COMPLETO
    assert len(fetched.items) == 1
    item = fetched.items[0]
    assert item.source_id == "s1"
    assert item.status == PipelineItemStatus.EXITOSO
    assert item.content_hash == "abc123"
    assert item.steps_completed == ["extraccion", "fragmentacion", "indexacion"]
    assert item.chunks_indexed == 3
    assert item.warnings == ["ojo con esto"]


def test_get_returns_none_for_missing_or_wrong_project(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyPipelineRunRepository(paths)
    repo.save(_run(project_id="p1"))

    assert repo.get("p1", "no-existe") is None


def test_list_for_project_orders_most_recent_first(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyPipelineRunRepository(paths)
    from datetime import datetime, timedelta, timezone
    older = _run(started_at=datetime.now(timezone.utc) - timedelta(hours=1))
    newer = _run(started_at=datetime.now(timezone.utc))
    repo.save(older)
    repo.save(newer)

    runs = repo.list_for_project("p1")
    assert [r.id for r in runs] == [newer.id, older.id]


def test_get_last_successful_item_ignores_failed_and_other_sources(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyPipelineRunRepository(paths)
    repo.save(_run(items=[
        PipelineRunItem(source_id="s1", source_title="Uno", status=PipelineItemStatus.FALLIDO, content_hash="h0"),
        PipelineRunItem(source_id="s2", source_title="Dos", status=PipelineItemStatus.EXITOSO, content_hash="h-otra-fuente"),
    ]))
    repo.save(_run(items=[
        PipelineRunItem(source_id="s1", source_title="Uno", status=PipelineItemStatus.EXITOSO, content_hash="h1"),
    ]))

    item = repo.get_last_successful_item("p1", "s1")
    assert item is not None
    assert item.content_hash == "h1"


def test_get_last_successful_item_returns_none_when_never_succeeded(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyPipelineRunRepository(paths)
    repo.save(_run(items=[
        PipelineRunItem(source_id="s1", source_title="Uno", status=PipelineItemStatus.FALLIDO),
    ]))

    assert repo.get_last_successful_item("p1", "s1") is None


def test_get_last_successful_item_picks_the_most_recent_success(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyPipelineRunRepository(paths)
    from datetime import datetime, timedelta, timezone
    repo.save(_run(items=[
        PipelineRunItem(
            source_id="s1", source_title="Uno", status=PipelineItemStatus.EXITOSO, content_hash="viejo",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ),
    ]))
    repo.save(_run(items=[
        PipelineRunItem(
            source_id="s1", source_title="Uno", status=PipelineItemStatus.EXITOSO, content_hash="nuevo",
            started_at=datetime.now(timezone.utc),
        ),
    ]))

    item = repo.get_last_successful_item("p1", "s1")
    assert item.content_hash == "nuevo"
