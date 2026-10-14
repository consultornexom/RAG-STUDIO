"""Pruebas de integración reales de los extractores (sin mocks): se
generan archivos .txt/.md/.docx/.pdf válidos y se verifica el texto
extraído, siguiendo el criterio de aceptación de A2/A3 (trazabilidad y
reproducibilidad)."""
import io

import docx
import pytest

from domain.documents.entities import SourceType
from domain.ingestion.exceptions import OcrEngineUnavailableError, UnsupportedSourceTypeError
from domain.ingestion.ports import OcrEngine
from infrastructure.extraction.ocr_engine import ocr_dependencies_available, TesseractOcrEngine
from infrastructure.extraction.text_extractors import (
    CompositeTextExtractor, HtmlExtractor, ImageNativeExtractor, ImageTextExtractor, JsonExtractor,
    PdfTextExtractor, XmlExtractor, repair_letter_spaced_text,
)

try:
    import fitz  # PyMuPDF -- extra opcional "ocr"; las pruebas que lo
    # necesitan (construir PDFs escaneados de prueba) se omiten si no
    # está instalado, sin afectar al resto de este archivo.
    from PIL import Image, ImageDraw, ImageFont
    _OCR_TEST_DEPS_AVAILABLE = True
except ImportError:
    _OCR_TEST_DEPS_AVAILABLE = False

_requires_ocr_test_deps = pytest.mark.skipif(
    not _OCR_TEST_DEPS_AVAILABLE,
    reason="PyMuPDF/Pillow (extra 'ocr') no instalados -- se omiten pruebas de OCR/páginas escaneadas",
)
_requires_real_tesseract = pytest.mark.skipif(
    not ocr_dependencies_available(),
    reason="pytesseract/Pillow/PyMuPDF no disponibles -- se omiten pruebas con Tesseract real",
)

