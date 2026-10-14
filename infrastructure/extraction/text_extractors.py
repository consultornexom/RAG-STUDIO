"""Adaptadores de TextExtractor (ADR-001, sección 4: infrastructure
implementa los puertos de domain). Núcleo de Etapa 3: TXT, Markdown,
DOCX y PDF con capa de texto, más OCR opcional para PDF escaneado
(Módulo 4, ver `PdfTextExtractor` y `infrastructure/extraction/
ocr_engine.py`). XLSX y CSV (`XlsxExtractor`/`CsvExtractor`) se
agregaron para cerrar la brecha detectada contra el alcance mínimo
obligatorio de la primera versión ("Debe incluir: ... Extracción de
PDF, DOCX, XLSX, CSV y texto.", RAG STUDIO.odt) -- ver bitácora
2026-07-27. HTML, JSON y XML (`HtmlExtractor`/`JsonExtractor`/
`XmlExtractor`) se agregaron para cerrar la brecha señalada en el
manual de usuario -- ver bitácora de esta misma iteración. API y base
de datos siguen deliberadamente sin extractor: no son archivos, son
conexiones vivas (URL/credenciales/consulta), un problema distinto de
"parsear un archivo" -- ver README, "Deliberadamente fuera de alcance".
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import docx
import docx.document
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from pypdf import PdfReader

from domain.documents.entities import SourceType
from domain.ingestion.exceptions import OcrEngineUnavailableError, UnsupportedSourceTypeError
from domain.ingestion.ports import OcrEngine, TextExtractor

_MIN_LETTER_SPACED_RUN = 4
_MIN_SHORT_RUN_BEFORE_WIDE_GAP = 2
# Puntuación de cierre de token, no una contraseña -- falso positivo de bandit.
_LETTER_TOKEN_TRAILING_PUNCTUATION = ".,;:)"  # nosec B105
_UPPERCASE_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9.,])(?=[A-ZÁÉÍÓÚÑ])")


def _is_single_letter_token(token: str) -> bool:
    """True si `token` es una sola letra/dígito, opcionalmente con un
    signo de puntuación pegado al final (p. ej. "r." dentro de una
    abreviatura como "3er."). Ese último caso es real: pypdf a veces
    letra-espacía solo la abreviatura de un ordinal ("3 e r." ) y deja
    intacta la palabra siguiente ("Cuatrimestre") -- sin este caso,
    "r." (dos caracteres) no calificaría como token de una sola
    letra y la abreviatura quedaría sin corregir."""
    if len(token) == 1:
        return True
    return len(token) == 2 and token[1] in _LETTER_TOKEN_TRAILING_PUNCTUATION


def repair_letter_spaced_text(text: str, min_run: int = _MIN_LETTER_SPACED_RUN) -> str:
    """Corrige un artefacto real de extracción de PDFs con pypdf: en
    ciertas fuentes con tracking/justificado amplio, `extract_text()`
    devuelve cada carácter como una "palabra" separada por un espacio
    simple, p. ej. "3 e r . C u a t r i m e s t r e" en vez de
    "3er. Cuatrimestre" (hallazgo real de validación visual, plan de
    estudios en PDF). Esto degrada mucho la calidad de los embeddings:
    el tokenizador ve 16 tokens de un carácter en vez de dos palabras.

    Se detecta como una corrida de `min_run` o más "palabras" de un
    solo carácter (o un carácter + puntuación, ver
    `_is_single_letter_token`) separadas por espacios simples, y se
    unen quitando esos espacios internos. Una vez unidas, se reinserta
    un espacio donde una mayúscula sigue a una minúscula/dígito/
    puntuación -- límite de palabra frecuente en Title Case (nombres
    de materias, encabezados) -- para recuperar al menos algunos de
    los cortes de palabra perdidos. No es una reconstrucción perfecta
    (texto totalmente en mayúsculas queda como un solo bloque), pero
    es muy superior a dejar el texto fragmentado letra por letra para
    el modelo de embeddings.

    Caso adicional real (plan de estudios en PDF, validación visual):
    a veces solo una abreviatura corta queda letra-espaciada ("3 e r.")
    e inmediatamente después viene un espacio doble antes de la
    palabra siguiente, ya intacta ("Cuatrimestre") -- pypdf reproduce
    en el ancho del espacio el hueco real entre "palabras" del PDF
    original. Una corrida corta (2 o 3 tokens) que termina justo antes
    de ese espacio doble se corrige también, aunque no llegue a
    `min_run`, porque el espacio doble es una señal adicional de que
    ahí termina una palabra real -- sin esa señal, no se toca (para no
    fusionar, p. ej., dos encabezados de una sola letra en una tabla).

    El umbral de 4+ (o 2+ junto al espacio doble) evita falsos
    positivos sobre texto normal en español, donde no es habitual
    encontrar varias palabras de una sola letra consecutivas (y, o, a,
    u, e)."""
    lines_out: list[str] = []
    for line in text.split("\n"):
        tokens = line.split(" ")
        repaired: list[str] = []
        i, n = 0, len(tokens)
        while i < n:
            j = i
            while j < n and _is_single_letter_token(tokens[j]):
                j += 1
            run_len = j - i
            followed_by_wide_gap = j < n and tokens[j] == ""
            if run_len >= min_run or (run_len >= _MIN_SHORT_RUN_BEFORE_WIDE_GAP and followed_by_wide_gap):
                joined = "".join(tokens[i:j])
                repaired.append(_UPPERCASE_WORD_BOUNDARY.sub(" ", joined))
            else:
                repaired.extend(tokens[i:j])
            if j < n:
                repaired.append(tokens[j])
                j += 1
            i = j
        lines_out.append(" ".join(repaired))
    return "\n".join(lines_out)


class TxtExtractor(TextExtractor):
    """TXT y Markdown: se leen directamente, sin transformación (el
    contenido Markdown ya viene con encabezados '#' listos para
    domain.ingestion.splitting.split_by_headings)."""

    _SUPPORTED = {SourceType.TXT, SourceType.MARKDOWN}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        path = Path(location)
        text = path.read_text(encoding="utf-8", errors="replace")
        return text, "texto_plano", [], []


def _iter_block_items(document: "docx.document.Document"):
    """Recorre párrafos y tablas de un documento DOCX en su orden real
    de aparición. python-docx no lo expone directamente
    (`document.paragraphs` y `document.tables` son dos listas
    separadas, sin orden relativo entre sí) -- este es el idiom
    estándar de la comunidad python-docx para resolverlo (ver su FAQ:
    "Access all paragraphs and tables, in document order").

    Nota de tipos: se anota con `docx.document.Document` (la clase
    real) y no `docx.Document` (la función fábrica de nivel superior,
    que devuelve una instancia de esa clase) -- un error de tipeo fácil
    de cometer porque python-docx no publica stubs de tipos oficiales.
    """
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield DocxParagraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield DocxTable(child, document)


def _escape_cell(value: str) -> str:
    # Una tabla Markdown exige una fila por línea: un salto de línea
    # dentro de una celda rompería el formato, así que se aplana a
    # espacios. El pipe literal se escapa para no crear una columna
    # falsa.
    return value.strip().replace("|", "\\|").replace("\n", " ")


def rows_to_markdown_table(rows: list[list[str]]) -> str:
    """Convierte filas de texto plano (encabezado + datos) en una tabla
    Markdown (fila de encabezado + fila separadora de guiones + filas
    de datos) -- el mismo formato que
    domain.ingestion.splitting.split_by_tables sabe reconocer (Módulo
    5, tipo documental "tabla"). Función genérica compartida por
    DOCX (`_table_to_markdown`), XLSX (`XlsxExtractor`) y CSV
    (`CsvExtractor`): las tres fuentes producen "filas de celdas de
    texto", solo cambia de dónde vienen."""
    if not rows:
        return ""
    header_cells = [_escape_cell(c) for c in rows[0]]
    lines = ["| " + " | ".join(header_cells) + " |", "|" + "|".join(" --- " for _ in header_cells) + "|"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(_escape_cell(c) for c in row) + " |")
    return "\n".join(lines)


