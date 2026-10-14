"""Caso de uso: validar la integridad de un paquete .agentproj sin importarlo."""
from __future__ import annotations

from domain.projects.packaging import IntegrityReport
from domain.projects.ports import ProjectPackager


class ValidateProjectIntegrity:
    def __init__(self, packager: ProjectPackager):
        self._packager = packager

    def execute(self, package_path: str) -> IntegrityReport:
        return self._packager.verify_integrity(package_path)