# PDF mínimo válido de una página con una cadena de texto real, escrito
# a mano en sintaxis PDF cruda (sin dependencias adicionales solo para
# generar el archivo de prueba).
_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 78 >>
stream
BT /F1 24 Tf 72 700 Td (Hola desde un PDF de prueba) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF"""


@pytest.fixture
def extractor():
    return CompositeTextExtractor()


def test_extracts_txt_verbatim(tmp_path, extractor):
    path = tmp_path / "sample.txt"
    path.write_text("Este es un texto de prueba.\nSegunda línea.", encoding="utf-8")

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.TXT)
    assert text == "Este es un texto de prueba.\nSegunda línea."
    assert method == "texto_plano"
    assert page_breaks == []
    assert warnings == []


def test_extracts_markdown_verbatim_preserving_headings(tmp_path, extractor):
    content = "# Sección Uno\nContenido.\n"
    path = tmp_path / "sample.md"
    path.write_text(content, encoding="utf-8")

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.MARKDOWN)
    assert text == content
    assert text.startswith("# ")


def test_extracts_docx_and_normalizes_headings_to_markdown(tmp_path, extractor):
    path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_heading("Título del documento", level=0)
    document.add_paragraph("Contenido introductorio.")
    document.add_heading("Primera sección", level=1)
    document.add_paragraph("Texto de la primera sección.")
    document.save(str(path))

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.DOCX)
    assert method == "docx"
    assert page_breaks == []
    assert "# Título del documento" in text
    assert "# Primera sección" in text
    assert "Contenido introductorio." in text


def test_extracts_docx_tables_as_markdown_pipe_tables_in_document_order(tmp_path, extractor):
    # Módulo 5 (tipo documental "tabla"): sin esto, una tabla DOCX
    # desaparecía del texto extraído por completo -- document.paragraphs
    # nunca incluye tablas (ver infrastructure/extraction/text_extractors.py,
    # _iter_block_items/_table_to_markdown).
    path = tmp_path / "con_tabla.docx"
    document = docx.Document()
    document.add_paragraph("Texto antes de la tabla.")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Programa"
    table.rows[0].cells[1].text = "Plantel"
    table.rows[1].cells[0].text = "Ing. Biomédica"
    table.rows[1].cells[1].text = "Mérida"
    document.add_paragraph("Texto después de la tabla.")
    document.save(str(path))

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.DOCX)
    assert method == "docx"
    before_index = text.index("Texto antes de la tabla.")
    header_index = text.index("| Programa | Plantel |")
    separator_index = text.index("| --- | --- |")
    row_index = text.index("| Ing. Biomédica | Mérida |")
    after_index = text.index("Texto después de la tabla.")
    assert before_index < header_index < separator_index < row_index < after_index


def test_extracts_xlsx_sheets_as_headings_with_markdown_tables(tmp_path, extractor):
    import openpyxl

    path = tmp_path / "catalogo.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Programas"
    sheet.append(["codigo", "nombre", "duracion_cuatrimestres"])
    sheet.append(["ISC", "Ingeniería en Sistemas", 12])
    sheet.append(["LAE", "Licenciatura en Administración", 9])
    workbook.create_sheet("VacíaDePrueba")
    workbook.save(str(path))

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.XLSX)
    assert method == "xlsx"
    assert page_breaks == []
    assert "## Programas" in text
    assert "| codigo | nombre | duracion_cuatrimestres |" in text
    assert "| ISC | Ingeniería en Sistemas | 12 |" in text
    assert any("VacíaDePrueba" in w for w in warnings)


def test_extracts_xlsx_structured_blocks_with_native_rows_per_sheet(tmp_path, extractor):
    # Pista B.2 del ADR-003: extract_structured_blocks() no aplana a
    # Markdown -- filas y columnas nativas, una hoja vacía se omite
    # igual que en extract() (sin aparecer como bloque vacío).
    import openpyxl

    path = tmp_path / "catalogo.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Programas"
    sheet.append(["codigo", "nombre", "duracion_cuatrimestres"])
    sheet.append(["ISC", "Ingeniería en Sistemas", 12])
    sheet.append(["LAE", "Licenciatura en Administración", 9])
    workbook.create_sheet("VacíaDePrueba")
    workbook.save(str(path))

    blocks = extractor.extract_structured_blocks(str(path), SourceType.XLSX)
    assert set(blocks.keys()) == {"Programas"}
    assert blocks["Programas"]["columnas"] == ["codigo", "nombre", "duracion_cuatrimestres"]
    assert blocks["Programas"]["filas"] == [
        {"codigo": "ISC", "nombre": "Ingeniería en Sistemas", "duracion_cuatrimestres": "12"},
        {"codigo": "LAE", "nombre": "Licenciatura en Administración", "duracion_cuatrimestres": "9"},
    ]


def test_extracts_xlsx_reads_calculated_formula_value_not_the_formula(tmp_path, extractor):
    import openpyxl

    path = tmp_path / "formula.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Datos"
    sheet["A1"] = "total"
    sheet["A2"] = "=1+1"
    workbook.save(str(path))
    # openpyxl no recalcula fórmulas al guardar sin Excel real -- se
    # simula el valor ya calculado reabriendo y sobreescribiendo la
    # celda con el resultado, para verificar que data_only=True lee un
    # valor (no la cadena de la fórmula) cuando el libro sí lo trae.
    with_value = openpyxl.load_workbook(str(path))
    with_value["Datos"]["A2"] = 2
    with_value.save(str(path))

    text, _, _, _ = extractor.extract(str(path), SourceType.XLSX)
    assert "=1+1" not in text
    assert "| total |" in text
    assert "| 2 |" in text


def test_extracts_csv_as_a_single_markdown_table(tmp_path, extractor):
    path = tmp_path / "programas.csv"
    path.write_text("codigo,nombre\nISC,Ingeniería en Sistemas\nLAE,Licenciatura en Administración\n", encoding="utf-8")

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.CSV)
    assert method == "csv"
    assert page_breaks == []
    assert warnings == []
    assert text.splitlines() == [
        "| codigo | nombre |",
        "| --- | --- |",
        "| ISC | Ingeniería en Sistemas |",
        "| LAE | Licenciatura en Administración |",
    ]


def test_extracts_csv_detects_semicolon_delimiter(tmp_path, extractor):
    path = tmp_path / "programas_es.csv"
    path.write_text("codigo;nombre\nISC;Ingeniería en Sistemas\n", encoding="utf-8")

    text, _, _, _ = extractor.extract(str(path), SourceType.CSV)
    assert "| codigo | nombre |" in text
    assert "| ISC | Ingeniería en Sistemas |" in text


def test_extracts_csv_strips_utf8_bom(tmp_path, extractor):
    path = tmp_path / "con_bom.csv"
    path.write_bytes("codigo,nombre\nISC,Sistemas\n".encode("utf-8-sig"))

    text, _, _, _ = extractor.extract(str(path), SourceType.CSV)
    assert text.startswith("| codigo | nombre |")


def test_csv_with_no_data_rows_produces_a_warning_instead_of_a_broken_table(tmp_path, extractor):
    path = tmp_path / "vacio.csv"
    path.write_text("", encoding="utf-8")

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.CSV)
    assert text == ""
    assert warnings != []


def test_extracts_csv_structured_blocks_under_the_fixed_key_datos(tmp_path, extractor):
    # Pista B.2 del ADR-003: un CSV no tiene varias tablas nombradas
    # (a diferencia de XLSX con hojas) -- se usa la clave fija "datos".
    path = tmp_path / "programas.csv"
    path.write_text("codigo,nombre\nISC,Ingeniería en Sistemas\nLAE,Licenciatura en Administración\n", encoding="utf-8")

    blocks = extractor.extract_structured_blocks(str(path), SourceType.CSV)
    assert set(blocks.keys()) == {"datos"}
    assert blocks["datos"]["columnas"] == ["codigo", "nombre"]
    assert blocks["datos"]["filas"] == [
        {"codigo": "ISC", "nombre": "Ingeniería en Sistemas"},
        {"codigo": "LAE", "nombre": "Licenciatura en Administración"},
    ]


def test_csv_structured_blocks_empty_when_no_data_rows(tmp_path, extractor):
    path = tmp_path / "vacio.csv"
    path.write_text("", encoding="utf-8")

    assert extractor.extract_structured_blocks(str(path), SourceType.CSV) == {}


def test_non_xlsx_csv_extractors_default_to_empty_structured_blocks(tmp_path, extractor):
    # Ítem central del diseño B.2: extract_structured_blocks() es un
    # método concreto en el puerto TextExtractor con "return {}" por
    # defecto -- ningún extractor que no sea XLSX/CSV necesita
    # sobrescribirlo, y CompositeTextExtractor debe seguir despachando
    # correctamente hacia ese comportamiento por defecto.
    path = tmp_path / "sample.txt"
    path.write_text("contenido cualquiera", encoding="utf-8")

    assert extractor.extract_structured_blocks(str(path), SourceType.TXT) == {}


def test_extracts_pdf_text_layer(tmp_path, extractor):
    path = tmp_path / "sample.pdf"
    path.write_bytes(_MINIMAL_PDF)

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.PDF)
    assert "Hola desde un PDF de prueba" in text
    assert method == "pdf_texto"
    assert page_breaks == []  # una sola página: no hay saltos que registrar


def test_unsupported_source_type_raises(tmp_path, extractor):
    # API y base_de_datos son los dos tipos que quedan deliberadamente
    # sin extractor (ver README, "Deliberadamente fuera de alcance"):
    # no son archivos, son conexiones vivas.
    path = tmp_path / "sample.txt"
    path.write_text("no importa el contenido", encoding="utf-8")
    with pytest.raises(UnsupportedSourceTypeError):
        extractor.extract(str(path), SourceType.API)


# ---------- repair_letter_spaced_text (hallazgo real: pypdf a veces
# extrae texto letra por letra en fuentes con tracking amplio) ----------

def test_repair_letter_spaced_text_joins_a_real_reported_case():
    # Caso real reportado por el usuario: "3 e r . C u a t r i m e s t r e"
    # extraído de un plan de estudios en PDF.
    result = repair_letter_spaced_text("3 e r . C u a t r i m e s t r e")
    assert result == "3er. Cuatrimestre"


def test_repair_letter_spaced_text_leaves_normal_text_untouched():
    text = "Formar profesionales capaces de diseñar sistemas electromecánicos."
    assert repair_letter_spaced_text(text) == text


def test_repair_letter_spaced_text_does_not_touch_short_runs_of_single_letters():
    # 3 "palabras" de una letra o menos no deben tocarse -- son
    # frecuentes en español normal (y, o, a) y no son el artefacto.
    text = "el gato y el perro"
    assert repair_letter_spaced_text(text) == text


def test_repair_letter_spaced_text_preserves_surrounding_normal_words():
    text = "Plan de Estudios\n1 e r . C u a t r i m e s t r e\nÁlgebra Lineal"
    result = repair_letter_spaced_text(text)
    assert result == "Plan de Estudios\n1er. Cuatrimestre\nÁlgebra Lineal"


def test_repair_letter_spaced_text_respects_custom_min_run():
    text = "a b c d"  # corrida de 4 letras -- min_run=5 la deja intacta
    assert repair_letter_spaced_text(text, min_run=5) == text


def test_repair_letter_spaced_text_joins_short_abbreviation_before_a_real_word():
    # Caso real reportado por el usuario, segunda ronda de pruebas:
    # solo la abreviatura "3er." quedó letra-espaciada (con el punto
    # pegado a la "r"), y la palabra siguiente ("Cuatrimestre") ya
    # estaba intacta -- pypdf deja un espacio doble justo en ese punto
    # (el hueco real entre palabras del PDF original), y esa es la
    # señal que permite corregir la abreviatura aunque la corrida sea
    # más corta que `min_run`.
    result = repair_letter_spaced_text("3 e r.  Cuatrimestre")
    assert "3er." in result
    assert "Cuatrimestre" in result
    # normaliza espacios para comparar el contenido, no el espaciado
    # cosmético entre la abreviatura corregida y la palabra siguiente.
    assert " ".join(result.split()) == "3er. Cuatrimestre"


def test_repair_letter_spaced_text_does_not_join_a_single_letter_before_a_wide_gap():
    # Un solo carácter aislado antes de un espacio doble no debe
    # tocarse -- se necesitan al menos 2 tokens cortos consecutivos
    # para considerarlo el artefacto (evita fusionar, p. ej., "A" de
    # un encabezado de una sola letra con lo que sigue).
    text = "A  Resultados"
    assert repair_letter_spaced_text(text) == text


def test_extracts_pdf_text_layer_repairs_letter_spacing_when_applicable(tmp_path, extractor):
    # El PDF mínimo de prueba no reproduce el artefacto (texto normal
    # de pypdf), así que esto confirma que el extractor de PDF sí pasa
    # el texto por repair_letter_spaced_text sin romper el caso normal.
    path = tmp_path / "sample.pdf"
    path.write_bytes(_MINIMAL_PDF)
    text, _, _, _ = extractor.extract(str(path), SourceType.PDF)
    assert text == repair_letter_spaced_text("Hola desde un PDF de prueba")


def test_supports_reports_coverage_without_api_or_database():
    extractor = CompositeTextExtractor()
    assert extractor.supports(SourceType.TXT)
    assert extractor.supports(SourceType.MARKDOWN)
    assert extractor.supports(SourceType.DOCX)
    assert extractor.supports(SourceType.PDF)
    # imagen_escaneada sí tiene extractor desde Módulo 5 (ImageTextExtractor)
    # -- "supports" significa "hay un extractor registrado", no "puede
    # producir texto ahora mismo" (eso depende de si hay ocr_engine, ver
    # las pruebas de ImageTextExtractor más abajo). Mismo criterio que
    # PdfTextExtractor, que también "soporta" PDF sin importar OCR.
    assert extractor.supports(SourceType.IMAGEN_ESCANEADA)
    # XLSX/CSV: cerraron la brecha frente al alcance mínimo obligatorio
    # de la primera versión (ver bitácora 2026-07-27).
    assert extractor.supports(SourceType.XLSX)
    assert extractor.supports(SourceType.CSV)
    # HTML/JSON/XML: cerraron la brecha señalada en el manual de usuario
    # (ver bitácora de esta misma iteración).
    assert extractor.supports(SourceType.HTML)
    assert extractor.supports(SourceType.JSON)
    assert extractor.supports(SourceType.XML)
    # API y base_de_datos quedan deliberadamente sin extractor: no son
    # archivos, son conexiones vivas (ver README, "Deliberadamente fuera
    # de alcance").
    assert not extractor.supports(SourceType.API)
    assert not extractor.supports(SourceType.BASE_DE_DATOS)


# ---------- HTML ----------

def test_extracts_html_headings_paragraphs_and_tables(tmp_path, extractor):
    path = tmp_path / "sample.html"
    path.write_text(
        "<html><head><title>ignorado</title><style>.a{color:red}</style></head>"
        "<body>"
        "<h1>Reglamento Escolar</h1>"
        "<p>Este es un <b>reglamento</b> de prueba.</p>"
        "<h2>Sección 1</h2>"
        "<p>Contenido de la sección uno.</p>"
        "<table><tr><th>Materia</th><th>Créditos</th></tr>"
        "<tr><td>Álgebra</td><td>5</td></tr></table>"
        "<script>alert(1)</script>"
        "</body></html>",
        encoding="utf-8",
    )
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.HTML)
    assert method == "html"
    assert page_breaks == []
    assert warnings == []
    assert "# Reglamento Escolar" in text
    assert "## Sección 1" in text
    assert "Este es un reglamento de prueba." in text
    assert "| Materia | Créditos |" in text
    assert "| Álgebra | 5 |" in text
    # <title>/<style>/<script> nunca son texto visible de la página
    assert "ignorado" not in text
    assert "color:red" not in text
    assert "alert(1)" not in text


def test_extracts_html_empty_body_produces_warning(tmp_path, extractor):
    path = tmp_path / "vacio.html"
    path.write_text("<html><head><title>Solo título</title></head><body></body></html>", encoding="utf-8")
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.HTML)
    assert text == ""
    assert warnings != []


def test_html_extractor_supports_only_html():
    ext = HtmlExtractor()
    assert ext.supports(SourceType.HTML)
    assert not ext.supports(SourceType.XML)


# ---------- JSON ----------

def test_extracts_json_list_of_flat_records_as_table(tmp_path, extractor):
    path = tmp_path / "alumnos.json"
    path.write_text(
        '[{"nombre": "Juan", "edad": 20}, {"nombre": "Ana", "edad": 22, "beca": true}]',
        encoding="utf-8",
    )
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.JSON)
    assert method == "json"
    assert page_breaks == []
    assert warnings == []
    assert "| nombre | edad | beca |" in text
    assert "| Juan | 20 | null |" in text  # "beca" ausente en el primer registro -> null
    assert "| Ana | 22 | true |" in text


def test_extracts_json_nested_object_as_flattened_paths(tmp_path, extractor):
    path = tmp_path / "config.json"
    path.write_text(
        '{"proyecto": {"nombre": "RAG STUDIO", "version": "0.1.0"}, "materias": ["Álgebra", "Física"]}',
        encoding="utf-8",
    )
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.JSON)
    assert method == "json"
    assert warnings == []
    assert "proyecto.nombre: RAG STUDIO" in text
    assert "proyecto.version: 0.1.0" in text
    assert "materias: Álgebra, Física" in text


def test_extracts_json_empty_document_produces_warning(tmp_path, extractor):
    path = tmp_path / "vacio.json"
    path.write_text("{}", encoding="utf-8")
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.JSON)
    assert text == ""
    assert warnings != []


def test_extracts_json_malformed_raises_json_decode_error(tmp_path, extractor):
    import json
    path = tmp_path / "roto.json"
    path.write_text("{no es json valido", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        extractor.extract(str(path), SourceType.JSON)


def test_json_extractor_supports_only_json():
    ext = JsonExtractor()
    assert ext.supports(SourceType.JSON)
    assert not ext.supports(SourceType.XML)


# ---------- XML ----------

def test_extracts_xml_elements_with_attributes(tmp_path, extractor):
    path = tmp_path / "reglamento.xml"
    path.write_text(
        '<?xml version="1.0"?>'
        '<reglamento id="r1">'
        "<titulo>Reglamento Escolar</titulo>"
        '<articulo numero="1">Los alumnos deben asistir puntualmente.</articulo>'
        '<articulo numero="2">Se prohibe el uso de telefonos en clase.</articulo>'
        "</reglamento>",
        encoding="utf-8",
    )
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.XML)
    assert method == "xml"
    assert page_breaks == []
    assert warnings == []
    assert "reglamento (id=r1).titulo: Reglamento Escolar" in text
    assert "reglamento (id=r1).articulo (numero=1): Los alumnos deben asistir puntualmente." in text
    assert "reglamento (id=r1).articulo (numero=2): Se prohibe el uso de telefonos en clase." in text


def test_extracts_xml_empty_elements_produce_warning(tmp_path, extractor):
    path = tmp_path / "vacio.xml"
    path.write_text("<raiz><vacio/></raiz>", encoding="utf-8")
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.XML)
    assert text == ""
    assert warnings != []


def test_extracts_xml_malformed_raises_parse_error(tmp_path, extractor):
    import xml.etree.ElementTree as ET
    path = tmp_path / "roto.xml"
    path.write_text("<raiz><sin_cerrar></raiz>", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        extractor.extract(str(path), SourceType.XML)


def test_xml_extractor_supports_only_xml():
    ext = XmlExtractor()
    assert ext.supports(SourceType.XML)
    assert not ext.supports(SourceType.JSON)


# ---------- OCR para PDF escaneado (Módulo 4) ----------
# Los PDFs de prueba se construyen con PyMuPDF insertando una IMAGEN
# (no texto real) por página -- reproduce fielmente el caso real
# ("PDF escaneado sin capa de texto") que pypdf no puede leer, sin
# necesitar un scanner ni un archivo de muestra externo.

def _test_font(size: int = 36):
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _render_text_image(text: str, size: tuple = (600, 100), font_size: int = 36) -> bytes:
    image = Image.new("RGB", size, color="white")
    ImageDraw.Draw(image).text((10, 10), text, fill="black", font=_test_font(font_size))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_scanned_pdf(path, pages_text: list) -> None:
    """PDF real donde cada página es solo una imagen (sin capa de
    texto real) -- pypdf debe devolver texto vacío para cada una."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=600, height=100)
        page.insert_image(fitz.Rect(0, 0, 600, 100), stream=_render_text_image(text))
    doc.save(str(path))
    doc.close()


