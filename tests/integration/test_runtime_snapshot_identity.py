"""Ronda 92 (2026-10-06): hallazgo real de usuario al desplegar un paquete
de entrega con una instantánea v2 -- el runtime asumía versión 1 porque
RAGSTUDIO_SNAPSHOT_VERSION tenía ese valor por defecto, y el consumidor
posterior rechazaba la identidad. Además: nombres de variables no
uniformes y ninguna validación previa al arranque.

Todo con componentes reales (project.db real vía Alembic, publicador y
empaquetador reales, .zip real extraído en otra carpeta -- simulando
"otro equipo")."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from application.release.commands.export_deployment_package import ExportDeploymentPackage
from domain.projects.entities import Project
from domain.release.entities import ProjectSnapshot
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.database.runtime_repositories import SqlAlchemyWidgetTokenRepository
from infrastructure.filesystem.deployment_packager import FilesystemDeploymentPackager
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.filesystem.snapshot_identity import (
    IDENTITY_FILENAME,
    content_fingerprint,
    read_snapshot_identity,
)
from interfaces.api import check_config
from interfaces.api.runtime_config import RuntimeConfigurationError, load_runtime_config
from interfaces.api.runtime_context import RuntimeContext, SnapshotNotFoundError

_PID = "p1"


def _publicar(paths: InstallationPaths, versiones: int) -> None:
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PID)
    SqlAlchemyProjectRepository(paths).save(Project(id=_PID, name="Proyecto de prueba"))
    for version in range(1, versiones + 1):
        snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PID, version)
        SqlAlchemyProjectSnapshotRepository(paths).save(
            ProjectSnapshot(project_id=_PID, version=version, snapshot_dir=snapshot_dir),
        )


def _exportar_y_extraer(tmp_path: Path, versiones: int = 2) -> Path:
    """Publica, exporta el paquete y lo extrae en OTRA carpeta (otro
    "equipo"); borra la instalación de origen. Devuelve la raíz extraída."""
    origen = InstallationPaths(tmp_path / "equipo_a" / "agent_studio")
    _publicar(origen, versiones)
    zip_path = tmp_path / "entrega.zip"
    ExportDeploymentPackage(
        SqlAlchemyProjectRepository(origen), SqlAlchemyProjectSnapshotRepository(origen),
        SqlAlchemyWidgetTokenRepository(origen.runtime_db_path()), FilesystemDeploymentPackager(),
    ).execute(_PID, str(zip_path))
    destino = tmp_path / "equipo_b" / f"entrega_cliente_{_PID}_v{versiones}"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(destino)
    shutil.rmtree(tmp_path / "equipo_a")
    return destino


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {"RAGSTUDIO_API_KEY": "clave-de-prueba-suficientemente-larga", "RAGSTUDIO_HOME": str(tmp_path / "home")}
    env.update(extra)
    return env


# ---------------------------------------------------------------- publicación

def test_publicar_escribe_identidad_portable_dentro_de_la_instantanea(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    _publicar(paths, 2)
    v2 = paths.snapshot_version_dir(_PID, 2)
    identidad = read_snapshot_identity(v2)
    assert identidad is not None
    assert (identidad.project_id, identidad.snapshot_version) == (_PID, 2)
    texto = (v2 / IDENTITY_FILENAME).read_text(encoding="utf-8")
    assert str(tmp_path) not in texto  # sin rutas absolutas del equipo
    # Mismo contenido en otra ruta => misma huella.
    copia = tmp_path / "otra" / "ruta" / "instantanea"
    shutil.copytree(v2, copia)
    assert content_fingerprint(copia) == identidad.content_fingerprint


def test_huella_detecta_un_cambio_real_de_contenido(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    _publicar(paths, 1)
    v1 = paths.snapshot_version_dir(_PID, 1)
    antes = content_fingerprint(v1)
    (v1 / "extra.txt").write_text("alterado", encoding="utf-8")
    assert content_fingerprint(v1) != antes


# ---------------------------------------------------------------- paquete

def test_paquete_trae_identidad_y_env_example_con_version_y_nombres_oficiales(tmp_path):
    raiz = _exportar_y_extraer(tmp_path, versiones=2)
    identidad = read_snapshot_identity(raiz / "instantanea")
    assert identidad is not None and identidad.snapshot_version == 2
    manifest = json.loads((raiz / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_version"] == 2
    assert manifest["instantanea_huella"] == identidad.content_fingerprint
    env_example = (raiz / ".env.example").read_text(encoding="utf-8")
    # Ronda 94: la versión es opcional -- solo aparece comentada, como verificación.
    assert "\n# RAGSTUDIO_SNAPSHOT_VERSION=2" in env_example
    assert "\nRAGSTUDIO_SNAPSHOT_VERSION=" not in env_example
    assert "# OBLIGATORIAS: RAGSTUDIO_SNAPSHOT_DIR, RAGSTUDIO_API_KEY." in env_example
    assert "\nRAGSTUDIO_API_KEY=" in env_example
    assert "\nRAG_API_KEY=" not in env_example
    guia = (raiz / "GUIA_DESPLIEGUE.md").read_text(encoding="utf-8")
    for texto in ("check_config", "--app-dir", "instantanea", "`RAGSTUDIO_SNAPSHOT_VERSION` es opcional",
                  '"snapshot_version": 2', "entorno virtual pertenece al proyecto RAG STUDIO"):
        assert texto in guia


# ---------------------------------------------------------------- configuración

def test_version_se_deriva_de_la_instantanea_sin_variable(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    config = load_runtime_config(_env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea")))
    assert config.pinned is not None
    assert (config.pinned.project_id, config.pinned.version) == (_PID, 2)
    assert config.pinned.version_source == IDENTITY_FILENAME


def test_hallazgo_original_version_1_con_instantanea_v2_no_arranca(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config(_env(
            tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea"), RAGSTUDIO_SNAPSHOT_VERSION="1",
        ))
    assert "no coincide" in str(exc.value) and "2" in str(exc.value)


def test_version_correcta_declarada_es_aceptada(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    config = load_runtime_config(_env(
        tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea"), RAGSTUDIO_SNAPSHOT_VERSION="2",
    ))
    assert config.pinned is not None and config.pinned.version == 2


def test_apuntar_a_la_raiz_del_paquete_da_un_error_que_indica_la_subcarpeta(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config(_env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz)))
    assert str(raiz / "instantanea") in str(exc.value)


def test_todos_los_problemas_se_reportan_juntos(tmp_path):
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config({
            "RAGSTUDIO_SNAPSHOT_DIR": str(tmp_path / "no-existe"),
            "RAGSTUDIO_RATE_LIMIT_PER_MINUTE": "muchas",
            "RAGSTUDIO_LOG_LEVEL": "ruidoso",
        }, default_home=str(tmp_path))
    problemas = exc.value.problems
    assert any("RAGSTUDIO_API_KEY" in p for p in problemas)
    assert any("no existe" in p for p in problemas)
    assert any("RATE_LIMIT" in p for p in problemas)
    assert any("LOG_LEVEL" in p for p in problemas)


def test_sin_instantanea_ni_home_explicito_no_arranca(tmp_path):
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config({"RAGSTUDIO_API_KEY": "x" * 20}, default_home=str(tmp_path))
    assert "RAGSTUDIO_SNAPSHOT_DIR" in str(exc.value)


def test_version_sin_instantanea_es_un_error(tmp_path):
    with pytest.raises(RuntimeConfigurationError):
        load_runtime_config(_env(tmp_path, RAGSTUDIO_SNAPSHOT_VERSION="2"))


def test_paquete_antiguo_sin_identidad_usa_manifest_del_paquete(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    (raiz / "instantanea" / IDENTITY_FILENAME).unlink()
    config = load_runtime_config(_env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea")))
    assert config.pinned is not None and config.pinned.version == 2
    assert "manifest.json" in config.pinned.version_source


def test_instantanea_suelta_sin_identidad_exige_la_variable(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    suelta = tmp_path / "suelta" / "instantanea"
    shutil.copytree(raiz / "instantanea", suelta)
    (suelta / IDENTITY_FILENAME).unlink()
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config(_env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(suelta)))
    assert "Ya no se asume la versión 1" in str(exc.value)
    config = load_runtime_config(_env(
        tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(suelta), RAGSTUDIO_SNAPSHOT_VERSION="2",
    ))
    assert config.pinned is not None and config.pinned.version == 2 and config.warnings


def test_alias_heredado_de_la_clave(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    base = {"RAGSTUDIO_SNAPSHOT_DIR": str(raiz / "instantanea"), "RAGSTUDIO_HOME": str(tmp_path / "home")}
    config = load_runtime_config({**base, "RAG_API_KEY": "clave-heredada-123456"})
    assert config.api_key == "clave-heredada-123456"
    assert any("RAG_API_KEY" in aviso for aviso in config.warnings)
    with pytest.raises(RuntimeConfigurationError):
        load_runtime_config({**base, "RAG_API_KEY": "una", "RAGSTUDIO_API_KEY": "otra"})


def test_perfil_de_embeddings_distinto_al_del_indice_no_arranca(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    import sqlite3
    from datetime import datetime, timezone
    db = raiz / "instantanea" / "project.db"
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO index_info (project_id, embedding_provider, embedding_model, dimensions, points_count, "
        "updated_at) VALUES (?, 'fastembed', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', "
        "384, 0, ?)", (_PID, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()
    config = load_runtime_config(_env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea")))
    assert config.embedding_profile == "simetrico"
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config(_env(
            tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea"),
            RAGSTUDIO_EMBEDDING_PROFILE="asimetrico_e5_large",
        ))
    assert "índice" in str(exc.value)


def test_check_config_verifica_la_huella(tmp_path, monkeypatch, capsys):
    raiz = _exportar_y_extraer(tmp_path)
    for nombre, valor in _env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea")).items():
        monkeypatch.setenv(nombre, valor)
    assert check_config.main(["--verificar-huella"]) == 0
    assert "LISTO" in capsys.readouterr().out
    (raiz / "instantanea" / "alterado.txt").write_text("x", encoding="utf-8")
    assert check_config.main(["--verificar-huella"]) == 1
    assert "huella" in capsys.readouterr().err


# ---------------------------------------------------------------- runtime

def _fake_factory(profile, cache_dir):  # noqa: ARG001
    from tests.integration.test_runtime_context_cache_eviction import _fake_embedding_provider_factory
    return _fake_embedding_provider_factory(profile, cache_dir)


def test_contexto_fijo_sin_version_la_deriva_y_solo_atiende_a_su_proyecto(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    contexto = RuntimeContext(
        tmp_path / "home", embedding_provider_factory=_fake_factory,
        pinned_snapshot_dir=raiz / "instantanea",
    )
    assert contexto.pinned_identity() == (_PID, 2)
    with pytest.raises(SnapshotNotFoundError) as exc:
        contexto.get_latest("otro-proyecto")
    assert _PID in str(exc.value)


def test_contexto_fijo_sin_version_ni_identidad_falla(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    suelta = tmp_path / "suelta"
    shutil.copytree(raiz / "instantanea", suelta)
    (suelta / IDENTITY_FILENAME).unlink()
    with pytest.raises(RuntimeConfigurationError):
        RuntimeContext(tmp_path / "home", embedding_provider_factory=_fake_factory, pinned_snapshot_dir=suelta)


def test_health_expone_la_identidad_servida(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from interfaces.api import app as app_module

    raiz = _exportar_y_extraer(tmp_path)
    for nombre, valor in _env(tmp_path, RAGSTUDIO_SNAPSHOT_DIR=str(raiz / "instantanea")).items():
        monkeypatch.setenv(nombre, valor)
    aplicacion = app_module.create_app_from_env()
    respuesta = TestClient(aplicacion).get("/health").json()
    assert respuesta["snapshot_mode"] == "fija"
    assert respuesta["snapshot_project_id"] == _PID
    assert respuesta["snapshot_version"] == 2
    assert str(tmp_path) not in json.dumps(respuesta)


def test_contexto_con_version_explicita_contradictoria_falla(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    with pytest.raises(RuntimeConfigurationError):
        RuntimeContext(
            tmp_path / "home", embedding_provider_factory=_fake_factory,
            pinned_snapshot_dir=raiz / "instantanea", pinned_snapshot_version=1,
        )


# ---------------------------------------------------------------- Ronda 94: contrato único de configuración

def _env_desde_env_example(raiz: Path, tmp_path: Path) -> dict[str, str]:
    """Variables NO comentadas del .env.example generado, tal cual; solo se
    sustituye el marcador de ruta por la carpeta real extraída."""
    env: dict[str, str] = {}
    for linea in (raiz / ".env.example").read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.lstrip().startswith("#"):
            nombre, _, valor = linea.partition("=")
            env[nombre.strip()] = valor.strip()
    env["RAGSTUDIO_SNAPSHOT_DIR"] = str(raiz / "instantanea")
    env["RAGSTUDIO_HOME"] = str(tmp_path / "home")
    return env


def test_env_example_tal_cual_pasa_check_config_y_arranca_sin_version(tmp_path, monkeypatch, capsys):
    """Hallazgo de validación real (paquete LIC_DAE, instantánea v4): el
    runtime funcionaba sin RAGSTUDIO_SNAPSHOT_VERSION pero .env.example la
    marcaba como obligatoria. Con las variables del propio .env.example
    (sin la versión) debe pasar check_config, arrancar y servir la versión
    de snapshot_identity.json."""
    from fastapi.testclient import TestClient

    from interfaces.api import app as app_module

    raiz = _exportar_y_extraer(tmp_path)
    env = _env_desde_env_example(raiz, tmp_path)
    assert "RAGSTUDIO_SNAPSHOT_VERSION" not in env
    monkeypatch.delenv("RAGSTUDIO_SNAPSHOT_VERSION", raising=False)
    for nombre, valor in env.items():
        monkeypatch.setenv(nombre, valor)
    assert check_config.main([]) == 0
    salida = capsys.readouterr().out
    assert "versión: 2 (tomada de snapshot_identity.json)" in salida
    salud = TestClient(app_module.create_app_from_env()).get("/health").json()
    assert salud["snapshot_version"] == 2 and salud["snapshot_project_id"] == _PID


def test_obligatorias_documentadas_son_exactamente_las_que_exige_el_runtime(tmp_path):
    """La lista OBLIGATORIAS de .env.example (y de la guía) debe coincidir
    con lo que load_runtime_config exige en modo instantánea fija: quitar
    cualquiera de ellas impide arrancar; quitar cualquier opcional, no."""
    from application.release.commands.export_deployment_package import _env_vars_doc

    raiz = _exportar_y_extraer(tmp_path)
    # RAGSTUDIO_HOME es opcional: se prueba sin ella, como en el .env.example.
    base = {k: v for k, v in _env_desde_env_example(raiz, tmp_path).items() if k != "RAGSTUDIO_HOME"}
    load_runtime_config(base, default_home=str(tmp_path / "home"))  # completo: arranca
    tabla = _env_vars_doc(2)
    for nombre, obligatoria, _desc in tabla:
        sin = {k: v for k, v in base.items() if k != nombre}
        if obligatoria:
            with pytest.raises(RuntimeConfigurationError):
                load_runtime_config(sin, default_home=str(tmp_path / "home"))
        else:
            load_runtime_config(sin, default_home=str(tmp_path / "home"))
    guia = (raiz / "GUIA_DESPLIEGUE.md").read_text(encoding="utf-8")
    bloque = guia[guia.index("Variables obligatorias para este modo"):guia.index("`RAGSTUDIO_SNAPSHOT_VERSION` es opcional")]
    for nombre, obligatoria, _desc in tabla:
        assert (f"{nombre}=" in bloque) == obligatoria, nombre
    for nombre, obligatoria, _desc in tabla:
        marca = "obligatoria" if obligatoria else "opcional"
        assert f"- `{nombre}` ({marca})" in guia


def test_version_definida_que_no_coincide_rechaza_con_mensaje_claro(tmp_path):
    raiz = _exportar_y_extraer(tmp_path)
    env = {**_env_desde_env_example(raiz, tmp_path), "RAGSTUDIO_SNAPSHOT_VERSION": "4"}
    with pytest.raises(RuntimeConfigurationError) as exc:
        load_runtime_config(env)
    assert "RAGSTUDIO_SNAPSHOT_VERSION=4 no coincide" in str(exc.value) and "(2," in str(exc.value)
