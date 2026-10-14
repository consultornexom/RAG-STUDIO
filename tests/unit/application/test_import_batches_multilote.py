"""Ronda 92 (SOLICITUD NEXOM "portabilidad, identidad y preparación
multi-lote"): checklist 07 del desarrollador, pruebas 1-6, sobre la
importación de carpetas de entrega de RAG CONTENT."""
from __future__ import annotations

import csv
import hashlib
import shutil
import unicodedata
from pathlib import Path

import pytest

from application.documents.commands.register_source import RegisterSource
from application.documents.commands.register_sources_from_folder import (
    MANIFEST_FILENAME,
    RegisterSourcesFromFolder,
)
from domain.documents.import_batch import BatchRelation, batch_fingerprint
from infrastructure.filesystem.import_batch_ledger import LEDGER_FILENAME, JsonlImportBatchLedger
from infrastructure.filesystem.paths import InstallationPaths
from tests.unit.application.fakes_documents import InMemorySourceRepository

_COLUMNS = ("manifest_schema_version", "titulo", "tipo_fuente", "ruta_archivo", "hash_contenido")
_PID = "p1"


def _lote(carpeta: Path, documentos: dict[str, str], delimitador: str = ",") -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    with (carpeta / MANIFEST_FILENAME).open("w", encoding="utf-8", newline="") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=_COLUMNS, delimiter=delimitador)
        writer.writeheader()
        for nombre, contenido in documentos.items():
            (carpeta / nombre).write_bytes(contenido.encode("utf-8"))
            writer.writerow({
                "manifest_schema_version": "2", "titulo": nombre.removesuffix(".md"), "tipo_fuente": "markdown",
                "ruta_archivo": nombre, "hash_contenido": hashlib.sha256(contenido.encode("utf-8")).hexdigest(),
            })
    return carpeta


