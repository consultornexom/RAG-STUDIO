import pytest

from application.projects.service import ProjectService
from domain.documents.entities import Source, SourceType
from domain.projects.entities import ProjectStatus
from domain.projects.exceptions import (
    DuplicateProjectError,
    IntegrityViolationError,
    InvalidStatusTransitionError,
    ProjectInUseError,
    ProjectNotFoundError,
)

from .fakes import FakeProjectPackager, InMemoryConfigurationRepository, InMemoryProjectRepository
from .fakes_documents import InMemorySourceRepository


@pytest.fixture
def source_repository():
    return InMemorySourceRepository()


@pytest.fixture
def service(source_repository):
    return ProjectService(
        InMemoryProjectRepository(), InMemoryConfigurationRepository(), FakeProjectPackager(),
        source_repository,
    )


def test_create_project(service):
    project = service.create_project("Agente de soporte", agent_type_hint="soporte")
    assert project.status == ProjectStatus.INICIAL
    assert service.get_project(project.id).name == "Agente de soporte"


def test_create_project_duplicate_name_raises(service):
    service.create_project("Agente de soporte")
    with pytest.raises(DuplicateProjectError):
        service.create_project("Agente de soporte")


def test_get_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.get_project("no-existe")


def test_clone_project_copies_metadata(service):
    original = service.create_project("Agente original", domain="rrhh")
    clone = service.clone_project(original.id, "Agente clonado")
    assert clone.id != original.id
    assert clone.domain == "rrhh"
    assert clone.name == "Agente clonado"


def test_clone_missing_source_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.clone_project("no-existe", "Copia")


def test_archive_project_transitions_status(service):
    project = service.create_project("Agente a archivar")
    archived = service.archive_project(project.id)
    assert archived.is_archived()


def test_list_projects_can_exclude_archived(service):
    service.create_project("Activo")
    b = service.create_project("Para archivar")
    service.archive_project(b.id)

    assert {p.name for p in service.list_projects(include_archived=True)} == {"Activo", "Para archivar"}
    assert {p.name for p in service.list_projects(include_archived=False)} == {"Activo"}


def test_export_project_delegates_to_packager(service):
    project = service.create_project("Agente exportable")
    manifest = service.export_project(project.id, "/tmp/no-usado.agentproj")
    assert manifest.project_id == project.id


def test_export_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.export_project("no-existe", "/tmp/no-usado.agentproj")


def test_import_rejects_invalid_package():
    service = ProjectService(
        InMemoryProjectRepository(), InMemoryConfigurationRepository(),
        FakeProjectPackager(integrity_is_valid=False),
    )
    with pytest.raises(IntegrityViolationError):
        service.import_project("/tmp/paquete-corrupto.agentproj", identity_policy="preserve")


def test_import_project_forwards_new_project_id_to_packager():
    # Auditoría Ronda 48: ProjectService.import_project() no exponía
    # new_project_id -- no había forma de pedir, desde la ruta real de
    # la aplicación, que un paquete se importara bajo un id nuevo para
    # evitar una colisión con un proyecto existente.
    packager = FakeProjectPackager()
    service = ProjectService(
        InMemoryProjectRepository(), InMemoryConfigurationRepository(), packager,
    )
    imported = service.import_project("/tmp/paquete.agentproj", new_project_id="otro-id", identity_policy="preserve")
    assert imported.id == "otro-id"
    assert packager.import_calls == ["/tmp/paquete.agentproj"]


def test_compare_projects(service):
    a = service.create_project("Uno")
    b = service.create_project("Dos")
    result = service.compare_projects(a.id, b.id)
    assert result["project_a"]["name"] == "Uno"
    assert result["project_b"]["name"] == "Dos"
    assert result["same_status"] is True


# ---------- update_project_name / delete_project (Ronda 3, punto 13) ----------

def test_update_project_name_corrects_typo(service):
    project = service.create_project("Agende de sopotre")  # typo intencional
    updated = service.update_project_name(project.id, "Agente de soporte")
    assert updated.name == "Agente de soporte"
    assert service.get_project(project.id).name == "Agente de soporte"


def test_update_project_name_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.update_project_name("no-existe", "Nuevo nombre")


def test_update_project_name_rejects_duplicate(service):
    service.create_project("Uno")
    dos = service.create_project("Dos")
    with pytest.raises(DuplicateProjectError):
        service.update_project_name(dos.id, "Uno")


def test_delete_project_without_sources_succeeds(service):
    project = service.create_project("Proyecto vacío creado por error")
    service.delete_project(project.id)
    with pytest.raises(ProjectNotFoundError):
        service.get_project(project.id)


