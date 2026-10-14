"""Implementación concreta de `PluginRepository` (ADR-001, sección 4).

A diferencia de todos los demás repositorios del proyecto, opera sobre
`application.db` (línea de migración `global/`), no sobre el
`project.db` de un proyecto -- un complemento no pertenece a un
proyecto."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select

from domain.plugins.entities import Plugin, PluginKind
from domain.plugins.ports import PluginRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import upgrade_global
from .models import PluginRecord


class SqlAlchemyPluginRepository(PluginRepository):
    def __init__(self, paths: InstallationPaths):
        upgrade_global(paths.application_db_path())
        self._session_factory = make_session_factory(make_sqlite_engine(paths.application_db_path()))

    def save(self, plugin: Plugin) -> None:
        with self._session_factory() as session:
            record = session.get(PluginRecord, plugin.id)
            if record is None:
                record = PluginRecord(id=plugin.id)
                session.add(record)
            record.kind = plugin.kind.value
            record.code = plugin.code
            record.name = plugin.name
            record.description = plugin.description
            record.version = plugin.version
            record.entry_point = plugin.entry_point
            record.config = json.dumps(plugin.config)
            record.enabled = plugin.enabled
            record.created_at = plugin.created_at
            record.updated_at = plugin.updated_at
            session.commit()

    def get(self, plugin_id: str) -> Optional[Plugin]:
        with self._session_factory() as session:
            record = session.get(PluginRecord, plugin_id)
            return _record_to_plugin(record) if record else None

    def get_by_code(self, kind: PluginKind, code: str) -> Optional[Plugin]:
        with self._session_factory() as session:
            record = session.execute(
                select(PluginRecord).where(PluginRecord.kind == kind.value, PluginRecord.code == code)
            ).scalar_one_or_none()
            return _record_to_plugin(record) if record else None

    def list_all(self) -> list[Plugin]:
        with self._session_factory() as session:
            records = session.execute(select(PluginRecord).order_by(PluginRecord.kind, PluginRecord.code)).scalars().all()
            return [_record_to_plugin(record) for record in records]

    def list_by_kind(self, kind: PluginKind) -> list[Plugin]:
        with self._session_factory() as session:
            records = session.execute(
                select(PluginRecord).where(PluginRecord.kind == kind.value).order_by(PluginRecord.code)
            ).scalars().all()
            return [_record_to_plugin(record) for record in records]

    def delete(self, plugin_id: str) -> None:
        with self._session_factory() as session:
            record = session.get(PluginRecord, plugin_id)
            if record is not None:
                session.delete(record)
                session.commit()


def _record_to_plugin(record: PluginRecord) -> Plugin:
    return Plugin(
        id=record.id, kind=PluginKind(record.kind), code=record.code, name=record.name,
        description=record.description, version=record.version, entry_point=record.entry_point,
        config=json.loads(record.config), enabled=record.enabled,
        created_at=record.created_at, updated_at=record.updated_at,
    )