def _table_to_markdown(table: DocxTable) -> str:
    """Convierte una tabla DOCX en una tabla Markdown -- ver
    `rows_to_markdown_table`. Sin esto, una tabla DOCX simplemente
    desaparecía del texto extraído: `document.paragraphs` nunca
    incluye el contenido de las tablas."""
    rows = [[cell.text for cell in row.cells] for row in table.rows]
    return rows_to_markdown_table(rows)


class DocxExtractor(TextExtractor):
    """DOCX: los párrafos con estilo 'Heading N' o 'Title' se
    normalizan a encabezados Markdown ('#' * nivel) para que la
    fragmentación por encabezado funcione igual sin importar el
    formato de origen. Las tablas (Módulo 5: tipo documental "tabla")
    se convierten a tablas Markdown en el mismo orden en que aparecen
    en el documento, para que FragmentationStrategy.POR_TABLA pueda
    reconocerlas. DOCX no tiene páginas fijas (dependen del
    renderizado), así que no se generan saltos de página."""

    _SUPPORTED = {SourceType.DOCX}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        document = docx.Document(location)
        lines: list[str] = []
        warnings: list[str] = []
        for block in _iter_block_items(document):
            if isinstance(block, DocxTable):
                table_markdown = _table_to_markdown(block)
                if table_markdown:
                    lines.append(table_markdown)
                continue
            text = block.text.strip()
            if not text:
                continue
            level = self._heading_level(block.style.name if block.style else "")
            if level:
                lines.append(f"{'#' * level} {text}")
            else:
                lines.append(text)
        if not lines:
            warnings.append("El documento DOCX no tiene párrafos ni tablas con texto.")
        return "\n\n".join(lines), "docx", [], warnings

    @staticmethod
    def _heading_level(style_name: str) -> int:
        style_name = (style_name or "").strip()
        if style_name == "Title":
            return 1
        if style_name.startswith("Heading "):
            suffix = style_name[len("Heading "):].strip()
            if suffix.isdigit():
                return min(int(suffix), 6)
        return 0


