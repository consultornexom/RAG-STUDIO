"""Caso de uso: importar en bloque las fuentes que RAG CONTENT STUDIO
deja listas en su carpeta de entrega (Validacion_observaciones_RAG_STUDIO.md,
punto 2 -- "que RAG STUDIO reciba los .md ya generados eligiendo la
carpeta del proyecto en vez de archivos sueltos").

Contrato v2 (2026-09-29, incidencia real de portabilidad -- ver
docs proyecto/CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md, la
fuente unica de verdad de este formato): un lote procesado en Windows
se copio a un equipo macOS y esta importacion reporto "Importadas: 0 /
Omitidas: 13" con los 13 .md fisicamente presentes en la carpeta de
entrega -- `ruta_archivo` traia la ruta absoluta completa del equipo
productor, y `Path(ruta_archivo).name` (la version anterior de este
comando) no la interpretaba como tal en un sistema POSIX. Este comando
ahora reconoce dos formatos, decididos fila por fila por la columna
`manifest_schema_version`:

- **V2** (`manifest_schema_version` == "2"): `ruta_archivo` es una ruta
  relativa POSIX al paquete, validada estrictamente
  (`domain.documents.manifest.validar_ruta_relativa_manifiesto`) --
  nunca absoluta, nunca con "..", nunca con "\\". Se resuelve de forma
  directa (`carpeta / ruta_archivo`) con una comprobacion de contencion
  fisica antes de leer el archivo (mismo patron de defensa en
  profundidad que `domain.projects.packaging`/`infrastructure.
  filesystem.packager` usan para los paquetes `.agentproj`, Zip Slip).
- **V1 / legado** (columna ausente o vacia, manifiestos generados antes
  de esta correccion): `ruta_archivo` puede traer la ruta absoluta del
  equipo productor con cualquier separador. Se extrae solo su nombre de
  archivo (`domain.documents.manifest.extraer_nombre_base_
  multiplataforma`, que reconoce "/" y "\\" sin depender de en que
  sistema operativo corre este proceso) y se busca ese nombre dentro de
  la carpeta importada -- 0 coincidencias se rechaza, mas de 1 se
  rechaza como ambiguo (nunca se elige la primera en silencio).

En ambos formatos, antes de registrar cualquier fila se verifica
`hash_contenido` (si viene declarado) contra el SHA-256 real del
archivo encontrado -- localizar un archivo con el nombre correcto ya no
basta para importarlo si su contenido no coincide con lo declarado en
el manifiesto (antes, `content_hash` solo se usaba para deduplicar,
nunca para verificar integridad). Tambien se detecta ambiguedad
CRUZADA entre filas: si dos filas distintas resuelven al mismo archivo
fisico con un `hash_contenido` declarado distinto, ninguna de las dos
se importa.

Dos detalles adicionales de formato que siguen aplicando igual que
antes:
- `autoridad_fuente` hoy siempre viaja vacío (RAG CONTENT todavía no
  lo calcula) y `nivel_acceso` es texto libre de su lado (viene de un
  campo de metadatos, no de un enum) -- puede no coincidir con los
  valores de `AccessLevel` de aquí. Ningún valor no reconocido debe
  bloquear la importación completa; se resuelve con un valor por
  defecto conservador y se sigue con las demás filas.
- El manifiesto no trae ninguna columna de tipo de documento (Ronda 3
  de Validacion_observaciones_RAG_STUDIO.md, punto 12): sin esto, un
  lote importado quedaba siempre en document_type_code="default",
  mezclando otra vez tipos de fuente distintos (p. ej. "contactos" y
  "requisitos de admisión") tal como antes de resolver el punto 10.
  Por eso execute() recibe un `document_type_code` único para todo el
  lote -- quien importa decide con qué tipo se etiquetan las fuentes
  de esa carpeta (una carpeta de entrega de RAG CONTENT suele
  corresponder a un solo tipo documental). Si más adelante RAG CONTENT
  agrega una columna de tipo al manifiesto, ese valor por fila debería
  tener prioridad sobre este parámetro de lote.

Reutiliza RegisterSource.execute() fila por fila (mismo mecanismo de
deduplicación por content_hash que ya usa el alta manual desde la UI:
DuplicateSourceError) en vez de escribir el repositorio directo, para
no duplicar las reglas de negocio de "qué es una fuente válida"."""
from __future__ import annotations

