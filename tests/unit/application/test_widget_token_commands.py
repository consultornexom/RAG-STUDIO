"""Pruebas unitarias de los comandos de WidgetToken (ADR-002, Fase 4)
-- con InMemoryWidgetTokenRepository, mismo criterio que el resto de
application/ que no necesita la pila completa de infraestructura."""
from __future__ import annotations

import pytest

from application.runtime.commands.issue_widget_token import IssueWidgetToken
from application.runtime.commands.revoke_widget_token import RevokeWidgetToken, WidgetTokenNotFoundError
from application.runtime.queries.list_widget_tokens import ListWidgetTokens

from .fakes_runtime import InMemoryWidgetTokenRepository


def test_issue_creates_a_token_scoped_to_the_project():
    repository = InMemoryWidgetTokenRepository()

    token = IssueWidgetToken(repository).execute("p1")

    assert token.project_id == "p1"
    assert token.is_active
    assert repository.get_by_token(token.token) == token


def test_issue_generates_a_different_token_each_time():
    repository = InMemoryWidgetTokenRepository()
    issue = IssueWidgetToken(repository)

    first = issue.execute("p1")
    second = issue.execute("p1")

    assert first.token != second.token
    assert first.id != second.id


def test_revoke_marks_the_token_inactive():
    repository = InMemoryWidgetTokenRepository()
    token = IssueWidgetToken(repository).execute("p1")

    RevokeWidgetToken(repository).execute(token.id)

    revoked = repository.get_by_id(token.id)
    assert not revoked.is_active
    assert revoked.revoked_at is not None


def test_revoke_is_idempotent():
    repository = InMemoryWidgetTokenRepository()
    token = IssueWidgetToken(repository).execute("p1")
    revoke = RevokeWidgetToken(repository)

    revoke.execute(token.id)
    first_revoked_at = repository.get_by_id(token.id).revoked_at
    revoke.execute(token.id)  # segunda vez -- no debe fallar ni cambiar nada.

    assert repository.get_by_id(token.id).revoked_at == first_revoked_at


def test_revoke_raises_for_an_unknown_token_id():
    repository = InMemoryWidgetTokenRepository()

    with pytest.raises(WidgetTokenNotFoundError):
        RevokeWidgetToken(repository).execute("no-existe")


def test_list_returns_only_the_project_own_tokens_most_recent_first():
    repository = InMemoryWidgetTokenRepository()
    issue = IssueWidgetToken(repository)
    issue.execute("otro-proyecto")
    first = issue.execute("p1")
    second = issue.execute("p1")

    tokens = ListWidgetTokens(repository).execute("p1")

    assert [t.id for t in tokens] == [second.id, first.id]


def test_list_includes_revoked_tokens():
    repository = InMemoryWidgetTokenRepository()
    token = IssueWidgetToken(repository).execute("p1")
    RevokeWidgetToken(repository).execute(token.id)

    tokens = ListWidgetTokens(repository).execute("p1")

    assert len(tokens) == 1
    assert not tokens[0].is_active


# ---------- max_access_level (Pista B.3 del ADR-003) ----------

def test_issue_without_max_access_level_defaults_to_restringido_no_ceiling():
    repository = InMemoryWidgetTokenRepository()

    token = IssueWidgetToken(repository).execute("p1")

    assert token.max_access_level == "restringido"


def test_issue_accepts_an_explicit_valid_max_access_level():
    repository = InMemoryWidgetTokenRepository()

    token = IssueWidgetToken(repository).execute("p1", max_access_level="publico")

    assert token.max_access_level == "publico"
    assert repository.get_by_token(token.token).max_access_level == "publico"


def test_issue_rejects_an_unknown_max_access_level():
    repository = InMemoryWidgetTokenRepository()

    with pytest.raises(ValueError):
        IssueWidgetToken(repository).execute("p1", max_access_level="no-es-un-nivel-valido")
