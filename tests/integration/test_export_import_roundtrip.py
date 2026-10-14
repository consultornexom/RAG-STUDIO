import hashlib
import json
import zipfile
from pathlib import Path

from application.projects.service import ProjectService
from domain.projects.entities import ConfigurationEntry
from domain.projects.exceptions import IntegrityViolationError, ProjectIdCollisionError
from infrastructure.database.repositories import (
    SqlAlchemyConfigurationRepository,
    SqlAlchemyProjectRepository,
)
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths


def _make_service(base_dir: Path) -> tuple[ProjectService, InstallationPaths]:
    paths = InstallationPaths(base_dir)
    paths.ensure_installation_layout()
    repo = SqlAlchemyProjectRepository(paths)
    cfg_repo = SqlAlchemyConfigurationRepository(paths)
    packager = FilesystemProjectPackager(paths)
    return ProjectService(repo, cfg_repo, packager), paths


def test_export_import_roundtrip_across_installations(tmp_path):
    service_a, paths_a = _make_service(tmp_path / "laptop_a")
    project = service_a.create_project("Agente RRHH", agent_type_hint="rrhh")

    cfg_repo_a = SqlAlchemyConfigurationRepository(paths_a)
    cfg_repo_a.save(ConfigurationEntry(project_id=project.id, key="idioma", value="es"))

    doc_path = paths_a.project_dir(project.id) / "sources" / "original" / "politica.txt"
    doc_path.write_text("contenido de prueba", encoding="utf-8")

    export_path = tmp_path / "export.agentproj"
    manifest = service_a.export_project(project.id, str(export_path), include_documents=True)
    assert {f.relative_path for f in manifest.files} == {"project.db", "sources/original/politica.txt"}

    report = service_a.validate_integrity(str(export_path))
    assert report.is_valid
    assert report.checked_files == 2

    service_b, paths_b = _make_service(tmp_path / "laptop_b")
    imported = service_b.import_project(str(export_path))
    assert imported.id == project.id
    assert imported.name == "Agente RRHH"

    restored_doc = paths_b.project_dir(imported.id) / "sources" / "original" / "politica.txt"
    assert restored_doc.read_text(encoding="utf-8") == "contenido de prueba"

    leido = service_b.get_project(imported.id)
    assert leido.agent_type_hint == "rrhh"


def test_export_without_documents_excludes_sources(tmp_path):
    service, paths = _make_service(tmp_path / "laptop")
    project = service.create_project("Agente sin documentos")
    (paths.project_dir(project.id) / "sources" / "original" / "doc.txt").write_text("x", encoding="utf-8")

    export_path = tmp_path / "sin_docs.agentproj"
    manifest = service.export_project(project.id, str(export_path), include_documents=False)

    relative_paths = {f.relative_path for f in manifest.files}
    assert "project.db" in relative_paths
    assert not any(p.startswith("sources/") for p in relative_paths)
    assert manifest.includes_documents is False


def test_tampered_package_fails_integrity_check(tmp_path):
    service, paths = _make_service(tmp_path / "laptop")
    project = service.create_project("Agente a manipular")
    (paths.project_dir(project.id) / "sources" / "original" / "doc.txt").write_text(
        "contenido original", encoding="utf-8"
    )

    export_path = tmp_path / "original.agentproj"
    service.export_project(project.id, str(export_path))

    tampered_path = tmp_path / "tampered.agentproj"
    with zipfile.ZipFile(export_path) as zin, zipfile.ZipFile(tampered_path, "w") as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item.endswith("doc.txt"):
                data = b"contenido alterado sin permiso"
            zout.writestr(item, data)

    report = service.validate_integrity(str(tampered_path))
    assert not report.is_valid
    assert "sources/original/doc.txt" in report.mismatched_files


def test_missing_manifest_is_reported_as_invalid(tmp_path):
    service, _ = _make_service(tmp_path / "laptop")
    bogus_zip = tmp_path / "sin_manifiesto.agentproj"
    with zipfile.ZipFile(bogus_zip, "w") as zf:
        zf.writestr("cualquier_archivo.txt", "contenido")

    report = service.validate_integrity(str(bogus_zip))
    assert not report.is_valid
    assert "manifest" in (report.error or "").lower()


