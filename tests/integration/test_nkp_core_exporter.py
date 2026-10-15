"""RAG-INC-01b — exportador CORE del NEXOM Knowledge Package v1.0.0.

Instantáneas reales publicadas con la aplicación (SQLite y disco reales). El
validador firmado v1.0.0 se usa como prueba EXTERNA (no se modifica)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app.lifecycle import shutdown, start
from domain.knowledge_package.exceptions import (
    BrokenReferenceError,
    ContractConstraintError,
    MissingContentHashError,
    MissingIdentityError,
    MissingTenantError,
    OutputExistsError,
    PortableIdentityCollisionError,
    SnapshotDirectoryMissingError,
    SnapshotInconsistentError,
    SnapshotNotFoundError,
)
from infrastructure.database.migrations import upgrade_project
from infrastructure.exporters import nexom_knowledge_package as modulo
from contracts.nexom_knowledge_package import load_id_scheme
from infrastructure.filesystem.snapshot_identity import content_fingerprint

from . import nkp_export_fixtures as fx

k = load_id_scheme()
TENANT = "nexom-pruebas"
ARCHIVOS = sorted([*modulo.DATA_FILES, "manifest.json", "checksums.json"])
requiere_validador = pytest.mark.skipif(not fx.validador_disponible(), reason="validador v1.0.0 sin dependencias")


@pytest.fixture
def ctx(tmp_path):
    context = start(base_dir=tmp_path / "inst")
    yield context
    shutdown(context)


def _exportar(ctx, pid, snap, salida, tenant=TENANT):
    return ctx.knowledge_package_export.execute(pid, snap.id, tenant, str(salida))


def _leer(zip_path) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        datos = {}
        for nombre in zf.namelist():
            texto = zf.read(nombre).decode("utf-8")
            if nombre.endswith(".jsonl"):
                datos[nombre] = [json.loads(linea) for linea in texto.splitlines() if linea.strip()]
            else:
                datos[nombre] = json.loads(texto)
        return datos


def _sin_salida(salida: Path) -> bool:
    return not salida.exists() or not any(salida.iterdir())


# --------------------------------------------------------------- válidos

@requiere_validador
def test_exportacion_minima_valida(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    r = _exportar(ctx, p.project_id, snap, tmp_path / "out")
    rc, salida = fx.validar(Path(r.zip_path))
    assert rc == 0 and "ERRORES: 0" in salida, salida
    assert r.counts == {"sources": 1, "chunks": 1, "evidence": 1, "media": 0, "intents": 0,
                        "guardrail_rules": 0, "acceptance_cases": 0}


@requiere_validador
def test_proyecto_sin_esquema_de_metadatos_usa_version_local_1(ctx, tmp_path):
    """Decisión NEXOM (RAG-INC-01b): sin esquema de metadatos definido,
    schema_version_local = 1 (estado inicial del esquema local, aunque esté
    vacío). Nunca 0 ni null; el paquete es válido."""
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    con = sqlite3.connect(Path(snap.snapshot_dir) / "project.db")
    try:
        assert con.execute("SELECT COUNT(*) FROM metadata_schema").fetchone()[0] == 0
    finally:
        con.close()
    r = _exportar(ctx, p.project_id, snap, tmp_path / "out")
    ms = _leer(r.zip_path)["metadata_schema.json"]
    assert ms["schema_version_local"] == 1 and ms["fields"] == [] and ms["catalogs"] == []
    rc, salida = fx.validar(Path(r.zip_path))
    assert rc == 0 and "ERRORES: 0" in salida, salida


@requiere_validador
def test_exportacion_completa_valida_como_zip_y_directorio_con_sidecar(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    r = _exportar(ctx, p.project_id, snap, tmp_path / "out")

    import subprocess
    import sys
    salida = subprocess.run([sys.executable, str(fx.VALIDADOR), r.zip_path, "--content-digest-file",
                             r.content_digest_path], capture_output=True, text=True).stdout
    assert "ERRORES: 0" in salida and "content_digest recalculado" in salida, salida
    directorio = tmp_path / "extraido"
    zipfile.ZipFile(r.zip_path).extractall(directorio)
    rc, salida = fx.validar(directorio)
    assert rc == 0 and "ERRORES: 0" in salida, salida


def test_estructura_del_zip_y_checksums(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    r = _exportar(ctx, p.project_id, snap, tmp_path / "out")
    salida = tmp_path / "out"
    assert sorted(x.name for x in salida.iterdir()) == sorted([Path(r.zip_path).name, Path(r.content_digest_path).name])
    with zipfile.ZipFile(r.zip_path) as zf:
        infos = zf.infolist()
        assert [i.filename for i in infos] == ARCHIVOS  # 13 archivos internos, ordenados, sin carpetas
        assert all(i.date_time == (1980, 1, 1, 0, 0, 0) and i.flag_bits & 0x1 == 0 for i in infos)
        contenido = {i.filename: zf.read(i) for i in infos}
    assert "signature.json" not in contenido
    checksums = json.loads(contenido["checksums.json"])
    assert checksums["algorithm"] == "sha256" and checksums["canonicalization"] == "rfc8785"
    assert set(checksums["files"]) == set(ARCHIVOS) - {"checksums.json"}
    for nombre, valor in checksums["files"].items():
        assert valor == hashlib.sha256(contenido[nombre]).hexdigest()  # bytes ya canónicos
    assert contenido["checksums.json"] == k.canonical_json_bytes(checksums)
    digest = k.content_digest(checksums["files"], k.sha256_hex(contenido["checksums.json"]))
    assert Path(r.content_digest_path).read_text() == digest + "\n" == r.content_digest + "\n"
    assert r.zip_sha256 == hashlib.sha256(Path(r.zip_path).read_bytes()).hexdigest()


def test_manifest_e_identidades(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    r = _exportar(ctx, p.project_id, snap, tmp_path / "out")
    d = _leer(r.zip_path)
    m = d["manifest.json"]
    proyecto = ctx.project_service.get_project(p.project_id)
    assert m["knowledge_base_id"] == proyecto.knowledge_base_id == r.knowledge_base_id
    assert m["package_id"] == modulo.package_id_for(proyecto.knowledge_base_id, snap.id, TENANT) == r.package_id
    assert m["schema_version"] == "1.0.0" and m["exporter_version"] == modulo.EXPORTER_VERSION
    assert m["knowledge_version"] == str(snap.version) and m["snapshot_id"] == snap.id
    assert m["created_at"] == modulo._iso_datetime(snap.created_at)
    assert m["project_id_origin"] == p.project_id and m["tenant"] == TENANT and m["profile"] == "CORE"
    assert m["parent_package_id"] is None and m["source_system"] == "rag-studio"
    assert m["files"] == ARCHIVOS
    assert m["capabilities"] == {"text_retrieval": True, "structured_retrieval": True, "image_retrieval": False}
    assert {o["code"] for o in m["omissions"]} == {
        "MEDIA_BINARIES_NOT_INCLUDED", "ORIGINALS_NOT_INCLUDED", "VECTORS_NOT_INCLUDED", "EVIDENCE_NOT_VERIFIED"}

    fuentes = {s["origin_id"]: s for s in d["sources.jsonl"]}
    vivas = {f.id: f for f in ctx.document_service.list_sources(p.project_id)}
    for origen, s in fuentes.items():
        assert s["logical_id"] == f"urn:nexom:source-logical:{vivas[origen].lineage_id}"
        vkey = k.source_version_key(s["content_hash"], s["title"], s["source_type"], s["updated_at"])
        assert s["id"] == k.portable_source_id(vivas[origen].lineage_id, vkey)
    r1, r2 = fuentes[p.fuentes["r1"]], fuentes[p.fuentes["r2"]]
    assert r2["logical_id"] == r1["logical_id"] and r2["id"] != r1["id"]  # misma familia, otra versión
    assert r2["supersedes_source_id"] == r1["id"]
    assert fuentes[p.fuentes["r1"]]["content_hash"].startswith(hashlib.sha256(b"reglamento 2025").hexdigest()[:8])
    assert fuentes[p.fuentes["api"]]["content_hash"] is None  # tipo sin archivo: clave noncontent
    for c in d["chunks.jsonl"]:
        assert c["id"] == k.portable_chunk_id(c["source_id"], c["chunk_index"], c["text"])


def test_metadata_embedding_acceso_bundle_y_aceptacion(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    d = _leer(_exportar(ctx, p.project_id, snap, tmp_path / "out").zip_path)
    kb = d["manifest.json"]["knowledge_base_id"]

    ms = d["metadata_schema.json"]
    assert ms["knowledge_base_id"] == kb and ms["schema_version_local"] == 1
    campos = {f["field_id"]: f for f in ms["fields"]}
    assert campos["campus"]["id"] == k.portable_field_definition_id(kb, "campus")
    assert campos["campus"]["catalog_id"] == k.portable_catalog_id(kb, "campus")
    assert campos["nota"]["catalog_id"] is None and campos["programas"]["multiple"] is True
    entradas = {e["value_code"]: e for c in ms["catalogs"] if c["name"] == "campus" for e in c["entries"]}
    assert entradas["LEON_CENTRO"]["parent_entry_code"] == "LEON" and entradas["LEON"]["parent_entry_code"] is None
    valores = {v["field_code"]: v for v in d["source_metadata.jsonl"]}
    assert valores["programas"]["value"] == ["DER", "ISC"] and valores["campus"]["value"] == ["LEON"]
    assert all(v["id"] == f"{v['source_id']}:{v['field_definition_id']}" for v in valores.values())
    heredado = next(c for c in d["chunks.jsonl"] if c["inherited_metadata"])
    assert heredado["inherited_metadata"] == {k.portable_field_definition_id(kb, "campus"): "LEON"}

    assert d["embedding_spaces.json"] == [{
        "id": "text_semantic_384", "modality": "text", "provider": "fastembed", "model": fx.MODELO,
        "revision": None, "dimensions": 384, "normalization": "unknown_not_verified",
        "preprocessing": {"query_prefix": None, "passage_prefix": None}, "distance_metric": "cosine",
        "dtype": "float32", "fingerprint": None}]
    idx = d["indexes.json"][0]
    assert idx["embedding_space_id"] == "text_semantic_384" and idx["points_count"] == 5
    assert idx["covers_chunk_types"] == ["encabezado", "tabla", "texto"]  # sin padre ni imagen

    assert d["access_hierarchy.json"]["order"] == ["publico", "interno", "confidencial", "restringido"]

    b = d["conversational_bundle.json"]
    var = k.portable_variable_id(kb, "folio_aspirante")
    intent = b["intents"][0]
    assert intent["required_variables"] == [var] and intent["clarifying_questions"] == {var: "¿Cuál es tu folio?"}
    assert intent["fallback_channeling_code"] == k.portable_channeling_id(kb, "admisiones_humano")
    assert b["guardrail_rules"][0]["conditions"] == [{"field": "confianza", "operator": "<", "value": "0.5"}]

    assert d["acceptance_cases.jsonl"] == []  # INC01-D5
    media = d["media.jsonl"][0]
    assert media["included_in_package"] is False and media["relative_path"].startswith("assets/images/")
    assert media["checksum"] == "sha256:" + hashlib.sha256(b"\x89PNG imagen").hexdigest()
    evidencias = {e["chunk_id"] for e in d["evidence.jsonl"]}
    tipos = {c["id"]: c["chunk_type"] for c in d["chunks.jsonl"]}
    assert {tipos[c] for c in evidencias} == {"encabezado", "texto", "tabla"}


def test_repeticion_produce_el_mismo_paquete_byte_a_byte(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    a = _exportar(ctx, p.project_id, snap, tmp_path / "a")
    b = _exportar(ctx, p.project_id, snap, tmp_path / "b")
    assert (a.package_id, a.content_digest, a.checksums_json_hash, a.zip_sha256) == \
           (b.package_id, b.content_digest, b.checksums_json_hash, b.zip_sha256)
    assert Path(a.zip_path).read_bytes() == Path(b.zip_path).read_bytes()
    # Otro tenant: otro package_id; mismas identidades lógicas.
    c = _exportar(ctx, p.project_id, snap, tmp_path / "c", tenant="otro-tenant")
    assert c.package_id != a.package_id
    assert _leer(c.zip_path)["sources.jsonl"] == _leer(a.zip_path)["sources.jsonl"]


def test_dos_instantaneas_conservan_ids_si_el_contenido_no_cambia(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    s1 = ctx.release_service.publish_snapshot(p.project_id)
    ctx.document_service.update_validation_status(p.project_id, p.fuentes["r2"], "en_revision")  # cambia updated_at
    s2 = ctx.release_service.publish_snapshot(p.project_id)
    d1 = _leer(_exportar(ctx, p.project_id, s1, tmp_path / "1").zip_path)
    d2 = _leer(_exportar(ctx, p.project_id, s2, tmp_path / "2").zip_path)
    ids = lambda d, f: {r["id"] for r in d[f]}  # noqa: E731
    assert ids(d1, "sources.jsonl") == ids(d2, "sources.jsonl")  # content_hash ⇒ id estable
    assert ids(d1, "chunks.jsonl") == ids(d2, "chunks.jsonl")
    assert d2["manifest.json"]["knowledge_version"] == "2"


def test_instantanea_no_se_modifica(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    antes = content_fingerprint(snap.snapshot_dir)
    archivos_antes = sorted(x.name for x in Path(snap.snapshot_dir).iterdir())
    _exportar(ctx, p.project_id, snap, tmp_path / "out")
    assert content_fingerprint(snap.snapshot_dir) == antes
    assert sorted(x.name for x in Path(snap.snapshot_dir).iterdir()) == archivos_antes  # ni -shm ni -wal nuevos


# --------------------------------------------------------------- compuertas

def test_tenant_obligatorio(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    for tenant in ("", "   ", None):
        with pytest.raises(MissingTenantError):
            ctx.knowledge_package_export.execute(p.project_id, snap.id, tenant, str(tmp_path / "out"))
    assert _sin_salida(tmp_path / "out")


def test_instantanea_inexistente(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    with pytest.raises(SnapshotNotFoundError):
        ctx.knowledge_package_export.execute(p.project_id, "no-existe", TENANT, str(tmp_path / "out"))


def test_instantanea_registrada_pero_sin_carpeta_o_sin_project_db(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    s1 = ctx.release_service.publish_snapshot(p.project_id)
    s2 = ctx.release_service.publish_snapshot(p.project_id)
    shutil.rmtree(s1.snapshot_dir)  # caso histórico AGENTE UDL
    with pytest.raises(SnapshotDirectoryMissingError, match="no existe físicamente"):
        _exportar(ctx, p.project_id, s1, tmp_path / "out")
    (Path(s2.snapshot_dir) / "project.db").unlink()
    with pytest.raises(SnapshotDirectoryMissingError, match="project.db"):
        _exportar(ctx, p.project_id, s2, tmp_path / "out")
    assert _sin_salida(tmp_path / "out")


@pytest.mark.parametrize("valor", [None, ""])
def test_content_hash_null_o_vacio_bloquea(ctx, tmp_path, valor):
    p = fx.proyecto_completo(ctx, tmp_path)
    fx.sql(ctx, p.project_id, "UPDATE source SET content_hash = ? WHERE id = ?", valor, p.fuentes["r1"])
    snap = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(MissingContentHashError, match="sin huella de contenido") as exc:
        _exportar(ctx, p.project_id, snap, tmp_path / "out")
    assert "publique una instantánea nueva" in str(exc.value)
    assert [sid for sid, _ in exc.value.fuentes] == [p.fuentes["r1"]]
    assert _sin_salida(tmp_path / "out")


def test_fuente_sin_archivo_no_requiere_huella(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    fx.sql(ctx, p.project_id, "UPDATE source SET content_hash = NULL WHERE id = ?", p.fuentes["api"])
    snap = ctx.release_service.publish_snapshot(p.project_id)
    assert _exportar(ctx, p.project_id, snap, tmp_path / "out").counts["sources"] == 5


@pytest.mark.parametrize("valor", ["no-es-uuid", "", "6073EDA1-268D-48BD-8257-E6D3FEF4F981"])
def test_knowledge_base_id_invalido_bloquea(ctx, tmp_path, valor):
    p = fx.proyecto_minimo(ctx, tmp_path)
    fx.sql(ctx, p.project_id, "UPDATE project SET knowledge_base_id = ?", valor)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(MissingIdentityError, match="knowledge_base_id"):
        _exportar(ctx, p.project_id, snap, tmp_path / "out")


def test_instantanea_anterior_a_0021_bloquea(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    vieja = Path(snap.snapshot_dir) / "project.db"
    vieja.unlink()
    upgrade_project(vieja, "0020")
    con = sqlite3.connect(vieja)
    con.execute("INSERT INTO project (id,name,description,language,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)", (p.project_id, "x", "", "es", "inicial", "2026-01-01", "2026-01-01"))
    con.commit()
    con.close()
    with pytest.raises(SnapshotInconsistentError, match="0021"):
        _exportar(ctx, p.project_id, snap, tmp_path / "out")


def test_project_db_de_otro_proyecto_bloquea(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path, "Uno")
    q = fx.proyecto_minimo(ctx, tmp_path, "Dos")
    s1 = ctx.release_service.publish_snapshot(p.project_id)
    s2 = ctx.release_service.publish_snapshot(q.project_id)
    shutil.copy2(Path(s2.snapshot_dir) / "project.db", Path(s1.snapshot_dir) / "project.db")
    with pytest.raises(SnapshotInconsistentError, match="no corresponde"):
        _exportar(ctx, p.project_id, s1, tmp_path / "out")


@pytest.mark.parametrize("valor", ["", "no-es-uuid"])
def test_lineage_id_invalido_bloquea(ctx, tmp_path, valor):
    p = fx.proyecto_completo(ctx, tmp_path)
    fx.sql(ctx, p.project_id, "UPDATE source SET lineage_id = ? WHERE id = ?", valor, p.fuentes["conf"])
    snap = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(MissingIdentityError, match="lineage_id") as exc:
        _exportar(ctx, p.project_id, snap, tmp_path / "out")
    assert exc.value.entidades == [p.fuentes["conf"]]


def test_source_id_portable_duplicado_bloquea(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    # Dos versiones de la misma familia con el mismo contenido ⇒ mismo source.id.
    fx.sql(ctx, p.project_id, "UPDATE source SET content_hash = (SELECT content_hash FROM source WHERE id = ?) "
           "WHERE id = ?", p.fuentes["r1"], p.fuentes["r2"])
    snap = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(PortableIdentityCollisionError) as exc:
        _exportar(ctx, p.project_id, snap, tmp_path / "out")
    assert exc.value.tipo == "source.id"
    assert sorted(next(iter(exc.value.colisiones.values()))) == sorted([p.fuentes["r1"], p.fuentes["r2"]])
    assert _sin_salida(tmp_path / "out")


def test_chunk_id_portable_duplicado_bloquea(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    fx.sql(ctx, p.project_id, "UPDATE chunk SET chunk_index = 2, text = 'Entregar acta de nacimiento.', "
           "chunk_type = 'texto' WHERE id = ?", p.chunks["enc"])
    snap = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(PortableIdentityCollisionError) as exc:
        _exportar(ctx, p.project_id, snap, tmp_path / "out")
    assert exc.value.tipo == "chunk.id"


def test_referencias_rotas_y_restricciones_del_contrato(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    fx.sql(ctx, p.project_id, "UPDATE intent SET required_variables = '[\"no_existe\"]'")
    s1 = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(BrokenReferenceError, match="no_existe"):
        _exportar(ctx, p.project_id, s1, tmp_path / "out")
    fx.sql(ctx, p.project_id, "UPDATE intent SET required_variables = '[]'")
    fx.sql(ctx, p.project_id, "UPDATE chunk SET text = '' WHERE id = ?", p.chunks["nota"])
    s2 = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(ContractConstraintError, match="texto vacío"):
        _exportar(ctx, p.project_id, s2, tmp_path / "out")
    fx.sql(ctx, p.project_id, "UPDATE chunk SET text = 'Acuerdo.' WHERE id = ?", p.chunks["nota"])
    fx.sql(ctx, p.project_id, "DELETE FROM index_info")
    s3 = ctx.release_service.publish_snapshot(p.project_id)
    with pytest.raises(ContractConstraintError, match="índice"):
        _exportar(ctx, p.project_id, s3, tmp_path / "out")
    assert _sin_salida(tmp_path / "out")


# ------------------------------------------------------- escritura segura

def test_salida_existente_no_se_sobrescribe(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    salida = tmp_path / "out"
    salida.mkdir()
    kb = ctx.project_service.get_project(p.project_id).knowledge_base_id
    nombre = "nexom-knowledge-package-" + modulo.package_id_for(kb, snap.id, TENANT).rsplit(":", 1)[-1]
    previo = salida / f"{nombre}.content.sha256"
    previo.write_text("no tocar")
    with pytest.raises(OutputExistsError):
        _exportar(ctx, p.project_id, snap, salida)
    assert previo.read_text() == "no tocar"
    assert sorted(x.name for x in salida.iterdir()) == [previo.name]  # ni ZIP ni staging


@pytest.mark.parametrize("punto", ["zip", "verificacion", "publicacion_sidecar"])
def test_fallo_durante_staging_o_publicacion_no_deja_restos(ctx, tmp_path, monkeypatch, punto):
    p = fx.proyecto_completo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    salida = tmp_path / "out"
    clase = modulo.NexomKnowledgePackageExporter

    def falla(*a, **kw):
        raise RuntimeError(f"fallo inyectado en {punto}")

    if punto == "zip":
        monkeypatch.setattr(clase, "_escribir_zip", staticmethod(falla))
    elif punto == "verificacion":
        monkeypatch.setattr(clase, "_verificar_zip", staticmethod(falla))
    else:
        real = clase._publicar_sin_sobrescribir

        def segunda_falla(origen, destino):
            if str(destino).endswith(".content.sha256"):
                raise RuntimeError("fallo inyectado al publicar el sidecar")
            return real(origen, destino)
        monkeypatch.setattr(clase, "_publicar_sin_sobrescribir", staticmethod(segunda_falla))

    with pytest.raises(RuntimeError, match="fallo inyectado"):
        _exportar(ctx, p.project_id, snap, salida)
    assert _sin_salida(salida)  # ni ZIP final, ni sidecar, ni .nkp-staging-*
    monkeypatch.undo()
    assert Path(_exportar(ctx, p.project_id, snap, salida).zip_path).is_file()
