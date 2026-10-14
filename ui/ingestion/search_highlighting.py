"""Lógica pura (sin Qt) del comparador de resultados de búsqueda:
decide qué palabras de la consulta resaltar y cómo envolverlas en HTML
dentro de la vista previa de cada resultado.

Separado de `ui/ingestion/panel.py` a propósito: son funciones sin
efectos secundarios ni dependencia de PySide6, así que se pueden
probar con pytest normal en cualquier entorno, incluso uno sin las
bibliotecas nativas de Qt (libEGL/libGL) donde `panel.py` no se puede
ni importar."""
from __future__ import annotations

import re

# Palabras muy cortas o conectores comunes del español no se resaltan --
# resaltar "de", "la", "y" en cada resultado sería ruido, no señal (casi
# cualquier fragmento las contiene, sin que eso explique por qué quedó
# arriba en el ranking semántico).
_SPANISH_STOPWORDS = {
    "de", "la", "el", "en", "y", "o", "a", "que", "del", "los", "las", "un", "una", "unos", "unas",
    "es", "son", "para", "por", "con", "sin", "su", "sus", "al", "lo", "se", "no", "sí", "e", "u",
}

_HIGHLIGHT_SPAN = '<span style="background-color:#fff2a8;">{}</span>'


def extract_highlight_terms(query_text: str) -> list[str]:
    """Palabras de la consulta lo bastante largas y no genéricas como
    para que resaltarlas en los resultados aporte señal real sobre por
    qué ese fragmento coincidió."""
    words = re.findall(r"\w+", query_text)
    return [w for w in words if len(w) >= 3 and w.lower() not in _SPANISH_STOPWORDS]


def highlight_terms(escaped_text: str, terms: list[str]) -> str:
    """Envuelve en un `<span>` resaltado las coincidencias de `terms`
    dentro de `escaped_text`. `escaped_text` debe venir ya escapado
    (p. ej. con `html.escape`) -- los términos son texto plano (sin
    HTML), así que el orden (escapar primero, resaltar después) no
    introduce marcado sin escapar. Se usa `<span style="...">` en vez
    de `<mark>` porque el motor de rich text de Qt (`QTextDocument`)
    soporta de forma confiable un subconjunto de HTML/CSS con estilos
    inline, pero no garantiza `<mark>` en todas las versiones."""
    terms = [t for t in terms if t]
    if not terms:
        return escaped_text
    pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    return pattern.sub(lambda m: _HIGHLIGHT_SPAN.format(m.group(0)), escaped_text)
