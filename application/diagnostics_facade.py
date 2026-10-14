"""Fachada de application sobre el exportador de diagnóstico (ítem 5
de la segunda evaluación de madurez post-8-etapas, ver bitácora).

Igual que `application.jobs_facade.BackgroundJobs` con `workers.jobs`:
esta fachada depende directamente de un módulo de `infrastructure`
(`infrastructure.filesystem.diagnostics`) sin pasar por un puerto de
`domain`, porque no hay ninguna regla de negocio que versionar aquí ni
un segundo adaptador intercambiable -- "empaquetar los logs en un
.zip" no es una decisión de dominio, es plomería operativa interna,
como ya se justificó para `workers` en `jobs_facade.py`.
"""
from __future__ import annotations

from infrastructure.filesystem.diagnostics import FilesystemDiagnosticsExporter


class DiagnosticsFacade:
    def __init__(self, exporter: FilesystemDiagnosticsExporter):
        self._exporter = exporter

    def export_diagnostics_package(self, destination_path: str) -> str:
        """Exporta un .zip con `info.json` (versión de RAG STUDIO,
        versión de Python, sistema operativo) y una copia de los
        archivos de `logs/` -- para adjuntar a un correo o ticket de
        soporte sin que el usuario tenga que ir a buscar la carpeta de
        instalación a mano."""
        return self._exporter.export(destination_path)
