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