class _FakeOcrEngine(OcrEngine):
    """Doble de prueba: no llama a Tesseract de verdad -- permite
    probar el control de flujo de PdfTextExtractor (qué método
    reporta, qué advertencias arma, que no reintenta OCR página por
    página tras fallar una vez) sin depender de que el binario de
    Tesseract esté instalado en quien corra las pruebas."""

    def __init__(self, text: str = "", raise_unavailable=None):
        self._text = text
        self._raise_unavailable = raise_unavailable
        self.calls = 0

    def image_to_text(self, image_bytes: bytes) -> str:
        self.calls += 1
        if self._raise_unavailable is not None:
            raise OcrEngineUnavailableError(self._raise_unavailable)
        return self._text


@_requires_ocr_test_deps
def test_pdf_without_ocr_engine_warns_and_extracts_nothing_from_scanned_page(tmp_path):
    # Regresión: sin ocr_engine (valor por defecto), el comportamiento
    # debe ser exactamente el mismo que antes de Módulo 4.
    path = tmp_path / "scanned.pdf"
    _build_scanned_pdf(path, ["Contenido que solo existe como imagen"])

    text, method, page_breaks, warnings = PdfTextExtractor().extract(str(path), SourceType.PDF)
    assert text == ""
    assert method == "pdf_texto"
    assert len(warnings) == 1
    assert "posible página escaneada sin OCR" in warnings[0]


