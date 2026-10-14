"""Detección de valores de variables conversacionales en el texto de la
consulta (Ronda 89, 2026-10-04, hallazgo real de usuario en AGENTE UDL).

Antes, una variable solo se consideraba "proporcionada" si venía
explícitamente en `provided_variables` (código=valor). Una consulta como
"¿Cuál es el objetivo del Diplomado de Alta Especialidad en Gestión
Profesional de Proyectos?" nombraba el programa, pero el motor marcaba
`programa_academico` como faltante y pedía aclaración.

Este módulo es puro (sin repositorios): recibe, por variable, los valores
posibles con sus formas de escribirse (alias) -- que la capa de
aplicación arma a partir de la configuración del proyecto: catálogos y
valores de metadatos ya capturados, nunca listas fijas en el código -- y
busca esos alias en la consulta como secuencias de palabras completas,
sin distinguir mayúsculas ni acentos.

Reglas:
- Se compara palabra por palabra: "Justicia Laboral I" no coincide dentro
  de "Justicia Laboral II", ni "arte" dentro de "artes".
- Si varios valores de la MISMA variable aparecen, gana la mención más
  larga ("Psicología Organizacional" sobre "Psicología"). Si empatan en
  longitud y son distintos, la variable queda ambigua y no se llena: el
  motor pide aclaración igual que antes, nunca adivina.
- Alias de menos de 3 letras se ignoran (evita coincidencias casuales).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text_normalization import normalize_text

_PALABRA = re.compile(r"\w+", re.UNICODE)
_MIN_ALIAS_CHARS = 3


@dataclass(frozen=True)
class ValueCandidate:
    """Un valor posible de una variable (p. ej. el código de una entrada de
    catálogo) y las formas en que puede aparecer escrito en una consulta."""

    value: str
    aliases: tuple[str, ...]


@dataclass
class ExtractionResult:
    detected: dict[str, str] = field(default_factory=dict)
    """variable -> valor detectado sin ambigüedad."""
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    """variable -> valores distintos mencionados con la misma longitud."""
    spans: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    """variable -> posiciones (inicio, fin) en el texto ORIGINAL de cada
    mención del valor detectado."""


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(normalize_text(m.group(0)), m.start(), m.end()) for m in _PALABRA.finditer(text)]


def alias_forms(*texts: str) -> tuple[str, ...]:
    """Formas razonables de escribir un valor a partir de su etiqueta y su
    código: "gestion_profesional_de_proyectos" -> "gestion profesional de
    proyectos". Sin duplicados (comparando normalizado)."""
    seen: set[str] = set()
    result: list[str] = []
    for text in texts:
        if not text:
            continue
        for form in (text, text.replace("_", " ").replace("-", " ")):
            key = " ".join(t for t, _, _ in _tokens(form))
            if key and key not in seen and len(key.replace(" ", "")) >= _MIN_ALIAS_CHARS:
                seen.add(key)
                result.append(form)
    return tuple(result)


def find_mentions(query: str, aliases: tuple[str, ...]) -> list[tuple[int, int, int]]:
    """Menciones de cualquiera de los alias en `query`: lista de
    (cantidad_de_palabras, inicio, fin) en el texto original."""
    query_tokens = _tokens(query)
    words = [t for t, _, _ in query_tokens]
    found: list[tuple[int, int, int]] = []
    for alias in aliases:
        alias_words = [t for t, _, _ in _tokens(alias)]
        if not alias_words or len("".join(alias_words)) < _MIN_ALIAS_CHARS:
            continue
        n = len(alias_words)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == alias_words:
                found.append((n, query_tokens[i][1], query_tokens[i + n - 1][2]))
    return found


def extract_variable_values(
    query: str, candidates_by_variable: dict[str, list[ValueCandidate]],
) -> ExtractionResult:
    result = ExtractionResult()
    for variable, candidates in candidates_by_variable.items():
        best_len = 0
        best: dict[str, list[tuple[int, int]]] = {}
        for candidate in candidates:
            mentions = find_mentions(query, candidate.aliases)
            if not mentions:
                continue
            longest = max(length for length, _, _ in mentions)
            spans = [(start, end) for length, start, end in mentions]
            if longest > best_len:
                best_len = longest
                best = {candidate.value: spans}
            elif longest == best_len:
                best.setdefault(candidate.value, []).extend(spans)
        if not best:
            continue
        if len(best) == 1:
            value, spans = next(iter(best.items()))
            result.detected[variable] = value
            result.spans[variable] = sorted(set(spans))
        else:
            result.ambiguous[variable] = sorted(best)
    return result


_CONECTORES = frozenset({
    "de", "del", "la", "las", "el", "los", "en", "a", "al", "y", "o", "e", "u", "para", "por", "con",
})
"""Palabras de enlace que quedan "colgando" junto a una mención quitada
("... termina la licenciatura en Derecho" -> "... termina la en"). Solo
se quitan si quedan PEGADAS a una mención retirada (Ronda 91)."""
_PALABRA_FINAL = re.compile(r"(\w+)\W*$", re.UNICODE)
_PALABRA_INICIAL = re.compile(r"^\W*(\w+)", re.UNICODE)


def _quitar_conectores_finales(pieza: str) -> str:
    while True:
        m = _PALABRA_FINAL.search(pieza)
        if not m or normalize_text(m.group(1)) not in _CONECTORES or m.group(0) != pieza[m.start():]:
            return pieza
        if pieza[m.end(1):].strip():  # hay puntuación después: no es la palabra pegada al hueco
            return pieza
        pieza = pieza[:m.start()]


def _quitar_conectores_iniciales(pieza: str) -> str:
    while True:
        m = _PALABRA_INICIAL.match(pieza)
        if not m or normalize_text(m.group(1)) not in _CONECTORES:
            return pieza
        if pieza[:m.start(1)].strip():
            return pieza
        pieza = pieza[m.end(1):]


def remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """`text` sin los fragmentos indicados, con espacios normalizados.

    Ronda 91: también quita las palabras de enlace que quedan pegadas a
    cada hueco ("la licenciatura en Derecho", si se quitan "licenciatura"
    y "Derecho", ya no deja "la en"). Ese residuo hacía que preguntas
    equivalentes se compararan distinto según cómo se escribiera el nombre
    del programa."""
    if not spans:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        if start < cursor:
            start = cursor
        pieces.append(text[cursor:start])
        cursor = max(cursor, end)
    pieces.append(text[cursor:])
    limpias: list[str] = []
    for i, pieza in enumerate(pieces):
        if i > 0:
            pieza = _quitar_conectores_iniciales(pieza)
        if i < len(pieces) - 1:
            pieza = _quitar_conectores_finales(pieza)
        limpias.append(pieza)
    return re.sub(r"\s+", " ", " ".join(limpias)).strip()
