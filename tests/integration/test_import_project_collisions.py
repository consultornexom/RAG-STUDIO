"""Ronda 88 (2026-10-02, hallazgo real de usuario): importar el paquete de
"AGENTE UDL" en una instalación que ya tenía otro proyecto con ese nombre
mostraba "UNIQUE constraint failed: project_index.name", dejaba los
archivos copiados sin registrar, y el reintento chocaba con "Ya existe un
proyecto real con id=...". Estas pruebas usan SQLite y disco reales."""
from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path

import pytest

from domain.conversational.entities import Intent
from domain.projects.exceptions import ImportNameCollisionError, ImportResidueError, ProjectIdCollisionError
from infrastructure.database.conversational_repositories import SqlAlchemyIntentRepository

from .test_export_import_roundtrip import _make_service


def _paquete_agente_udl(tmp_path: Path) -> tuple[Path, str]:
    service_a, paths_a = _make_service(tmp_path / "equipo_origen")
    project = service_a.create_project("AGENTE UDL")
    SqlAlchemyIntentRepository(paths_a).save(Intent(project_id=project.id, name="Consultar requisitos"))
    (paths_a.project_dir(project.id) / "sources" / "original" / "plan.txt").write_text("plan", encoding="utf-8")
    package = tmp_path / "agente_udl.agentproj"
    service_a.export_project(project.id, str(package), include_documents=True)
    return package, project.id


def test_nombre_repetido_se_detecta_antes_de_copiar_y_no_deja_restos(tmp_path):
    package, package_id = _paquete_agente_udl(tmp_path)
    service, paths = _make_service(tmp_path / "equipo_destino")
    service.create_project("AGENTE UDL")  # otro proyecto, mismo nombre (caso de la captura)

    with pytest.raises(ImportNameCollisionError) as exc:
        service.import_project(str(package))
    assert exc.value.suggested_name == "AGENTE UDL (importado)"
    assert not paths.project_dir(package_id).exists()

    # Reintento: ya no aparece "Ya existe un proyecto real con id=...".
    with pytest.raises(ImportNameCollisionError):
        service.import_project(str(package))


def test_importar_con_otro_nombre_conserva_los_datos(tmp_path):
    package, package_id = _paquete_agente_udl(tmp_path)
    service, paths = _make_service(tmp_path / "equipo_destino")
    service.create_project("AGENTE UDL")

    imported = service.import_project(str(package), new_name="AGENTE UDL (importado)")

    assert imported.id == package_id
    assert {p.name for p in service.list_projects()} == {"AGENTE UDL", "AGENTE UDL (importado)"}
    assert service.get_project(package_id).name == "AGENTE UDL (importado)"
    assert [i.name for i in SqlAlchemyIntentRepository(paths).list_for_project(package_id)] == ["Consultar requisitos"]


def test_restos_de_un_intento_fallido_se_apartan_sin_borrarse(tmp_path):
    package, package_id = _paquete_agente_udl(tmp_path)
    service, paths = _make_service(tmp_path / "equipo_destino")
    # Estado real que dejó la versión anterior: carpeta copiada pero sin registrar.
    residuo = paths.project_dir(package_id)
    residuo.mkdir(parents=True)
    with zipfile.ZipFile(package) as zf:
        zf.extractall(residuo)

    with pytest.raises(ImportResidueError):
        service.import_project(str(package))

    imported = service.import_project(str(package), set_aside_residue=True)

    assert imported.id == package_id
    apartados = list((paths.base_dir / "residuos_importacion").iterdir())
    assert len(apartados) == 1 and apartados[0].name.startswith(package_id)
    assert (apartados[0] / "project.db").exists()  # movido, no borrado