@_requires_ocr_test_deps
def test_pdf_extractor_uses_ocr_engine_to_recover_scanned_page_text(tmp_path):
    path = tmp_path / "scanned.pdf"
    _build_scanned_pdf(path, ["cualquier imagen"])
    fake_ocr = _FakeOcrEngine(text="Texto reconocido por OCR")

    text, method, page_breaks, warnings = PdfTextExtractor(ocr_engine=fake_ocr).extract(str(path), SourceType.PDF)
    assert "Texto reconocido por OCR" in text
    assert method == "pdf_ocr"
    assert warnings == []
    assert fake_ocr.calls == 1


@_requires_ocr_test_deps
def test_pdf_extractor_reports_ocr_unavailable_reason_and_does_not_retry_per_page(tmp_path):
    # PDF real de 2 páginas escaneadas (PyMuPDF sí debe poder
    # rasterizarlas) -- el fallo simulado ocurre en el reconocimiento
    # (image_to_text), no en el rasterizado, para aislar justo el
    # camino de "Tesseract no disponible".
    path = tmp_path / "scanned_2pages.pdf"
    _build_scanned_pdf(path, ["página uno", "página dos"])
    fake_ocr = _FakeOcrEngine(raise_unavailable="Tesseract no instalado (prueba)")
    extractor = PdfTextExtractor(ocr_engine=fake_ocr)

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.PDF)

    assert text == ""
    assert method == "pdf_texto"
    assert len(warnings) == 2
    assert all("Tesseract no instalado (prueba)" in w for w in warnings)
    # no debe reintentar OCR en la segunda página tras fallar en la primera
    assert fake_ocr.calls == 1


