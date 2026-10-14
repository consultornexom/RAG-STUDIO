"""RAG-INC-01a — migración 0021 (identidades NEXOM), casos M-01..M-08 y
R-01..R-03 de `docs proyecto/RAG-INC-01/preparacion_01a/Preparacion_Hito_01a.md`,
sobre bases sintéticas desechables. M-09 (copias reales) se ejecuta aparte."""
from __future__ import annotations

import sqlite3

import pytest

from application.documents.commands.register_source import RegisterSource
from application.projects.commands.clone_project import CloneProject
from domain.documents.entities import SourceType
from domain.projects.entities import Project
from infrastructure.database import migrations as mig
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.filesystem.paths import InstallationPaths

_COLS = ("id,project_id,title,source_type,location,access_level,language,version,validation_status,"
         "created_at,updated_at,supersedes_source_id,document_type_code")


def _base_0020(tmp_path, fuentes: list[tuple[str, str | None]], proyectos=("p1",)):
    db = tmp_path / "project.db"
    mig.upgrade_project(db, "0020")
    con = sqlite3.connect(db)
    for pid in proyectos:
        con.execute(
            "INSERT INTO project (id,name,description,language,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?)", (pid, f"Proyecto {pid}", "", "es", "inicial", "2026-01-01", "2026-01-01"),
        )
    for fid, sup in fuentes:
        con.execute(
            f"INSERT INTO source ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, proyectos[0], f"t{fid}", "txt", "", "interno", "es", 1, "borrador",
             "2026-01-01", "2026-01-01", sup, "default"),
        )
    con.execute("INSERT INTO chunk (id, project_id, source_id, chunk_index, text, token_count, chunk_type, created_at) "
                "SELECT 'c-' || id, project_id, id, 0, 'texto', 1, 'texto', '2026-01-01' FROM source")
    con.commit()
    con.close()
    return db


def _leer(db, sql):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _version(db):
    return _leer(db, "SELECT version_num FROM alembic_version")[0][0]


def _columnas(db, tabla):
    return {r[1]: r for r in _leer(db, f"PRAGMA table_info({tabla})")}


def _linajes(db):
    return dict(_leer(db, "SELECT id, lineage_id FROM source"))


