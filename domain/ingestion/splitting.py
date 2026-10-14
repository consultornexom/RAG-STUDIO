"""Funciones puras de fragmentación (RAG STUDIO INVESTIGACION.odt, A2).

Sin dependencias externas: son reglas de negocio, no detalles de
infraestructura, así que viven en domain (ADR-001, sección 4).

El "conteo de tokens" por defecto (`word_count`) es una aproximación
deliberada: cuenta palabras separadas por espacios, no tokens de un
tokenizador real. Sigue siendo el comportamiento de siempre para quien
no inyecta nada -- pero cada función de este módulo que decide tamaños
de fragmento acepta ahora un parámetro opcional `count_tokens`
(ítem 7 de la evaluación de madurez post-8-etapas): una función
`str -> int` intercambiable, para que `application.ingestion.commands.
fragment_source.FragmentSource` pueda inyectar un tokenizador real
(ver domain.ingestion.ports.TokenCounter/
infrastructure.tokenization.tiktoken_counter) sin que este módulo
tenga que importar ninguna librería externa -- domain sigue sin
dependencias más allá de stdlib + Pydantic.
"""
from __future__ import annotations

import re
from typing import Callable, NamedTuple, Optional

CountTokensFn = Callable[[str], int]


class TextSpan(NamedTuple):
    """Un fragmento de texto con su posición de carácter en el texto
    original, para poder trazar página y sección."""

    text: str
    char_start: int
    char_end: int


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def word_count(text: str) -> int:
    return len(text.split())


def split_by_size(
    text: str, target_tokens: int, overlap_tokens: int, count_tokens: CountTokensFn = word_count,
) -> list[TextSpan]:
    """Ventana deslizante por palabras, con solapamiento -- nunca parte
    una palabra a la mitad, sin importar qué `count_tokens` se use.
    Reconstruye los desplazamientos de carácter buscando cada palabra
    en orden para poder trazar páginas más adelante.

    El ancho de cada ventana se decide por PRESUPUESTO de tokens
    (suma de `count_tokens` por palabra, calculado una sola vez): con
    el `word_count` de siempre (1 "token" por palabra) esto es
    exactamente equivalente al criterio anterior de "target_tokens
    palabras por ventana" -- con un tokenizador real inyectado, el
    presupuesto pasa a ser de tokens de verdad, aunque las palabras
    sigan siendo la unidad mínima de corte."""
    if not text.strip():
        return []

    words_with_pos: list[tuple[str, int, int]] = []
    for match in re.finditer(r"\S+", text):
        words_with_pos.append((match.group(0), match.start(), match.end()))
    if not words_with_pos:
        return []

    n = len(words_with_pos)
    per_word_tokens = [count_tokens(w) for (w, _start, _end) in words_with_pos]

    spans: list[TextSpan] = []
    start = 0
    while start < n:
        end = start
        budget = 0
        while end < n and (end == start or budget + per_word_tokens[end] <= target_tokens):
            budget += per_word_tokens[end]
            end += 1
        char_start = words_with_pos[start][1]
        char_end = words_with_pos[end - 1][2]
        spans.append(TextSpan(text=text[char_start:char_end], char_start=char_start, char_end=char_end))
        if end == n:
            break
        # Retrocede desde `end` acumulando tokens hasta cubrir
        # overlap_tokens (presupuesto real, no un número fijo de
        # palabras) -- con word_count por defecto esto reproduce
        # exactamente `step = max(target_tokens - overlap_tokens, 1)`
        # del diseño anterior.
        back = end
        overlap_budget = 0
        while back > start and overlap_budget < overlap_tokens:
            back -= 1
            overlap_budget += per_word_tokens[back]
        start = max(back, start + 1)  # siempre avanza al menos una palabra
    return spans


def split_by_headings(text: str) -> list[tuple[Optional[str], TextSpan]]:
    """Divide por líneas de encabezado estilo Markdown ('#', '##', ...).
    Si el texto no tiene encabezados, devuelve el texto completo como
    una sola sección sin título (equivalente a DOCUMENTO_COMPLETO)."""
    if not text.strip():
        return []

    lines = text.splitlines(keepends=True)
    sections: list[tuple[Optional[str], int, int]] = []
    current_title: Optional[str] = None
    current_start = 0
    offset = 0

    for line in lines:
        match = _HEADING_RE.match(line.strip())
        if match:
            if offset > current_start:
                sections.append((current_title, current_start, offset))
            current_title = match.group(2).strip()
            current_start = offset
        offset += len(line)
    if offset > current_start:
        sections.append((current_title, current_start, offset))

    return [
        (title, TextSpan(text=text[start:end], char_start=start, char_end=end))
        for title, start, end in sections
        if text[start:end].strip()
    ]