@_requires_ocr_test_deps
def test_pdf_extractor_mixes_real_text_and_ocr_pages(tmp_path):
    path = tmp_path / "mixed.pdf"
    doc = fitz.open()
    page1 = doc.new_page(width=300, height=100)
    page1.insert_text((20, 50), "Real text layer here", fontsize=14)
    page2 = doc.new_page(width=300, height=100)
    page2.insert_image(fitz.Rect(0, 0, 300, 100), stream=_render_text_image("imagen escaneada"))
    doc.save(str(path))
    doc.close()

    fake_ocr = _FakeOcrEngine(text="Texto de la página escaneada")
    text, method, page_breaks, warnings = PdfTextExtractor(ocr_engine=fake_ocr).extract(str(path), SourceType.PDF)
    assert "Real text layer here" in text
    assert "Texto de la página escaneada" in text
    assert method == "pdf_texto+ocr"
    assert warnings == []


@_requires_ocr_test_deps
@_requires_real_tesseract
def test_pdf_extractor_real_ocr_recovers_text_from_scanned_page(tmp_path):
    # Única prueba con Tesseract real (no un doble) -- confirma que el
    # camino completo (rasterizar con PyMuPDF + reconocer con
    # pytesseract) funciona de punta a punta, no solo el control de
    # flujo. lang="eng" porque este entorno de construcción solo tiene
    # el paquete de idioma inglés instalado (ver el comentario de OCR
    # en requirements.txt para instalar también "spa" en una máquina real).
    path = tmp_path / "scanned_real.pdf"
    _build_scanned_pdf(path, ["Hello OCR World"])

    extractor = PdfTextExtractor(ocr_engine=TesseractOcrEngine(lang="eng"))
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.PDF)
    assert "Hello" in text
    assert "OCR" in text
    assert method == "pdf_ocr"
    assert warnings == []


