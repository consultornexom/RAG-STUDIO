"""Normalización de texto (RAG STUDIO.odt: paso propio entre
"Extracción" y "Fragmentación" en el alcance mínimo obligatorio de la
primera versión -- "Debe incluir: ... Normalización. Laboratorio de
fragmentación...").

Alcance deliberado: normalización de forma (codificación, saltos de
línea, espacios en blanco, caracteres de control), no de contenido --
no corrige ortografía, no traduce, no reescribe. Los formatos
estructurados que ya producen su propio marcado (encabezados Markdown
de DocxExtractor, tablas Markdown de XlsxExtractor/CsvExtractor/
DocxExtractor) no se ven afectados: esta función nunca toca espacios
internos de una línea, solo limpia alrededor de ella."""
from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS_EXCEPT_TAB_NEWLINE = re.compile(
    "[" + "".join(chr(c) for c in range(0, 32) if c not in (9, 10)) + chr(127) + "]"
)
_THREE_OR_MORE_NEWLINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Aplica, en este orden:

    1. Normalización Unicode NFC (caracteres compuestos vs.
       precompuestos -- p. ej. "é" como un solo code point en vez de
       "e" + acento combinante -- para que dos fuentes con el mismo
       texto visible produzcan los mismos tokens al embeber).
    2. Unifica saltos de línea (\\r\\n, \\r -> \\n) -- archivos de
       origen Windows no deben producir fragmentos con saltos de línea
       mixtos.
    3. Quita espacios en blanco al final de cada línea.
    4. Colapsa 3 o más saltos de línea consecutivos en exactamente 2
       (un único párrafo en blanco de separación) -- un PDF o DOCX con
       espaciado irregular no debe inflar artificialmente el tamaño de
       un fragmento con líneas vacías.
    5. Quita caracteres de control (excepto tab y salto de línea) --
       artefactos ocasionales de una extracción real (p. ej. un
       carácter nulo dentro de un DOCX corrupto).
    6. Quita espacios en blanco al inicio/final del texto completo.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _THREE_OR_MORE_NEWLINES.sub("\n\n", text)
    text = _CONTROL_CHARS_EXCEPT_TAB_NEWLINE.sub("", text)
    return text.strip()
