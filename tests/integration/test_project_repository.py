"""Pruebas de integración reales (SQLite vía Alembic) de
SqlAlchemyProjectRepository -- enfocadas en quality_regression_threshold
(Ronda 53, migración 0019), que no tenía ninguna prueba de roundtrip
real contra BD hasta esta ronda."""
import sqlite3
import uuid

from domain.projects.entities import Project
from infrastructure.database import migrations as mig
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_quality_regression_threshold_round_trips_through_sqlite(tmp_path):
    repo = SqlAlchemyProjectRepository(_paths(tmp_path))
    project = Project(name="Agente de prueba", quality_regression_threshold=0.25)
    repo.save(project)

    fetched = repo.get(project.id)
    assert fetched is not None
    assert fetched.quality_regression_threshold == 0.25


def test_quality_regression_threshold_defaults_to_none_for_existing_projects(tmp_path):
    """Toda instalación existente antes de la migración 0019 queda con
    NULL -- el mismo comportamiento (usar el umbral por defecto de la
    instalación) que tendría si el campo no existiera."""
    repo = SqlAlchemyProjectRepository(_paths(tmp_path))
    project = Project(name="Agente sin umbral propio")
    repo.save(project)

    fetched = repo.get(project.id)
    assert fetched is not None
    assert fetched.quality_regression_threshold is None


def test_quality_regression_threshold_can_be_updated_and_cleared(tmp_path):
    repo = SqlAlchemyProjectRepository(_paths(tmp_path))
    project = Project(name="Agente de prueba", quality_regression_threshold=0.25)
    repo.save(project)

    cleared = project.model_copy(update={"quality_regression_threshold": None})
    repo.save(cleared)

    fetched = repo.get(project.id)
    assert fetched.quality_regression_threshold is None


def test_get_upgrades_a_project_db_that_was_stamped_at_an_old_revision(tmp_path):
    """Ronda 55 -- reproduce el fallo real reportado por el consultor
    (sqlite3.OperationalError: no such column:
    project.quality_regression_threshold) tras reiniciar la aplicación.

    Simula un project.db creado con una versión anterior del código
    (revisión 0016, ANTES de la migración 0019 que agrega
    quality_regression_threshold) y abierto por primera vez en un
    proceso/instalación nuevos -- exactamente lo que pasa al reiniciar
    RAG STUDIO y listar los proyectos existentes (list_projects() ->
    list() -> get()). Antes de esta ronda, get() abría el archivo
    directamente con SQLAlchemy sin llamar nunca a ensure_project_db(),
    así que esta prueba fallaba con OperationalError incluso después de
    la corrección de caché de la Ronda 54 (que solo afecta a quién SÍ
    llama a ensure_project_db())."""
    paths = _paths(tmp_path)
    project_id = str(uuid.uuid4())
    paths.ensure_project_layout(project_id)
    db_path = paths.project_db_path(project_id)

    # Crea el archivo y lo deja exactamente en la revisión 0016 -- sin
    # pasar por quality_regression_threshold (migración 0019) ni por
    # ensure_project_db()/el repositorio, para no tocar la caché de
    # `_ensured_project_dbs` con esta ruta antes de la prueba.
    mig.upgrade_project(db_path, "0016")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO project "
            "(id, name, description, language, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                "Agente creado con esquema viejo",
                "",
                "es",
                "inicial",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    repo = SqlAlchemyProjectRepository(paths)
    fetched = repo.get(project_id)

    assert fetched is not None
    assert fetched.name == "Agente creado con esquema viejo"
    assert fetched.quality_regression_threshold is None

    # La lista también debe funcionar (mismo camino de código que
    # dispara el arranque real de la aplicación al abrir el panel de
    # proyectos): ProjectIndexRecord no existe para este proyecto
    # (se creó sin pasar por save()), así que solo se verifica get()
    # una segunda vez para confirmar que la migración quedó aplicada
    # de forma persistente, no solo "en memoria" para esta llamada.
    fetched_again = repo.get(project_id)
    assert fetched_again is not None
