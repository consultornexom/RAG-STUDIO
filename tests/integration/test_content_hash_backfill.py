"""RAG-INC-01 — relleno de content_hash de fuentes heredadas (decisión NEXOM
sobre INC01-R1: opción B, comando/servicio explícito). SQLite y disco reales,
con la aplicación completa (bootstrap)."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.lifecycle import shutdown, start
from domain.documents.content_hash_backfill import BackfillStatus
from domain.documents.entities import SourceType
from domain.documents.exceptions import ContentHashBackfillConflictError
from infrastructure.database import content_hash_writer as modulo_writer
from infrastructure.database.content_hash_writer import SqliteSourceContentHashWriter

ESTADOS_ESPERADOS = {
    "rellenada", "ya_tenía", "no_aplica", "sin_copia_original", "ilegible",
    "colisión_mismo_linaje", "contenido_compartido_entre_linajes",
}


@pytest.fixture
def ctx(tmp_path):
    context = start(base_dir=tmp_path / "inst")
    yield context
    shutdown(context)


def _archivo(tmp_path: Path, nombre: str, contenido: bytes) -> Path:
    ruta = tmp_path / "externos" / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


def _registrar(ctx, pid, tmp_path, titulo, contenido: bytes | None, tipo=SourceType.PDF, supersedes=None,
               content_hash=None, ext=".pdf"):
    location = str(_archivo(tmp_path, f"{uuid.uuid4().hex}{ext}", contenido)) if contenido is not None else ""
    return ctx.document_service.register_source(
        pid, titulo, tipo, location=location, supersedes_source_id=supersedes, content_hash=content_hash,
    )


def _db(ctx, pid):
    return ctx.paths.project_db_path(pid)


def _filas(ctx, pid):
    con = sqlite3.connect(_db(ctx, pid))
    try:
        return {r[0]: {"hash": r[1], "lineage": r[2], "updated_at": r[3]}
                for r in con.execute("SELECT id, content_hash, lineage_id, updated_at FROM source")}
    finally:
        con.close()


def _estado(informe):
    return {r.source_id: r.status for r in informe.results}


def _proyecto(ctx, nombre="P"):
    return ctx.project_service.create_project(nombre).id


# ----------------------------------------------------------------- normal

def test_relleno_normal_idempotente_y_sin_tocar_updated_at(ctx, tmp_path):
    pid = _proyecto(ctx)
    contenidos = [b"uno", b"dos", b"tres"]
    fuentes = [_registrar(ctx, pid, tmp_path, f"F{i}", c) for i, c in enumerate(contenidos)]
    antes = _filas(ctx, pid)
    assert all(f["hash"] is None for f in antes.values())

    informe = ctx.document_service.backfill_content_hashes(pid)

    assert informe.write_outcome == "aplicada"
    assert (informe.missing_before, informe.missing_after) == (3, 0)
    despues = _filas(ctx, pid)
    for fuente, contenido in zip(fuentes, contenidos, strict=True):
        assert despues[fuente.id]["hash"] == hashlib.sha256(contenido).hexdigest()
        assert despues[fuente.id]["updated_at"] == antes[fuente.id]["updated_at"]
        assert despues[fuente.id]["lineage"] == antes[fuente.id]["lineage"]
    assert set(_estado(informe).values()) == {BackfillStatus.RELLENADA}

    # Informe JSON en reports/.
    ruta = Path(informe.report_path)
    assert ruta.parent == ctx.paths.project_dir(pid) / "reports"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["escritura"] == "aplicada" and datos["faltantes_antes"] == 3 and datos["faltantes_despues"] == 0
    assert set(datos["conteos"]) == ESTADOS_ESPERADOS
    assert {f["estado"] for f in datos["fuentes"]} == {"rellenada"}
    assert "location" in datos["fuente_del_hash"]  # documenta que no se usa

    # Idempotencia: segunda ejecución no cambia nada.
    segundo = ctx.document_service.backfill_content_hashes(pid)
    assert segundo.write_outcome == "sin_cambios"
    assert set(_estado(segundo).values()) == {BackfillStatus.YA_TENIA}
    assert _filas(ctx, pid) == despues
    assert segundo.report_path != informe.report_path


def test_hash_existente_no_se_sobrescribe(ctx, tmp_path):
    pid = _proyecto(ctx)
    previa = _registrar(ctx, pid, tmp_path, "Con hash", b"contenido", content_hash="hash-previo")
    informe = ctx.document_service.backfill_content_hashes(pid)
    assert _estado(informe)[previa.id] == BackfillStatus.YA_TENIA
    assert _filas(ctx, pid)[previa.id]["hash"] == "hash-previo"
    assert informe.write_outcome == "sin_cambios"


def test_no_usa_location_y_no_aplica_a_fuentes_sin_archivo(ctx, tmp_path):
    pid = _proyecto(ctx)
    fuente = _registrar(ctx, pid, tmp_path, "PDF", b"original")
    api = _registrar(ctx, pid, tmp_path, "API", None, tipo=SourceType.API)
    # El archivo externo cambia después del registro: no debe usarse.
    Path(ctx.document_service.get_source(pid, fuente.id).location).write_bytes(b"MODIFICADO")
    informe = ctx.document_service.backfill_content_hashes(pid)
    assert _filas(ctx, pid)[fuente.id]["hash"] == hashlib.sha256(b"original").hexdigest()
    assert _estado(informe)[api.id] == BackfillStatus.NO_APLICA
    assert _filas(ctx, pid)[api.id]["hash"] is None
    assert informe.missing_after == 0  # no_aplica no cuenta como faltante


# ------------------------------------------------- archivo faltante / ilegible

def _copia(ctx, pid, sid) -> Path:
    return next((ctx.paths.project_dir(pid) / "sources" / "original").glob(f"{sid}*"))


def test_archivo_faltante_e_ilegible_no_detienen_a_las_demas(ctx, tmp_path):
    pid = _proyecto(ctx)
    ok = _registrar(ctx, pid, tmp_path, "OK", b"ok")
    falta = _registrar(ctx, pid, tmp_path, "Falta", b"falta")
    dir_ = _registrar(ctx, pid, tmp_path, "Directorio", b"dir")
    ambigua = _registrar(ctx, pid, tmp_path, "Ambigua", b"amb")
    _copia(ctx, pid, falta.id).unlink()
    copia_dir = _copia(ctx, pid, dir_.id)
    copia_dir.unlink()
    copia_dir.mkdir()
    (copia_dir.parent / f"{ambigua.id}.otro").write_bytes(b"x")
    con = sqlite3.connect(_db(ctx, pid))
    con.execute("UPDATE source SET original_copy_path = NULL WHERE id = ?", (ambigua.id,))
    con.commit()
    con.close()

    informe = ctx.document_service.backfill_content_hashes(pid)
    estados = _estado(informe)
    assert estados[ok.id] == BackfillStatus.RELLENADA
    assert estados[falta.id] == BackfillStatus.SIN_COPIA_ORIGINAL
    assert estados[dir_.id] == BackfillStatus.ILEGIBLE
    assert estados[ambigua.id] == BackfillStatus.ILEGIBLE
    assert "varias copias" in next(r.detail for r in informe.results if r.source_id == ambigua.id)
    filas = _filas(ctx, pid)
    assert [sid for sid, f in filas.items() if f["hash"]] == [ok.id]
    assert (informe.missing_before, informe.missing_after) == (4, 3)


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="requiere permisos POSIX sin root")
def test_copia_sin_permiso_de_lectura_es_ilegible(ctx, tmp_path):
    pid = _proyecto(ctx)
    fuente = _registrar(ctx, pid, tmp_path, "Sin permiso", b"secreto")
    copia = _copia(ctx, pid, fuente.id)
    copia.chmod(0)
    try:
        informe = ctx.document_service.backfill_content_hashes(pid)
    finally:
        copia.chmod(0o600)
    assert _estado(informe)[fuente.id] == BackfillStatus.ILEGIBLE


def test_original_copy_path_de_otro_equipo_se_resuelve_por_id(ctx, tmp_path):
    """Proyectos llegados de otro equipo (.agentproj): la ruta guardada no
    existe aquí, pero la copia está en sources/original/<id>.<ext>."""
    pid = _proyecto(ctx)
    fuente = _registrar(ctx, pid, tmp_path, "Viajera", b"viajera")
    con = sqlite3.connect(_db(ctx, pid))
    con.execute("UPDATE source SET original_copy_path = ? WHERE id = ?",
                (f"C:\\Users\\otro\\proyecto\\sources\\original\\{fuente.id}.pdf", fuente.id))
    con.commit()
    con.close()
    informe = ctx.document_service.backfill_content_hashes(pid)
    assert _estado(informe)[fuente.id] == BackfillStatus.RELLENADA


# ------------------------------------------------------------- duplicados

def test_mismo_hash_distinto_linaje_se_rellena_y_reporta(ctx, tmp_path):
    pid = _proyecto(ctx)
    a = _registrar(ctx, pid, tmp_path, "A", b"igual")
    b = _registrar(ctx, pid, tmp_path, "B", b"igual")
    c = _registrar(ctx, pid, tmp_path, "C", b"otro")
    informe = ctx.document_service.backfill_content_hashes(pid)
    estados = _estado(informe)
    assert estados[a.id] == estados[b.id] == BackfillStatus.CONTENIDO_COMPARTIDO_ENTRE_LINAJES
    assert estados[c.id] == BackfillStatus.RELLENADA
    filas = _filas(ctx, pid)
    assert filas[a.id]["hash"] == filas[b.id]["hash"] == hashlib.sha256(b"igual").hexdigest()
    assert next(r for r in informe.results if r.source_id == a.id).related_source_ids == [b.id]


def test_mismo_hash_mismo_linaje_es_colision_y_no_rellena_ninguna(ctx, tmp_path):
    pid = _proyecto(ctx)
    raiz = _registrar(ctx, pid, tmp_path, "Reglamento", b"mismo")
    sucesora = _registrar(ctx, pid, tmp_path, "Reglamento v2", b"mismo", supersedes=raiz.id)
    otra = _registrar(ctx, pid, tmp_path, "Otra", b"distinto")
    informe = ctx.document_service.backfill_content_hashes(pid)
    estados = _estado(informe)
    assert estados[raiz.id] == estados[sucesora.id] == BackfillStatus.COLISION_MISMO_LINAJE
    assert estados[otra.id] == BackfillStatus.RELLENADA
    filas = _filas(ctx, pid)
    assert filas[raiz.id]["hash"] is None and filas[sucesora.id]["hash"] is None
    assert informe.missing_after == 2
    # Repetir no lo "resuelve" solo.
    assert _estado(ctx.document_service.backfill_content_hashes(pid))[raiz.id] == BackfillStatus.COLISION_MISMO_LINAJE


def test_caso_mixto_hash_existente_en_el_mismo_linaje(ctx, tmp_path):
    pid = _proyecto(ctx)
    h = hashlib.sha256(b"mismo").hexdigest()
    raiz = _registrar(ctx, pid, tmp_path, "Con hash", b"mismo", content_hash=h)
    # RegisterSource rechaza el duplicado por hash; la sucesora heredada sin
    # hash se crea registrándola con otro contenido y copiando luego los bytes.
    sucesora = _registrar(ctx, pid, tmp_path, "Heredada", b"provisional", supersedes=raiz.id)
    _copia(ctx, pid, sucesora.id).write_bytes(b"mismo")
    informe = ctx.document_service.backfill_content_hashes(pid)
    estados = _estado(informe)
    assert estados[sucesora.id] == BackfillStatus.COLISION_MISMO_LINAJE
    assert estados[raiz.id] == BackfillStatus.YA_TENIA
    filas = _filas(ctx, pid)
    assert filas[raiz.id]["hash"] == h and filas[sucesora.id]["hash"] is None


# ----------------------------------------------------------- rollback

def test_rollback_de_escritura_no_deja_nada_y_guarda_informe(ctx, tmp_path, monkeypatch):
    pid = _proyecto(ctx)
    for i in range(3):
        _registrar(ctx, pid, tmp_path, f"F{i}", f"c{i}".encode())
    real = modulo_writer._actualizar
    llamadas = {"n": 0}

    def falla(*a, **k):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("fallo inyectado en la escritura")
        return real(*a, **k)

    monkeypatch.setattr(modulo_writer, "_actualizar", falla)
    with pytest.raises(RuntimeError, match="fallo inyectado"):
        ctx.document_service.backfill_content_hashes(pid)
    assert all(f["hash"] is None for f in _filas(ctx, pid).values())
    informes = sorted((ctx.paths.project_dir(pid) / "reports").glob("content_hash_backfill_*.json"))
    datos = json.loads(informes[-1].read_text(encoding="utf-8"))
    assert datos["escritura"] == "revertida" and "fallo inyectado" in datos["error"]
    assert datos["faltantes_despues"] == 3
    monkeypatch.undo()
    assert ctx.document_service.backfill_content_hashes(pid).missing_after == 0


def test_escritor_revierte_si_aparece_colision_en_el_mismo_linaje(ctx, tmp_path):
    """Defensa final del escritor: otro proceso dejó, entre el cálculo y la
    escritura, el mismo hash en otra fuente del mismo linaje."""
    pid = _proyecto(ctx)
    raiz = _registrar(ctx, pid, tmp_path, "Raíz", b"r")
    sucesora = _registrar(ctx, pid, tmp_path, "v2", b"s", supersedes=raiz.id)
    otra = _registrar(ctx, pid, tmp_path, "Otra", b"o")
    con = sqlite3.connect(_db(ctx, pid))
    con.execute("UPDATE source SET content_hash = 'H' WHERE id = ?", (raiz.id,))
    con.commit()
    con.close()
    writer = SqliteSourceContentHashWriter(ctx.paths)
    with pytest.raises(ContentHashBackfillConflictError):
        writer.fill_missing(pid, {sucesora.id: "H", otra.id: "X"})
    filas = _filas(ctx, pid)
    assert filas[sucesora.id]["hash"] is None and filas[otra.id]["hash"] is None


def test_escritor_nunca_sobrescribe(ctx, tmp_path):
    pid = _proyecto(ctx)
    f = _registrar(ctx, pid, tmp_path, "F", b"f", content_hash="original")
    assert SqliteSourceContentHashWriter(ctx.paths).fill_missing(pid, {f.id: "otro"}) == set()
    assert _filas(ctx, pid)[f.id]["hash"] == "original"


# --------------------------------------------------------- concurrencia

def _rellenar_en_otro_proceso(base_dir: str, pid: str, cola) -> None:
    from app.lifecycle import shutdown as _shutdown
    from app.lifecycle import start as _start

    c = _start(base_dir=base_dir)
    try:
        informe = c.document_service.backfill_content_hashes(pid)
        cola.put(("ok", len(informe.written_ids())))
    except Exception as exc:  # noqa: BLE001
        cola.put((type(exc).__name__, str(exc)))
    finally:
        _shutdown(c)


def test_dos_procesos_rellenan_a_la_vez_sin_duplicar_ni_fallar(ctx, tmp_path):
    pid = _proyecto(ctx)
    for i in range(12):
        _registrar(ctx, pid, tmp_path, f"F{i}", os.urandom(200_000))
    mp = multiprocessing.get_context("spawn")
    cola = mp.Queue()
    procesos = [mp.Process(target=_rellenar_en_otro_proceso, args=(str(ctx.paths.base_dir), pid, cola))
                for _ in range(2)]
    for p in procesos:
        p.start()
    for p in procesos:
        p.join(120)
    resultados = [cola.get(timeout=10) for _ in procesos]
    assert all(r[0] == "ok" for r in resultados), resultados
    assert sum(r[1] for r in resultados) == 12  # cada fuente se escribió una sola vez
    assert all(f["hash"] for f in _filas(ctx, pid).values())


# ------------------------------------------------------- preserve / fork

def test_preserve_y_fork_conservan_hashes_sin_colisiones(ctx, tmp_path):
    pid = _proyecto(ctx, "Origen")
    raiz = _registrar(ctx, pid, tmp_path, "Raíz", b"r1")
    _registrar(ctx, pid, tmp_path, "v2", b"r2", supersedes=raiz.id)
    ctx.document_service.backfill_content_hashes(pid)
    origen = _filas(ctx, pid)
    paquete = tmp_path / "p.agentproj"
    ctx.project_service.export_project(pid, str(paquete))

    destino = start(base_dir=tmp_path / "destino")
    try:
        destino.project_service.import_project(str(paquete), identity_policy="preserve")
        copia = destino.project_service.import_project(
            str(paquete), new_project_id=str(uuid.uuid4()), new_name="Copia", identity_policy="fork")
        preservado = _filas(destino, pid)
        bifurcado = _filas(destino, copia.id)
        assert preservado == origen
        assert sorted(f["hash"] for f in bifurcado.values()) == sorted(f["hash"] for f in origen.values())
        assert not {f["lineage"] for f in bifurcado.values()} & {f["lineage"] for f in origen.values()}
        # Ambos quedan completos: el relleno no tiene nada que hacer.
        for proyecto in (pid, copia.id):
            informe = destino.document_service.backfill_content_hashes(proyecto)
            assert informe.write_outcome == "sin_cambios" and informe.missing_after == 0
    finally:
        shutdown(destino)