class PdfTextExtractor(TextExtractor):
    """PDF con capa de texto: extrae página por página con pypdf y
    registra en qué desplazamiento de carácter empieza cada página
    nueva, para poder trazar page_start/page_end en cada fragmento
    (INVESTIGACION.odt, A2: trazabilidad de página).

    OCR (Módulo 4, opcional): si se pasa `ocr_engine`, las páginas que
    pypdf no logra leer (PDF escaneado sin capa de texto) se rasterizan
    con PyMuPDF y se reconocen con ese motor -- sin `ocr_engine` (el
    valor por defecto), el comportamiento es exactamente el mismo que
    antes de Módulo 4: solo una advertencia por página, sin extraer
    nada. Un fallo de OCR (motor no instalado, Tesseract ausente) se
    captura por página, no aborta el resto del documento."""

    _SUPPORTED = {SourceType.PDF}

    def __init__(self, ocr_engine: Optional[OcrEngine] = None):
        self._ocr_engine = ocr_engine

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        reader = PdfReader(location)
        parts: list[str] = []
        page_breaks: list[int] = []
        warnings: list[str] = []
        offset = 0
        methods_used: set[str] = set()
        # Si el motor de OCR falla por falta de dependencias/binario,
        # se recuerda para no reintentarlo página por página (sería
        # lento y repetiría el mismo mensaje muchas veces) -- una sola
        # razón clara basta para todas las páginas restantes.
        ocr_unavailable_reason: Optional[str] = None
        for i, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            page_text = repair_letter_spaced_text(page_text)
            page_method = "pdf_texto"
            if not page_text and self._ocr_engine is not None and ocr_unavailable_reason is None:
                try:
                    ocr_text = repair_letter_spaced_text(self._ocr_page(location, i - 1).strip())
                except OcrEngineUnavailableError as exc:
                    ocr_unavailable_reason = str(exc)
                else:
                    if ocr_text:
                        page_text = ocr_text
                        page_method = "ocr"
            if not page_text:
                if self._ocr_engine is None:
                    warnings.append(
                        f"La página {i} no produjo texto (posible página escaneada sin OCR)."
                    )
                elif ocr_unavailable_reason is not None:
                    warnings.append(f"La página {i} no produjo texto -- OCR no disponible: {ocr_unavailable_reason}")
                else:
                    warnings.append(
                        f"La página {i} no produjo texto ni con OCR (puede estar en blanco "
                        "o ser una imagen de muy baja calidad)."
                    )
                continue
            methods_used.add(page_method)
            if parts:
                separator = "\n\n"
                offset += len(separator)
                parts.append(separator)
                page_breaks.append(offset)
            parts.append(page_text)
            offset += len(page_text)
        method_label = "pdf_texto"
        if methods_used == {"ocr"}:
            method_label = "pdf_ocr"
        elif "ocr" in methods_used:
            method_label = "pdf_texto+ocr"
        return "".join(parts), method_label, page_breaks, warnings

    def _ocr_page(self, location: str, page_index: int) -> str:
        # Solo se llama desde extract() cuando self._ocr_engine ya se
        # comprobó no-None (ver arriba); se repite aquí para que el
        # invariante quede explícito también dentro de este método, no
        # solo en quien lo llama.
        if self._ocr_engine is None:
            raise OcrEngineUnavailableError("No hay un motor de OCR configurado.")
        try:
            import fitz  # PyMuPDF -- import perezoso: no debe exigirse
            # esta dependencia si nunca se usa OCR (extra opcional).
        except ImportError as exc:
            raise OcrEngineUnavailableError(
                "El renderizador de páginas (PyMuPDF) no está instalado. "
                "Instala el extra opcional: pip install ragstudio[ocr]"
            ) from exc
        with fitz.open(location) as doc:
            pix = doc[page_index].get_pixmap(dpi=200)
            image_bytes = pix.tobytes("png")
        return self._ocr_engine.image_to_text(image_bytes)


