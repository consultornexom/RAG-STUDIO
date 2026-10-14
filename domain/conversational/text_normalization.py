"""Normalización de texto compartida por la evaluación de guardrails
(Ronda 87, 2026-10-02, hallazgo real de usuario sobre la sintaxis de
condiciones).

Antes, `rule_evaluation._coerce_pair` decía en su docstring que la
comparación de texto no dependía "de mayúsculas/acentos exactos", pero
solo pasaba a minúsculas: una condición `intencion = Solicitar asesoría`
no reconocía una intención llamada "Solicitar asesoria" (o al revés), y
un campo escrito `intención` (con acento) nunca coincidía con el campo
real `intencion`, de modo que la regla no se disparaba nunca y sin
ningún aviso. Este módulo concentra la regla para que la evaluación, la
validación de condiciones y la búsqueda de reglas que referencian una
intención usen exactamente la misma."""
from __future__ import annotations

import re
import unicodedata

_SEPARADORES_DE_CAMPO = re.compile(r"[\s\-]+")
_COMILLAS = ('"', "'", "“", "”", "‘", "’", "«", "»")


def normalize_text(value: object) -> str:
    """Minúsculas, sin espacios en los extremos y sin acentos ni
    diéresis (á→a, ñ→n, ü→u). Se usa para comparar, nunca para mostrar."""
    texto = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalize_field_name(name: str) -> str:
    """Nombre de campo de una condición en su forma canónica: igual que
    `normalize_text`, y además espacios y guiones internos se convierten
    en "_" ("Nivel riesgo" → "nivel_riesgo", "intención" → "intencion")."""
    return _SEPARADORES_DE_CAMPO.sub("_", normalize_text(name))


def strip_matching_quotes(value: str) -> str:
    """Quita UN par de comillas que envuelva todo el valor
    (`"Campus Norte"` → `Campus Norte`). El manual mostraba ejemplos con
    comillas y, sin esto, las comillas formaban parte del valor
    comparado, así que la condición nunca se cumplía."""
    texto = value.strip()
    if len(texto) >= 2 and texto[0] in _COMILLAS and texto[-1] in _COMILLAS:
        return texto[1:-1].strip()
    return texto