def merge_small_spans(
    spans: list[TextSpan], min_tokens: int, count_tokens: CountTokensFn = word_count,
) -> list[TextSpan]:
    """Une fragmentos menores que min_tokens con el siguiente (o, si es
    el último, con el anterior), preservando el orden y los
    desplazamientos de carácter combinados (INVESTIGACION.odt, A2:
    "fragmentos menores de 80 tokens: unir con la sección relacionada")."""
    if not spans:
        return []

    merged: list[TextSpan] = list(spans)
    i = 0
    while i < len(merged) - 1:
        if count_tokens(merged[i].text) < min_tokens:
            a, b = merged[i], merged[i + 1]
            combined = TextSpan(
                text=a.text + ("\n" if not a.text.endswith("\n") else "") + b.text,
                char_start=a.char_start,
                char_end=b.char_end,
            )
            merged[i : i + 2] = [combined]
        else:
            i += 1

    if len(merged) > 1 and count_tokens(merged[-1].text) < min_tokens:
        a, b = merged[-2], merged[-1]
        combined = TextSpan(
            text=a.text + ("\n" if not a.text.endswith("\n") else "") + b.text,
            char_start=a.char_start,
            char_end=b.char_end,
        )
        merged[-2:] = [combined]

    return merged


_ARTICLE_HEADING_RE = re.compile(r"^(art[íi]culo\s+\d+\w*\.?-?|art\.\s*\d+\w*\.?-?)\b", re.IGNORECASE)
_QA_HEADING_RE = re.compile(r"^(pregunta\s*[:.]|p\s*[:.]|q\s*[:.])", re.IGNORECASE)
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def _split_by_line_trigger(
    text: str, trigger_re: re.Pattern[str], title_from_first_line,
) -> list[tuple[Optional[str], TextSpan]]:
    """Agrupa el texto en bloques que empiezan en cada línea que
    coincide con `trigger_re` (p. ej. "Artículo 12.-", "Pregunta:").

    A diferencia de split_by_headings, la línea disparadora es parte
    del cuerpo del fragmento, no un título aparte: en reglamentos y
    FAQ el contenido empieza en la misma línea que el marcador
    ("Artículo 12.- No se permite..."), no en la línea siguiente. Si
    el texto no tiene ninguna línea disparadora, se devuelve completo
    como una sola sección sin título (mismo criterio de respaldo que
    split_by_headings)."""
    if not text.strip():
        return []

    lines = text.splitlines(keepends=True)
    trigger_offsets: list[int] = []
    offset = 0
    for line in lines:
        if trigger_re.match(line.strip()):
            trigger_offsets.append(offset)
        offset += len(line)

    if not trigger_offsets:
        stripped = text.strip()
        start = text.index(stripped[0])
        return [(None, TextSpan(text=stripped, char_start=start, char_end=start + len(stripped)))]

    boundaries = [0, *trigger_offsets, len(text)] if trigger_offsets[0] > 0 else [*trigger_offsets, len(text)]
    result: list[tuple[Optional[str], TextSpan]] = []
    # strict=False es intencional: boundaries[1:] tiene un elemento
    # menos que boundaries por construccion (ventana deslizante de a
    # pares), no es un error a detectar.
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        block = text[start:end]
        lstripped = block.lstrip()
        if not lstripped.strip():
            continue
        leading_ws = len(block) - len(lstripped)
        stripped_block = block.strip()
        block_start = start + leading_ws
        block_end = block_start + len(stripped_block)
        # El bloque previo al primer disparador (p. ej. un preámbulo
        # antes del primer "Artículo") no tiene marcador propio y se
        # deja sin título, igual que una sección huérfana de
        # split_by_headings.
        is_preamble = start == 0 and (not trigger_offsets or trigger_offsets[0] > 0)
        title = None if is_preamble else title_from_first_line(stripped_block.splitlines()[0])
        result.append((title, TextSpan(text=stripped_block, char_start=block_start, char_end=block_end)))

    return result


def _article_title(first_line: str) -> str:
    match = _ARTICLE_HEADING_RE.match(first_line.strip())
    label = match.group(0).rstrip(".-").strip() if match else first_line.strip()
    return label[:120]


def _qa_title(first_line: str) -> str:
    return first_line.strip()[:200]


def split_by_articles(text: str) -> list[tuple[Optional[str], TextSpan]]:
    """Reglamento: un fragmento por artículo/inciso completo, sin
    sub-dividir aunque exceda el tamaño estándar (INVESTIGACION.odt,
    A2). `section_title` queda como el número de artículo detectado
    (p. ej. "Artículo 12"), para trazabilidad ("qué sección
    representa")."""
    return _split_by_line_trigger(text, _ARTICLE_HEADING_RE, _article_title)


def split_by_qa_pairs(text: str) -> list[tuple[Optional[str], TextSpan]]:
    """Preguntas frecuentes: un fragmento por pregunta completa
    (pregunta + respuesta), sin solapamiento (INVESTIGACION.odt, A2).
    `section_title` queda como la línea de la pregunta completa, para
    trazabilidad."""
    return _split_by_line_trigger(text, _QA_HEADING_RE, _qa_title)