class ImageTextExtractor(TextExtractor):
    """Imagen escaneada como fuente independiente (Módulo 5): un
    archivo de imagen suelto (JPG, PNG, TIFF...) registrado
    directamente como fuente, no embebido dentro de un PDF.

    A diferencia de PdfTextExtractor (donde OCR es un respaldo para
    las páginas que pypdf no logra leer), aquí el OCR es el único
    mecanismo posible: una imagen no tiene "capa de texto" que probar
    primero. Por eso tampoco necesita PyMuPDF -- la imagen ya viene
    rasterizada, no hay una página de PDF que convertir a imagen antes
    de reconocerla.

    Sin `ocr_engine` (valor por defecto), no puede extraer nada -- se
    reporta con una advertencia clara en vez de fallar en silencio,
    igual que PdfTextExtractor sin OCR (Módulo 4): el llamador
    (ExtractSourceText) convierte el texto vacío resultante en
    EmptyExtractionError, con la advertencia disponible para explicar
    por qué."""

    _SUPPORTED = {SourceType.IMAGEN_ESCANEADA}

    def __init__(self, ocr_engine: Optional[OcrEngine] = None):
        self._ocr_engine = ocr_engine

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        if self._ocr_engine is None:
            return "", "imagen_sin_ocr", [], [
                "Esta fuente es una imagen escaneada, pero no hay un motor OCR configurado "
                "-- instala el extra opcional 'ocr' (incluido en requirements.txt) para poder "
                "extraer su texto."
            ]
        with open(location, "rb") as file:
            image_bytes = file.read()
        try:
            text = self._ocr_engine.image_to_text(image_bytes).strip()
        except OcrEngineUnavailableError as exc:
            return "", "imagen_sin_ocr", [], [f"No se pudo reconocer texto en la imagen -- OCR no disponible: {exc}"]
        if not text:
            return "", "imagen_ocr", [], [
                "La imagen no produjo texto reconocible (puede estar en blanco o ser de muy baja calidad)."
            ]
        return text, "imagen_ocr", [], []


class ImageNativeExtractor(TextExtractor):
    """Imagen nativa (Fase 2 de multimodalidad, RAG 3 -- ver docs
    proyecto/RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx). A
    diferencia de ImageTextExtractor (SourceType.IMAGEN_ESCANEADA, que
    transcribe texto vía OCR), aquí la imagen ES el contenido -- no hay
    ningún texto que extraer, ni con OCR ni de ninguna otra forma.

    Devuelve texto vacío a propósito, sin advertencia: no es un fallo ni
    un caso degradado (a diferencia de ImageTextExtractor sin OCR
    configurado), es el resultado correcto y esperado para este tipo de
    fuente. application.ingestion.commands.extract_source_text.
    ExtractSourceText reconoce SourceType.IMAGEN_NATIVA explícitamente y
    no lo convierte en EmptyExtractionError.

    Este extractor NO copia ni referencia el archivo de imagen -- eso ya
    lo resuelve SourceFileStore al registrar la fuente (domain.documents.
    ports.SourceFileStore, sources/original/). Tampoco produce el
    ChunkType.IMAGEN final: eso es responsabilidad de la Fase 3
    (IndexImageSource), que lee el Source directamente (para obtener la
    ruta ya copiada) en vez de pasar por FragmentSource -- FragmentSource
    fragmenta TEXTO extraído, y aquí no hay texto que fragmentar."""

    _SUPPORTED = {SourceType.IMAGEN_NATIVA}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        return "", "imagen_nativa", [], []


