"""Afinidad entre la intención reconocida y el TÍTULO de la sección de un
fragmento (Ronda 91, 2026-10-05, hallazgo real de usuario en AGENTE UDL).

Problema: con la intención correcta ("Consultar perfil de egreso") y el
filtro de programa ya aplicado, el apartado "Perfil del egresado" quedaba
cuarto, detrás de "Casos que requieren handoff", "Requisitos de ingreso"
y "Perfil del aspirante". El reordenamiento final lo hacía un modelo de
reranking entrenado en inglés, que ante preguntas en español produce
puntajes casi iguales y ruidosos (-9.2, -10.2, -10.7, -10.8...).

Estrategia general (sin listas fijas de secciones ni de programas): la
intención ya describe QUÉ se pregunta con sus propios textos -- nombre,
descripción y ejemplos positivos, todos escritos por quien diseña el
agente --, y cada fragmento indica de qué trata con el título de su
sección. Se mide qué proporción de las palabras del título aparecen en
esos textos (o en la consulta), comparando raíces de palabra sin acentos.
Las palabras que comparten muchas intenciones pesan menos (no distinguen
entre ellas). El resultado es un número entre 0 y 1 que solo REORDENA los
fragmentos ya recuperados y filtrados; a igual afinidad se conserva el
orden de la búsqueda.

Efecto sobre los fragmentos de control editorial ("Uso permitido por el
agente", "Nota de control para chunking", "Casos que requieren
handoff"...): siguen indexados y siguen apareciendo, pero como su título
no comparte vocabulario con las intenciones de contenido, quedan después
del apartado solicitado. Si una intención sí habla de ellos (p. ej. una
intención de canalización cuyo texto mencione "handoff"), suben.

Ronda 102 (hallazgo real de NEXOM, LOTE01_Bachillerato): hasta esta ronda
la afinidad era la clave PRINCIPAL del orden y el puntaje de la búsqueda
solo desempataba. Un documento compartido que la búsqueda ponía primero
(requisitos_ingreso.md) quedaba detrás de secciones de otros documentos
cuyo título nombraba el tema pero solo remitían al archivo. Desde esta
ronda:
- C1 (`combine_with_retrieval`): la afinidad es una lista más en una
  fusión RRF con el orden de la búsqueda, igual que la señal jerárquica
  de la Ronda 100. Entre fragmentos con afinidad, un mejor puesto en la
  búsqueda compensa un peor puesto de afinidad (uno a uno); los que no
  tienen ninguna afinidad de título siguen detrás de los que sí la
  tienen, como en la Ronda 91.
- C2 (`affinity_title`): un fragmento sin título de sección
  (documento_completo, por_tamanio, preámbulo) usa su primer encabezado
  Markdown -- sin confundir el encabezado YAML ("---") con un título -- y,
  si no tiene, el título de la fuente. Antes usaba la primera línea del
  texto, que en los documentos reales de LOTE01 era "---".
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable

from .entities import Intent
from .text_normalization import normalize_text

_PALABRA = re.compile(r"[a-z0-9]+")
_LONGITUD_RAIZ = 5
_VACIAS = frozenset({
    "de", "la", "el", "en", "y", "o", "a", "que", "del", "los", "las", "un", "una", "unos", "unas",
    "es", "son", "para", "por", "con", "sin", "su", "sus", "al", "lo", "se", "no", "si", "e", "u",
    "mi", "tu", "me", "te", "le", "les", "como", "cual", "cuales", "quien", "donde", "cuando",
    "quiero", "dame", "consultar", "consulta", "saber", "conocer",
})
"""Palabras que no describen el TEMA de una sección: conectores y verbos de
petición comunes ("quiero", "dame", "consultar"...)."""

_PESO_NOMBRE = 1.0
_PESO_CONSULTA = 1.0
_PESO_EJEMPLOS = 0.6
_PESO_DESCRIPCION = 0.6


def raices(texto: str) -> set[str]:
    """Raíces (primeras 5 letras, sin acentos) de las palabras con
    contenido: "egresado" y "egreso" -> "egres"; "estudios" -> "estud"."""
    return {
        palabra[:_LONGITUD_RAIZ]
        for palabra in _PALABRA.findall(normalize_text(texto))
        if len(palabra) >= 3 and palabra not in _VACIAS
    }


class SectionAffinity:
    """Calcula la afinidad de títulos de sección con UNA intención, dentro
    del conjunto de intenciones del proyecto (que define qué palabras
    distinguen)."""

    def __init__(
        self, intent: Intent, all_intents: Iterable[Intent], query_text: str,
        text_transform: Callable[[str], str] | None = None,
    ):
        transformar = text_transform or (lambda texto: texto)

        def perfil(it: Intent) -> tuple[set[str], set[str], set[str]]:
            ejemplos: set[str] = set()
            for ejemplo in it.positive_examples:
                ejemplos |= raices(transformar(ejemplo))
            return raices(transformar(it.name)), ejemplos, raices(transformar(it.description))

        perfiles = [perfil(it) for it in all_intents if it.active]
        self._n = max(1, len(perfiles))
        self._frecuencia: dict[str, int] = {}
        for nombre, ejemplos, descripcion in perfiles:
            for raiz in nombre | ejemplos | descripcion:
                self._frecuencia[raiz] = self._frecuencia.get(raiz, 0) + 1
        self._nombre, self._ejemplos, self._descripcion = perfil(intent)
        self._consulta = raices(transformar(query_text))

    def _especificidad(self, raiz: str) -> float:
        """1.0 si solo la usa esta intención; menos cuanto más intenciones
        la comparten (tipo IDF, normalizado a 0..1)."""
        frecuencia = self._frecuencia.get(raiz, 0)
        return math.log((self._n + 1) / (frecuencia + 1)) / math.log(self._n + 1)

    def score(self, section_title: str | None) -> float:
        titulo = raices(section_title or "")
        if not titulo:
            return 0.0
        total = 0.0
        for raiz in titulo:
            if raiz in self._consulta:
                total += _PESO_CONSULTA
                continue
            peso = max(
                _PESO_NOMBRE if raiz in self._nombre else 0.0,
                _PESO_EJEMPLOS if raiz in self._ejemplos else 0.0,
                _PESO_DESCRIPCION if raiz in self._descripcion else 0.0,
            )
            total += peso * self._especificidad(raiz)
        return total / len(titulo)


# ---------- Ronda 102, C2: título para fragmentos sin título de sección ----------

_ENCABEZADO_MD = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")


def _sin_encabezado_yaml(lineas: list[str]) -> list[str]:
    """Quita el bloque YAML inicial ("---" ... "---" o "...") si el texto
    empieza con él. Sin cierre, no se considera YAML y se deja igual."""
    inicio = 0
    while inicio < len(lineas) and not lineas[inicio].strip():
        inicio += 1
    if inicio >= len(lineas) or lineas[inicio].strip() != "---":
        return lineas[inicio:]
    for fin in range(inicio + 1, len(lineas)):
        if lineas[fin].strip() in ("---", "..."):
            return lineas[fin + 1:]
    return lineas[inicio:]


def first_markdown_heading(text: str | None) -> str | None:
    """Primer encabezado Markdown ATX ("# Título" ... "###### Título") del
    texto, fuera del encabezado YAML inicial. None si no hay ninguno."""
    for linea in _sin_encabezado_yaml((text or "").split("\n")):
        coincidencia = _ENCABEZADO_MD.match(linea)
        if coincidencia and coincidencia.group(1).strip():
            return coincidencia.group(1).strip()
    return None


def affinity_title(section_title: str | None, text: str | None, source_title: str | None) -> str:
    """Título con el que se mide la afinidad de un fragmento: su título de
    sección (por_encabezado lo guarda); si no tiene, su primer encabezado
    Markdown; si tampoco, el título de la fuente (sin extensión de
    archivo). Cadena vacía si no hay nada (afinidad cero)."""
    if section_title and section_title.strip():
        return section_title.strip()
    encabezado = first_markdown_heading(text)
    if encabezado:
        return encabezado
    titulo = (source_title or "").strip()
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", titulo)


# ---------- Ronda 102, C1: combinar afinidad y recuperación ----------

RRF_K = 60
"""Mismo k de la fusión RRF de la búsqueda híbrida (application.rag.
queries.hybrid_search)."""


def combine_with_retrieval(affinities: list[float], k: int = RRF_K) -> list[int]:
    """Orden final de candidatos que ya vienen ordenados por la búsqueda
    (posición i -> puesto i+1), combinando por RRF dos listas:
    - el orden de la búsqueda (todos los candidatos);
    - el orden por afinidad (solo los candidatos con afinidad > 0; los
      empatados comparten puesto, valores redondeados a 3 decimales).

    puntaje = 1/(k + puesto_búsqueda) + 1/(k + puesto_afinidad)

    A igual puntaje se conserva el orden de la búsqueda. Devuelve los
    índices de `affinities` en el orden final."""
    valores = sorted({round(a, 3) for a in affinities if a > 0}, reverse=True)
    puesto_afinidad = {valor: n + 1 for n, valor in enumerate(valores)}

    def puntaje(i: int) -> float:
        total = 1.0 / (k + i + 1)
        valor = round(affinities[i], 3)
        if valor in puesto_afinidad:
            total += 1.0 / (k + puesto_afinidad[valor])
        return total

    return sorted(range(len(affinities)), key=lambda i: (-puntaje(i), i))