def _is_table_row(stripped_line: str) -> bool:
    return "|" in stripped_line


def split_by_tables(
    text: str, target_tokens: int, count_tokens: CountTokensFn = word_count,
) -> list[tuple[Optional[str], TextSpan, bool]]:
    """Detecta tablas en formato Markdown (fila de encabezado + fila
    separadora de guiones, ambas con '|', seguidas de filas de datos)
    y arma fragmentos que siempre repiten encabezado y separador
    (INVESTIGACION.odt, A2: "Tabla completa o grupo lógico de filas...
    Repetir encabezados en cada fragmento"). Si una tabla excede
    `target_tokens`, se reparte en grupos de filas -- cada grupo con
    su propio encabezado repetido -- en vez de partir a la mitad una
    fila. El texto que no es tabla (párrafos alrededor) se fragmenta
    con la misma ventana por tamaño de POR_TAMANIO, sin fusionar
    fragmentos pequeños (limitación conocida, ver README).

    Devuelve tuplas (title, span, es_tabla): a diferencia de las demás
    funciones de este módulo, aquí el llamador necesita distinguir
    fragmentos de tabla (ChunkType.TABLA) de fragmentos de texto
    normal (ChunkType.TEXTO) dentro del mismo documento."""
    if not text.strip():
        return []

    lines = text.splitlines(keepends=True)
    n = len(lines)
    stripped_lines = [line.strip() for line in lines]

    table_ranges: list[tuple[int, int]] = []
    i = 0
    while i < n - 1:
        if _is_table_row(stripped_lines[i]) and _TABLE_SEPARATOR_RE.match(stripped_lines[i + 1]):
            start = i
            j = i + 2
            while j < n and _is_table_row(stripped_lines[j]):
                j += 1
            table_ranges.append((start, j))
            i = j
        else:
            i += 1

    line_offsets = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line))

    if not table_ranges:
        spans = split_by_size(text, target_tokens, overlap_tokens=0, count_tokens=count_tokens)
        return [(None, span, False) for span in spans]

    result: list[tuple[Optional[str], TextSpan, bool]] = []
    cursor = 0
    for start, end in table_ranges:
        if start > cursor:
            result.extend(_split_text_run(lines, line_offsets, cursor, start, target_tokens, count_tokens))
        result.extend(_split_table_rows(lines, line_offsets, start, end, target_tokens, count_tokens))
        cursor = end
    if cursor < n:
        result.extend(_split_text_run(lines, line_offsets, cursor, n, target_tokens, count_tokens))

    return result


def _split_text_run(
    lines: list[str], line_offsets: list[int], line_start: int, line_end: int, target_tokens: int,
    count_tokens: CountTokensFn = word_count,
) -> list[tuple[Optional[str], TextSpan, bool]]:
    run_text = "".join(lines[line_start:line_end])
    base_offset = line_offsets[line_start]
    return [
        (None, TextSpan(text=span.text, char_start=base_offset + span.char_start, char_end=base_offset + span.char_end), False)
        for span in split_by_size(run_text, target_tokens, overlap_tokens=0, count_tokens=count_tokens)
    ]


def _split_table_rows(
    lines: list[str], line_offsets: list[int], start: int, end: int, target_tokens: int,
    count_tokens: CountTokensFn = word_count,
) -> list[tuple[Optional[str], TextSpan, bool]]:
    header_text = "".join(lines[start:start + 2])
    data_start = start + 2

    groups: list[tuple[int, int]] = []
    group_start = data_start
    word_total = 0
    for row_index in range(data_start, end):
        row_words = count_tokens(lines[row_index])
        if word_total and word_total + row_words > target_tokens:
            groups.append((group_start, row_index))
            group_start = row_index
            word_total = 0
        word_total += row_words
    groups.append((group_start, end))

    result: list[tuple[Optional[str], TextSpan, bool]] = []
    for row_start, row_end in groups:
        # El texto de cada grupo repite el encabezado, así que ya no
        # es una porción contigua del original a partir del segundo
        # grupo -- char_start/char_end se mantienen sobre el rango de
        # la tabla completa (con encabezado incluido) solo para
        # ubicar una página razonable, no como una igualdad exacta con
        # text[char_start:char_end] (excepción documentada aquí).
        full_text = (header_text + "".join(lines[row_start:row_end])).strip()
        result.append(("Tabla", TextSpan(
            text=full_text, char_start=line_offsets[start], char_end=line_offsets[row_end],
        ), True))
    return result


def resolve_page(char_offset: int, page_breaks: list[int]) -> Optional[int]:
    """Página 1-indexada a la que corresponde un desplazamiento de
    carácter, dados los desplazamientos donde inicia cada página nueva
    a partir de la 2 (page_breaks[0] es donde empieza la página 2,
    etc.). None si no hay información de páginas (TXT/DOCX/Markdown)."""
    if not page_breaks:
        return None
    page = 1
    for break_offset in page_breaks:
        if char_offset >= break_offset:
            page += 1
        else:
            break
    return page