class XlsxExtractor(TextExtractor):
    """XLSX: cada hoja se convierte en un encabezado Markdown (su
    nombre) seguido de una tabla Markdown con sus filas -- mismo
    formato que produce `DocxExtractor` para tablas DOCX, así que
    `FragmentationStrategy.POR_TABLA`/`POR_ENCABEZADO` funcionan igual
    sin importar el origen del archivo. Una hoja vacía se omite (con
    advertencia), en vez de producir una tabla de cero filas.

    Se lee con `read_only=True, data_only=True` (openpyxl): la primera
    evita cargar todo el libro en memoria de una vez (importante para
    hojas grandes); la segunda lee el último valor calculado de una
    fórmula en vez de la fórmula en sí -- un usuario de negocio espera
    ver "1,234.56", no "=SUMA(A1:A10)"."""

    _SUPPORTED = {SourceType.XLSX}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        import openpyxl

        workbook = openpyxl.load_workbook(location, read_only=True, data_only=True)
        try:
            blocks: list[str] = []
            warnings: list[str] = []
            for sheet in workbook.worksheets:
                rows = [
                    [_cell_to_text(value) for value in row]
                    for row in sheet.iter_rows(values_only=True)
                    if any(value is not None and str(value).strip() for value in row)
                ]
                if not rows:
                    warnings.append(f"La hoja {sheet.title!r} no tiene datos.")
                    continue
                table = rows_to_markdown_table(rows)
                blocks.append(f"## {sheet.title}\n\n{table}")
            if not blocks:
                warnings.append("El libro XLSX no tiene ninguna hoja con datos.")
            return "\n\n".join(blocks), "xlsx", [], warnings
        finally:
            workbook.close()

    def extract_structured_blocks(self, location: str, source_type: SourceType) -> dict[str, dict]:
        """Pista B.2 del ADR-003: mismas filas que ya calcula extract()
        (una hoja vacía se omite igual, con el mismo criterio), pero sin
        aplanar a Markdown -- columnas y filas nativas, clave = nombre de
        hoja. Vuelve a abrir y recorrer el libro por separado en vez de
        compartir trabajo con extract(): ExtractSourceText llama a ambos
        métodos por separado (ver diseño, sección 3.1), así que un XLSX
        se parsea dos veces -- costo pequeño y acotado, aceptado a
        cambio de no complicar la firma de extract()."""
        import openpyxl

        workbook = openpyxl.load_workbook(location, read_only=True, data_only=True)
        try:
            blocks: dict[str, dict] = {}
            for sheet in workbook.worksheets:
                rows = [
                    [_cell_to_text(value) for value in row]
                    for row in sheet.iter_rows(values_only=True)
                    if any(value is not None and str(value).strip() for value in row)
                ]
                if not rows:
                    continue
                columnas = rows[0]
                # strict=False a propósito: una fila de hoja de cálculo
                # más corta que el encabezado (celdas finales vacías que
                # openpyxl no rellena) es un caso real, no un error --
                # dict(zip(...)) simplemente deja esas columnas fuera de
                # ese registro en vez de lanzar ValueError.
                blocks[sheet.title] = {
                    "columnas": columnas,
                    "filas": [dict(zip(columnas, row, strict=False)) for row in rows[1:]],
                }
            return blocks
        finally:
            workbook.close()