# ---------- imagen_escaneada como fuente independiente (Módulo 5) ----------
# A diferencia de PdfTextExtractor, aquí no hace falta PyMuPDF: la
# imagen ya viene rasterizada, no hay una página de PDF que convertir
# antes de reconocerla -- por eso estas pruebas solo se omiten si falta
# Pillow (para construir la imagen de prueba), no PyMuPDF.

_requires_pillow = pytest.mark.skipif(
    not _OCR_TEST_DEPS_AVAILABLE, reason="Pillow (extra 'ocr') no instalado -- se omiten pruebas de imagen_escaneada",
)


@_requires_pillow
def test_composite_extractor_dispatches_imagen_escaneada_to_image_extractor(tmp_path, extractor):
    path = tmp_path / "escaneo.png"
    path.write_bytes(_render_text_image("cualquier imagen"))

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.IMAGEN_ESCANEADA)
    assert text == ""
    assert method == "imagen_sin_ocr"
    assert "no hay un motor OCR configurado" in warnings[0]


def test_image_extractor_only_supports_imagen_escaneada():
    extractor = ImageTextExtractor()
    assert extractor.supports(SourceType.IMAGEN_ESCANEADA)
    assert not extractor.supports(SourceType.PDF)


@_requires_pillow
def test_image_extractor_without_ocr_engine_warns_and_extracts_nothing(tmp_path):
    path = tmp_path / "escaneo.png"
    path.write_bytes(_render_text_image("cualquier imagen"))

    text, method, page_breaks, warnings = ImageTextExtractor().extract(str(path), SourceType.IMAGEN_ESCANEADA)
    assert text == ""
    assert method == "imagen_sin_ocr"
    assert page_breaks == []
    assert len(warnings) == 1
    assert "no hay un motor OCR configurado" in warnings[0]


