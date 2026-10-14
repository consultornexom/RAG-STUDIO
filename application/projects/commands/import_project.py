"""Caso de uso: importar un proyecto desde un paquete .agentproj.

Nunca importa un paquete sin verificar su integridad primero — regla
de no relajar validaciones silenciosamente (Documento Maestro, sección 4).

Ronda 88 (2026-10-02, hallazgo real de usuario): al importar el paquete
de "AGENTE UDL" en una instalación que ya tenía otro proyecto con ese
mismo nombre, la interfaz mostró el error crudo de SQLite "UNIQUE
constraint failed: project_index.name" y la importación quedó a medias:
los archivos ya estaban copiados en projects/<id>/ pero el proyecto no
quedó registrado. Cualquier reintento chocaba después con "Ya existe un
proyecto real con id=...", sin salida desde la interfaz. Ahora:

1. Todas las colisiones se detectan ANTES de copiar nada:
   - id de un proyecto registrado -> ProjectIdCollisionError (la
     interfaz ofrece importar como copia, con id nuevo);
   - carpeta del id sin registrar (restos de un intento fallido) ->
     ImportResidueError (la interfaz ofrece apartarla y continuar);
   - nombre ya usado -> ImportNameCollisionError (la interfaz pide otro
     nombre).
2. Si el registro final falla por cualquier motivo, se borran los
   archivos que este mismo caso de uso acaba de copiar: nunca queda una
   importación a medias.
"""
from __future__ import annotations

import re
from typing import Optional

from domain.projects.entities import Project
from domain.projects.exceptions import (
    ImportNameCollisionError,
    ImportResidueError,
    IntegrityViolationError,
    ProjectIdCollisionError,
)
from domain.projects.ports import ProjectPackager, ProjectRepository

_SUFIJO_IMPORTADO = re.compile(r"\s*\(importado(?: \d+)?\)$")


def suggest_import_name(name: str, taken: set[str]) -> str:
    """Primer nombre libre de la forma "<nombre> (importado)",
    "<nombre> (importado 2)", ..."""
    base = _SUFIJO_IMPORTADO.sub("", name).strip() or name
    candidate = f"{base} (importado)"
    counter = 2
    while candidate in taken:
        candidate = f"{base} (importado {counter})"
        counter += 1
    return candidate


class ImportProject:
    def __init__(self, repository: ProjectRepository, packager: ProjectPackager):
        self._repository = repository
        self._packager = packager

    def execute(
        self,
        package_path: str,
        new_project_id: Optional[str] = None,
        new_name: Optional[str] = None,
        set_aside_residue: bool = False,
    ) -> Project:
        report = self._packager.verify_integrity(package_path)
        if not report.is_valid:
            detail = report.error or (
                f"archivos con hash distinto={report.mismatched_files}, "
                f"faltantes={report.missing_files}"
            )
            raise IntegrityViolationError(f"Paquete inválido ({package_path}): {detail}")

        manifest = self._packager.inspect_package(package_path)
        target_id = new_project_id or manifest.project_id
        final_name = (new_name or "").strip() or manifest.project_name

        # 1a. id de un proyecto registrado (Auditoría Ronda 48: nunca
        # mezclar archivos con un proyecto existente). Se consulta la
        # LISTA de proyectos (índice global), no get(): get() lee el
        # project.db en disco y confundiría los restos sin registrar de un
        # intento fallido con un proyecto real.
        registered = {project.id: project for project in self._repository.list(include_archived=True)}
        if target_id in registered:
            raise ProjectIdCollisionError(target_id, registered[target_id].name)

        # 1b. restos sin registrar de un intento anterior.
        if self._packager.has_project_data(target_id):
            if not set_aside_residue:
                raise ImportResidueError(target_id)
            self._packager.quarantine_project_data(target_id)

        # 1c. nombre repetido (el índice global exige nombres únicos).
        if self._repository.get_by_name(final_name) is not None:
            taken = {project.name for project in registered.values()}
            raise ImportNameCollisionError(final_name, suggest_import_name(final_name, taken))

        project = self._packager.import_project(
            package_path, new_project_id=new_project_id,
            new_name=final_name if final_name != manifest.project_name else None,
        )
        # 2. Todo o nada: si no se puede registrar, se deshace la copia.
        try:
            self._repository.save(project)
        except Exception:
            self._packager.discard_project_data(project.id)
            raise
        return project