def _cell_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class CsvExtractor(TextExtractor):
    """CSV: se convierte en una sola tabla Markdown (fila de encabezado
    + filas de datos) -- mismo formato que `XlsxExtractor`/
    `DocxExtractor`. El delimitador se detecta automáticamente
    (`csv.Sniffer`) entre coma/punto y coma/tabulador -- suficiente
    para los tres separadores reales más comunes en archivos
    exportados desde hojas de cálculo, sin exigirle al usuario elegirlo
    a mano; si la detección falla (archivo muy corto o ambiguo), se usa
    coma como respaldo."""

    _SUPPORTED = {SourceType.CSV}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        import csv

        # utf-8-sig: si el archivo trae BOM (típico de un CSV exportado
        # por Excel en Windows), se descarta en vez de colarse como
        # parte del primer encabezado ("﻿codigo" en vez de "codigo").
        with open(location, "r", encoding="utf-8-sig", errors="replace", newline="") as file:
            sample = file.read(4096)
            file.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            rows = [row for row in csv.reader(file, dialect) if any(cell.strip() for cell in row)]
        if not rows:
            return "", "csv", [], ["El archivo CSV no tiene filas con datos."]
        return rows_to_markdown_table(rows), "csv", [], []

    def extract_structured_blocks(self, location: str, source_type: SourceType) -> dict[str, dict]:
        """Pista B.2 del ADR-003: mismo parseo que extract(), sin
        aplanar a Markdown. Un CSV no tiene varias tablas nombradas
        (a diferencia de un XLSX con varias hojas), así que se usa
        la clave fija "datos" -- ver docstring de
        `ExtractionRecord.structured_blocks`."""
        import csv

        with open(location, "r", encoding="utf-8-sig", errors="replace", newline="") as file:
            sample = file.read(4096)
            file.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            rows = [row for row in csv.reader(file, dialect) if any(cell.strip() for cell in row)]
        if not rows:
            return {}
        columnas = rows[0]
        # strict=False: mismo criterio que XlsxExtractor -- una fila
        # CSV más corta que el encabezado no debe abortar la extracción.
        return {
            "datos": {
                "columnas": columnas,
                "filas": [dict(zip(columnas, row, strict=False)) for row in rows[1:]],
            }
        }