@_requires_pillow
def test_image_extractor_uses_ocr_engine_to_recover_text(tmp_path):
    path = tmp_path / "escaneo.png"
    path.write_bytes(_render_text_image("cualquier imagen"))
    fake_ocr = _FakeOcrEngine(text="Texto reconocido por OCR")

    text, method, page_breaks, warnings = ImageTextExtractor(ocr_engine=fake_ocr).extract(
        str(path), SourceType.IMAGEN_ESCANEADA,
    )
    assert text == "Texto reconocido por OCR"
    assert method == "imagen_ocr"
    assert warnings == []
    assert fake_ocr.calls == 1


@_requires_pillow
def test_image_extractor_reports_ocr_unavailable_reason(tmp_path):
    path = tmp_path / "escaneo.png"
    path.write_bytes(_render_text_image("cualquier imagen"))
    fake_ocr = _FakeOcrEngine(raise_unavailable="Tesseract no instalado (prueba)")

    text, method, page_breaks, warnings = ImageTextExtractor(ocr_engine=fake_ocr).extract(
        str(path), SourceType.IMAGEN_ESCANEADA,
    )
    assert text == ""
    assert method == "imagen_sin_ocr"
    assert len(warnings) == 1
    assert "Tesseract no instalado (prueba)" in warnings[0]