def _build_manifest_dict(project_id: str, relative_path: str, content: bytes) -> dict:
    """Fabrica a mano un manifest.json con hashes correctos, sin pasar
    por FileEntry/PackageManifest -- así se simula un paquete .agentproj
    malicioso construido a mano por fuera de RAG STUDIO, no uno que este
    mismo código haya podido rechazar antes de tiempo."""
    payload = {
        "project_id": project_id,
        "project_name": "Agente manipulado",
        "format_version": "1.0",
        "exported_at": "2026-08-20T00:00:00Z",
        "includes_documents": True,
        "files": [
            {
                "relative_path": relative_path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        ],
        "manifest_sha256": None,
    }
    canonical = json.dumps(payload, sort_keys=True)
    payload["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def test_a_package_with_a_path_traversal_entry_is_reported_as_invalid(tmp_path):
    # Auditoría Ronda 46, hallazgo crítico -- Zip Slip: antes de esta
    # corrección, un .agentproj con una entrada "../../../fuera.txt" (y
    # sus propios hashes calculados correctamente) pasaba
    # verify_integrity() sin problema, porque esta solo comprobaba que
    # el manifiesto fuera autoconsistente, nunca que las rutas fueran
    # seguras.
    service, _ = _make_service(tmp_path / "laptop")
    content = b"contenido que intenta escapar del proyecto"
    manifest_dict = _build_manifest_dict("p-malicioso", "../../fuera_del_proyecto.txt", content)

    malicious_path = tmp_path / "malicioso.agentproj"
    with zipfile.ZipFile(malicious_path, "w") as zf:
        zf.writestr("../../fuera_del_proyecto.txt", content)
        zf.writestr("manifest.json", json.dumps(manifest_dict))

    report = service.validate_integrity(str(malicious_path))
    assert not report.is_valid
    assert "insegura" in (report.error or "").lower() or "inválidos" in (report.error or "").lower()

    try:
        service.import_project(str(malicious_path))
        raise AssertionError("import_project debía rechazar el paquete con path traversal")
    except IntegrityViolationError:
        pass

    # Ninguna escritura debe haber ocurrido fuera de la carpeta de
    # instalación -- ni siquiera parcialmente, antes de detectar la
    # ruta insegura.
    assert not (tmp_path.parent / "fuera_del_proyecto.txt").exists()
    assert not (tmp_path / "fuera_del_proyecto.txt").exists()


def test_exporting_the_same_project_twice_produces_two_valid_packages(tmp_path):
    # Auditoría Ronda 48 (pruebas reales con documentos de
    # Licenciatura/), hallazgo importante: antes de esta corrección,
    # export() escribía una copia de referencia de manifest.json dentro
    # de la propia carpeta del proyecto; una SEGUNDA exportación de ese
    # mismo proyecto encontraba esa copia con rglob("*") y la empaquetaba
    # como si fuera contenido del proyecto, produciendo un .zip con dos
    # entradas "manifest.json" y is_valid=False en su propia
    # verify_integrity().
    service, paths = _make_service(tmp_path / "laptop")
    project = service.create_project("Agente exportado dos veces")
    (paths.project_dir(project.id) / "sources" / "original" / "doc.txt").write_text(
        "contenido de prueba", encoding="utf-8"
    )

    first_export = tmp_path / "primera.agentproj"
    second_export = tmp_path / "segunda.agentproj"
    service.export_project(project.id, str(first_export))
    service.export_project(project.id, str(second_export))

    for export_path in (first_export, second_export):
        report = service.validate_integrity(str(export_path))
        assert report.is_valid, f"{export_path.name}: {report.error or report.mismatched_files}"
        with zipfile.ZipFile(export_path) as zf:
            assert zf.namelist().count("manifest.json") == 1
            assert "manifest.json" not in {
                name for name in zf.namelist() if name.startswith("sources/")
            }


def test_importing_a_package_whose_project_id_already_exists_is_rejected(tmp_path):
    # Auditoría Ronda 48, hallazgo importante: antes de esta corrección,
    # import_project() nunca comprobaba si el project_id del manifiesto
    # ya correspondía a un proyecto real en disco -- los archivos del
    # paquete importado se mezclaban en silencio con los del proyecto
    # existente.
    service, paths = _make_service(tmp_path / "laptop")
    original = service.create_project("ORIGINAL")
    (paths.project_dir(original.id) / "sources" / "original" / "propio.txt").write_text(
        "archivo legítimo de ORIGINAL", encoding="utf-8"
    )

    intruso = service.create_project("INTRUSO")
    (paths.project_dir(intruso.id) / "sources" / "original" / "intruso.txt").write_text(
        "archivo del proyecto INTRUSO", encoding="utf-8"
    )
    intruso_export = tmp_path / "intruso.agentproj"
    service.export_project(intruso.id, str(intruso_export))

    # Edita a mano el manifiesto exportado para que declare el
    # project_id de ORIGINAL (recalculando su hash), exactamente como
    # podría llegar un paquete ajeno o corrupto en la vida real.
    with zipfile.ZipFile(intruso_export) as zf:
        manifest_dict = json.loads(zf.read("manifest.json"))
        other_entries = {
            name: zf.read(name) for name in zf.namelist() if name != "manifest.json"
        }
    manifest_dict["project_id"] = original.id
    manifest_dict["manifest_sha256"] = None
    canonical = json.dumps(
        {k: v for k, v in manifest_dict.items() if k != "manifest_sha256"}, sort_keys=True
    )
    manifest_dict["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    tampered_path = tmp_path / "intruso_disfrazado.agentproj"
    with zipfile.ZipFile(tampered_path, "w") as zf:
        for name, data in other_entries.items():
            zf.writestr(name, data)
        zf.writestr("manifest.json", json.dumps(manifest_dict))

    report = service.validate_integrity(str(tampered_path))
    assert report.is_valid  # el manifiesto es autoconsistente; la colisión se detecta al importar

    try:
        service.import_project(str(tampered_path))
        raise AssertionError("import_project debía rechazar la colisión de project_id")
    except ProjectIdCollisionError as exc:
        assert exc.project_id == original.id

    # El archivo legítimo de ORIGINAL debe seguir intacto, y el archivo
    # de INTRUSO nunca debe haberse mezclado en su carpeta.
    original_file = paths.project_dir(original.id) / "sources" / "original" / "propio.txt"
    assert original_file.read_text(encoding="utf-8") == "archivo legítimo de ORIGINAL"
    assert not (paths.project_dir(original.id) / "sources" / "original" / "intruso.txt").exists()