def test_delete_project_with_sources_is_blocked(service, source_repository):
    project = service.create_project("Proyecto con datos reales")
    source_repository.save(
        Source(project_id=project.id, title="Reglamento", source_type=SourceType.PDF)
    )
    with pytest.raises(ProjectInUseError):
        service.delete_project(project.id)
    # sigue existiendo -- el bloqueo no debe borrar nada a medias
    assert service.get_project(project.id) is not None


def test_delete_project_without_source_repository_configured_raises_runtime_error():
    service_sin_source_repo = ProjectService(
        InMemoryProjectRepository(), InMemoryConfigurationRepository(), FakeProjectPackager(),
    )
    project = service_sin_source_repo.create_project("Proyecto")
    with pytest.raises(RuntimeError):
        service_sin_source_repo.delete_project(project.id)


# ---------- update_project_details / change_project_status / get_allowed_next_statuses (Ronda 15, punto 48) ----------

def test_create_project_accepts_all_descriptive_fields(service):
    project = service.create_project(
        "Agente completo",
        agent_type_hint="soporte",
        description="Atiende dudas de nómina",
        domain="rrhh",
        target_users="empleados",
        language="es",
        risk_level="bajo",
        template_id="tpl-1",
    )
    assert project.agent_type_hint == "soporte"
    assert project.description == "Atiende dudas de nómina"
    assert project.risk_level == "bajo"


def test_update_project_details_changes_only_given_fields(service):
    project = service.create_project("Agente", domain="rrhh", risk_level="bajo")
    updated = service.update_project_details(project.id, domain="finanzas")
    assert updated.domain == "finanzas"
    # risk_level no se tocó: None significa "sin cambios", no "borrar".
    assert updated.risk_level == "bajo"
    assert updated.name == "Agente"


def test_update_project_details_can_clear_description(service):
    project = service.create_project("Agente", description="borrador inicial")
    updated = service.update_project_details(project.id, description="")
    assert updated.description == ""


def test_update_project_details_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.update_project_details("no-existe", domain="rrhh")


# ---------- update_quality_regression_threshold (Ronda 53, opción B') ----------

def test_update_quality_regression_threshold_sets_the_value(service):
    project = service.create_project("Agente")
    updated = service.update_quality_regression_threshold(project.id, 0.2)
    assert updated.quality_regression_threshold == 0.2
    assert service.get_project(project.id).quality_regression_threshold == 0.2


def test_update_quality_regression_threshold_can_reset_to_none(service):
    project = service.create_project("Agente")
    service.update_quality_regression_threshold(project.id, 0.2)
    reset = service.update_quality_regression_threshold(project.id, None)
    assert reset.quality_regression_threshold is None


def test_update_quality_regression_threshold_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.update_quality_regression_threshold("no-existe", 0.2)


def test_update_quality_regression_threshold_rejects_out_of_range_value(service):
    project = service.create_project("Agente")
    with pytest.raises(ValueError):
        service.update_quality_regression_threshold(project.id, 1.5)


def test_change_project_status_moves_through_graph(service):
    project = service.create_project("Agente")
    moved = service.change_project_status(project.id, "en_configuracion")
    assert moved.status == ProjectStatus.EN_CONFIGURACION


def test_change_project_status_rejects_invalid_transition(service):
    project = service.create_project("Agente")
    with pytest.raises(InvalidStatusTransitionError):
        service.change_project_status(project.id, "liberado")


def test_change_project_status_rejects_unknown_status_string(service):
    project = service.create_project("Agente")
    with pytest.raises(InvalidStatusTransitionError):
        service.change_project_status(project.id, "no_es_un_estado")


def test_change_project_status_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.change_project_status("no-existe", "en_configuracion")


def test_get_allowed_next_statuses_returns_plain_strings(service):
    project = service.create_project("Agente")
    assert service.get_allowed_next_statuses(project.id) == ["archivado", "en_configuracion"]


def test_get_allowed_next_statuses_empty_when_archived(service):
    project = service.create_project("Agente")
    service.archive_project(project.id)
    assert service.get_allowed_next_statuses(project.id) == []


# ---------- Ronda 102 (C4): "Reranking en el agente" ----------

@pytest.mark.parametrize("valor", [True, False, None])
def test_update_agent_reranking_guarda_el_ajuste(service, valor):
    project = service.create_project("Agente")
    assert project.agent_reranking is None  # predeterminado: automático
    updated = service.update_agent_reranking(project.id, valor)
    assert updated.agent_reranking is valor
    assert service.get_project(project.id).agent_reranking is valor


def test_update_agent_reranking_proyecto_inexistente(service):
    with pytest.raises(ProjectNotFoundError):
        service.update_agent_reranking("no-existe", True)
