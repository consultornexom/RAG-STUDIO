"""Implementaciones concretas de los puertos ProjectRepository y
ConfigurationRepository (ADR-001, sección 4: solo infrastructure conoce
SQLAlchemy; domain y application no lo importan)."""
from __future__ import annotations

import shutil
from typing import Optional

from sqlalchemy import select

from domain.projects.entities import ConfigurationEntry, Project, ProjectStatus
from domain.projects.exceptions import DuplicateProjectError
from domain.projects.ports import ConfigurationRepository, ProjectRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db, upgrade_global
from .models import ConfigurationRecord, ProjectIndexRecord, ProjectRecord


def _project_to_record(project: Project) -> ProjectRecord:
    return ProjectRecord(
        id=project.id,
        knowledge_base_id=project.knowledge_base_id,
        name=project.name,
        agent_type_hint=project.agent_type_hint,
        description=project.description,
        domain=project.domain,
        target_users=project.target_users,
        language=project.language,
        risk_level=project.risk_level,
        status=project.status.value,
        template_id=project.template_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        quality_regression_threshold=project.quality_regression_threshold,
        agent_reranking=project.agent_reranking,
    )


def record_to_project(record: ProjectRecord) -> Project:
    return Project(
        id=record.id,
        knowledge_base_id=record.knowledge_base_id,
        name=record.name,
        agent_type_hint=record.agent_type_hint,
        description=record.description,
        domain=record.domain,
        target_users=record.target_users,
        language=record.language,
        risk_level=record.risk_level,
        status=ProjectStatus(record.status),
        template_id=record.template_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
        quality_regression_threshold=record.quality_regression_threshold,
        agent_reranking=record.agent_reranking,
    )


class ProjectAgentRerankingReader:
    """Ronda 102 (C4): lee Project.agent_reranking directamente del
    project.db de `paths` -- sin tocar application.db, para que el canal
    de mensajes (interfaces/api/runtime_context.py) lea el ajuste de la
    INSTANTÁNEA publicada que sirve, no del proyecto en edición. Devuelve
    None (automático) si el proyecto o su project.db no existen."""

    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def __call__(self, project_id: str) -> Optional[bool]:
        if not self._paths.project_db_path(project_id).exists():
            return None
        session_factory = make_session_factory(make_sqlite_engine(ensure_project_db(self._paths, project_id)))
        with session_factory() as session:
            record = session.get(ProjectRecord, project_id)
            return record.agent_reranking if record is not None else None