import csv
import glob
import hashlib
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from domain.documents.entities import AccessLevel, SourceType
from domain.documents.exceptions import DuplicateSourceError
from domain.documents.import_batch import (
    BatchRelation,
    ImportBatchRecord,
    ImportBatchRow,
    batch_fingerprint,
    classify_batch,
    nombre_logico,
)
from domain.documents.manifest import (
    RutaManifiestoInsegura,
    es_manifiesto_v2,
    extraer_nombre_base_multiplataforma,
    validar_ruta_relativa_manifiesto,
)

from domain.documents.ports import ImportBatchLedger

from .register_source import RegisterSource

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifiesto.csv"


@dataclass
class ImportedSourceRow:
    title: str
    source_id: str


@dataclass
class SkippedSourceRow:
    title: str
    reason: str


_MOTIVO_DUPLICADO = "ya estaba registrada (mismo contenido)"

_DESCRIPCION_RELACION = {
    BatchRelation.NUEVO: "lote nuevo en este proyecto",
    BatchRelation.REIMPORTACION: "reimportación idéntica de un lote ya importado (no se duplicó nada)",
    BatchRelation.NUEVA_VERSION: "versión nueva de un lote ya importado (hay documentos con contenido distinto)",
    BatchRelation.AMPLIACION: "comparte documentos idénticos con un lote ya importado",
}


@dataclass
class ImportSourcesFromFolderResult:
    imported: list[ImportedSourceRow] = field(default_factory=list)
    skipped: list[SkippedSourceRow] = field(default_factory=list)
    batch_fingerprint: Optional[str] = None
    """Ronda 92: huella portable del lote (ver domain.documents.import_batch)."""
    batch_label: Optional[str] = None
    batch_relation: Optional[BatchRelation] = None
    related_batch_label: Optional[str] = None

    @property
    def batch_summary(self) -> Optional[str]:
        if self.batch_relation is None:
            return None
        texto = f"Lote '{self.batch_label}': {_DESCRIPCION_RELACION[self.batch_relation]}"
        if self.related_batch_label:
            texto += f" (lote anterior: '{self.related_batch_label}')"
        if self.batch_relation == BatchRelation.NUEVA_VERSION:
            texto += (
                ". Las fuentes del lote anterior siguen activas: si esta versión las reemplaza, "
                "márcalo con 'Sustituye a' en cada fuente nueva"
            )
        return texto + "."

    @property
    def imported_count(self) -> int:
        return len(self.imported)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def _parse_date(value: Optional[str]) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_authority(value: Optional[str]) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed or None


def _map_access_level(value: Optional[str]) -> AccessLevel:
    value = (value or "").strip().lower()
    for level in AccessLevel:
        if level.value == value:
            return level
    # nivel_acceso llega como texto libre desde RAG CONTENT (metadato
    # "nivel_confidencialidad", sin vocabulario compartido con
    # AccessLevel de aquí) -- ante un valor vacío o no reconocido se
    # usa INTERNO como default conservador (nunca PUBLICO en silencio)
    # y queda a criterio del usuario revisarlo/editarlo después.
    return AccessLevel.INTERNO


def _map_source_type(value: Optional[str]) -> SourceType:
    value = (value or "").strip().lower()
    for source_type in SourceType:
        if source_type.value == value:
            return source_type
    return SourceType.MARKDOWN  # hoy RAG CONTENT solo entrega markdown (tipo_fuente="markdown" fijo)


