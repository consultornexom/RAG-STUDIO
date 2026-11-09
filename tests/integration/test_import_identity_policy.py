"""RAG-INC-01a — política de identidad en la importación (Alcance firmado,
INC01-D3/INC01-R9; decisión NEXOM D-1). SQLite y disco reales.

Cubre: preserve sin/con colisión (proyecto activo y archivado), fork sin
colisión y desde un proyecto cuya identidad ya existe, coexistencia,
tratamiento de linajes, política ausente, rollback con fallos inyectados,
paquetes anteriores a 0021 y bloqueo entre procesos."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path

import pytest

from application.documents.commands.register_source import RegisterSource
from application.projects.service import ProjectService
from domain.documents.entities import SourceType
from domain.projects.exceptions import (
    ImportLockTimeoutError,
    KnowledgeBaseIdentityCollisionError,
    MissingIdentityPolicyError,
    ProjectIdCollisionError,
)
from infrastructure.database import migrations as mig
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.repositories import SqlAlchemyConfigurationRepository, SqlAlchemyProjectRepository
from infrastructure.filesystem.import_lock import FileImportLock
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths


def _servicio(base_dir: Path, timeout_s: float = 30.0) -> tuple[ProjectService, InstallationPaths]:
    paths = InstallationPaths(base_dir)
    paths.ensure_installation_layout()
    repo = SqlAlchemyProjectRepository(paths)
    service = ProjectService(
        repo, SqlAlchemyConfigurationRepository(paths), FilesystemProjectPackager(paths),
        import_lock=FileImportLock(paths.base_dir, timeout_s=timeout_s),
    )
    return service, paths


def _paquete(tmp_path: Path) -> tuple[Path, str, dict]:
    """Proyecto con dos familias: A <- B <- C (cadena) y X (sola)."""
    service, paths = _servicio(tmp_path / "origen")
    project = service.create_project("AGENTE UDL")
    registrar = RegisterSource(SqlAlchemySourceRepository(paths))
    a = registrar.execute(project.id, "Reglamento", SourceType.TXT, content_hash="h1")
    b = registrar.execute(project.id, "Reglamento v2", SourceType.TXT, content_hash="h2", supersedes_source_id=a.id)
    c = registrar.execute(project.id, "Reglamento v3", SourceType.TXT, content_hash="h3", supersedes_source_id=b.id)
    x = registrar.execute(project.id, "Calendario", SourceType.TXT, content_hash="h4")
    package = tmp_path / "agente_udl.agentproj"
    service.export_project(project.id, str(package), include_documents=True)
    origen = _identidades(paths.project_db_path(project.id))
    origen["ids"] = {"A": a.id, "B": b.id, "C": c.id, "X": x.id}
    return package, project.id, origen


def _identidades(db: Path) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        kb = con.execute("SELECT knowledge_base_id FROM project").fetchone()[0]
        fuentes = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, lineage_id, supersedes_source_id FROM source")}
    finally:
        con.close()
    return {"kb": kb, "fuentes": fuentes}


def _estado_instalacion(paths: InstallationPaths) -> tuple:
    """Todo lo que una importación fallida NO debe cambiar."""
    con = sqlite3.connect(paths.base_dir / "application.db")
    try:
        indice = sorted(con.execute("SELECT id, name FROM project_index").fetchall())
    finally:
        con.close()
    carpetas = sorted(p.name for p in paths.projects_dir().iterdir())
    return indice, carpetas


def _sin_restos(paths: InstallationPaths) -> bool:
    return not [p for p in paths.projects_dir().iterdir() if p.name.startswith(".importando_")]


# ------------------------------------------------------------------ política

@pytest.mark.parametrize("valor", [None, "", "  ", "copiar", "PRESERVAR"])
def test_politica_ausente_o_invalida_aborta_antes_de_leer(tmp_path, valor, monkeypatch):
    package, _, _ = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")
    llamadas = []
    monkeypatch.setattr(service._import._packager, "verify_integrity", lambda p: llamadas.append(p))
    antes = _estado_instalacion(paths)
    with pytest.raises(MissingIdentityPolicyError):
        service.import_project(str(package), identity_policy=valor)
    assert llamadas == []  # ni siquiera abrió el paquete
    assert _estado_instalacion(paths) == antes


def test_politica_acepta_enum_y_mayusculas(tmp_path):
    from domain.projects.entities import IdentityPolicy

    package, _, _ = _paquete(tmp_path)
    service, _ = _servicio(tmp_path / "destino")
    assert service.import_project(str(package), identity_policy=IdentityPolicy.PRESERVE) is not None
    service2, _ = _servicio(tmp_path / "destino2")
    assert service2.import_project(str(package), identity_policy=" Fork ") is not None


# ------------------------------------------------------------------ preserve

def test_preserve_sin_colision_conserva_kb_y_linajes(tmp_path):
    package, package_id, origen = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")

    imported = service.import_project(str(package), identity_policy="preserve")

    assert imported.id == package_id
    assert imported.knowledge_base_id == origen["kb"]
    assert _identidades(paths.project_db_path(package_id)) == {"kb": origen["kb"], "fuentes": origen["fuentes"]}
    assert service.get_project(package_id).knowledge_base_id == origen["kb"]


def test_preserve_con_colision_activo_no_modifica_nada(tmp_path, caplog):
    package, package_id, origen = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")
    service.import_project(str(package), identity_policy="preserve")
    antes = _estado_instalacion(paths)

    # Aun con otro id y otro nombre, la identidad lógica es la misma.
    with caplog.at_level("WARNING"):
        with pytest.raises(KnowledgeBaseIdentityCollisionError) as exc:
            service.import_project(str(package), new_project_id=str(uuid.uuid4()), new_name="Otro nombre",
                                   identity_policy="preserve")
    assert exc.value.knowledge_base_id == origen["kb"]
    assert exc.value.existing_project_id == package_id
    assert "como copia" in str(exc.value)
    assert origen["kb"] in caplog.text  # L-05: queda en el log técnico
    assert _estado_instalacion(paths) == antes
    assert _sin_restos(paths)


def test_preserve_con_colision_contra_proyecto_archivado(tmp_path):
    package, package_id, _ = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")
    service.import_project(str(package), identity_policy="preserve")
    service.archive_project(package_id)
    antes = _estado_instalacion(paths)

    with pytest.raises(KnowledgeBaseIdentityCollisionError):
        service.import_project(str(package), new_project_id=str(uuid.uuid4()), new_name="Nuevo",
                               identity_policy="preserve")
    assert _estado_instalacion(paths) == antes


def test_preserve_colision_de_identidad_se_detecta_antes_que_la_de_id(tmp_path):
    package, _, _ = _paquete(tmp_path)
    service, _ = _servicio(tmp_path / "destino")
    service.import_project(str(package), identity_policy="preserve")
    with pytest.raises(KnowledgeBaseIdentityCollisionError):
        service.import_project(str(package), identity_policy="preserve")


# ---------------------------------------------------------------------- fork

def _familias(fuentes: dict, ids: dict) -> dict:
    return {nombre: fuentes[fid][0] for nombre, fid in ids.items()}


def test_fork_sin_colision_genera_identidades_nuevas_y_conserva_familias(tmp_path):
    package, package_id, origen = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")

    imported = service.import_project(str(package), identity_policy="fork")

    assert imported.id == package_id  # el id local se conserva si está libre
    copia = _identidades(paths.project_db_path(package_id))
    assert copia["kb"] == imported.knowledge_base_id != origen["kb"]
    lin = _familias(copia["fuentes"], origen["ids"])
    lin_origen = _familias(origen["fuentes"], origen["ids"])
    # Regla de linaje en fork: un lineage_id nuevo por familia.
    assert lin["A"] == lin["B"] == lin["C"] != lin["X"]
    assert not set(lin.values()) & set(lin_origen.values())
    # Las relaciones de supersesión no cambian.
    assert {k: v[1] for k, v in copia["fuentes"].items()} == {k: v[1] for k, v in origen["fuentes"].items()}


def test_fork_desde_identidad_existente_coexiste_con_el_original(tmp_path):
    package, package_id, origen = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")
    original = service.import_project(str(package), identity_policy="preserve")
    original_antes = _identidades(paths.project_db_path(package_id))

    # Fork con el mismo project_id: sigue rigiendo la regla de id.
    with pytest.raises(ProjectIdCollisionError):
        service.import_project(str(package), identity_policy="fork")

    nuevo_id = str(uuid.uuid4())
    copia = service.import_project(str(package), new_project_id=nuevo_id, new_name="AGENTE UDL (copia)",
                                   identity_policy="fork")

    assert {p.id for p in service.list_projects()} == {package_id, nuevo_id}
    assert copia.knowledge_base_id not in (original.knowledge_base_id, None)
    assert _identidades(paths.project_db_path(package_id)) == original_antes  # original intacto
    lin_original = {v[0] for v in original_antes["fuentes"].values()}
    lin_copia = {v[0] for v in _identidades(paths.project_db_path(nuevo_id))["fuentes"].values()}
    assert len(lin_copia) == len(lin_original) == 2 and not lin_copia & lin_original

    # Un segundo fork del mismo paquete es otra base más.
    tercera = service.import_project(str(package), new_project_id=str(uuid.uuid4()), new_name="AGENTE UDL (copia 2)",
                                     identity_policy="fork")
    assert len({original.knowledge_base_id, copia.knowledge_base_id, tercera.knowledge_base_id}) == 3


# ------------------------------------------------------------------ rollback

@pytest.mark.parametrize("politica", ["preserve", "fork"])
@pytest.mark.parametrize("punto", ["registro", "fork_identidades", "migracion", "layout", "segunda_comprobacion"])
def test_rollback_sin_artefactos_parciales(tmp_path, monkeypatch, politica, punto):
    package, package_id, _ = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino")
    otro = service.create_project("Existente")
    antes = _estado_instalacion(paths)
    packager = service._import._packager

    def falla(*a, **k):
        raise RuntimeError(f"fallo inyectado en {punto}")

    if punto == "registro":
        monkeypatch.setattr(service._import._repository, "save", falla)
    elif punto == "fork_identidades":
        if politica != "fork":
            pytest.skip("solo aplica a fork")
        monkeypatch.setattr(type(packager), "_fork_identities", staticmethod(falla))
    elif punto == "migracion":
        import types

        import infrastructure.filesystem.packager as modulo_packager
        monkeypatch.setattr(modulo_packager, "_migraciones", types.SimpleNamespace(upgrade_project=falla))
    elif punto == "layout":
        original = paths.ensure_project_layout

        def layout(pid):
            if pid == package_id:
                raise RuntimeError("fallo inyectado en layout")
            return original(pid)
        monkeypatch.setattr(paths, "ensure_project_layout", layout)
    elif punto == "segunda_comprobacion":
        # Simula que otro registro con la misma identidad apareció entre la
        # primera comprobación y el registro (la segunda lo detiene).
        llamadas = {"n": 0}
        real = service._import._proyecto_con_identidad

        def segunda(kb):
            llamadas["n"] += 1
            return otro if llamadas["n"] >= (2 if politica == "preserve" else 1) else real(kb)
        monkeypatch.setattr(service._import, "_proyecto_con_identidad", segunda)

    with pytest.raises((RuntimeError, KnowledgeBaseIdentityCollisionError)):
        service.import_project(str(package), identity_policy=politica)

    assert _estado_instalacion(paths) == antes
    assert not paths.project_dir(package_id).exists()
    assert _sin_restos(paths)
    # Tras quitar la causa, la importación funciona (no quedaron restos).
    monkeypatch.undo()
    assert service.import_project(str(package), identity_policy=politica).id == package_id


# ------------------------------------------------- paquetes anteriores a 0021

def _paquete_con_db(package: Path, destino: Path, db_bytes: bytes) -> Path:
    with zipfile.ZipFile(package) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        otros = {n: zf.read(n) for n in zf.namelist() if n not in ("manifest.json", "project.db")}
    for entrada in manifest["files"]:
        if entrada["relative_path"] == "project.db":
            entrada["sha256"] = hashlib.sha256(db_bytes).hexdigest()
            entrada["size_bytes"] = len(db_bytes)
    manifest["manifest_sha256"] = None
    canon = json.dumps({k: v for k, v in manifest.items() if k != "manifest_sha256"}, sort_keys=True)
    manifest["manifest_sha256"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    with zipfile.ZipFile(destino, "w") as zf:
        for nombre, datos in otros.items():
            zf.writestr(nombre, datos)
        zf.writestr("project.db", db_bytes)
        zf.writestr("manifest.json", json.dumps(manifest))
    return destino


def _db_0020(tmp_path: Path, project_id: str) -> bytes:
    db = tmp_path / "vieja" / "project.db"
    db.parent.mkdir()
    mig.upgrade_project(db, "0020")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO project (id,name,description,language,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)", (project_id, "AGENTE UDL", "", "es", "inicial", "2026-01-01", "2026-01-01"))
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    return db.read_bytes()


def test_paquete_anterior_a_0021_recibe_identidades_al_importar(tmp_path):
    package, package_id, _ = _paquete(tmp_path)
    viejo = _paquete_con_db(package, tmp_path / "viejo.agentproj", _db_0020(tmp_path, package_id))
    service, paths = _servicio(tmp_path / "destino")

    assert service._import._packager.read_knowledge_base_id(str(viejo)) is None
    imported = service.import_project(str(viejo), identity_policy="preserve")

    assert imported.knowledge_base_id and len(imported.knowledge_base_id) == 36
    assert service.get_project(package_id).knowledge_base_id == imported.knowledge_base_id
    con = sqlite3.connect(paths.project_db_path(package_id))
    try:
        # Ronda 98: la copia se lleva al head actual (0022, posterior a 0021).
        assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0022"
    finally:
        con.close()


def test_fallo_de_migracion_del_paquete_no_deja_restos(tmp_path, monkeypatch):
    package, package_id, _ = _paquete(tmp_path)
    viejo = _paquete_con_db(package, tmp_path / "viejo.agentproj", _db_0020(tmp_path, package_id))
    service, paths = _servicio(tmp_path / "destino")
    antes = _estado_instalacion(paths)
    monkeypatch.setenv("RAGSTUDIO_0021_FALLO_DE_PRUEBA", "tras_relleno")
    with pytest.raises(Exception, match="Fallo inyectado"):
        service.import_project(str(viejo), identity_policy="preserve")
    assert _estado_instalacion(paths) == antes
    assert _sin_restos(paths)


# ------------------------------------------------------ bloqueo interproceso

def _importar_en_otro_proceso(base_dir: str, package: str, demora: float, cola, con_bloqueo: bool = True) -> None:
    import time as _t

    from infrastructure.filesystem.packager import FilesystemProjectPackager as _P

    real = _P.import_project

    def lento(self, *a, **k):
        _t.sleep(demora)  # ensancha la ventana entre comprobar y registrar
        return real(self, *a, **k)

    _P.import_project = lento  # type: ignore[method-assign]
    service, _ = _servicio(Path(base_dir))
    if not con_bloqueo:  # solo para el control negativo manual
        service._import._lock = None
    try:
        # id y nombre distintos por proceso: lo único que comparten es la
        # identidad lógica (knowledge_base_id), que ningún índice único de
        # la instalación protege; solo el bloqueo serializa la comprobación.
        sufijo = uuid.uuid4().hex[:8]
        service.import_project(package, new_project_id=str(uuid.uuid4()), new_name=f"AGENTE UDL {sufijo}",
                               identity_policy="preserve")
        cola.put("ok")
    except Exception as exc:  # noqa: BLE001
        cola.put(type(exc).__name__)


def test_dos_procesos_importan_la_misma_identidad_solo_uno_la_registra(tmp_path):
    package, package_id, _ = _paquete(tmp_path)
    destino = tmp_path / "destino"
    _servicio(destino)
    ctx = multiprocessing.get_context("spawn")
    cola = ctx.Queue()
    # Sin bloqueo, ambos pasarían las comprobaciones previas durante la demora.
    procesos = [ctx.Process(target=_importar_en_otro_proceso, args=(str(destino), str(package), 1.0, cola))
                for _ in range(2)]
    for p in procesos:
        p.start()
    for p in procesos:
        p.join(120)
    resultados = sorted(cola.get(timeout=5) for _ in procesos)
    assert resultados == ["KnowledgeBaseIdentityCollisionError", "ok"]
    service, paths = _servicio(destino)
    proyectos = service.list_projects()
    assert len(proyectos) == 1 and proyectos[0].id != package_id
    assert _sin_restos(paths)


def _retener_bloqueo(base_dir: str, listo, soltar) -> None:
    with FileImportLock(base_dir).hold():
        listo.set()
        soltar.wait(30)


def test_bloqueo_tomado_por_otro_proceso_agota_tiempo_sin_cambios(tmp_path):
    package, _, _ = _paquete(tmp_path)
    service, paths = _servicio(tmp_path / "destino", timeout_s=0.5)
    antes = _estado_instalacion(paths)
    ctx = multiprocessing.get_context("spawn")
    listo, soltar = ctx.Event(), ctx.Event()
    proceso = ctx.Process(target=_retener_bloqueo, args=(str(paths.base_dir), listo, soltar))
    proceso.start()
    try:
        assert listo.wait(30)
        inicio = time.monotonic()
        with pytest.raises(ImportLockTimeoutError):
            service.import_project(str(package), identity_policy="preserve")
        assert time.monotonic() - inicio >= 0.5
        assert _estado_instalacion(paths) == antes
    finally:
        soltar.set()
        proceso.join(30)
    # Liberado el bloqueo (o muerto el proceso), la importación procede.
    assert service.import_project(str(package), identity_policy="preserve") is not None


def test_bloqueo_se_libera_si_el_proceso_muere(tmp_path):
    paths = InstallationPaths(tmp_path / "inst")
    paths.ensure_installation_layout()
    ctx = multiprocessing.get_context("spawn")
    listo, soltar = ctx.Event(), ctx.Event()
    proceso = ctx.Process(target=_retener_bloqueo, args=(str(paths.base_dir), listo, soltar))
    proceso.start()
    assert listo.wait(30)
    proceso.kill()
    proceso.join(30)
    with FileImportLock(paths.base_dir, timeout_s=2).hold():
        pass


def test_bloqueo_excluye_tambien_dentro_del_mismo_proceso(tmp_path):
    lock_a = FileImportLock(tmp_path, timeout_s=0.2)
    lock_b = FileImportLock(tmp_path, timeout_s=0.2)
    with lock_a.hold():
        with pytest.raises(ImportLockTimeoutError):
            with lock_b.hold():
                pass
    with lock_b.hold():
        pass
    assert lock_a.path.name == ".importacion.lock"
