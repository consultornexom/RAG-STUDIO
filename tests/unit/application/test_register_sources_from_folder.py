"""Punto 2 de Validacion_observaciones_RAG_STUDIO.md: alta masiva de
fuentes desde la carpeta de entrega de RAG CONTENT STUDIO.

Contrato v2 (2026-09-29, incidencia real de portabilidad Windows ->
macOS -- ver docs proyecto/CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md,
seccion 11: "Pruebas de contrato exigidas"). Las pruebas de la seccion
"Casos de contrato (seccion 11)" de este archivo llevan el MISMO numero
que ese documento -- no reordenar ni renumerar sin actualizar ambos a
la vez.

Nota sobre `hash_contenido` en las pruebas: se calcula con `_hash()`
sobre el contenido REAL que la propia prueba escribe, nunca un valor
inventado -- desde que la verificacion de integridad (seccion 6 del
contrato) es obligatoria, un hash que no coincide con el archivo hace
que la fila se rechace aunque el nombre/ruta sea correcto."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from application.documents.commands.register_source import RegisterSource
from application.documents.commands.register_sources_from_folder import (
    MANIFEST_FILENAME,
    RegisterSourcesFromFolder,
)
from domain.documents.entities import AccessLevel, SourceType
from tests.unit.application.fakes_documents import InMemorySourceRepository

_COLUMNS = (
    "manifest_schema_version", "titulo", "tipo_fuente", "ruta_archivo", "area_propietaria",
    "nivel_acceso", "idioma", "hash_contenido", "vigente_desde", "vigente_hasta",
    "autoridad_fuente", "sustituye_a",
)

_RUTA_FIXTURE_GOLDEN_PACKAGE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "golden_package_14_entrega_rag_studio"
)


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _write_manifest(folder: Path, rows: list[dict]) -> None:
    with (folder / MANIFEST_FILENAME).open("w", encoding="utf-8", newline="") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in _COLUMNS})


def _make_use_case():
    repository = InMemorySourceRepository()
    return RegisterSourcesFromFolder(RegisterSource(repository)), repository


def test_importa_una_fila_valida_del_manifiesto(tmp_path: Path):
    contenido = "contenido de prueba"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Plan de estudios 2026",
        "tipo_fuente": "markdown",
        "ruta_archivo": "/ruta/original/en/rag-content/07_markdown/doc-1.md",
        "area_propietaria": "Control Escolar",
        "nivel_acceso": "interno",
        "idioma": "es",
        "hash_contenido": _hash(contenido),
        "vigente_desde": "2026-01-01",
        "vigente_hasta": "",
        "autoridad_fuente": "",
        "sustituye_a": "",
    }])

    use_case, repository = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))

    assert result.imported_count == 1
    assert result.skipped_count == 0
    sources = repository.list_for_project("PROY-1")
    assert len(sources) == 1
    source = sources[0]
    assert source.title == "Plan de estudios 2026"
    assert source.source_type == SourceType.MARKDOWN
    assert source.owner_area == "Control Escolar"
    assert source.access_level == AccessLevel.INTERNO
    assert source.valid_from.isoformat() == "2026-01-01"
    assert source.valid_to is None
    # location se resuelve al archivo local (junto al manifiesto), no a
    # la ruta original del CSV (inalcanzable desde RAG STUDIO).
    assert source.location == str(tmp_path / "doc-1.md")


def test_omite_fila_con_hash_ya_registrado(tmp_path: Path):
    contenido = "contenido de prueba"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Duplicado", "tipo_fuente": "markdown",
        "ruta_archivo": "/otra/ruta/doc-1.md", "hash_contenido": _hash(contenido),
    }])
    use_case, repository = _make_use_case()
    first = use_case.execute("PROY-1", str(tmp_path))
    assert first.imported_count == 1

    second = use_case.execute("PROY-1", str(tmp_path))
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert "ya estaba registrada" in second.skipped[0].reason


def test_omite_fila_sin_archivo_local(tmp_path: Path):
    _write_manifest(tmp_path, [{
        "titulo": "Sin archivo", "tipo_fuente": "markdown",
        "ruta_archivo": "/no/existe/aqui.md", "hash_contenido": "x",
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert "no se encontró" in result.skipped[0].reason


def test_nivel_acceso_no_reconocido_cae_a_interno(tmp_path: Path):
    (tmp_path / "doc-1.md").write_text("x", encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Valor libre", "tipo_fuente": "markdown", "ruta_archivo": "/x/doc-1.md",
        "nivel_acceso": "algo-que-rag-content-no-comparte-con-rag-studio",
    }])
    use_case, repository = _make_use_case()
    use_case.execute("PROY-1", str(tmp_path))
    source = repository.list_for_project("PROY-1")[0]
    assert source.access_level == AccessLevel.INTERNO


def test_manifiesto_ausente_lanza_error_explicito(tmp_path: Path):
    use_case, _ = _make_use_case()
    with pytest.raises(FileNotFoundError):
        use_case.execute("PROY-1", str(tmp_path))


# ---------- document_type_code de lote (Ronda 3, punto 12 de Validacion_observaciones_RAG_STUDIO.md) ----------

def test_sin_document_type_code_las_fuentes_importadas_quedan_en_default(tmp_path: Path):
    (tmp_path / "doc-1.md").write_text("x", encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Sin tipo", "tipo_fuente": "markdown", "ruta_archivo": "/x/doc-1.md",
    }])
    use_case, repository = _make_use_case()
    use_case.execute("PROY-1", str(tmp_path))
    source = repository.list_for_project("PROY-1")[0]
    assert source.document_type_code == "default"


def test_document_type_code_de_lote_se_asigna_a_todas_las_filas_importadas(tmp_path: Path):
    (tmp_path / "doc-1.md").write_text("x", encoding="utf-8")
    (tmp_path / "doc-2.md").write_text("y", encoding="utf-8")
    _write_manifest(tmp_path, [
        {"titulo": "Contacto 1", "tipo_fuente": "markdown", "ruta_archivo": "/x/doc-1.md",
         "hash_contenido": _hash("x")},
        {"titulo": "Contacto 2", "tipo_fuente": "markdown", "ruta_archivo": "/x/doc-2.md",
         "hash_contenido": _hash("y")},
    ])
    use_case, repository = _make_use_case()
    use_case.execute("PROY-1", str(tmp_path), document_type_code="contactos")

    sources = repository.list_for_project("PROY-1")
    assert len(sources) == 2
    assert all(s.document_type_code == "contactos" for s in sources)


# ======================================================================
# Casos de contrato (CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md,
# seccion 11) -- numeracion compartida con RAG CONTENT STUDIO y con el
# propio documento. No renumerar sin actualizar las tres fuentes.
# ======================================================================

def test_caso_01_paquete_v2_mismo_equipo(tmp_path: Path):
    contenido = "documento nuevo, contrato v2, mismo equipo"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Caso 1", "tipo_fuente": "markdown",
        "ruta_archivo": "doc-1.md", "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1
    assert result.skipped_count == 0


def test_caso_02_paquete_legado_generado_en_windows_importado_en_posix(tmp_path: Path):
    """Incidencia real: manifiesto V1 (sin manifest_schema_version) con
    ruta_archivo absoluta de Windows -- debe resolverse por su nombre
    de archivo, sin importar que este proceso corra en un sistema
    POSIX."""
    contenido = "contenido generado en windows"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Caso 2", "tipo_fuente": "markdown",
        "ruta_archivo": "C:\\Users\\sopor\\RAG Content Studio Desktop\\proyectos\\PROY-9928\\07_markdown\\doc-1.md",
        "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1
    assert result.skipped_count == 0


def test_caso_03_paquete_legado_generado_en_posix_importado_en_otro_entorno(tmp_path: Path):
    contenido = "contenido generado en macOS/Linux"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Caso 3", "tipo_fuente": "markdown",
        "ruta_archivo": "/Users/alguien/RAG Content Studio/proyectos/PROY-1/07_markdown/doc-1.md",
        "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1
    assert result.skipped_count == 0


def test_caso_04_manifiesto_legado_con_ruta_absoluta_inexistente_pero_md_presente(tmp_path: Path):
    """La ruta absoluta del CSV no existe en este equipo (nunca podria
    existir -- es la ruta del equipo PRODUCTOR), pero el .md esta
    fisicamente en el paquete: debe importarse igual, sin edicion
    manual del manifiesto."""
    contenido = "contenido de PROY-9928"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    ruta_muerta = "C:\\Users\\sopor\\RAG Content Studio Desktop\\proyectos\\PROY-9928\\07_markdown\\doc-1.md"
    assert not Path(ruta_muerta).exists()
    _write_manifest(tmp_path, [{
        "titulo": "Caso 4", "tipo_fuente": "markdown", "ruta_archivo": ruta_muerta,
        "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1
    assert result.skipped_count == 0


def test_caso_05_referencia_a_archivo_que_realmente_no_existe(tmp_path: Path):
    _write_manifest(tmp_path, [{
        "titulo": "Caso 5", "tipo_fuente": "markdown",
        "ruta_archivo": "/x/no-existe-en-ningun-lado.md", "hash_contenido": "x",
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert "no se encontró" in result.skipped[0].reason


def test_caso_06_ambiguedad_legado_dos_candidatos_para_el_mismo_nombre(tmp_path: Path):
    (tmp_path / "doc-1.md").write_text("version A", encoding="utf-8")
    subcarpeta = tmp_path / "otra_subcarpeta"
    subcarpeta.mkdir()
    (subcarpeta / "doc-1.md").write_text("version B", encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Caso 6", "tipo_fuente": "markdown",
        "ruta_archivo": "/x/doc-1.md", "hash_contenido": _hash("version A"),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert "ambigua" in result.skipped[0].reason


def test_caso_07_v2_con_ruta_absoluta_se_rechaza(tmp_path: Path):
    contenido = "no deberia importarse"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Caso 7", "tipo_fuente": "markdown",
        "ruta_archivo": "/doc-1.md", "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert "absoluta" in result.skipped[0].reason


def test_caso_08_v2_con_escape_de_directorio_se_rechaza(tmp_path: Path):
    fuera = tmp_path.parent / "fuera_del_paquete.md"
    fuera.write_text("secreto fuera del paquete", encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Caso 8", "tipo_fuente": "markdown",
        "ruta_archivo": "../fuera_del_paquete.md", "hash_contenido": _hash("secreto fuera del paquete"),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert ".." in result.skipped[0].reason or "path traversal" in result.skipped[0].reason
    fuera.unlink()


def test_caso_09_archivo_encontrado_pero_hash_no_coincide_se_rechaza(tmp_path: Path):
    (tmp_path / "doc-1.md").write_text("contenido real del archivo", encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Caso 9", "tipo_fuente": "markdown",
        "ruta_archivo": "doc-1.md", "hash_contenido": _hash("contenido DECLARADO, distinto del real"),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert result.skipped[0].reason == (
        "el archivo fue localizado, pero su contenido no coincide con el hash declarado en el manifiesto"
    )


def test_caso_10_dos_filas_resuelven_al_mismo_archivo_con_hash_distinto_se_rechazan_ambas(tmp_path: Path):
    (tmp_path / "doc-1.md").write_text("contenido unico", encoding="utf-8")
    _write_manifest(tmp_path, [
        {"manifest_schema_version": "2", "titulo": "Caso 10 - fila A", "tipo_fuente": "markdown",
         "ruta_archivo": "doc-1.md", "hash_contenido": _hash("contenido unico")},
        {"manifest_schema_version": "2", "titulo": "Caso 10 - fila B", "tipo_fuente": "markdown",
         "ruta_archivo": "doc-1.md", "hash_contenido": _hash("otro contenido que no es el real")},
    ])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 0
    assert result.skipped_count == 2
    assert all("ambigua" in fila.reason for fila in result.skipped)


def test_caso_11_manifiesto_sin_version_con_ruta_windows_se_acepta_via_legado(tmp_path: Path):
    contenido = "caso 11"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Caso 11", "tipo_fuente": "markdown",
        "ruta_archivo": "C:\\proyectos\\PROY-1\\07_markdown\\doc-1.md",
        "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1


def test_caso_12_manifiesto_sin_version_con_ruta_posix_se_acepta_via_legado(tmp_path: Path):
    contenido = "caso 12"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "titulo": "Caso 12", "tipo_fuente": "markdown",
        "ruta_archivo": "/home/alguien/proyectos/PROY-1/07_markdown/doc-1.md",
        "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1


def test_caso_13_manifiesto_v2_con_referencia_relativa_valida_se_acepta(tmp_path: Path):
    contenido = "caso 13"
    subcarpeta = tmp_path / "anexos"
    subcarpeta.mkdir()
    (subcarpeta / "doc-anexo.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Caso 13", "tipo_fuente": "markdown",
        "ruta_archivo": "anexos/doc-anexo.md", "hash_contenido": _hash(contenido),
    }])
    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))
    assert result.imported_count == 1
    assert result.skipped_count == 0


def test_caso_14_golden_package_producido_por_content_e_importado_por_studio(tmp_path: Path):
    """Paquete contractual identico al que checa RAG CONTENT STUDIO
    (tests/fixtures/golden_package_14_entrega_rag_studio/, con copia
    idéntica en ambos repos -- ver seccion 11 del contrato sobre por
    que no hay una sola prueba que cruce ambos entornos/virtualenvs).
    Este lado solo verifica la importacion; el lado de RAG CONTENT
    STUDIO verifica que su propio generador produce un manifiesto con
    esta misma forma."""
    assert _RUTA_FIXTURE_GOLDEN_PACKAGE.is_dir(), (
        f"Fixture del golden package no encontrado en {_RUTA_FIXTURE_GOLDEN_PACKAGE}"
    )
    use_case, repository = _make_use_case()
    result = use_case.execute("PROY-1", str(_RUTA_FIXTURE_GOLDEN_PACKAGE))
    assert result.skipped_count == 0
    assert result.imported_count == 2
    titulos = {source.title for source in repository.list_for_project("PROY-1")}
    assert titulos == {"Documento A (golden package)", "Documento B (golden package)"}


# ---------------------------------------------------------------------------
# Auditoria 2026-09-30 (incidencia: lote generado en Windows rechazado por
# hash). La verificacion sigue siendo sobre los bytes exactos.
# ---------------------------------------------------------------------------


def test_crlf_con_hash_calculado_sobre_lf_se_sigue_rechazando(tmp_path: Path):
    """El receptor NO normaliza fines de linea (contrato, seccion 6.1): la
    correccion corresponde al productor."""
    (tmp_path / "doc-1.md").write_bytes(b"# Titulo\r\n\r\nTexto.\r\n")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Doc", "tipo_fuente": "markdown",
        "ruta_archivo": "doc-1.md", "hash_contenido": hashlib.sha256(b"# Titulo\n\nTexto.\n").hexdigest(),
    }])

    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))

    assert result.imported_count == 0
    assert "no coincide con el hash" in result.skipped[0].reason


def test_manifiesto_con_bom_se_lee_como_v2(tmp_path: Path):
    """Dos archivos con el mismo nombre en subcarpetas distintas: como V2
    la fila "a/doc.md" se resuelve directo; si el BOM hiciera tratarla como
    legado, el resolutor por nombre la rechazaria como ambigua."""
    contenido = "contenido a"
    for sub, texto in (("a", contenido), ("b", "contenido b")):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "doc.md").write_text(texto, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Doc", "tipo_fuente": "markdown",
        "ruta_archivo": "a/doc.md", "hash_contenido": _hash(contenido),
    }])
    ruta = tmp_path / MANIFEST_FILENAME
    ruta.write_bytes(b"\xef\xbb\xbf" + ruta.read_bytes())

    use_case, _ = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))

    assert result.imported_count == 1, [s.reason for s in result.skipped]


def test_hash_declarado_en_mayusculas_se_acepta(tmp_path: Path):
    contenido = "contenido"
    (tmp_path / "doc-1.md").write_text(contenido, encoding="utf-8")
    _write_manifest(tmp_path, [{
        "manifest_schema_version": "2", "titulo": "Doc", "tipo_fuente": "markdown",
        "ruta_archivo": "doc-1.md", "hash_contenido": _hash(contenido).upper(),
    }])

    use_case, repository = _make_use_case()
    result = use_case.execute("PROY-1", str(tmp_path))

    assert result.imported_count == 1
