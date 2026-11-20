"""Ronda 106 (autorizada por NEXOM), componente R: resolución de referencias
entre fuentes ("fragmentos puente").

Problema (Rondas 102, 104 y 105, hallazgos reales en AGENTE UDL): un
fragmento corto que solo remite a otro documento ("Para evitar duplicación,
consultar requisitos_ingreso.md") puede quedar por delante del contenido del
documento al que remite. Con la afinidad ponderada por valor (componente V,
section_affinity.combine_by_value), una sección puente con el título exacto
de la intención volvería a superar al documento referido: la regresión
sintética de la Ronda 102. Por eso R opera siempre junto con V (procedimiento
r106, ver retrieval_procedure.py).

Diseño de la Ronda 104b (prototipo_referencias.py), con los ajustes medidos
en las Rondas 105c a 105f:

1. Detección. Un candidato "remite" a otra fuente si su texto (sin el
   encabezado YAML) menciona el título registrado de esa fuente CON
   extensión ("requisitos_ingreso.md") o su raíz si tiene forma de
   identificador (sin espacios, con "_" o "-", >= 6 caracteres).
   Coincidencia sin distinguir mayúsculas y con límites de palabra. Un
   título sin extensión ni forma de identificador ("Información general")
   no cuenta (ajuste de la Ronda 105).
   - Fuente propia: se ignora.
   - Nombre de más de una fuente: AMBIGUO, no se resuelve (queda en la traza).
   - Nombre que no corresponde a ninguna fuente permitida: no hace nada.
2. Puente. Solo un candidato CORTO (<= 80 palabras sin YAML) que remite al
   menos a una fuente. Un fragmento largo que cita otro documento tiene
   contenido propio y no se toca.
3. Destino. Para cada fuente referida, los MAX_POR_FUENTE mejores candidatos
   de esa fuente que ya estén en el conjunto de la búsqueda (modo "pool"),
   con contenido (>= 5 palabras fuera de YAML y encabezados) y que no sean a
   su vez puentes. Así:
   - filtros de metadatos, vigencia/validación y nivel de acceso son los de
     la búsqueda original (un destino nunca viene de otra parte);
   - no hay recursión (los destinos no se examinan) y un puente nunca es
     destino: no hay ciclos;
   - como máximo MAX_DESTINOS destinos por consulta.
4. Orden. Cada destino se inserta inmediatamente antes de su puente (hereda
   su puesto); después se aplica la afinidad y, al final, la RESTRICCIÓN
   (`enforce_destinations_first`): cada destino queda por delante de todos
   sus puentes, de modo que si un puente entra en el resultado entregado, su
   destino también.
5. Traza: destino -> puentes; nombres ambiguos.

Sin reglas por nombre de documento, programa ni proyecto.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

MAX_PALABRAS_PUENTE = 80
MIN_PALABRAS_CONTENIDO = 5
MAX_POR_FUENTE = 2
"""Destinos por fuente referida (Ronda 104b, variante YR2; medido en 105c-f)."""
MAX_DESTINOS = 5
"""Destinos por consulta."""

_PALABRA = re.compile(r"\w+", re.UNICODE)
_ENCABEZADO = re.compile(r"^\s{0,3}#{1,6}\s")
_EXTENSION = re.compile(r"\.[a-z0-9]{1,5}$")


def lines_without_yaml(text: str | None) -> list[str]:
    """Líneas del texto sin el encabezado YAML inicial ("---" ... "---" o
    "..."). Sin cierre no se considera YAML."""
    lineas = (text or "").split("\n")
    i = 0
    while i < len(lineas) and not lineas[i].strip():
        i += 1
    if i < len(lineas) and lineas[i].strip() == "---":
        for j in range(i + 1, len(lineas)):
            if lineas[j].strip() in ("---", "..."):
                return lineas[j + 1:]
    return lineas[i:]


def words_without_yaml(text: str | None) -> int:
    return len(_PALABRA.findall("\n".join(lines_without_yaml(text))))


def content_words(text: str | None) -> int:
    """Palabras fuera del YAML y de las líneas de encabezado Markdown."""
    return len(_PALABRA.findall(
        "\n".join(linea for linea in lines_without_yaml(text) if not _ENCABEZADO.match(linea))
    ))


def is_yaml_only(text: str | None) -> bool:
    """True si el fragmento no tiene ninguna palabra fuera del encabezado YAML
    (componente Y: un fragmento así no recibe afinidad)."""
    return words_without_yaml(text) == 0


def source_names(title: str | None) -> list[str]:
    """Nombres con los que un texto puede referirse a una fuente: su título
    registrado si tiene extensión ("requisitos_ingreso.md") y su raíz si tiene
    forma de identificador ("requisitos_ingreso")."""
    titulo = (title or "").strip().lower()
    if not titulo:
        return []
    nombres = [titulo]
    raiz = _EXTENSION.sub("", titulo)
    if raiz != titulo and " " not in raiz and len(raiz) >= 6 and re.search(r"[_\-]", raiz):
        nombres.append(raiz)
    # Ajuste de la Ronda 105: un título sin extensión ni forma de
    # identificador no cuenta como referencia.
    return [n for n in nombres if _EXTENSION.search(n) or re.search(r"[_\-]", n)]


def names_index(sources: Mapping[str, str]) -> dict[str, set[str]]:
    """nombre -> ids de fuente (más de uno = ambiguo)."""
    indice: dict[str, set[str]] = {}
    for source_id, titulo in sources.items():
        for nombre in source_names(titulo):
            indice.setdefault(nombre, set()).add(source_id)
    return indice


def detect_references(text: str | None, own_source_id: str, index: Mapping[str, set[str]]) -> tuple[list[str], list[str]]:
    """(fuentes referidas sin ambigüedad, en orden de aparición; nombres ambiguos)."""
    cuerpo = "\n".join(lines_without_yaml(text)).lower()
    encontradas: list[tuple[int, str]] = []
    ambiguas: list[str] = []
    for nombre, ids in index.items():
        coincidencia = re.search(r"(?<![\w.])" + re.escape(nombre) + r"(?![\w])", cuerpo)
        if not coincidencia:
            continue
        otras = ids - {own_source_id}
        if len(otras) > 1:
            ambiguas.append(nombre)
        elif len(otras) == 1:
            encontradas.append((coincidencia.start(), next(iter(otras))))
    orden: list[str] = []
    for _, source_id in sorted(encontradas):
        if source_id not in orden:
            orden.append(source_id)
    return orden, sorted(set(ambiguas))


@dataclass
class ReferenceResolution:
    candidates: list[Any]
    """Resultados en orden de búsqueda, con los destinos insertados antes de
    su primer puente (sin duplicados)."""
    links: dict[str, list[str]] = field(default_factory=dict)
    """chunk_id destino -> chunk_ids de los puentes que lo trajeron."""
    ambiguous: list[str] = field(default_factory=list)
    """Nombres de fuente mencionados que corresponden a más de una fuente."""


def resolve_references(
    candidates: Sequence[Any], permitted_sources: Mapping[str, str], *,
    max_per_source: int = MAX_POR_FUENTE, max_destinations: int = MAX_DESTINOS,
) -> ReferenceResolution:
    """candidates: resultados de la búsqueda ya filtrada (objetos con
    `.chunk.id`, `.chunk.source_id`, `.chunk.text`), en orden de búsqueda.
    permitted_sources: id -> título de las fuentes que la búsqueda podía
    devolver (las que cumplen los filtros)."""
    indice = names_index(permitted_sources)
    puentes: dict[str, list[str]] = {}
    ambiguas: set[str] = set()
    for resultado in candidates:
        if words_without_yaml(resultado.chunk.text) > MAX_PALABRAS_PUENTE:
            continue
        referidas, ambiguos = detect_references(resultado.chunk.text, resultado.chunk.source_id, indice)
        ambiguas.update(ambiguos)
        if referidas:
            puentes[resultado.chunk.id] = referidas

    def destino_valido(resultado: Any) -> bool:
        return resultado.chunk.id not in puentes and content_words(resultado.chunk.text) >= MIN_PALABRAS_CONTENIDO

    mejores: dict[str, list[Any]] = {}
    for resultado in candidates:
        lista = mejores.setdefault(resultado.chunk.source_id, [])
        if destino_valido(resultado) and len(lista) < max_per_source:
            lista.append(resultado)

    salida: list[Any] = []
    enlaces: dict[str, list[str]] = {}
    usados: set[str] = set()
    for resultado in candidates:
        for source_id in puentes.get(resultado.chunk.id, []):
            for destino in mejores.get(source_id) or []:
                if destino.chunk.id in enlaces:
                    enlaces[destino.chunk.id].append(resultado.chunk.id)
                    continue
                if len(enlaces) >= max_destinations:
                    continue
                enlaces[destino.chunk.id] = [resultado.chunk.id]
                if destino.chunk.id not in usados:
                    salida.append(destino)
                    usados.add(destino.chunk.id)
        if resultado.chunk.id not in usados:
            salida.append(resultado)
            usados.add(resultado.chunk.id)
    return ReferenceResolution(salida, enlaces, sorted(ambiguas))


def enforce_destinations_first(order: Sequence[str], links: Mapping[str, list[str]]) -> list[str]:
    """Restricción final: cada destino por delante de TODOS sus puentes. Si
    está detrás del primero de ellos, se mueve justo antes de ese puente. Si
    ningún puente está en `order`, no se mueve nada."""
    orden = list(order)
    for destino, puentes in links.items():
        presentes = [orden.index(p) for p in puentes if p in orden]
        if destino not in orden or not presentes:
            continue
        primero = min(presentes)
        if orden.index(destino) > primero:
            orden.remove(destino)
            orden.insert(primero, destino)
    return orden
