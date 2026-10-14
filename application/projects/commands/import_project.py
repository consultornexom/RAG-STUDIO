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

import logging
import re
from contextlib import nullcontext
from typing import Optional

from domain.projects.entities import IdentityPolicy, Project
from domain.projects.exceptions import (
    ImportIdentityCheckError,
    ImportNameCollisionError,
    ImportResidueError,
    IntegrityViolationError,
    KnowledgeBaseIdentityCollisionError,
    MissingIdentityPolicyError,
    ProjectIdCollisionError,
)
from domain.projects.ports import ImportLock, ProjectPackager, ProjectRepository

logger = logging.getLogger(__name__)


def parse_identity_policy(valor: object) -> IdentityPolicy:
    """RAG-INC-01a: la política es obligatoria y explícita. None, vacío o un
    valor desconocido abortan antes de leer o modificar nada."""
    if isinstance(valor, IdentityPolicy):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return IdentityPolicy(valor.strip().lower())
        except ValueError:
            pass
    raise MissingIdentityPolicyError(valor)

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
    """RAG-INC-01a — política de identidad (Alcance firmado, INC01-D3 y
    INC01-R9; decisión NEXOM D-1):

    - `identity_policy` es obligatoria: "preserve" o "fork". Sin ella se
      aborta antes de leer o modificar nada (MissingIdentityPolicyError).
    - PRESERVE: conserva `knowledge_base_id` y `lineage_id`. Si el
      `knowledge_base_id` del paquete ya lo tiene un proyecto de la
      instalación (activo o archivado), KnowledgeBaseIdentityCollisionError
      sin modificar nada. Esta comprobación va ANTES que la de project_id
      (Alcance, tabla de políticas).
    - FORK: el paquete se importa como otra base de conocimiento (identidades
      nuevas en la copia temporal, ver FilesystemProjectPackager). Si su
      project_id ya existe y no se indicó `new_project_id`,
      ProjectIdCollisionError (regla vigente).
    - Toda la secuencia comprobar → importar → registrar corre bajo un
      bloqueo ENTRE PROCESOS (ImportLock) y la colisión de identidad se
      vuelve a comprobar justo antes de registrar.
    - Atomicidad (Ronda 88 + 01a): la copia, la migración y la reescritura
      de identidades ocurren en una carpeta temporal; si algo falla después,
      se borra lo copiado. Nunca queda una importación parcial."""

    def __init__(
        self, repository: ProjectRepository, packager: ProjectPackager, import_lock: Optional[ImportLock] = None,
    ):
        self._repository = repository
        self._packager = packager
        self._lock = import_lock

    def _proyecto_con_identidad(self, knowledge_base_id: str) -> Optional[Project]:
        """Proyecto instalado (activo o archivado) con ese knowledge_base_id.
        Fail-closed (L-04): si no puede leerse alguno, aborta."""
        try:
            instalados = self._repository.list(include_archived=True)
        except Exception as exc:  # noqa: BLE001 - se traduce a un error tipado y se aborta
            raise ImportIdentityCheckError("(lista de proyectos)", str(exc)) from exc
        for proyecto in instalados:
            if proyecto.knowledge_base_id == knowledge_base_id:
                return proyecto
        return None

    def _verificar_identidad_libre(self, knowledge_base_id: str, policy: IdentityPolicy) -> None:
        existente = self._proyecto_con_identidad(knowledge_base_id)
        if existente is not None:
            # L-05: queda en el log técnico.
            logger.warning(
                "Importación detenida por colisión de identidad: knowledge_base_id=%s ya pertenece al "
                "proyecto %s (%r); política=%s.",
                knowledge_base_id, existente.id, existente.name, policy.value,
            )
            raise KnowledgeBaseIdentityCollisionError(knowledge_base_id, existente.id, existente.name)

    def execute(
        self,
        package_path: str,
        new_project_id: Optional[str] = None,
        new_name: Optional[str] = None,
        set_aside_residue: bool = False,
        identity_policy: object = None,
    ) -> Project:
        policy = parse_identity_policy(identity_policy)
        with self._lock.hold() if self._lock is not None else nullcontext():
            return self._importar(package_path, new_project_id, new_name, set_aside_residue, policy)

    def _importar(
        self, package_path: str, new_project_id: Optional[str], new_name: Optional[str],
        set_aside_residue: bool, policy: IdentityPolicy,
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

        # 01a: identidad lógica, antes que cualquier otra colisión (preserve).
        identidad_paquete: Optional[str] = None
        if policy == IdentityPolicy.PRESERVE:
            identidad_paquete = self._packager.read_knowledge_base_id(package_path)
            if identidad_paquete:
                self._verificar_identidad_libre(identidad_paquete, policy)

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
            identity_policy=policy,
        )
        # 2. Todo o nada: si no se puede registrar, se deshace la copia.
        try:
            # 01a: segunda comprobación inmediatamente antes de registrar
            # (también cubre paquetes anteriores a 0021, cuya identidad se
            # asigna al migrar la copia, y el resultado de FORK).
            self._verificar_identidad_libre(project.knowledge_base_id, policy)
            self._repository.save(project)
        except Exception:
            self._packager.discard_project_data(project.id)
            raise
        return project