def _sha256_de_archivo(ruta: Path) -> str:
    """Hash real del archivo fisico -- deliberadamente distinto de
    `hash_contenido` (el valor DECLARADO por el manifiesto): comparar
    ambos es exactamente la verificacion de integridad que exige el
    contrato v2 (seccion 6)."""
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _clave_portable(ruta: str) -> str:
    """Forma comparable de un nombre/ruta entre sistemas de archivos:
    Unicode NFC (macOS guarda "í" descompuesta, NFD) y sin distinguir
    mayúsculas (Windows y macOS no las distinguen; Linux sí)."""
    return unicodedata.normalize("NFC", ruta).casefold()


def _buscar_equivalente(carpeta: Path, relativa: str) -> list[Path]:
    """Ronda 92 (portabilidad entre equipos): archivos del paquete cuya
    ruta relativa es la MISMA que `relativa` salvo forma Unicode o
    mayúsculas. Un lote creado en Windows/macOS y abierto en Linux (o
    descomprimido con otra herramienta) puede traer "Psicología.md" en
    NFD o con otra capitalización; antes eso daba "no se encontró" aunque
    el archivo estuviera ahí. La verificación de hash posterior sigue
    garantizando que es exactamente el contenido declarado."""
    buscada = _clave_portable(relativa)
    return sorted({
        p.resolve() for p in carpeta.rglob("*")
        if p.is_file() and _clave_portable(p.relative_to(carpeta).as_posix()) == buscada
    })


def _resolver_v2(ruta_cruda: str, carpeta: Path) -> tuple[Optional[Path], Optional[str]]:
    """Resuelve `ruta_archivo` de una fila V2. Devuelve `(ruta, None)`
    si se pudo resolver a un archivo real dentro del paquete, o
    `(None, motivo)` si se rechaza -- nunca lanza."""
    try:
        ruta_valida = validar_ruta_relativa_manifiesto(ruta_cruda)
    except RutaManifiestoInsegura as exc:
        return None, str(exc)
    carpeta_resuelta = carpeta.resolve()
    candidato_resuelto = (carpeta / ruta_valida).resolve()
    # Defensa en profundidad (mismo patron que infrastructure.filesystem.
    # packager.import_project() usa contra Zip Slip): aunque
    # validar_ruta_relativa_manifiesto() ya rechazo "..", una ruta
    # absoluta y separadores ajenos, se vuelve a comprobar la
    # contencion fisica tras resolver symlinks antes de leer nada.
    if candidato_resuelto != carpeta_resuelta and carpeta_resuelta not in candidato_resuelto.parents:
        return None, f"ruta_archivo {ruta_valida!r} queda fuera de la carpeta del paquete"
    if not candidato_resuelto.is_file():
        equivalentes = _buscar_equivalente(carpeta, ruta_valida)
        if len(equivalentes) == 1:
            return equivalentes[0], None
        if len(equivalentes) > 1:
            return None, f"referencia ambigua: '{ruta_valida}' coincide con más de un archivo dentro del paquete"
        return None, f"no se encontró '{ruta_valida}' dentro del paquete"
    return candidato_resuelto, None


def _resolver_legado(ruta_cruda: str, carpeta: Path) -> tuple[Optional[Path], Optional[str]]:
    """Resuelve `ruta_archivo` de una fila V1/legado (manifiestos
    generados antes de esta correccion, con ruta absoluta del equipo
    productor). Devuelve `(ruta, None)` o `(None, motivo)`, nunca
    lanza."""
    nombre = extraer_nombre_base_multiplataforma(ruta_cruda)
    if not nombre:
        return None, "el manifiesto no trae un nombre de archivo reconocible en ruta_archivo"
    # glob.escape: `nombre` viene de un CSV externo -- si alguna vez
    # trajera caracteres especiales de glob ("*", "?", "[...]"), no
    # deben interpretarse como comodines.
    candidatos = sorted({p.resolve() for p in carpeta.rglob(glob.escape(nombre)) if p.is_file()})
    if not candidatos:
        clave = _clave_portable(nombre)
        candidatos = sorted({
            p.resolve() for p in carpeta.rglob("*") if p.is_file() and _clave_portable(p.name) == clave
        })
    if not candidatos:
        return None, f"no se encontró '{nombre}' dentro del paquete"
    if len(candidatos) > 1:
        return None, f"referencia ambigua: '{nombre}' coincide con más de un archivo dentro del paquete"
    return candidatos[0], None


