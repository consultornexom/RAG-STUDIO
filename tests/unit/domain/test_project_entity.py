import pytest

from domain.projects.entities import Project, ProjectStatus
from domain.projects.exceptions import InvalidStatusTransitionError


def test_new_project_starts_in_inicial():
    project = Project(name="Agente de prueba")
    assert project.status == ProjectStatus.INICIAL
    assert project.id
    assert project.created_at == project.updated_at


def test_name_cannot_be_empty():
    with pytest.raises(ValueError):
        Project(name="   ")


def test_valid_transition_updates_status_and_timestamp():
    project = Project(name="Agente de prueba")
    moved = project.transition_to(ProjectStatus.EN_CONFIGURACION)
    assert moved.status == ProjectStatus.EN_CONFIGURACION
    assert moved.updated_at >= project.updated_at
    # el objeto original no se muta (Project es inmutable en la práctica)
    assert project.status == ProjectStatus.INICIAL


def test_invalid_transition_raises():
    project = Project(name="Agente de prueba")
    with pytest.raises(InvalidStatusTransitionError):
        project.transition_to(ProjectStatus.LIBERADO)


def test_archiving_sets_archived_at():
    project = Project(name="Agente de prueba").transition_to(ProjectStatus.ARCHIVADO)
    assert project.is_archived()
    assert project.archived_at is not None


def test_archived_project_has_no_further_transitions():
    project = Project(name="Agente de prueba").transition_to(ProjectStatus.ARCHIVADO)
    with pytest.raises(InvalidStatusTransitionError):
        project.transition_to(ProjectStatus.EN_CONFIGURACION)


# ---------- allowed_next_statuses (Ronda 15, punto 48) ----------

def test_allowed_next_statuses_matches_transition_graph():
    project = Project(name="Agente de prueba")
    assert project.allowed_next_statuses() == {ProjectStatus.EN_CONFIGURACION, ProjectStatus.ARCHIVADO}


def test_allowed_next_statuses_empty_for_archived():
    project = Project(name="Agente de prueba").transition_to(ProjectStatus.ARCHIVADO)
    assert project.allowed_next_statuses() == set()


# ---------- quality_regression_threshold (Ronda 53, opción B') ----------

def test_quality_regression_threshold_defaults_to_none():
    project = Project(name="Agente de prueba")
    assert project.quality_regression_threshold is None


def test_quality_regression_threshold_accepts_values_within_0_and_1():
    project = Project(name="Agente de prueba", quality_regression_threshold=0.15)
    assert project.quality_regression_threshold == 0.15


def test_quality_regression_threshold_accepts_the_boundaries():
    assert Project(name="A", quality_regression_threshold=0.0).quality_regression_threshold == 0.0
    assert Project(name="A", quality_regression_threshold=1.0).quality_regression_threshold == 1.0


def test_quality_regression_threshold_rejects_values_outside_0_and_1():
    with pytest.raises(ValueError):
        Project(name="Agente de prueba", quality_regression_threshold=1.5)
    with pytest.raises(ValueError):
        Project(name="Agente de prueba", quality_regression_threshold=-0.1)
