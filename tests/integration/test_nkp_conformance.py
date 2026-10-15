"""RAG-INC-01c — compuerta de conformidad NEXOM Knowledge Package v1.0.0.

Para cada paquete se ejecutan la compuerta interna y el validador firmado
vendorizado (proceso aparte) y se exige equivalencia: válido → válido,
inválido → inválido, sin falsos PASS de la compuerta. Única excepción
documentada: identificadores repetidos, que el validador firmado no detecta
y la compuerta sí (más estricta)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.lifecycle import shutdown, start
from contracts.nexom_knowledge_package import V1_0_0_DIR
from domain.knowledge_package.conformance import (
    ConformanceCategory,
    ConformanceReport,
    ConformanceStatus,
)
from domain.knowledge_package.exceptions import ContractConformanceError
from domain.knowledge_package.ports import KnowledgePackageConformanceValidator
from infrastructure.exporters import nexom_knowledge_package as modulo
from infrastructure.exporters import nkp_conformance
from infrastructure.exporters.nkp_conformance import ContractV1ConformanceValidator

from . import nkp_conformance_cases as cc
from . import nkp_export_fixtures as fx

pytestmark = pytest.mark.skipif(not fx.validador_disponible(), reason="dependencias del validador v1.0.0 ausentes")

GATE = ContractV1ConformanceValidator()


def _firmado(ruta: Path, sidecar: Path | None = None) -> tuple[int, str]:
    cmd = [sys.executable, str(fx.VALIDADOR), str(ruta)]
    if sidecar is not None:
        cmd += ["--content-digest-file", str(sidecar)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture(scope="module")
def paquetes(tmp_path_factory):
    """Paquetes CORE completo y mínimo generados por el exportador (una sola vez)."""
    tmp = tmp_path_factory.mktemp("nkp01c")
    ctx = start(base_dir=tmp / "inst")
    try:
        completo = fx.proyecto_completo(ctx, tmp)
        minimo = fx.proyecto_minimo(ctx, tmp)
        resultado = {}
        for nombre, p in (("completo", completo), ("minimo", minimo)):
            snap = ctx.release_service.publish_snapshot(p.project_id)
            resultado[nombre] = ctx.knowledge_package_export.execute(p.project_id, snap.id, "nexom", str(tmp / nombre))
        yield resultado, tmp
    finally:
        shutdown(ctx)


# ---------------------------------------------------------------- válidos

@pytest.mark.parametrize("nombre", ["completo", "minimo"])
def test_fixture_valida_pasa_compuerta_y_validador_firmado(paquetes, nombre):
    resultados, tmp = paquetes
    r = resultados[nombre]
    assert r.conformance is not None and r.conformance.status == ConformanceStatus.PASS  # del exportador
    reporte = GATE.validate(r.zip_path, r.content_digest_path)
    assert reporte.passed and reporte.issues == () and reporte.checks_ok > 0, reporte.summary()
    rc, salida = _firmado(Path(r.zip_path), Path(r.content_digest_path))
    assert rc == 0 and "ERRORES: 0" in salida
    directorio = cc.preparar(Path(r.zip_path), tmp / f"dir_{nombre}")
    assert GATE.validate(str(directorio), str(cc.sidecar(directorio))).passed
    assert _firmado(directorio, cc.sidecar(directorio))[0] == 0


def test_fixture_oficial_del_contrato_pasa():
    ejemplo = V1_0_0_DIR / "example_package"
    sidecar = V1_0_0_DIR / "delivery" / "nexom-knowledge-package-demo-v1.0.0.content.sha256"
    assert GATE.validate(str(ejemplo), str(sidecar)).passed
    assert GATE.validate(str(V1_0_0_DIR / "nexom-knowledge-package-demo-v1.0.0.zip"), str(sidecar)).passed
    rc, salida = _firmado(ejemplo, sidecar)
    assert rc == 0 and "ERRORES: 0" in salida


def test_suite_negativa_firmada_20_de_20():
    """validator/test_negative_cases.py (QA §4.2, vendorizado) sobre la copia vendorizada."""
    r = subprocess.run([sys.executable, str(V1_0_0_DIR / "validator" / "test_negative_cases.py")],
                       capture_output=True, text=True, timeout=600, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": ""})
    assert r.returncode == 0 and "RESUMEN: 20/20 casos correctos" in r.stdout, r.stdout + r.stderr


# --------------------------------------------------------------- negativos

ESPERADO = {
    "schema_roto": ConformanceCategory.SCHEMA,
    "manifest_invalido": ConformanceCategory.SCHEMA,
    "checksum_roto": ConformanceCategory.CHECKSUM,
    "content_digest_roto": ConformanceCategory.CONTENT_DIGEST,
    "source_id_incorrecto": ConformanceCategory.IDS,
    "chunk_id_incorrecto": ConformanceCategory.IDS,
    "id_duplicado": ConformanceCategory.UNICIDAD,
    "archivo_requerido_faltante": ConformanceCategory.SCHEMA,
    "archivo_inesperado": ConformanceCategory.ESTRUCTURA,
    "referencia_rota": ConformanceCategory.REFERENCIA,
    "cardinalidad_incorrecta": ConformanceCategory.CARDINALIDAD,
    "metadata_schema_invalido": ConformanceCategory.REFERENCIA,
    "embeddings_invalidos": ConformanceCategory.SCHEMA,
    "indice_sin_espacio": ConformanceCategory.REFERENCIA,
    "access_hierarchy_invalida": ConformanceCategory.SCHEMA,
    "bundle_invalido": ConformanceCategory.REFERENCIA,
    "acceptance_invalido": ConformanceCategory.ACEPTACION,
}


@pytest.mark.parametrize("caso", sorted(cc.CASOS_DIRECTORIO))
def test_negativo_rechazado_y_equivalente_al_validador_firmado(paquetes, caso):
    resultados, tmp = paquetes
    d = cc.preparar(Path(resultados["completo"].zip_path), tmp / "neg" / caso)
    cc.CASOS_DIRECTORIO[caso](d)
    reporte = GATE.validate(str(d), str(cc.sidecar(d)))
    assert reporte.status == ConformanceStatus.FAIL
    assert ESPERADO[caso] in {i.category for i in reporte.issues}, reporte.summary()
    rc, _ = _firmado(d, cc.sidecar(d))
    if caso == "id_duplicado":
        # Hallazgo 01c: el validador firmado indexa registros por id en un
        # diccionario y acepta el duplicado (rc 0); la compuerta lo rechaza.
        assert rc == 0
        assert all(i.origin == nkp_conformance.ORIGEN_RAG_STUDIO for i in reporte.issues)
    else:
        assert rc == 1  # equivalencia: inválido → inválido


@pytest.mark.parametrize("coleccion", ["sources", "intents", "catalog_entries"])
def test_unicidad_en_otras_colecciones(paquetes, coleccion):
    resultados, tmp = paquetes
    d = cc.preparar(Path(resultados["completo"].zip_path), tmp / "uni" / coleccion)
    if coleccion == "sources":
        fuentes = cc.leer_jsonl(d, "sources.jsonl")
        (d / "sources.jsonl").write_bytes(cc.k.canonical_jsonl_bytes(fuentes) + cc.k.canonical_jsonl_bytes([fuentes[0]]))
        m = cc.leer_json(d, "manifest.json")
        m["counts"]["sources"] += 1
        cc.escribir_json(d, "manifest.json", m)
    elif coleccion == "intents":
        b = cc.leer_json(d, "conversational_bundle.json")
        b["intents"].append(dict(b["intents"][0]))
        cc.escribir_json(d, "conversational_bundle.json", b)
        m = cc.leer_json(d, "manifest.json")
        m["counts"]["intents"] += 1
        cc.escribir_json(d, "manifest.json", m)
    else:
        ms = cc.leer_json(d, "metadata_schema.json")
        ms["catalogs"][0]["entries"].append(dict(ms["catalogs"][0]["entries"][0]))
        cc.escribir_json(d, "metadata_schema.json", ms)
    cc.recalcular(d)
    reporte = GATE.validate(str(d), str(cc.sidecar(d)))
    assert not reporte.passed and ConformanceCategory.UNICIDAD in {i.category for i in reporte.issues}


@pytest.mark.parametrize("manipulacion", ["entrada_extra", "contenido_alterado"])
def test_manipulacion_posterior_del_zip(paquetes, manipulacion):
    resultados, tmp = paquetes
    r = resultados["completo"]
    funcion = cc.zip_con_entrada_extra if manipulacion == "entrada_extra" else cc.zip_con_contenido_alterado
    alterado = funcion(Path(r.zip_path), tmp / f"manipulado_{manipulacion}.zip")
    assert not GATE.validate(str(alterado), r.content_digest_path).passed
    assert _firmado(alterado, Path(r.content_digest_path))[0] == 1


def test_contrato_vendorizado_alterado_falla_cerrado(tmp_path, monkeypatch, paquetes):
    copia = tmp_path / "v1_0_0"
    shutil.copytree(V1_0_0_DIR, copia, ignore=shutil.ignore_patterns("__pycache__"))
    esquema = copia / "schemas" / "chunk.schema.json"
    esquema.write_text(esquema.read_text().replace('"minimum": 0', '"minimum": 1', 1))
    monkeypatch.setattr(nkp_conformance, "V1_0_0_DIR", copia)
    reporte = ContractV1ConformanceValidator().validate(paquetes[0]["minimo"].zip_path)
    assert reporte.status == ConformanceStatus.FAIL
    assert [i.category for i in reporte.issues] == [ConformanceCategory.CONTRATO]
    assert "chunk.schema.json" in reporte.issues[0].message


# ------------------------------------------------- integración exportador

class _Rechaza(KnowledgePackageConformanceValidator):
    def __init__(self):
        self.validados: list[str] = []

    def validate(self, package_path, content_digest_file=None):
        self.validados.append(package_path)
        assert Path(package_path).is_file() and Path(content_digest_file).is_file()  # se valida lo que se publicaría
        from domain.knowledge_package.conformance import ConformanceIssue

        return ConformanceReport(ConformanceStatus.FAIL, "1.0.0", 0, (
            ConformanceIssue(ConformanceCategory.SCHEMA, "[schema] defecto simulado", "prueba"),))


@pytest.fixture
def ctx(tmp_path):
    context = start(base_dir=tmp_path / "inst")
    yield context
    shutdown(context)


def test_exportador_no_publica_si_la_compuerta_falla(ctx, tmp_path):
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    rechazo = _Rechaza()
    ctx.knowledge_package_export._exporter = modulo.NexomKnowledgePackageExporter(conformance=rechazo)
    salida = tmp_path / "out"
    with pytest.raises(ContractConformanceError, match="no cumple el contrato") as exc:
        ctx.knowledge_package_export.execute(p.project_id, snap.id, "nexom", str(salida))
    assert exc.value.report.issues[0].message == "[schema] defecto simulado"
    assert len(rechazo.validados) == 1 and ".nkp-staging-" in rechazo.validados[0]
    assert not any(salida.iterdir())  # ni ZIP, ni sidecar, ni staging


def test_compuerta_real_rechaza_un_defecto_del_exportador(ctx, tmp_path, monkeypatch):
    """Si el exportador generara algo no conforme, la compuerta real lo
    detiene antes de publicar (se simula alterando la regla de acceso)."""
    p = fx.proyecto_minimo(ctx, tmp_path)
    snap = ctx.release_service.publish_snapshot(p.project_id)
    monkeypatch.setattr(modulo, "_ACCESS_RULE", "regla distinta a la constante del contrato")
    salida = tmp_path / "out"
    with pytest.raises(ContractConformanceError) as exc:
        ctx.knowledge_package_export.execute(p.project_id, snap.id, "nexom", str(salida))
    assert exc.value.report.by_category() == {"schema": 1}
    assert not any(salida.iterdir())


def test_exportador_usa_la_compuerta_del_contrato_por_defecto():
    exportador = modulo.NexomKnowledgePackageExporter()
    assert isinstance(exportador._conformance, ContractV1ConformanceValidator)
