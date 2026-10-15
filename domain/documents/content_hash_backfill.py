"""Relleno de `content_hash` de fuentes heredadas (RAG-INC-01, precondición
técnica de 01b; decisión NEXOM sobre INC01-R1, opción B, mecanismo
"comando/servicio explícito").

Reglas puras (sin E/S) para clasificar cada fuente del proyecto. El contrato
NEXOM Knowledge Package v1.0.0 define

    source.id = uuid5(lineage_id, "content:" + content_hash)

así que dos fuentes con el mismo hash solo tienen el mismo `source.id` si
además comparten `lineage_id`:

- mismo hash + distinto lineage_id → permitido: se rellenan todas y se
  reportan como `contenido_compartido_entre_linajes`;
- mismo hash + mismo lineage_id → colisión real: NO se rellena ninguna
  fuente sin hash del grupo, se reporta `colisión_mismo_linaje` y no se
  resuelve automáticamente. Incluye el caso mixto: una fuente sin hash cuyo
  contenido coincide con el hash YA guardado de otra fuente de su mismo
  linaje (ese hash existente no se toca).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .entities import NON_FILE_SOURCE_TYPES, Source


class BackfillStatus(str, Enum):
    RELLENADA = "rellenada"
    YA_TENIA = "ya_tenía"
    NO_APLICA = "no_aplica"
    SIN_COPIA_ORIGINAL = "sin_copia_original"
    ILEGIBLE = "ilegible"
    COLISION_MISMO_LINAJE = "colisión_mismo_linaje"
    CONTENIDO_COMPARTIDO_ENTRE_LINAJES = "contenido_compartido_entre_linajes"


# Estados que implican escribir el hash calculado.
ESTADOS_QUE_ESCRIBEN = frozenset({BackfillStatus.RELLENADA, BackfillStatus.CONTENIDO_COMPARTIDO_ENTRE_LINAJES})


@dataclass
class SourceBackfillResult:
    source_id: str
    title: str
    source_type: str
    lineage_id: str
    status: BackfillStatus
    content_hash: Optional[str] = None
    """Hash guardado (ya_tenía) o calculado (resto, cuando se pudo leer)."""
    detail: str = ""
    related_source_ids: list[str] = field(default_factory=list)


@dataclass
class ContentHashBackfillReport:
    project_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    results: list[SourceBackfillResult] = field(default_factory=list)
    write_outcome: str = "sin_cambios"
    """`aplicada` (se escribió al menos un hash), `sin_cambios` o
    `revertida` (la transacción falló y no se escribió nada)."""
    error: Optional[str] = None
    missing_before: int = 0
    missing_after: int = 0
    report_path: Optional[str] = None

    def counts(self) -> dict[str, int]:
        conteo = {estado.value: 0 for estado in BackfillStatus}
        for resultado in self.results:
            conteo[resultado.status.value] += 1
        return conteo

    def written_ids(self) -> list[str]:
        if self.write_outcome != "aplicada":
            return []
        return [r.source_id for r in self.results if r.status in ESTADOS_QUE_ESCRIBEN]

    def to_dict(self) -> dict:
        return {
            "tipo": "content_hash_backfill",
            "version_informe": 1,
            "project_id": self.project_id,
            "iniciado": self.started_at.isoformat(),
            "terminado": self.finished_at.isoformat() if self.finished_at else None,
            "fuente_del_hash": "SHA-256 de los bytes de <proyecto>/sources/original/<source_id>.<ext> (sin usar location)",
            "escritura": self.write_outcome,
            "error": self.error,
            "faltantes_antes": self.missing_before,
            "faltantes_despues": self.missing_after,
            "conteos": self.counts(),
            "fuentes": [
                {
                    "source_id": r.source_id,
                    "titulo": r.title,
                    "source_type": r.source_type,
                    "lineage_id": r.lineage_id,
                    "estado": r.status.value,
                    "content_hash": r.content_hash,
                    "detalle": r.detail,
                    "relacionadas": list(r.related_source_ids),
                }
                for r in self.results
            ],
        }


def necesita_hash(source: Source) -> bool:
    """Fuente basada en archivo y sin `content_hash` (regla IS NULL)."""
    return source.content_hash is None and source.source_type not in NON_FILE_SOURCE_TYPES


def clasificar(
    sources: list[Source], calculados: dict[str, str], fallos: dict[str, tuple[BackfillStatus, str]],
) -> list[SourceBackfillResult]:
    """Clasifica cada fuente.

    - `calculados`: source_id → hash calculado de la copia del original
      (solo fuentes que necesitan hash y se pudieron leer).
    - `fallos`: source_id → (SIN_COPIA_ORIGINAL | ILEGIBLE, detalle).
    """
    por_id = {s.id: s for s in sources}
    resultados: dict[str, SourceBackfillResult] = {}

    def base(s: Source, estado: BackfillStatus, h: Optional[str] = None, detalle: str = "") -> SourceBackfillResult:
        return SourceBackfillResult(
            source_id=s.id, title=s.title, source_type=s.source_type.value, lineage_id=s.lineage_id,
            status=estado, content_hash=h, detail=detalle,
        )

    for s in sources:
        if s.content_hash is not None:
            detalle = ""
            if s.content_hash == "":
                detalle = "content_hash vacío (''): no es NULL, así que no se modifica; revisar."
            resultados[s.id] = base(s, BackfillStatus.YA_TENIA, s.content_hash, detalle)
        elif s.source_type in NON_FILE_SOURCE_TYPES:
            resultados[s.id] = base(s, BackfillStatus.NO_APLICA, detalle="tipo de fuente sin archivo")
        elif s.id in fallos:
            estado, detalle = fallos[s.id]
            resultados[s.id] = base(s, estado, detalle=detalle)
        elif s.id in calculados:
            resultados[s.id] = base(s, BackfillStatus.RELLENADA, calculados[s.id])
        else:  # pragma: no cover - quien llama siempre informa calculado o fallo
            resultados[s.id] = base(s, BackfillStatus.ILEGIBLE, detalle="sin resultado de lectura")

    # Grupos (lineage_id, hash) con hashes existentes y candidatos.
    existentes: dict[tuple[str, str], list[str]] = defaultdict(list)
    candidatos: dict[tuple[str, str], list[str]] = defaultdict(list)
    for s in sources:
        if s.content_hash:
            existentes[(s.lineage_id, s.content_hash)].append(s.id)
    for sid, h in calculados.items():
        if resultados[sid].status == BackfillStatus.RELLENADA:
            candidatos[(por_id[sid].lineage_id, h)].append(sid)

    for clave, ids in candidatos.items():
        ya = existentes.get(clave, [])
        if len(ids) >= 2 or ya:
            for sid in ids:
                r = resultados[sid]
                r.status = BackfillStatus.COLISION_MISMO_LINAJE
                r.related_source_ids = sorted([x for x in ids if x != sid] + ya)
                r.detail = (
                    "mismo contenido que otra(s) fuente(s) del mismo linaje: tendrían el mismo source.id "
                    "portable. No se rellenó ninguna; requiere decisión manual."
                    + (" Caso mixto: el hash ya existe en el mismo linaje y no se modificó." if ya else "")
                )
            for sid in ya:
                r = resultados[sid]
                r.related_source_ids = sorted(set(r.related_source_ids) | set(ids))
                r.detail = "su hash coincide con fuente(s) sin hash del mismo linaje (colisión); no se modificó."

    # Contenido compartido entre linajes: entre lo que quedará con hash
    # (existentes + lo que se va a escribir).
    con_hash: dict[str, list[tuple[str, str]]] = defaultdict(list)  # hash -> [(lineage, id)]
    for s in sources:
        if s.content_hash:
            con_hash[s.content_hash].append((s.lineage_id, s.id))
    for r in resultados.values():
        if r.status == BackfillStatus.RELLENADA and r.content_hash:
            con_hash[r.content_hash].append((r.lineage_id, r.source_id))
    for r in resultados.values():
        if r.status != BackfillStatus.RELLENADA or not r.content_hash:
            continue
        otros = [sid for lin, sid in con_hash[r.content_hash] if lin != r.lineage_id]
        if otros:
            r.status = BackfillStatus.CONTENIDO_COMPARTIDO_ENTRE_LINAJES
            r.related_source_ids = sorted(otros)
            r.detail = "mismo contenido que fuente(s) de otro linaje: permitido (source.id distintos); se rellenó."

    return [resultados[s.id] for s in sources]
