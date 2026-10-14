"""Caso de uso: exportar el paquete de entregables de una liberación
ya evaluada (ítem 6 de la evaluación de madurez post-8-etapas)."""
from __future__ import annotations

from domain.release.exceptions import ReleaseRecordNotFoundError
from domain.release.ports import ReleasePackager, ReleaseRecordRepository


class ExportDeliverablesPackage:
    def __init__(self, repository: ReleaseRecordRepository, packager: ReleasePackager):
        self._repository = repository
        self._packager = packager

    def execute(self, project_id: str, record_id: str, destination_path: str) -> str:
        record = self._repository.get(project_id, record_id)
        if record is None:
            raise ReleaseRecordNotFoundError(project_id, record_id)
        return self._packager.export(record, destination_path)
