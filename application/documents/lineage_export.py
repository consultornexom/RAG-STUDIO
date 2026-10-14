"""Pista C.2b del ADR-003 (docs proyecto/
RAG_STUDIO_Propuesta_C2_Procedencia_Temporalidad.docx): formato
exportable del linaje de versiones de una fuente (ver
queries/get_source_lineage.py) -- CSV plano, sin ninguna dependencia
nueva. Vive en application (no en ui/sources/panel.py) para que la
UI solo escriba el archivo elegido por el usuario, nunca construya el
formato -- mismo criterio de capas que el resto del proyecto."""
from __future__ import annotations

import csv
import io

from domain.documents.entities import Source

_HEADER = [
    "orden", "id", "titulo", "estado_validacion", "vigente_desde", "vigente_hasta",
    "content_hash", "sustituye_a",
]


def format_source_lineage_as_csv(lineage: list[Source]) -> str:
    """`lineage` ya viene ordenado de la más antigua a la más nueva
    (ver GetSourceLineage.execute) -- "orden" es exactamente esa
    posición (1-based), para que quien abra el CSV en una hoja de
    cálculo pueda reordenar y siga siendo reconstruible sin depender
    de created_at."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_HEADER)
    for position, source in enumerate(lineage, start=1):
        writer.writerow([
            position,
            source.id,
            source.title,
            source.validation_status.value,
            source.valid_from.isoformat() if source.valid_from else "",
            source.valid_to.isoformat() if source.valid_to else "",
            source.content_hash or "",
            source.supersedes_source_id or "",
        ])
    return buffer.getvalue()
