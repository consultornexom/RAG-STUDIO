"""Registro de lotes de RAG CONTENT importados (Ronda 92) -- un archivo
JSON Lines por proyecto: `projects/<id>/lotes_importados.jsonl`.

Por qué un archivo y no una tabla: viaja sin cambios dentro del
.agentproj y de cada instantánea publicada (ambos copian la carpeta del
proyecto completa) y no requiere una migración nueva de project.db.
Append-only: nunca se reescribe ni se borra una línea (trazabilidad;
retirar un lote no borra su historia). Bytes UTF-8 con "\\n" explícito
(sin traducción de fin de línea según el sistema operativo) y sin rutas
absolutas: el archivo es idéntico en cualquier equipo.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from domain.documents.import_batch import ImportBatchRecord, ImportBatchRow
from domain.documents.ports import ImportBatchLedger
from infrastructure.filesystem.paths import InstallationPaths

logger = logging.getLogger(__name__)

LEDGER_FILENAME = "lotes_importados.jsonl"


def read_ledger_file(path: Path) -> list[ImportBatchRecord]:
    if not path.is_file():
        return []
    registros: list[ImportBatchRecord] = []
    for numero, linea in enumerate(path.read_bytes().decode("utf-8").split("\n"), start=1):
        if not linea.strip():
            continue
        try:
            data = json.loads(linea)
            filas = tuple(ImportBatchRow(**fila) for fila in data.pop("rows", []))
            registros.append(ImportBatchRecord(rows=filas, **data))
        except (ValueError, TypeError) as exc:
            # Una línea dañada no debe impedir importar ni ocultar las demás.
            logger.warning("Línea %d de %s ilegible, se ignora: %s", numero, path, exc)
    return registros


class JsonlImportBatchLedger(ImportBatchLedger):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def _path(self, project_id: str) -> Path:
        return self._paths.project_dir(project_id) / LEDGER_FILENAME

    def list_batches(self, project_id: str) -> list[ImportBatchRecord]:
        return read_ledger_file(self._path(project_id))

    def append(self, project_id: str, record: ImportBatchRecord) -> None:
        destino = self._path(project_id)
        destino.parent.mkdir(parents=True, exist_ok=True)
        linea = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n"
        with destino.open("ab") as archivo:
            archivo.write(linea.encode("utf-8"))