class SqlAlchemyProjectRepository(ProjectRepository):
    """Escribe el registro autoritativo en el project.db de cada proyecto
    y mantiene un índice ligero en la base global (application.db) para
    poder listar sin abrir cada project.db."""

    def __init__(self, paths: InstallationPaths):
        self._paths = paths
        upgrade_global(paths.application_db_path())
        self._global_session_factory = make_session_factory(
            make_sqlite_engine(paths.application_db_path())
        )

    def _project_session_factory(self, project_id: str):
        db_path = ensure_project_db(self._paths, project_id)
        return make_session_factory(make_sqlite_engine(db_path))

    def save(self, project: Project) -> None:
        # Ronda 55: unificado para pasar por _project_session_factory()
        # (el mismo punto único que get() usa ahora, ver abajo) en vez
        # de repetir aquí su propia llamada a ensure_project_db() +
        # make_session_factory() -- ambos métodos hacían exactamente lo
        # mismo por caminos de código distintos, y fue precisamente esa
        # duplicación la que dejó a get() sin la llamada a
        # ensure_project_db() sin que nadie lo notara (ver el hallazgo
        # de la auditoría de esta ronda). Un solo punto de paso impide
        # que esta clase de error se repita.
        #
        # Ronda 88 (2026-10-02, hallazgo real de usuario): el nombre debe
        # ser único en el índice global, pero esa restricción solo se
        # comprobaba al FINAL, después de haber escrito ya project.db. Un
        # nombre repetido que se escapara a la validación previa (por
        # ejemplo "  AGENTE UDL " con espacios, que el modelo recorta)
        # terminaba en "UNIQUE constraint failed: project_index.name" con
        # project.db ya modificado: al crear quedaba una carpeta huérfana,
        # y al renombrar el proyecto aparecía en la lista con el nombre
        # nuevo aunque el cambio había "fallado". Ahora se comprueba
        # primero y no se escribe nada si el nombre ya es de otro proyecto.
        with self._global_session_factory() as session:
            duplicate = session.execute(
                select(ProjectIndexRecord).where(
                    ProjectIndexRecord.name == project.name, ProjectIndexRecord.id != project.id,
                )
            ).scalars().first()
        if duplicate is not None:
            raise DuplicateProjectError(project.name)

        is_new = not self._paths.project_db_path(project.id).exists()
        try:
            self._save_records(project)
        except Exception:
            if is_new:
                # Nada de este proyecto existía antes de esta llamada: no
                # dejar una carpeta a medias que bloquee reintentos.
                shutil.rmtree(self._paths.project_dir(project.id), ignore_errors=True)
            raise

    def _save_records(self, project: Project) -> None:
        session_factory = self._project_session_factory(project.id)
        with session_factory() as session:
            existing = session.get(ProjectRecord, project.id)
            if existing is None:
                session.add(_project_to_record(project))
            else:
                for field in (
                    "name", "agent_type_hint", "description", "domain",
                    "target_users", "language", "risk_level", "template_id",
                    "created_at", "updated_at", "archived_at", "quality_regression_threshold",
                    "agent_reranking",
                ):
                    setattr(existing, field, getattr(project, field))
                existing.status = project.status.value
            session.commit()

        with self._global_session_factory() as session:
            index = session.get(ProjectIndexRecord, project.id)
            if index is None:
                session.add(ProjectIndexRecord(
                    id=project.id, name=project.name, status=project.status.value,
                    created_at=project.created_at, updated_at=project.updated_at,
                ))
            else:
                index.name = project.name
                index.status = project.status.value
                index.updated_at = project.updated_at
            session.commit()

    def get(self, project_id: str) -> Optional[Project]:
        # Ronda 55: antes de esta corrección, get() nunca llamaba a
        # ensure_project_db() -- a diferencia de save() y de
        # SqlAlchemyConfigurationRepository, abría el archivo
        # directamente si ya existía, sin verificar ni aplicar ninguna
        # migración pendiente. Esa es la causa real (más fundamental
        # que la caché corregida en la Ronda 54) del error real
        # reportado por el consultor tras reiniciar la aplicación:
        # list_projects() -> list() -> get() nunca pasaba por Alembic
        # en absoluto, en un proceso recién iniciado con la caché
        # vacía -- así que ni siquiera un reinicio de la aplicación
        # alcanzaba a aplicar las migraciones 0017-0019 sobre
        # project.db al listar los proyectos existentes.
        #
        # La comprobación de existencia va ANTES de
        # _project_session_factory()/ensure_project_db() a propósito:
        # ensure_project_db() crea el archivo si no existe (vía
        # upgrade_project(), que hace que SQLite lo cree) -- get() sobre
        # un project_id que no existe debe devolver None, no crear un
        # project.db vacío como efecto secundario de solo consultarlo.
        db_path = self._paths.project_db_path(project_id)
        if not db_path.exists():
            return None
        session_factory = self._project_session_factory(project_id)
        with session_factory() as session:
            record = session.get(ProjectRecord, project_id)
            return record_to_project(record) if record else None

    def get_by_name(self, name: str) -> Optional[Project]:
        # Ronda 88: mismo recorte de espacios que aplica Project.name, para
        # que "  AGENTE UDL " se reconozca como el nombre ya existente.
        name = name.strip()
        with self._global_session_factory() as session:
            index = session.execute(
                select(ProjectIndexRecord).where(ProjectIndexRecord.name == name)
            ).scalar_one_or_none()
        if index is None:
            return None
        return self.get(index.id)

    def list(self, include_archived: bool = True) -> list[Project]:
        with self._global_session_factory() as session:
            indexes = session.execute(select(ProjectIndexRecord)).scalars().all()
        projects = []
        for idx in indexes:
            if not include_archived and idx.status == ProjectStatus.ARCHIVADO.value:
                continue
            project = self.get(idx.id)
            if project is not None:
                projects.append(project)
        return projects

    def delete(self, project_id: str) -> None:
        """Ronda 3/4 de Validacion_observaciones_RAG_STUDIO.md (mejora 2):
        antes de esto la única forma de "quitar de en medio" un proyecto
        era Archivar (transición permanente, sin eliminación real). La
        capa de aplicación (DeleteProject) ya validó que el proyecto no
        tiene fuentes registradas antes de llegar aquí -- este método
        solo ejecuta el borrado: elimina la carpeta completa del
        proyecto (project.db incluido) y, solo si eso funcionó, quita el
        índice de application.db.

        Hallazgo de la Ronda 4 (re-análisis posterior a la primera
        versión de esta mejora): el orden original borraba primero el
        índice de application.db y luego intentaba shutil.rmtree(...,
        ignore_errors=True) -- si el borrado físico fallaba a medias
        (permisos, project.db con un handle abierto, antivirus...), el
        proyecto ya no aparecía en la app pero sus datos seguían en
        disco, sin ningún aviso. Se invierte el orden (carpeta primero,
        índice después) y ya no se ignoran los errores: si algo en la
        carpeta no se pudo borrar, se levanta un error real en vez de
        dejar el índice borrado con la carpeta todavía presente."""
        project_dir = self._paths.project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir)

        with self._global_session_factory() as session:
            index = session.get(ProjectIndexRecord, project_id)
            if index is not None:
                session.delete(index)
                session.commit()


class SqlAlchemyConfigurationRepository(ConfigurationRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def _session_factory(self, project_id: str):
        db_path = ensure_project_db(self._paths, project_id)
        return make_session_factory(make_sqlite_engine(db_path))

    def save(self, entry: ConfigurationEntry) -> None:
        with self._session_factory(entry.project_id)() as session:
            session.add(ConfigurationRecord(
                project_id=entry.project_id, key=entry.key, value=entry.value,
                version=entry.version, created_at=entry.created_at,
            ))
            session.commit()

    def get_latest(self, project_id: str, key: str) -> Optional[ConfigurationEntry]:
        with self._session_factory(project_id)() as session:
            record = session.execute(
                select(ConfigurationRecord)
                .where(ConfigurationRecord.project_id == project_id, ConfigurationRecord.key == key)
                .order_by(ConfigurationRecord.version.desc())
            ).scalars().first()
        if record is None:
            return None
        return ConfigurationEntry(
            project_id=record.project_id, key=record.key, value=record.value,
            version=record.version, created_at=record.created_at,
        )

    def list_for_project(self, project_id: str) -> list[ConfigurationEntry]:
        with self._session_factory(project_id)() as session:
            records = session.execute(
                select(ConfigurationRecord).where(ConfigurationRecord.project_id == project_id)
            ).scalars().all()
        return [
            ConfigurationEntry(
                project_id=r.project_id, key=r.key, value=r.value,
                version=r.version, created_at=r.created_at,
            )
            for r in records
        ]
