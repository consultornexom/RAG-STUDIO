"""Ronda 99 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
contexto jerárquico de encabezados Markdown, DERIVADO del texto extraído
de la fuente (no se guarda ni se indexa).

`split_by_headings` (estrategia por_encabezado) corta en cada línea
`#`..`######` pero conserva solo el título del ÚLTIMO encabezado: el nivel
y los encabezados superiores se pierden. En un plan de estudios con

    ## Área Económico-Administrativa y Humanidades
    ### 5.º semestre
    ...
    ## Área Físico-Matemática y Químico-Biológicas
    ### 5.º semestre

los dos fragmentos "5.º semestre" no dicen a qué área pertenecen. Este
módulo reconstruye, para diagnóstico, la ruta completa de encabezados
que corresponde a una posición del texto, para poder mostrarla junto al
fragmento y comprobar si su texto contiene ese contexto.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
"""Mismo patrón que domain.ingestion.splitting (líneas `#`..`######`)."""


@dataclass(frozen=True)
class HeadingEntry:
    level: int
    title: str
    char_start: int


def heading_outline(text: str) -> list[HeadingEntry]:
    """Encabezados Markdown del texto, en orden, con su nivel y posición."""
    resultado: list[HeadingEntry] = []
    offset = 0
    for linea in text.splitlines(keepends=True):
        match = _HEADING_RE.match(linea.strip())
        if match:
            resultado.append(HeadingEntry(len(match.group(1)), match.group(2).strip(), offset))
        offset += len(linea)
    return resultado


def heading_path_at(outline: list[HeadingEntry], position: int) -> list[HeadingEntry]:
    """Ruta de encabezados (del más general al más específico) que rige la
    posición indicada: el último encabezado anterior a ella y, por encima,
    el último de cada nivel superior."""
    pila: list[HeadingEntry] = []
    for entrada in outline:
        if entrada.char_start > position:
            break
        while pila and pila[-1].level >= entrada.level:
            pila.pop()
        pila.append(entrada)
    return pila


def locate_text(haystack: str, needle: str) -> Optional[int]:
    """Posición de `needle` (un fragmento ya recortado con strip) en el
    texto extraído; None si no aparece tal cual."""
    needle = needle.strip()
    if not needle:
        return None
    posicion = haystack.find(needle)
    return posicion if posicion >= 0 else None


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto.lower())
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return re.sub(r"\W+", " ", sin_acentos).strip()


def missing_from_text(path: list[HeadingEntry], text: str) -> list[str]:
    """Títulos de la ruta que NO aparecen en el texto del fragmento
    (comparación sin mayúsculas, acentos ni puntuación): contexto que el
    fragmento no lleva consigo y que la búsqueda no puede usar."""
    cuerpo = f" {_normalizar(text)} "
    return [e.title for e in path if f" {_normalizar(e.title)} " not in cuerpo]