class _HtmlToMarkdownParser(HTMLParser):
    """Recorre el HTML de forma incremental (event-driven, como exige
    `html.parser.HTMLParser`) y produce el mismo formato Markdown que
    los demás extractores: encabezados '#'*N para h1-h6 y tablas
    Markdown para <table> (ver `rows_to_markdown_table`), para que
    `FragmentationStrategy.POR_ENCABEZADO`/`POR_TABLA` reconozcan HTML
    igual que DOCX/XLSX/CSV. <script>/<style> se descartan por
    completo (su contenido no es texto legible). No intenta ser un
    renderizador HTML completo -- tablas anidadas, por ejemplo, no se
    preservan con exactitud -- pero cubre bien el caso común de páginas
    de contenido (reglamentos, manuales, FAQs exportados a HTML)."""

    _HEADING_LEVELS = {f"h{n}": n for n in range(1, 7)}
    # "head" descarta todo su contenido de un golpe (title, meta, link,
    # y cualquier script/style que también viva ahí) -- nunca es texto
    # visible de la página. script/style se repiten aquí además porque
    # también pueden aparecer sueltos dentro de <body>.
    _SKIP_CONTENT_TAGS = {"script", "style", "head", "title"}
    _PARAGRAPH_BREAK_TAGS = {"p", "div", "li", "br", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._blocks: list[str] = []
        self._current_text: list[str] = []
        self._skip_depth = 0
        self._heading_level: Optional[int] = None
        self._in_table = False
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP_CONTENT_TAGS:
            self._skip_depth += 1
        elif tag == "table":
            self._flush_paragraph()
            self._in_table = True
            self._table_rows = []
        elif self._in_table and tag == "tr":
            self._current_row = []
        elif self._in_table and tag in ("td", "th"):
            self._current_cell = []
        elif tag in self._HEADING_LEVELS:
            self._flush_paragraph()
            self._heading_level = self._HEADING_LEVELS[tag]
        elif tag in self._PARAGRAPH_BREAK_TAGS:
            self._flush_paragraph()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_CONTENT_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._in_table and tag in ("td", "th"):
            self._current_row.append(" ".join("".join(self._current_cell).split()))
            self._current_cell = []
        elif self._in_table and tag == "tr":
            if self._current_row:
                self._table_rows.append(self._current_row)
            self._current_row = []
        elif self._in_table and tag == "table":
            if self._table_rows:
                self._blocks.append(rows_to_markdown_table(self._table_rows))
            self._in_table = False
            self._table_rows = []
        elif tag in self._HEADING_LEVELS:
            text = " ".join("".join(self._current_text).split())
            if text:
                self._blocks.append(f"{'#' * (self._heading_level or 1)} {text}")
            self._current_text = []
            self._heading_level = None
        elif tag in self._PARAGRAPH_BREAK_TAGS:
            self._flush_paragraph()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_table:
            self._current_cell.append(data)
        else:
            self._current_text.append(data)

    def _flush_paragraph(self) -> None:
        text = " ".join("".join(self._current_text).split())
        if text:
            self._blocks.append(text)
        self._current_text = []

    def get_markdown(self) -> str:
        self._flush_paragraph()
        return "\n\n".join(self._blocks)


class HtmlExtractor(TextExtractor):
    """HTML: se convierte a Markdown con la misma estructura que ya
    reconocen las estrategias de fragmentación (encabezados h1-h6 y
    tablas) -- ver `_HtmlToMarkdownParser`. <script>/<style> se
    descartan; el resto del texto visible se conserva en su orden de
    aparición. HTML no tiene páginas fijas, así que no se generan
    saltos de página (mismo criterio que DocxExtractor)."""

    _SUPPORTED = {SourceType.HTML}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        html_content = Path(location).read_text(encoding="utf-8", errors="replace")
        parser = _HtmlToMarkdownParser()
        parser.feed(html_content)
        parser.close()
        text = parser.get_markdown()
        if not text.strip():
            return "", "html", [], ["El archivo HTML no tiene texto visible (o todo su contenido está en <script>/<style>)."]
        return text, "html", [], []


def _json_scalar_to_text(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _is_flat_json_object(value: object) -> bool:
    """True si `value` es un dict cuyos valores son todos escalares
    (ni dict ni list) -- el caso en el que conviene una tabla Markdown
    en vez de aplanar cada campo en su propia línea."""
    return isinstance(value, dict) and all(not isinstance(v, (dict, list)) for v in value.values())


def _json_records_to_table(records: list[dict]) -> str:
    """Convierte una lista de objetos JSON "planos" (sin anidar) en una
    tabla Markdown -- mismo formato que XlsxExtractor/CsvExtractor. Las
    columnas son la unión de las claves de todos los registros, en
    orden de primera aparición; un registro sin alguna clave deja esa
    celda vacía (no todos los objetos de un array JSON real tienen
    exactamente las mismas claves)."""
    header: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                header.append(key)
    rows = [header] + [[_json_scalar_to_text(record.get(key)) for key in header] for record in records]
    return rows_to_markdown_table(rows)


def _flatten_json(value: object, prefix: str = "") -> list[str]:
    """Aplana un valor JSON arbitrario (anidado o irregular) en líneas
    de texto "ruta: valor", para el caso general en que no aplica la
    tabla de `_json_records_to_table` (JSON no es tabular por
    naturaleza: puede anidar objetos y listas de forma arbitraria)."""
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}: {{}}"] if prefix else []
        lines: list[str] = []
        for key, v in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json(v, path))
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}: []"] if prefix else []
        if all(not isinstance(item, (dict, list)) for item in value):
            joined = ", ".join(_json_scalar_to_text(item) for item in value)
            return [f"{prefix}: {joined}" if prefix else joined]
        lines = []
        for i, item in enumerate(value):
            path = f"{prefix}[{i}]" if prefix else f"[{i}]"
            lines.extend(_flatten_json(item, path))
        return lines
    text = _json_scalar_to_text(value)
    return [f"{prefix}: {text}" if prefix else text]


class JsonExtractor(TextExtractor):
    """JSON: si la raíz es una lista de objetos "planos" (sin anidar,
    el caso más común de un export de datos), se convierte en una tabla
    Markdown -- mismo formato que XLSX/CSV, para que
    FragmentationStrategy.POR_TABLA lo reconozca igual. En cualquier
    otro caso (objeto anidado, lista mixta, valores anidados dentro de
    los registros), se aplana a líneas "ruta.a.el.campo: valor" (ver
    `_flatten_json`) -- JSON no es tabular por naturaleza, así que no
    siempre hay una tabla razonable que producir, pero aplanado sigue
    siendo texto buscable."""

    _SUPPORTED = {SourceType.JSON}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        import json

        with open(location, "r", encoding="utf-8-sig", errors="replace") as file:
            data = json.load(file)  # JSONDecodeError se deja propagar, igual que un DOCX corrupto

        if isinstance(data, list) and data and all(_is_flat_json_object(item) for item in data):
            text = _json_records_to_table(data)
        else:
            text = "\n".join(_flatten_json(data))

        if not text.strip():
            return "", "json", [], ["El archivo JSON no tiene contenido (documento vacío o solo null/[]/{})."]
        return text, "json", [], []


