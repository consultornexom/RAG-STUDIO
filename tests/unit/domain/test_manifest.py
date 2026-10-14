"""Pruebas unitarias de domain.documents.manifest (contrato de
intercambio v2, ver docs proyecto/CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md
-- incidencia real de portabilidad Windows -> macOS, 2026-09-29)."""
from __future__ import annotations

import pytest

from domain.documents.manifest import (
    RutaManifiestoInsegura,
    es_manifiesto_v2,
    extraer_nombre_base_multiplataforma,
    validar_ruta_relativa_manifiesto,
)


@pytest.mark.parametrize(
    ("version_declarada", "esperado"),
    [
        ("2", True),
        (" 2 ", True),
        ("1", False),
        ("", False),
        (None, False),
        ("v2", False),
    ],
)
def test_es_manifiesto_v2(version_declarada, esperado):
    assert es_manifiesto_v2(version_declarada) is esperado


@pytest.mark.parametrize(
    "ruta",
    [
        "doc-1.md",
        "documents/doc-1.md",
        "a/b/c/doc.md",
    ],
)
def test_validar_ruta_relativa_manifiesto_acepta_rutas_seguras(ruta):
    assert validar_ruta_relativa_manifiesto(ruta) == ruta


@pytest.mark.parametrize(
    "ruta",
    [
        "",
        "   ",
        "/doc-1.md",
        "~/doc-1.md",
        "C:/Users/sopor/doc-1.md",
        "C:\\Users\\sopor\\doc-1.md",
        "doc-1.md\\otro",
        "../doc-1.md",
        "../../etc/passwd",
        "documents/../../../etc/passwd",
        "..",
    ],
)
def test_validar_ruta_relativa_manifiesto_rechaza_rutas_inseguras(ruta):
    with pytest.raises(RutaManifiestoInsegura):
        validar_ruta_relativa_manifiesto(ruta)


@pytest.mark.parametrize(
    ("ruta", "nombre_esperado"),
    [
        ("doc-1.md", "doc-1.md"),
        ("/proyecto/07_markdown/doc-1.md", "doc-1.md"),
        (
            "C:\\Users\\sopor\\RAG Content Studio Desktop\\proyectos\\PROY-9928\\07_markdown\\doc-1.md",
            "doc-1.md",
        ),
        ("C:/Users/sopor/07_markdown/doc-1.md", "doc-1.md"),
        ("a/b\\c/doc-1.md", "doc-1.md"),
    ],
)
def test_extraer_nombre_base_multiplataforma(ruta, nombre_esperado):
    """Caso central de la incidencia real: una ruta absoluta de Windows
    (con backslashes) debe resolverse a su nombre de archivo sin
    importar en que sistema operativo corre este proceso -- a
    diferencia de `pathlib.Path(...).name`, que solo reconoce el
    separador nativo de ESTE sistema operativo."""
    assert extraer_nombre_base_multiplataforma(ruta) == nombre_esperado


@pytest.mark.parametrize("ruta", ["", "   ", "///", "\\\\\\"])
def test_extraer_nombre_base_multiplataforma_devuelve_vacio_si_no_hay_segmento(ruta):
    assert extraer_nombre_base_multiplataforma(ruta) == ""