_COLUMNA_OBLIGATORIA = "ruta_archivo"


def _leer_manifiesto(manifest_path: Path) -> list[dict[str, str]]:
    """Lee manifiesto.csv con diagnóstico claro (Ronda 92):
    - "utf-8-sig" (auditoría 2026-09-30): Excel agrega BOM al guardar.
    - Si no es UTF-8 (p. ej. guardado con Excel como "CSV" ANSI/Windows-1252
      en otro equipo), antes la importación terminaba con un error crudo de
      decodificación; ahora se explica la causa.
    - Excel en configuración regional en español guarda con ";" como
      separador; antes todas las filas se omitían con "el manifiesto no
      trae ruta_archivo". Se detecta el separador por el encabezado."""
    datos = manifest_path.read_bytes()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"'{manifest_path.name}' no está en UTF-8 (byte inválido en la posición {exc.start}). "
            "Probablemente se abrió y guardó con otro programa en otro equipo; vuelve a tomarlo de la "
            "entrega original de RAG CONTENT (sin editarlo) o guárdalo como 'CSV UTF-8'."
        ) from exc
    primera_linea = texto.split("\n", 1)[0]
    separador = ";" if primera_linea.count(";") > primera_linea.count(",") else ","
    filas = list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador))
    columnas = {(c or "").strip() for c in (filas[0].keys() if filas else [])}
    if filas and _COLUMNA_OBLIGATORIA not in columnas:
        raise ValueError(
            f"'{manifest_path.name}' no tiene la columna '{_COLUMNA_OBLIGATORIA}' (columnas leídas: "
            f"{', '.join(sorted(c for c in columnas if c)) or 'ninguna'}). No parece un manifiesto de "
            "entrega de RAG CONTENT."
        )
    return filas


_PATRON_VERSION_CARPETA = re.compile(r"^v\d+$", re.IGNORECASE)


def _etiqueta_lote(folder: Path) -> str:
    """Etiqueta legible (no es identidad): "<lote>/vN" si la carpeta es una
    versión de entrega por lote de RAG CONTENT, o el nombre de la carpeta."""
    if _PATRON_VERSION_CARPETA.match(folder.name) and folder.parent.name:
        return f"{folder.parent.name}/{folder.name}"
    return folder.name or str(folder)