@pytest.fixture
def entorno(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    repo = InMemorySourceRepository()
    caso = RegisterSourcesFromFolder(RegisterSource(repo), batch_ledger=JsonlImportBatchLedger(paths))
    return caso, repo, paths


LOTE_A = {"lic_derecho.md": "Derecho v1", "lic_psicologia.md": "Psicología v1"}
LOTE_B = {"dip_proyectos.md": "Proyectos v1", "dip_finanzas.md": "Finanzas v1"}


def test_prueba_2_mismo_lote_en_otro_equipo_misma_identidad(tmp_path):
    a = _lote(tmp_path / "equipo_A" / "C" / "entregas" / "lote_lic" / "v1", LOTE_A)
    b = tmp_path / "equipo_B" / "home" / "usuario" / "Descargas" / "lote_lic" / "v1"
    shutil.copytree(a, b)
    resultados = []
    for carpeta in (a, b):
        repo = InMemorySourceRepository()
        resultados.append(RegisterSourcesFromFolder(RegisterSource(repo)).execute(_PID, str(carpeta)))
    assert resultados[0].batch_fingerprint == resultados[1].batch_fingerprint
    assert resultados[0].imported_count == resultados[1].imported_count == 2


def test_huella_independiente_del_orden_de_filas():
    filas = [("a.md", "1" * 64), ("b.md", "2" * 64)]
    assert batch_fingerprint(filas) == batch_fingerprint(list(reversed(filas)))


def test_prueba_3_alteracion_real_se_detecta(tmp_path, entorno):
    caso, _repo, _paths = entorno
    carpeta = _lote(tmp_path / "lote_lic" / "v1", LOTE_A)
    (carpeta / "lic_derecho.md").write_text("alterado", encoding="utf-8")
    resultado = caso.execute(_PID, str(carpeta))
    assert resultado.imported_count == 1
    assert any("no coincide con el hash" in s.reason for s in resultado.skipped)


def test_prueba_4_reimportacion_idempotente(tmp_path, entorno):
    caso, repo, paths = entorno
    carpeta = _lote(tmp_path / "lote_lic" / "v1", LOTE_A)
    primero = caso.execute(_PID, str(carpeta))
    segundo = caso.execute(_PID, str(carpeta))
    assert primero.batch_relation == BatchRelation.NUEVO
    assert segundo.batch_relation == BatchRelation.REIMPORTACION
    assert segundo.imported_count == 0 and len(repo.list_for_project(_PID)) == 2
    lotes = JsonlImportBatchLedger(paths).list_batches(_PID)
    assert [f.source_id for f in lotes[1].rows] == [f.source_id for f in lotes[0].rows]


def test_prueba_5_dos_lotes_coexisten_con_identidad_propia(tmp_path, entorno):
    caso, repo, paths = entorno
    ra = caso.execute(_PID, str(_lote(tmp_path / "lote_lic" / "v1", LOTE_A)))
    rb = caso.execute(_PID, str(_lote(tmp_path / "lote_dip" / "v1", LOTE_B)))
    assert ra.batch_fingerprint != rb.batch_fingerprint
    assert rb.batch_relation == BatchRelation.NUEVO
    assert (ra.batch_label, rb.batch_label) == ("lote_lic/v1", "lote_dip/v1")
    assert len(repo.list_for_project(_PID)) == 4
    texto = (paths.project_dir(_PID) / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert str(tmp_path) not in texto  # sin rutas físicas en la procedencia


def test_prueba_6_version_nueva_no_se_confunde_con_duplicado(tmp_path, entorno):
    caso, repo, _paths = entorno
    caso.execute(_PID, str(_lote(tmp_path / "lote_dip" / "v1", LOTE_B)))
    v2 = dict(LOTE_B, **{"dip_finanzas.md": "Finanzas v2 corregido"})
    resultado = caso.execute(_PID, str(_lote(tmp_path / "lote_dip" / "v2", v2)))
    assert resultado.batch_relation == BatchRelation.NUEVA_VERSION
    assert resultado.related_batch_label == "lote_dip/v1"
    assert resultado.imported_count == 1  # solo el documento que cambió
    assert "Sustituye a" in (resultado.batch_summary or "")
    assert len(repo.list_for_project(_PID)) == 3  # nada se retira en silencio


def test_intento_fallido_no_cuenta_como_lote_ya_importado(tmp_path, entorno):
    caso, _repo, _paths = entorno
    carpeta = _lote(tmp_path / "lote_lic" / "v1", LOTE_A)
    original = (carpeta / "lic_derecho.md").read_bytes()
    (carpeta / "lic_derecho.md").write_text("dañado", encoding="utf-8")
    caso.execute(_PID, str(carpeta))
    (carpeta / "lic_derecho.md").write_bytes(original)
    resultado = caso.execute(_PID, str(carpeta))
    assert resultado.batch_relation != BatchRelation.REIMPORTACION
    assert resultado.imported_count == 1


# ---------------------------------------------------------------- portabilidad

def test_nombre_en_nfd_de_macos_se_resuelve(tmp_path):
    carpeta = _lote(tmp_path / "lote", {"psicología.md": "contenido"})
    nfd = unicodedata.normalize("NFD", "psicología.md")
    (carpeta / "psicología.md").rename(carpeta / nfd)
    if (carpeta / "psicología.md").exists():
        pytest.skip("el sistema de archivos normaliza Unicode por sí mismo")
    resultado = RegisterSourcesFromFolder(RegisterSource(InMemorySourceRepository())).execute(_PID, str(carpeta))
    assert resultado.imported_count == 1, resultado.skipped


def test_mayusculas_distintas_se_resuelven_y_el_hash_sigue_verificando(tmp_path):
    carpeta = _lote(tmp_path / "lote", {"Plan.md": "contenido"})
    (carpeta / "Plan.md").rename(carpeta / "plan.md")
    if (carpeta / "Plan.md").exists():
        pytest.skip("sistema de archivos sin distinción de mayúsculas")
    resultado = RegisterSourcesFromFolder(RegisterSource(InMemorySourceRepository())).execute(_PID, str(carpeta))
    assert resultado.imported_count == 1, resultado.skipped


def test_manifiesto_guardado_con_punto_y_coma(tmp_path):
    carpeta = _lote(tmp_path / "lote", LOTE_A, delimitador=";")
    resultado = RegisterSourcesFromFolder(RegisterSource(InMemorySourceRepository())).execute(_PID, str(carpeta))
    assert resultado.imported_count == 2


def test_manifiesto_no_utf8_da_error_claro(tmp_path):
    carpeta = _lote(tmp_path / "lote", {"psicologia.md": "x"})
    texto = (carpeta / MANIFEST_FILENAME).read_text(encoding="utf-8") + "2,Psicología,markdown,y.md,\n"
    (carpeta / MANIFEST_FILENAME).write_bytes(texto.encode("cp1252"))
    with pytest.raises(ValueError, match="UTF-8"):
        RegisterSourcesFromFolder(RegisterSource(InMemorySourceRepository())).execute(_PID, str(carpeta))