def test_m01_base_vacia_columnas_not_null_unico_e_indice(tmp_path):
    db = _base_0020(tmp_path, [], proyectos=())
    mig.upgrade_project(db)
    assert _version(db) == "0021"
    assert _columnas(db, "project")["knowledge_base_id"][3] == 1  # notnull
    assert _columnas(db, "source")["lineage_id"][3] == 1
    indices = {r[0] for r in _leer(db, "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "ix_source_lineage_id" in indices
    ddl = _leer(db, "SELECT sql FROM sqlite_master WHERE name='project'")[0][0]
    assert "knowledge_base_id" in ddl and "UNIQUE (knowledge_base_id)" in ddl.replace("CONSTRAINT uq_project_knowledge_base_id ", "")


def test_m02_m03_m05_familias_lineales_y_ramificadas(tmp_path):
    db = _base_0020(tmp_path, [("A", None), ("B", "A"), ("C", "B"), ("E", "A"), ("X", None), ("Y", None)])
    mig.upgrade_project(db)
    lin = _linajes(db)
    assert lin["A"] == lin["B"] == lin["C"] == lin["E"]  # M-03 y M-05
    assert len({lin["A"], lin["X"], lin["Y"]}) == 3  # M-02
    assert all(len(v) == 36 for v in lin.values())
    kb = _leer(db, "SELECT knowledge_base_id FROM project")
    assert len(kb) == 1 and len(kb[0][0]) == 36


def test_m04_referencia_rota_es_raiz(tmp_path, caplog):
    db = _base_0020(tmp_path, [("A", None), ("R", "NO-EXISTE"), ("R2", "R")])
    with caplog.at_level("WARNING"):
        mig.upgrade_project(db)
    lin = _linajes(db)
    assert lin["R"] == lin["R2"] != lin["A"]
    assert "NO-EXISTE" in caplog.text


@pytest.mark.parametrize("fuentes", [
    [("X", "Y"), ("Y", "X")],  # M-06
    [("S", "S")],  # M-07
    [("A", None), ("P", "Q"), ("Q", "R"), ("R", "P"), ("T", "P")],  # ciclo con cola
])
def test_m06_m07_ciclos_abortan_sin_cambios(tmp_path, fuentes):
    db = _base_0020(tmp_path, fuentes)
    antes = _leer(db, "SELECT sql FROM sqlite_master ORDER BY name")
    with pytest.raises(Exception, match="Ciclo de supersesión"):
        mig.upgrade_project(db)
    assert _version(db) == "0020"
    assert _leer(db, "SELECT sql FROM sqlite_master ORDER BY name") == antes
    assert _leer(db, "PRAGMA integrity_check") == [("ok",)]


@pytest.mark.parametrize("etapa", ["tras_relleno", "tras_not_null"])
def test_rollback_integro_ante_fallo(tmp_path, monkeypatch, etapa):
    db = _base_0020(tmp_path, [("A", None), ("B", "A")])
    antes_esquema = _leer(db, "SELECT sql FROM sqlite_master ORDER BY name")
    antes_datos = _leer(db, "SELECT * FROM source ORDER BY id")
    monkeypatch.setenv("RAGSTUDIO_0021_FALLO_DE_PRUEBA", etapa)
    with pytest.raises(Exception, match="Fallo inyectado"):
        mig.upgrade_project(db)
    assert _version(db) == "0020"
    assert _leer(db, "SELECT sql FROM sqlite_master ORDER BY name") == antes_esquema
    assert _leer(db, "SELECT * FROM source ORDER BY id") == antes_datos
    # Tras corregir la causa, se aplica normalmente.
    monkeypatch.delenv("RAGSTUDIO_0021_FALLO_DE_PRUEBA")
    mig.upgrade_project(db)
    assert _version(db) == "0021"


def test_ids_locales_y_project_id_no_cambian(tmp_path):
    db = _base_0020(tmp_path, [("A", None), ("B", "A")])
    antes = _leer(db, "SELECT id, project_id, supersedes_source_id FROM source ORDER BY id")
    chunks_antes = _leer(db, "SELECT id, source_id, project_id FROM chunk ORDER BY id")
    mig.upgrade_project(db)
    assert _leer(db, "SELECT id, project_id, supersedes_source_id FROM source ORDER BY id") == antes
    assert _leer(db, "SELECT id, source_id, project_id FROM chunk ORDER BY id") == chunks_antes
    assert _leer(db, "SELECT id FROM project") == [("p1",)]


def test_m08_downgrade_bloqueado_sin_bandera(tmp_path, monkeypatch):
    db = _base_0020(tmp_path, [("A", None)])
    mig.upgrade_project(db)
    monkeypatch.delenv("RAGSTUDIO_PERMITIR_DOWNGRADE_0021", raising=False)
    with pytest.raises(Exception, match="no se revierte"):
        mig.downgrade_project(db, "0020")
    assert _version(db) == "0021"
    assert "lineage_id" in _columnas(db, "source")


def test_downgrade_con_bandera_de_pruebas(tmp_path, monkeypatch):
    db = _base_0020(tmp_path, [("A", None)])
    mig.upgrade_project(db)
    monkeypatch.setenv("RAGSTUDIO_PERMITIR_DOWNGRADE_0021", "1")
    mig.downgrade_project(db, "0020")
    assert _version(db) == "0020"
    assert "lineage_id" not in _columnas(db, "source")
    assert "knowledge_base_id" not in _columnas(db, "project")


def test_base_creada_en_0016_se_actualiza_y_rellena(tmp_path):
    """Proyectos de esquemas antiguos llegan a 0021 por ensure_project_db."""
    db = tmp_path / "project.db"
    mig.upgrade_project(db, "0016")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO project (id,name,description,language,status,created_at,updated_at) "
                "VALUES ('p1','Viejo','','es','inicial','2026-01-01','2026-01-01')")
    con.commit()
    con.close()
    mig.upgrade_project(db)
    assert _leer(db, "SELECT COUNT(*) FROM project WHERE knowledge_base_id IS NOT NULL") == [(1,)]


# ---------------------------------------------------------------- R-01..R-03

def _instalacion(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout("p1")
    proyectos = SqlAlchemyProjectRepository(paths)
    proyectos.save(Project(id="p1", name="P1"))
    return paths, proyectos


def test_r01_r02_register_source_hereda_o_genera_lineage(tmp_path):
    paths, _ = _instalacion(tmp_path)
    repo = SqlAlchemySourceRepository(paths)
    registrar = RegisterSource(repo)
    raiz = registrar.execute("p1", "Reglamento", SourceType.TXT, content_hash="h1")
    sucesora = registrar.execute("p1", "Reglamento v2", SourceType.TXT, content_hash="h2",
                                 supersedes_source_id=raiz.id)
    otra = registrar.execute("p1", "Otro", SourceType.TXT, content_hash="h3")
    rota = registrar.execute("p1", "Huérfana", SourceType.TXT, content_hash="h4", supersedes_source_id="no-existe")
    assert repo.get("p1", sucesora.id).lineage_id == repo.get("p1", raiz.id).lineage_id  # R-01
    assert len({raiz.lineage_id, otra.lineage_id, rota.lineage_id}) == 3  # R-02


def test_knowledge_base_id_persistente_y_estable(tmp_path):
    paths, proyectos = _instalacion(tmp_path)
    kb = proyectos.get("p1").knowledge_base_id
    p = proyectos.get("p1")
    proyectos.save(p.model_copy(update={"description": "editado", "knowledge_base_id": "otro-valor"}))
    assert proyectos.get("p1").knowledge_base_id == kb  # nunca se sobrescribe


def test_r03_clone_project_recibe_knowledge_base_id_nuevo(tmp_path):
    paths, proyectos = _instalacion(tmp_path)
    original = proyectos.get("p1")
    clon = CloneProject(proyectos).execute("p1", "P1 clon")
    assert clon.knowledge_base_id != original.knowledge_base_id
    assert proyectos.get(clon.id).knowledge_base_id == clon.knowledge_base_id