class RegisterSourcesFromFolder:
    """Recorre una carpeta de entrega de RAG CONTENT STUDIO
    (manifiesto.csv + los .md que referencia) y da de alta una fuente
    por cada fila, saltando las que ya existan en el proyecto (mismo
    contenido), no se puedan resolver a un archivo real, o cuyo
    contenido no coincida con el hash declarado."""

    def __init__(self, register_source: RegisterSource, batch_ledger: Optional[ImportBatchLedger] = None):
        self._register_source = register_source
        self._batch_ledger = batch_ledger

    def execute(
        self, project_id: str, folder_path: str, document_type_code: str = "default",
    ) -> ImportSourcesFromFolderResult:
        folder = Path(folder_path)
        manifest_path = folder / MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"No se encontró '{MANIFEST_FILENAME}' en '{folder_path}'. Verifica que sea la carpeta "
                "14_entrega_rag_studio del proyecto de RAG CONTENT STUDIO."
            )

        # "utf-8-sig" (auditoria 2026-09-30): si el operador abre y guarda
        # el manifiesto con Excel, se agrega un BOM y la primera columna
        # pasaba a llamarse "\ufeffmanifest_schema_version" -- todas las
        # filas se trataban en silencio como legado (V1).
        filas = _leer_manifiesto(manifest_path)

        # Fase 1: resolver, para cada fila, el archivo candidato dentro
        # del paquete -- sin tocar el repositorio todavia. `None` en la
        # ruta significa "no se pudo resolver" (ver `motivo`).
        resoluciones: list[tuple[Optional[Path], Optional[str]]] = []
        for row in filas:
            ruta_cruda = (row.get("ruta_archivo") or "").strip()
            if not ruta_cruda:
                resoluciones.append((None, "el manifiesto no trae ruta_archivo"))
                continue
            if es_manifiesto_v2(row.get("manifest_schema_version")):
                resoluciones.append(_resolver_v2(ruta_cruda, folder))
            else:
                resoluciones.append(_resolver_legado(ruta_cruda, folder))

        # Fase 2: ambigüedad CRUZADA entre filas -- dos o más filas que
        # resuelven al MISMO archivo físico con un hash_contenido
        # declarado distinto no deben importarse (ninguna de las dos):
        # no hay forma segura de saber cuál descripción es la correcta.
        # Si el hash declarado coincide entre ellas, no es una
        # ambigüedad real -- es la deduplicación ya existente por
        # content_hash (fase 4) la que decide, igual que siempre.
        indices_por_archivo: dict[Path, list[int]] = {}
        for indice, (archivo_resuelto, _motivo) in enumerate(resoluciones):
            if archivo_resuelto is not None:
                indices_por_archivo.setdefault(archivo_resuelto, []).append(indice)

        indices_ambiguos: set[int] = set()
        for indices in indices_por_archivo.values():
            if len(indices) < 2:
                continue
            hashes_declarados = {(filas[i].get("hash_contenido") or "").strip().lower() for i in indices}
            if len(hashes_declarados) > 1:
                indices_ambiguos.update(indices)

        result = ImportSourcesFromFolderResult()
        resultados_por_fila: dict[int, tuple[str, Optional[str]]] = {}
        for indice, row in enumerate(filas):
            title = (row.get("titulo") or "").strip() or "(sin título)"
            archivo_resuelto, motivo_fallo = resoluciones[indice]

            if indice in indices_ambiguos:
                result.skipped.append(SkippedSourceRow(
                    title,
                    "referencia ambigua: coincide con el mismo archivo que otra fila del manifiesto, "
                    "con hash declarado distinto",
                ))
                continue
            if archivo_resuelto is None:
                result.skipped.append(SkippedSourceRow(title, motivo_fallo or "no se pudo resolver ruta_archivo"))
                continue

            # Fase 3: verificación de integridad -- localizar el archivo
            # correcto por nombre/ruta ya no basta para importarlo si su
            # contenido no coincide con lo declarado en el manifiesto
            # (antes, content_hash solo se usaba para deduplicar).
            # El contrato (seccion 4) define hexadecimal en minusculas;
            # se normaliza para que un hash editado a mano en mayusculas no
            # se rechace como si el contenido fuera distinto (auditoria
            # 2026-09-30). La comparacion sigue siendo sobre bytes exactos.
            content_hash = (row.get("hash_contenido") or "").strip().lower() or None
            if content_hash:
                hash_real = _sha256_de_archivo(archivo_resuelto)
                if hash_real != content_hash:
                    result.skipped.append(SkippedSourceRow(
                        title,
                        "el archivo fue localizado, pero su contenido no coincide con el hash "
                        "declarado en el manifiesto",
                    ))
                    continue

            # Fase 4: alta real (dedup por content_hash ya la resuelve
            # RegisterSource.execute(), sin cambios respecto de antes).
            try:
                source = self._register_source.execute(
                    project_id,
                    title,
                    _map_source_type(row.get("tipo_fuente")),
                    location=str(archivo_resuelto),
                    owner_area=(row.get("area_propietaria") or "").strip() or None,
                    access_level=_map_access_level(row.get("nivel_acceso")),
                    language=(row.get("idioma") or "es").strip() or "es",
                    content_hash=content_hash,
                    valid_from=_parse_date(row.get("vigente_desde")),
                    valid_to=_parse_date(row.get("vigente_hasta")),
                    source_authority=_parse_authority(row.get("autoridad_fuente")),
                    document_type_code=document_type_code,
                )
            except DuplicateSourceError:
                result.skipped.append(SkippedSourceRow(title, _MOTIVO_DUPLICADO))
                existente = self._register_source.find_by_content_hash(project_id, content_hash)
                resultados_por_fila[indice] = (_MOTIVO_DUPLICADO, existente.id if existente else None)
                continue
            except Exception as exc:  # noqa: BLE001 - una fila con error no debe tumbar el resto del lote
                logger.warning(
                    "No se pudo importar la fila '%s' del manifiesto '%s': %s", title, manifest_path, exc,
                )
                result.skipped.append(SkippedSourceRow(title, str(exc)))
                continue

            result.imported.append(ImportedSourceRow(title, source.id))
            resultados_por_fila[indice] = ("importada", source.id)

        self._registrar_lote(project_id, folder, filas, result, resultados_por_fila)
        return result

    def _registrar_lote(
        self, project_id: str, folder: Path, filas: list[dict[str, str]],
        result: ImportSourcesFromFolderResult, resultados_por_fila: dict[int, tuple[str, Optional[str]]],
    ) -> None:
        """Ronda 92: identidad y procedencia del lote (multi-lote)."""
        if not filas:
            return
        motivos_omision = iter(result.skipped)
        filas_lote: list[ImportBatchRow] = []
        for indice, row in enumerate(filas):
            nombre = nombre_logico(row.get("ruta_archivo") or "", row.get("manifest_schema_version"))
            hash_declarado = (row.get("hash_contenido") or "").strip().lower()
            titulo = (row.get("titulo") or "").strip() or "(sin título)"
            if indice in resultados_por_fila:
                resultado, source_id = resultados_por_fila[indice]
                if resultado == _MOTIVO_DUPLICADO:
                    next(motivos_omision, None)
            else:
                omitida = next(motivos_omision, None)
                resultado, source_id = (omitida.reason if omitida else "omitida"), None
            filas_lote.append(ImportBatchRow(titulo, nombre, hash_declarado, resultado, source_id))

        huella = batch_fingerprint([(f.nombre, f.hash_contenido) for f in filas_lote])
        documentos = {f.nombre: f.hash_contenido for f in filas_lote}
        anteriores = self._batch_ledger.list_batches(project_id) if self._batch_ledger else []
        relacion, relacionado = classify_batch(huella, documentos, anteriores)
        result.batch_fingerprint = huella
        result.batch_label = _etiqueta_lote(folder)
        result.batch_relation = relacion
        result.related_batch_label = relacionado.label if relacionado else None
        if self._batch_ledger is None:
            return
        completo = all(f.resultado in ("importada", _MOTIVO_DUPLICADO) for f in filas_lote)
        version = next((
            (row.get("manifest_schema_version") or "").strip() for row in filas
            if (row.get("manifest_schema_version") or "").strip()
        ), "1")
        try:
            self._batch_ledger.append(project_id, ImportBatchRecord(
                fingerprint=huella, label=result.batch_label, manifest_schema_version=version,
                imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                relation=relacion.value, related_label=result.related_batch_label,
                rows=tuple(filas_lote), complete=completo,
            ))
        except OSError as exc:  # el registro de procedencia nunca deshace una importación ya hecha
            logger.warning("No se pudo registrar el lote '%s' en el proyecto '%s': %s", result.batch_label,
                           project_id, exc)
