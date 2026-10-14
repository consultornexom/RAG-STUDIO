"""Implementacion concreta de IndexInfoRepository (contexto RAG,
Etapa 4). Sigue el mismo patron _session_factory_for que
ingestion_repositories.py."""
from __future__ import annotations

from typing import Optional


from domain.rag.entities import IndexInfo
from domain.rag.ports import IndexInfoRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import IndexInfoRecord


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyIndexInfoRepository(IndexInfoRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, info: IndexInfo) -> None:
        with _session_factory_for(self._paths, info.project_id)() as session:
            existing = session.get(IndexInfoRecord, info.project_id)
            if existing is None:
                session.add(IndexInfoRecord(
                    project_id=info.project_id, embedding_provider=info.embedding_provider,
                    embedding_model=info.embedding_model, dimensions=info.dimensions,
                    points_count=info.points_count, updated_at=info.updated_at,
                ))
            else:
                existing.embedding_provider = info.embedding_provider
                existing.embedding_model = info.embedding_model
                existing.dimensions = info.dimensions
                existing.points_count = info.points_count
                existing.updated_at = info.updated_at
            session.commit()

    def get(self, project_id: str) -> Optional[IndexInfo]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(IndexInfoRecord, project_id)
            if record is None:
                return None
            return IndexInfo(
                project_id=record.project_id, embedding_provider=record.embedding_provider,
                embedding_model=record.embedding_model, dimensions=record.dimensions,
                points_count=record.points_count, updated_at=record.updated_at,
            )
