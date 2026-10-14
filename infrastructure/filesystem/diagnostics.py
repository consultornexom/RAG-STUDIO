"""Paquete de diagnóstico para soporte (ítem 5 de la segunda
evaluación de madurez post-8-etapas, ver bitácora en README).

`app/logging_setup.py` ya escribe un log estructurado real (con
redacción de credenciales), pero antes de este ítem la única forma de
llegar a él era que el propio usuario abriera manualmente la carpeta
`logs/` de la instalación -- nada empaquetaba eso, junto con
información básica del entorno (versión de RAG STUDIO, versión de
Python, sistema operativo), en algo fácil de adjuntar a un correo o
ticket de soporte. `FilesystemDiagnosticsExporter` hace exactamente
eso: un .zip con `info.json` + una copia de los archivos de `logs/`."""
from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.filesystem.paths import InstallationPaths


def _ragstudio_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python < 3.8, fuera de alcance (requires-python >=3.10)
        return "desconocida"
    try:
        return version("ragstudio")
    except PackageNotFoundError:
        return "desconocida (instalación en modo editable/desarrollo)"


class FilesystemDiagnosticsExporter:
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def export(self, destination_path: str) -> str:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        info = {
            "generado_en": datetime.now(timezone.utc).isoformat(),
            "ragstudio_version": _ragstudio_version(),
            "python_version": sys.version,
            "plataforma": platform.platform(),
            "base_dir": str(self._paths.base_dir),
        }

        logs_dir = self._paths.logs_dir()
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("info.json", json.dumps(info, indent=2, ensure_ascii=False))
            if logs_dir.exists():
                for log_file in sorted(logs_dir.glob("*")):
                    if log_file.is_file():
                        zf.write(log_file, arcname=f"logs/{log_file.name}")
        return str(destination)
