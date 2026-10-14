"""Pruebas unitarias de PurgeOldConversations (Ronda 12, ver
Validacion_observaciones_RAG_STUDIO.md -- brecha de retención de
datos)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from application.runtime.commands.purge_old_conversations import (
    InvalidRetentionWindowError,
    PurgeOldConversations,
)
from domain.runtime.entities import ConversationLogEntry

from .fakes_runtime import InMemoryConversationLogRepository


def _entry_aged_days(days: int) -> ConversationLogEntry:
    return ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="hola", action="responder",
        created_at=datetime.now(timezone.utc) - timedelta(days=days),
    )


def test_count_eligible_only_counts_entries_older_than_the_retention_window():
    repository = InMemoryConversationLogRepository()
    repository.save(_entry_aged_days(100))
    repository.save(_entry_aged_days(1))
    purge = PurgeOldConversations(repository)

    assert purge.count_eligible(90) == 1


def test_execute_deletes_entries_older_than_the_retention_window():
    repository = InMemoryConversationLogRepository()
    old_entry = _entry_aged_days(100)
    recent_entry = _entry_aged_days(1)
    repository.save(old_entry)
    repository.save(recent_entry)
    purge = PurgeOldConversations(repository)

    deleted = purge.execute(90)

    assert deleted == 1
    assert repository.get_by_id(old_entry.id) is None
    assert repository.get_by_id(recent_entry.id) is not None


def test_execute_does_not_delete_anything_before_calling_it():
    repository = InMemoryConversationLogRepository()
    repository.save(_entry_aged_days(100))
    PurgeOldConversations(repository)  # solo construir -- no debe borrar nada por sí solo

    assert repository.count_older_than(datetime.now(timezone.utc)) == 1


@pytest.mark.parametrize("retention_days", [0, -1, -30])
def test_rejects_a_non_positive_retention_window(retention_days):
    repository = InMemoryConversationLogRepository()
    purge = PurgeOldConversations(repository)

    with pytest.raises(InvalidRetentionWindowError):
        purge.execute(retention_days)

    with pytest.raises(InvalidRetentionWindowError):
        purge.count_eligible(retention_days)