@_requires_pillow
def test_image_extractor_warns_when_image_produces_no_recognizable_text(tmp_path):
    path = tmp_path / "en_blanco.png"
    path.write_bytes(_render_text_image(""))
    fake_ocr = _FakeOcrEngine(text="   ")

    text, method, page_breaks, warnings = ImageTextExtractor(ocr_engine=fake_ocr).extract(
        str(path), SourceType.IMAGEN_ESCANEADA,
    )
    assert text == ""
    assert method == "imagen_ocr"
    assert len(warnings) == 1
    assert "no produjo texto reconocible" in warnings[0]


@_requires_pillow
@_requires_real_tesseract
def test_image_extractor_real_ocr_recovers_text_from_a_real_image_file(tmp_path):
    # Única prueba con Tesseract real (no un doble) para imagen_escaneada
    # -- confirma el camino completo (leer bytes del archivo + reconocer
    # con pytesseract) de punta a punta, no solo el control de flujo.
    path = tmp_path / "real.png"
    path.write_bytes(_render_text_image("Hello Image OCR"))

    extractor = ImageTextExtractor(ocr_engine=TesseractOcrEngine(lang="eng"))
    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.IMAGEN_ESCANEADA)
    assert "Hello" in text
    assert "Image" in text or "OCR" in text
    assert method == "imagen_ocr"
    assert warnings == []


# ---------- Fase 2 de multimodalidad nativa (RAG 3): ImageNativeExtractor ----------

def test_image_native_extractor_only_supports_imagen_nativa():
    extractor = ImageNativeExtractor()
    assert extractor.supports(SourceType.IMAGEN_NATIVA)
    assert not extractor.supports(SourceType.IMAGEN_ESCANEADA)
    assert not extractor.supports(SourceType.PDF)


def test_image_native_extractor_returns_empty_text_without_warnings(tmp_path):
    # A diferencia de ImageTextExtractor (OCR), texto vacío aquí no es un
    # caso degradado -- es el resultado correcto: no hay nada que
    # transcribir, el contenido real es la imagen misma.
    path = tmp_path / "foto.png"
    path.write_bytes(b"contenido binario cualquiera, no se lee de verdad")

    text, method, page_breaks, warnings = ImageNativeExtractor().extract(str(path), SourceType.IMAGEN_NATIVA)
    assert text == ""
    assert method == "imagen_nativa"
    assert page_breaks == []
    assert warnings == []


def test_composite_extractor_dispatches_imagen_nativa_to_image_native_extractor(extractor, tmp_path):
    path = tmp_path / "foto.png"
    path.write_bytes(b"contenido binario cualquiera")

    text, method, page_breaks, warnings = extractor.extract(str(path), SourceType.IMAGEN_NATIVA)
    assert text == ""
    assert method == "imagen_nativa"
    assert warnings == []
