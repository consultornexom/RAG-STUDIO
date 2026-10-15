"""Informe JSON del relleno de content_hash en `<proyecto>/reports/`
(RAG-INC-01, decisión NEXOM sobre INC01-R1). Escritura atómica: archivo
temporal en la misma carpeta + `os.replace`."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from domain.documents.ports import BackfillReportStore

from .paths import InstallationPaths


class JsonBackfillReportStore(BackfillReportStore):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, project_id: str, report: dict) -> str:
        carpeta = self._paths.project_dir(project_id) / "reports"
        carpeta.mkdir(parents=True, exist_ok=True)
        marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destino = carpeta / f"content_hash_backfill_{marca}_{uuid.uuid4().hex[:6]}.json"
        temporal = carpeta / f".{destino.name}.tmp"
        with open(temporal, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(temporal, destino)
        return str(destino)
