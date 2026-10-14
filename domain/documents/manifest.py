"""Reglas puras del contrato de manifiesto de entrega de RAG CONTENT
STUDIO (ver docs proyecto/CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md,
la fuente unica de verdad de este formato -- este modulo solo implementa
lo que ese documento especifica, no inventa reglas nuevas).

Incidencia real que origina este modulo (2026-09-29): un lote procesado
en RAG Content Studio en Windows se copio a un equipo macOS: RAG Studio
reporto "Importadas: 0 / Omitidas: 13" porque el manifiesto traia la
ruta absoluta completa del equipo productor (con backslashes) en
`ruta_archivo`, y `pathlib.Path(...).name` no la interpreta como tal en
un sistema POSIX (no reconoce "\\" como separador ajeno). La correccion
formaliza dos resolutores segun la version del manifiesto (columna
`manifest_schema_version`):

- V2 (version == "2"): `ruta_archivo` es una ruta relativa POSIX al
  paquete, validada aqui de forma estricta (nunca absoluta, nunca con
  "..", nunca con "\\") -- mismo patron de defensa que
  `domain.projects.packaging.FileEntry._relative_path_debe_ser_segura`
  usa para los paquetes `.agentproj` (Zip Slip, auditoria Ronda 46),
  pero como funcion independiente: este modulo no importa
  `domain.projects` a proposito (los dos contextos no deben acoplarse
  solo porque comparten un patron de validacion).
- V1 / legado (columna ausente o vacia): `ruta_archivo` puede ser una
  ruta absoluta del equipo productor, con cualquier separador -- solo
  se usa su ultimo segmento (nombre de archivo), extraido sin depender
  de en que sistema operativo corre ESTE proceso.

Todo lo de aqui es puro (sin tocar disco): la resolucion real contra el
sistema de archivos (buscar candidatos, verificar existencia, calcular
hash) vive en `application.documents.commands.register_sources_from_folder`,
que si puede leer disco (mismo criterio que ese mismo caso de uso ya
aplicaba antes de esta correccion: `Path(folder_path)`, `.is_file()`)."""
from __future__ import annotations

import re

_PATRON_SEPARADOR_MULTIPLATAFORMA = re.compile(r"[\\/]+")

VERSION_ESQUEMA_V2 = "2"
"""Valor de la columna `manifest_schema_version` que identifica un
manifiesto en el contrato portable nuevo. Cualquier otro valor --
incluida su ausencia o una cadena vacia -- se trata como legado (V1)."""


class RutaManifiestoInsegura(ValueError):
    """`ruta_archivo` de una fila V2 no es una ruta relativa segura
    dentro del paquete (ver CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md,
    seccion 5) -- puede ser absoluta, usar "\\" como separador, o
    contener un segmento de escape "..". Nunca se intenta adivinar o
    corregir la ruta: se rechaza con diagnostico explicito."""


def es_manifiesto_v2(version_declarada: str | None) -> bool:
    """`version_declarada` es el valor crudo de la columna
    `manifest_schema_version` de una fila (puede venir `None` si la
    columna no existe en el CSV -- manifiesto legado sin ninguna fila
    con esa columna, o `""` si la columna existe pero la fila la dejo
    vacia). Ambos casos son legado (V1); solo `"2"` exacto es V2."""
    return (version_declarada or "").strip() == VERSION_ESQUEMA_V2


def validar_ruta_relativa_manifiesto(ruta_archivo: str) -> str:
    """Valida que `ruta_archivo` (columna del manifiesto V2) sea una
    ruta relativa POSIX segura dentro del paquete. Devuelve la misma
    cadena si es valida; lanza `RutaManifiestoInsegura` si no.

    Reglas (ver seccion 5 del contrato):
    1. no vacia:
    2. sin "\\" (solo "/" es separador valido en V2);
    3. no absoluta (no empieza con "/" ni "~", ni con unidad de Windows
       "X:");
    4. sin ningun segmento "..".
    """
    if not ruta_archivo or not ruta_archivo.strip():
        raise RutaManifiestoInsegura("ruta_archivo no puede estar vacío.")
    if "\\" in ruta_archivo:
        raise RutaManifiestoInsegura(
            f"ruta_archivo {ruta_archivo!r} usa '\\\\' -- un manifiesto v2 solo acepta '/' como separador."
        )
    if ruta_archivo.startswith("/") or ruta_archivo.startswith("~"):
        raise RutaManifiestoInsegura(f"ruta_archivo {ruta_archivo!r} no puede ser una ruta absoluta.")
    if len(ruta_archivo) >= 2 and ruta_archivo[1] == ":":  # unidad de Windows, p. ej. "C:/..."
        raise RutaManifiestoInsegura(f"ruta_archivo {ruta_archivo!r} no puede ser una ruta absoluta.")
    if any(segmento == ".." for segmento in ruta_archivo.split("/")):
        raise RutaManifiestoInsegura(
            f"ruta_archivo {ruta_archivo!r} no puede contener un segmento '..' (path traversal)."
        )
    return ruta_archivo


def extraer_nombre_base_multiplataforma(ruta_archivo: str) -> str:
    """Ultimo segmento no vacio de `ruta_archivo` (columna del
    manifiesto V1/legado), reconociendo TANTO "/" como "\\" como
    separador -- a proposito NO usa `pathlib.Path(...).name`: ese
    metodo solo reconoce el separador nativo del sistema operativo
    donde corre el proceso que lo llama, nunca el del equipo que
    origino la ruta (por eso `Path("C:\\Users\\...\\doc.md").name`
    devuelve la cadena completa sin cambios en un sistema POSIX -- la
    causa raiz exacta de la incidencia real que origina este modulo).

    Devuelve cadena vacia si `ruta_archivo` no tiene ningun segmento
    aprovechable (vacia, o solo separadores) -- quien llama debe tratar
    eso como "no se pudo resolver", nunca como un nombre de archivo
    valido."""
    segmentos = [s for s in _PATRON_SEPARADOR_MULTIPLATAFORMA.split(ruta_archivo.strip()) if s]
    return segmentos[-1] if segmentos else ""