def _strip_xml_namespace(tag: str) -> str:
    # ElementTree expone las etiquetas con namespace como
    # "{http://.../ns}etiqueta"; para el texto extraído importa el
    # nombre del elemento, no la URI completa del namespace.
    return tag.split("}", 1)[1] if "}" in tag else tag


def _xml_element_to_lines(element, path: str) -> list[str]:
    """Aplana un elemento XML (y sus hijos) en líneas "ruta: texto" --
    mismo espíritu que `_flatten_json`, adaptado a que XML distingue
    atributos de contenido y permite texto mixto. Elementos puramente
    estructurales (sin texto propio) no producen línea, pero sus hijos
    igual se recorren -- evita ruido de "etiqueta: " vacías."""
    tag = _strip_xml_namespace(element.tag)
    current_path = f"{path}.{tag}" if path else tag
    if element.attrib:
        attrs = ", ".join(f"{_strip_xml_namespace(k)}={v}" for k, v in element.attrib.items())
        current_path = f"{current_path} ({attrs})"
    lines: list[str] = []
    text = (element.text or "").strip()
    if text:
        lines.append(f"{current_path}: {text}")
    for child in element:
        lines.extend(_xml_element_to_lines(child, current_path))
    return lines


class XmlExtractor(TextExtractor):
    """XML: se aplana a líneas "ruta.al.elemento: texto" (ver
    `_xml_element_to_lines`), incluyendo los atributos de cada elemento
    entre paréntesis para no perder contexto (p. ej. un id o código).
    Igual que JSON, XML no es tabular por naturaleza -- a diferencia de
    JsonExtractor no se intenta detectar el caso "lista de registros"
    (XML representa eso de formas mucho más variadas: elementos
    repetidos con el mismo nombre, atributos vs. sub-elementos, etc.),
    así que siempre se aplana."""

    _SUPPORTED = {SourceType.XML}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._SUPPORTED

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        # defusedxml, no xml.etree.ElementTree directo: bandit (B314/B405,
        # hallado al configurar la herramienta -- ver bitácora) señala que
        # parsear XML sin protección es vulnerable a ataques de entidades
        # externas/"billion laughs". defusedxml.ElementTree es un reemplazo
        # directo (misma API, mismo ParseError) que bloquea esos patrones.
        import defusedxml.ElementTree as ET

        tree = ET.parse(location)  # ParseError se deja propagar, igual que un DOCX corrupto
        root = tree.getroot()
        text = "\n".join(_xml_element_to_lines(root, ""))
        if not text.strip():
            return "", "xml", [], ["El archivo XML no tiene contenido de texto en ningún elemento."]
        return text, "xml", [], []


class CompositeTextExtractor(TextExtractor):
    """Despacha al extractor concreto según source_type. Único
    extractor que se cablea en AppContext; los demás son detalle
    interno de infraestructura."""

    def __init__(self, extractors: list[TextExtractor] | None = None):
        self._extractors = extractors or [
            TxtExtractor(), DocxExtractor(), PdfTextExtractor(), ImageTextExtractor(),
            ImageNativeExtractor(), XlsxExtractor(), CsvExtractor(), HtmlExtractor(),
            JsonExtractor(), XmlExtractor(),
        ]

    def supports(self, source_type: SourceType) -> bool:
        return any(e.supports(source_type) for e in self._extractors)

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        for extractor in self._extractors:
            if extractor.supports(source_type):
                return extractor.extract(location, source_type)
        raise UnsupportedSourceTypeError(source_type.value)

    def extract_structured_blocks(self, location: str, source_type: SourceType) -> dict[str, dict]:
        for extractor in self._extractors:
            if extractor.supports(source_type):
                return extractor.extract_structured_blocks(location, source_type)
        raise UnsupportedSourceTypeError(source_type.value)
