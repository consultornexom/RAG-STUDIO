"""Ronda 100 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
funciones puras para usar el contexto jerárquico de los fragmentos
(`Chunk.section_path`) en la búsqueda textual e híbrida.

Tres piezas, todas sin dependencias externas:

1. **Ordinales normalizados** (`ordinal_terms`): "5.º semestre", "5to.
   semestre", "quinto semestre", "semestre 5" y "5° semestre" producen el
   mismo término canónico `semestre_5`. Solo con una UNIDAD de periodo
   (semestre, cuatrimestre, trimestre, bimestre, grado, año, ciclo, periodo)
   y nunca con cardinales sueltos: "6 semestres" (duración), "artículo 5",
   "apartado 5" o "inciso 5" no producen nada, y "5.º grado" produce
   `grado_5`, distinto de `semestre_5`. El texto original no se modifica:
   los términos canónicos se AGREGAN al vocabulario de búsqueda.
2. **Documento léxico** (`lexical_document`): lo que BM25 puntúa por cada
   fragmento -- su texto, más los títulos de sus encabezados SUPERIORES (el
   propio ya está en el texto), más los términos canónicos de ordinales.
   `chunk.text` no cambia y el vector del fragmento tampoco: la ruta NO se
   concatena al texto que va al modelo de embeddings (la medición de la
   Ronda 99 mostró que eso ayuda al área pero perjudica al semestre).
3. **Coincidencia jerárquica** (`hierarchy_match`/`hierarchy_rank`): qué
   términos de la consulta aparecen en los encabezados SUPERIORES del
   fragmento, más los ordinales normalizados de toda su ruta (comparación
   sin mayúsculas ni acentos, sin palabras vacías, ignorando términos
   comunes a más de la mitad de los candidatos). La búsqueda híbrida la usa
   como una tercera lista de RRF, solo entre los candidatos que ya trajeron
   la búsqueda semántica y la textual (nunca agrega candidatos).
4. **Entrada del reranker** (`contextualized_text`): con reranking, el
   cross-encoder recibe "ruta\ntexto" y su orden se fusiona con la lista
   jerárquica.

Decisiones respaldadas por docs proyecto/Ronda100_Contexto_Jerarquico/
evaluacion_recuperacion.py (corpus sintético, ver Resultados_Ronda100.md).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional, Sequence

_UNIDADES = {
    "semestre": "semestre", "cuatrimestre": "cuatrimestre", "trimestre": "trimestre",
    "bimestre": "bimestre", "grado": "grado", "ano": "ano", "ciclo": "ciclo", "periodo": "periodo",
}
"""Unidad (singular, sin acentos) -> nombre del término canónico."""

_ORDINALES_PALABRA = {
    "primer": 1, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercer": 3, "tercero": 3,
    "tercera": 3, "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5, "sexto": 6, "sexta": 6,
    "septimo": 7, "septima": 7, "setimo": 7, "octavo": 8, "octava": 8, "noveno": 9, "novena": 9,
    "decimo": 10, "decima": 10, "undecimo": 11, "onceavo": 11, "duodecimo": 12, "doceavo": 12,
}

# Número con marca ordinal: 5.º 5º 5° 5o 5a 5to 5to. 1er 1ro 2do 3er 3ro 7mo 8vo 9no 10mo (con o sin punto)
_NUM_ORDINAL = r"(\d{1,2})(?:\s?\.?\s?[ºª°]|\.?(?:er|ro|do|to|vo|no|mo|o|a)\b)\.?"
_PALABRA_ORDINAL = r"(" + "|".join(sorted(_ORDINALES_PALABRA, key=len, reverse=True)) + r")"
_UNIDAD = r"(semestre|cuatrimestre|trimestre|bimestre|grado|ano|ciclo|periodo)"

_RE_ORDINAL_UNIDAD = re.compile(rf"(?:{_NUM_ORDINAL}|\b{_PALABRA_ORDINAL})\s+{_UNIDAD}\b")
_RE_UNIDAD_NUMERO = re.compile(rf"\b{_UNIDAD}\s+(?:{_NUM_ORDINAL}|(\d{{1,2}})\b(?!\s*(?:{_UNIDAD}|%)))")

_STOPWORDS = frozenset("""
a al ante bajo con contra de del desde durante e el en entre esta este esto hacia hasta la las le les lo los
mas mi mis muy ni o para pero por que se segun sin sobre su sus tal tambien te tu un una uno unos unas y ya
cual cuales cuando donde como quien que hay es son ser fue han he se lleva llevan cursa cursan curso dan da
materias materia asignaturas asignatura plantel area areas
semestre semestres cuatrimestre cuatrimestres trimestre trimestres bimestre bimestres grado grados ano anos
ciclo ciclos periodo periodos
""".split())
"""Palabras vacías para la coincidencia jerárquica. 'materias', 'plantel' y
'área' se excluyen porque dicen QUÉ se pregunta o introducen el nombre,
no qué sección; el nombre propio que sigue sí cuenta. Las unidades de
periodo ('semestre'...) tampoco cuentan solas: lo que distingue una
sección de otra es su término canónico (`semestre_5`)."""


def _sin_acentos(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in normal if not unicodedata.combining(c))


def ordinal_terms(text: str) -> list[str]:
    """Términos canónicos `<unidad>_<n>` presentes en el texto, sin repetir."""
    base = _sin_acentos(text)
    encontrados: list[str] = []
    for m in _RE_ORDINAL_UNIDAD.finditer(base):
        numero = int(m.group(1)) if m.group(1) else _ORDINALES_PALABRA[m.group(2)]
        encontrados.append(f"{_UNIDADES[m.group(3)]}_{numero}")
    for m in _RE_UNIDAD_NUMERO.finditer(base):
        digitos = m.group(2) or m.group(3)
        if digitos is not None:
            encontrados.append(f"{_UNIDADES[m.group(1)]}_{int(digitos)}")
    return list(dict.fromkeys(encontrados))


def content_terms(text: str) -> set[str]:
    """Palabras con contenido (sin acentos, minúsculas, sin palabras vacías,
    3+ letras) más los términos canónicos de ordinales."""
    palabras = {w for w in re.findall(r"[a-z0-9]+", _sin_acentos(text)) if len(w) >= 3 and w not in _STOPWORDS}
    return palabras | set(ordinal_terms(text))


def path_titles(section_path: Optional[Sequence]) -> list[str]:
    """Títulos de una ruta (acepta SectionHeading, dicts o pares)."""
    titulos = []
    for h in section_path or []:
        if isinstance(h, dict):
            titulos.append(str(h.get("title", "")))
        elif isinstance(h, (list, tuple)):
            titulos.append(str(h[-1]))
        else:
            titulos.append(str(getattr(h, "title", "")))
    return [t for t in titulos if t]


def lexical_document(text: str, section_path: Optional[Sequence] = None) -> str:
    """Texto que BM25 puntúa por un fragmento: su texto + los títulos de sus
    encabezados superiores + los términos canónicos de ordinales del texto y
    de la ruta. Sin ruta ni ordinales, es exactamente `text`."""
    superiores = path_titles(section_path)[:-1]
    partes = [text, *superiores]
    canonicos = ordinal_terms("\n".join([text, *path_titles(section_path)]))
    if canonicos:
        partes.append(" ".join(canonicos))
    return "\n".join(partes)


def contextualized_text(text: str, section_path: Optional[Sequence] = None) -> str:
    """Entrada del reranker para un fragmento: la ruta de encabezados en una
    línea y debajo el texto. Sin ruta, el texto tal cual. NUNCA se usa para
    el vector del fragmento (ver docstring del módulo)."""
    titulos = path_titles(section_path)
    return text if not titulos else " > ".join(titulos) + "\n" + text


def lexical_query(query: str) -> str:
    """Consulta para BM25: la original más sus términos canónicos de ordinales."""
    canonicos = ordinal_terms(query)
    return query if not canonicos else f"{query} {' '.join(canonicos)}"


def hierarchy_match(query: str, section_path: Optional[Sequence]) -> list[str]:
    """Términos de la consulta que coinciden con el CONTEXTO jerárquico del
    fragmento: las palabras de sus encabezados SUPERIORES y los ordinales
    normalizados de toda la ruta (incluido su propio encabezado, p. ej.
    `semestre_5`). Las palabras del título propio no cuentan aquí: ya están
    en el texto del fragmento y la búsqueda textual las puntúa; contarlas
    otra vez favorecía a cualquier sección con ese título por encima de un
    documento sin ruta con el mismo tema. Lista ordenada (trazable)."""
    titulos = path_titles(section_path)
    if not titulos:
        return []
    contexto = content_terms("\n".join(titulos[:-1])) | set(ordinal_terms("\n".join(titulos)))
    return sorted(content_terms(query) & contexto)


def ordinal_conflicts(query: str, section_path: Optional[Sequence]) -> list[str]:
    """Ronda 101 (validación real de NEXOM, LOTE01_Bachillerato): ordinales
    de la RUTA del fragmento que contradicen un ordinal EXPLÍCITO de la
    consulta en la misma unidad -- p. ej. la consulta pide `semestre_5` y la
    ruta es de `semestre_6`. Lista vacía si la consulta no menciona ningún
    ordinal, si la ruta no tiene ordinales de esa unidad o si alguno
    coincide ("quinto y sexto semestre" acepta ambos). Solo mira la ruta de
    encabezados, nunca el texto libre del fragmento."""
    pedidos: dict[str, set[str]] = {}
    for termino in ordinal_terms(query):
        unidad, numero = termino.rsplit("_", 1)
        pedidos.setdefault(unidad, set()).add(numero)
    if not pedidos:
        return []
    en_ruta: dict[str, set[str]] = {}
    for termino in ordinal_terms("\n".join(path_titles(section_path))):
        unidad, numero = termino.rsplit("_", 1)
        en_ruta.setdefault(unidad, set()).add(numero)
    return sorted(
        f"{unidad}_{n}" for unidad, numeros in en_ruta.items()
        if unidad in pedidos and not numeros & pedidos[unidad] for n in numeros
    )


def hierarchy_rank(query: str, items: Iterable[tuple[str, Optional[Sequence]]]) -> list[tuple[str, list[str]]]:
    """Ordena (id, ruta) por los términos de la consulta presentes en la ruta;
    solo los que tienen al menos uno.

    Solo cuentan los términos que DISTINGUEN entre candidatos: un término que
    aparece en la ruta de más de la mitad de los candidatos (p. ej. el título
    raíz "Bachillerato", común a todo un plan de estudios) no dice qué
    sección es la correcta y se ignora -- sin esta regla, una consulta
    genérica ("requisitos de ingreso al bachillerato") empujaba todas las
    secciones del plan por encima de un documento compartido sin ruta. Los
    ordinales canónicos cuentan doble: separan secciones hermanas ("5.º"
    frente a "6.º")."""
    lista = list(items)
    coincidencias = [(item_id, hierarchy_match(query, ruta)) for item_id, ruta in lista]
    limite = len(lista) / 2
    frecuencia: dict[str, int] = {}
    for _, terminos in coincidencias:
        for t in terminos:
            frecuencia[t] = frecuencia.get(t, 0) + 1
    puntuados = []
    for orden, (item_id, terminos) in enumerate(coincidencias):
        utiles = [t for t in terminos if frecuencia[t] <= limite]
        if utiles:
            peso = sum(2 if "_" in t else 1 for t in utiles)
            puntuados.append((peso, orden, item_id, utiles))
    puntuados.sort(key=lambda x: (-x[0], x[1]))
    return [(item_id, terminos) for _, _, item_id, terminos in puntuados]
