"""Ronda 104b -- PROTOTIPO fiel al diseño propuesto de las correcciones Y y
R (no modifica el motor; es la referencia para la implementación).

Y  Un fragmento sin texto fuera del encabezado YAML no tiene título para la
   afinidad (afinidad 0), en vez de tomar el título de la fuente (efecto
   lateral de C2, Ronda 102).

R  Resolución de referencias entre fuentes, de UN nivel:
   1. Detección. Un candidato "remite" a otra fuente si su texto (sin YAML)
      menciona el título registrado de esa fuente con extensión
      ("requisitos_ingreso.md") o su raíz si tiene forma de identificador
      (sin espacios, con "_" o "-", >= 6 caracteres). Coincidencia sin
      distinguir mayúsculas y con límites de palabra.
      - Fuente propia: se ignora.
      - Nombre que corresponde a más de una fuente: AMBIGUA, no se resuelve
        (queda en la traza).
      - Nombre que no corresponde a ninguna fuente: no hace nada.
   2. Puente. Solo se trata como puente un candidato CORTO (<= 80 palabras
      sin YAML) que remite al menos a una fuente. Un fragmento largo que cita
      otro documento tiene contenido propio y no se toca.
   3. Destino. Para cada fuente referida se toma el MEJOR candidato de esa
      fuente que ya esté en el conjunto de candidatos de la búsqueda (modo
      "pool", recomendado) -- o, en modo "busqueda", el mejor de una búsqueda
      acotada a esa fuente -- que tenga contenido (>= 5 palabras fuera de
      YAML y encabezados) y que no sea a su vez un puente. Así:
      - filtros de metadatos, vigencia/validación y nivel de acceso son los
        de la búsqueda original (el destino nunca viene de otra parte);
      - no hay recursión: los destinos no se examinan en busca de nuevas
        referencias, y un puente nunca es destino (sin ciclos A->B->A).
      - como máximo MAX_DESTINOS destinos por consulta, en el orden de los
        puentes en la búsqueda.
   4. Orden. El destino se coloca inmediatamente antes de su puente en la
      lista de la búsqueda (hereda su puesto); luego se aplica la afinidad
      (RRF, Ronda 102) y, al final, una pasada de RESTRICCIÓN garantiza que
      en el resultado final cada destino quede por delante de su puente
      (si el puente entra en el top `limit`, su destino también).
   5. Traza: destino -> (puente, fuente del puente); referencias ambiguas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

MAX_PALABRAS_PUENTE = 80
MIN_PALABRAS_CONTENIDO = 5
MAX_DESTINOS = 3
MAX_POR_FUENTE = 1
"""Destinos por fuente referida (2 = también el segundo mejor fragmento de
esa fuente; útil si el documento referido está fragmentado por encabezado)."""

_PALABRA = re.compile(r"\w+", re.UNICODE)
_ENCABEZADO = re.compile(r"^\s{0,3}#{1,6}\s")


def _sin_yaml(texto: str) -> list[str]:
    lineas = (texto or "").split("\n")
    i = 0
    while i < len(lineas) and not lineas[i].strip():
        i += 1
    if i < len(lineas) and lineas[i].strip() == "---":
        for j in range(i + 1, len(lineas)):
            if lineas[j].strip() in ("---", "..."):
                return lineas[j + 1:]
    return lineas[i:]


def palabras_sin_yaml(texto: str) -> int:
    return len(_PALABRA.findall("\n".join(_sin_yaml(texto))))


def palabras_de_contenido(texto: str) -> int:
    return len(_PALABRA.findall("\n".join(linea for linea in _sin_yaml(texto) if not _ENCABEZADO.match(linea))))


def solo_yaml(texto: str) -> bool:
    return palabras_sin_yaml(texto) == 0


def nombres_de_fuente(titulo: str) -> list[str]:
    titulo = (titulo or "").strip().lower()
    if not titulo:
        return []
    nombres = [titulo]
    raiz = re.sub(r"\.[a-z0-9]{1,5}$", "", titulo)
    if raiz != titulo and " " not in raiz and len(raiz) >= 6 and re.search(r"[_\-]", raiz):
        nombres.append(raiz)
    return nombres


def indice_de_nombres(fuentes: dict[str, str]) -> dict[str, set[str]]:
    """nombre -> ids de fuente (más de uno = ambiguo)."""
    indice: dict[str, set[str]] = {}
    for source_id, titulo in fuentes.items():
        for nombre in nombres_de_fuente(titulo):
            indice.setdefault(nombre, set()).add(source_id)
    return indice


def detectar_referencias(texto: str, propia: str, indice: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """(fuentes referidas sin ambigüedad, en orden de aparición; nombres ambiguos)."""
    cuerpo = "\n".join(_sin_yaml(texto)).lower()
    encontradas: list[tuple[int, str]] = []
    ambiguas: list[str] = []
    for nombre, ids in indice.items():
        m = re.search(r"(?<![\w.])" + re.escape(nombre) + r"(?![\w])", cuerpo)
        if not m:
            continue
        otras = ids - {propia}
        if len(otras) > 1:
            ambiguas.append(nombre)
        elif len(otras) == 1:
            encontradas.append((m.start(), next(iter(otras))))
    orden: list[str] = []
    for _, sid in sorted(encontradas):
        if sid not in orden:
            orden.append(sid)
    return orden, sorted(set(ambiguas))


@dataclass
class ResultadoReferencias:
    candidatos: list  # SemanticSearchResult en orden de búsqueda, con destinos insertados
    enlaces: dict[str, list[str]] = field(default_factory=dict)  # chunk destino -> chunks puente
    ambiguas: list[str] = field(default_factory=list)


def resolver_referencias(
    candidatos: list, fuentes_permitidas: dict[str, str], *,
    modo: str = "pool", buscar_en_fuente: Optional[Callable[[str], list]] = None,
) -> ResultadoReferencias:
    """candidatos: resultados de la búsqueda (ya filtrados). fuentes_permitidas:
    id -> título de las fuentes que la búsqueda podía devolver (filtros)."""
    indice = indice_de_nombres(fuentes_permitidas)
    es_puente: dict[str, list[str]] = {}
    ambiguas: set[str] = set()
    for r in candidatos:
        if palabras_sin_yaml(r.chunk.text) > MAX_PALABRAS_PUENTE:
            continue
        refs, amb = detectar_referencias(r.chunk.text, r.chunk.source_id, indice)
        ambiguas.update(amb)
        if refs:
            es_puente[r.chunk.id] = refs

    def destino_valido(r) -> bool:
        return r.chunk.id not in es_puente and palabras_de_contenido(r.chunk.text) >= MIN_PALABRAS_CONTENIDO

    mejores_por_fuente: dict[str, list] = {}
    for r in candidatos:
        lista = mejores_por_fuente.setdefault(r.chunk.source_id, [])
        if destino_valido(r) and len(lista) < MAX_POR_FUENTE:
            lista.append(r)

    salida: list = []
    enlaces: dict[str, list[str]] = {}
    usados: set[str] = set()
    for r in candidatos:
        for sid in es_puente.get(r.chunk.id, []):
            destinos = mejores_por_fuente.get(sid) or []
            if not destinos and modo == "busqueda" and buscar_en_fuente is not None:
                destinos = [d for d in buscar_en_fuente(sid) if destino_valido(d)][:MAX_POR_FUENTE]
                mejores_por_fuente[sid] = destinos
            for destino in destinos:
                if destino.chunk.id in enlaces:
                    enlaces[destino.chunk.id].append(r.chunk.id)
                    continue
                if len(enlaces) >= MAX_DESTINOS:
                    continue
                enlaces[destino.chunk.id] = [r.chunk.id]
                if destino.chunk.id not in usados:
                    salida.append(destino)
                    usados.add(destino.chunk.id)
        if r.chunk.id not in usados:
            salida.append(r)
            usados.add(r.chunk.id)
    return ResultadoReferencias(salida, enlaces, sorted(ambiguas))


def aplicar_restriccion(orden: list[str], enlaces: dict[str, list[str]]) -> list[str]:
    """Cada destino por delante de TODOS sus puentes: si está detrás del
    primero de ellos, se mueve justo antes de ese puente."""
    orden = list(orden)
    for destino, puentes in enlaces.items():
        presentes = [orden.index(p) for p in puentes if p in orden]
        if destino not in orden or not presentes:
            continue
        primero = min(presentes)
        if orden.index(destino) > primero:
            orden.remove(destino)
            orden.insert(primero, destino)
    return orden