def test_mismo_proyecto_ya_registrado_se_importa_como_copia_con_todos_sus_datos(tmp_path):
    """Además del hallazgo: importar con un id nuevo solo cambiaba la fila
    `project`; fuentes, intenciones, etc. conservaban el id viejo y el
    proyecto copiado aparecía vacío."""
    package, package_id = _paquete_agente_udl(tmp_path)
    service, paths = _make_service(tmp_path / "equipo_destino")
    service.import_project(str(package))

    with pytest.raises(ProjectIdCollisionError) as exc:
        service.import_project(str(package))
    assert exc.value.existing_name == "AGENTE UDL"

    nuevo_id = str(uuid.uuid4())
    with pytest.raises(ImportNameCollisionError):
        service.import_project(str(package), new_project_id=nuevo_id)
    copia = service.import_project(str(package), new_project_id=nuevo_id, new_name="AGENTE UDL (copia)")

    assert copia.id == nuevo_id
    intents = SqlAlchemyIntentRepository(paths)
    assert [i.name for i in intents.list_for_project(nuevo_id)] == ["Consultar requisitos"]
    assert [i.name for i in intents.list_for_project(package_id)] == ["Consultar requisitos"]  # original intacto
    assert (paths.project_dir(nuevo_id) / "sources" / "original" / "plan.txt").exists()


def test_si_el_registro_falla_se_deshace_la_copia(tmp_path, monkeypatch):
    package, package_id = _paquete_agente_udl(tmp_path)
    service, paths = _make_service(tmp_path / "equipo_destino")

    def falla(project):
        raise RuntimeError("fallo simulado al registrar")

    monkeypatch.setattr(service._import._repository, "save", falla)
    with pytest.raises(RuntimeError):
        service.import_project(str(package))

    assert not paths.project_dir(package_id).exists()
    assert not [p for p in paths.projects_dir().iterdir() if p.name.startswith(".importando_")]


def test_paquete_sin_project_db_no_deja_carpeta_temporal(tmp_path):
    from domain.projects.exceptions import ProjectDomainError

    package, package_id = _paquete_agente_udl(tmp_path)
    service, paths = _make_service(tmp_path / "equipo_destino")
    packager = service._import._packager
    monkey_manifest = packager.inspect_package(str(package))
    monkey_manifest.files = [f for f in monkey_manifest.files if f.relative_path != "project.db"]
    original = packager.inspect_package
    packager.inspect_package = lambda path: monkey_manifest  # type: ignore[method-assign]
    try:
        with pytest.raises(ProjectDomainError):
            packager.import_project(str(package))
    finally:
        packager.inspect_package = original  # type: ignore[method-assign]
    assert not paths.project_dir(package_id).exists()
    assert not [p for p in paths.projects_dir().iterdir() if p.name.startswith(".importando_")]
    shutil.rmtree(tmp_path / "equipo_destino", ignore_errors=True)


# ---------- Auditoría posterior (Ronda 88): mismo error en otras operaciones ----------

@pytest.mark.parametrize("operacion", ["crear", "renombrar", "clonar"])
def test_nombre_repetido_con_espacios_da_error_claro_y_no_deja_estado_inconsistente(tmp_path, operacion):
    from domain.projects.exceptions import DuplicateProjectError

    service, paths = _make_service(tmp_path / "equipo")
    service.create_project("AGENTE UDL")
    otro = service.create_project("Otro")
    acciones = {
        "crear": lambda: service.create_project("  AGENTE UDL "),
        "renombrar": lambda: service.update_project_name(otro.id, "AGENTE UDL "),
        "clonar": lambda: service.clone_project(otro.id, " AGENTE UDL"),
    }
    with pytest.raises(DuplicateProjectError):
        acciones[operacion]()

    # Antes: al renombrar, la lista mostraba dos "AGENTE UDL"; al crear o
    # clonar quedaba una carpeta huérfana.
    assert sorted(p.name for p in service.list_projects()) == ["AGENTE UDL", "Otro"]
    assert len([d for d in paths.projects_dir().iterdir() if not d.name.startswith(".")]) == 2
