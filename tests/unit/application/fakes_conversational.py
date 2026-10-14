"""Dobles de prueba en memoria para el contexto Conversacional (Etapa 5)."""
from __future__ import annotations

from typing import Optional

from domain.conversational.entities import ChannelingScheme, ConversationalVariable, GuardrailRule, Intent
from domain.conversational.ports import (
    ChannelingSchemeRepository, ConversationalVariableRepository, GuardrailRuleRepository, IntentRepository,
)


class InMemoryIntentRepository(IntentRepository):
    def __init__(self):
        self._by_id: dict[str, Intent] = {}

    def save(self, intent: Intent) -> None:
        self._by_id[intent.id] = intent

    def get(self, project_id: str, intent_id: str) -> Optional[Intent]:
        intent = self._by_id.get(intent_id)
        return intent if intent and intent.project_id == project_id else None

    def list_for_project(self, project_id: str) -> list[Intent]:
        return [i for i in self._by_id.values() if i.project_id == project_id]

    def delete(self, project_id: str, intent_id: str) -> None:
        intent = self._by_id.get(intent_id)
        if intent is not None and intent.project_id == project_id:
            del self._by_id[intent_id]


class InMemoryConversationalVariableRepository(ConversationalVariableRepository):
    def __init__(self):
        self._by_id: dict[str, ConversationalVariable] = {}

    def save(self, variable: ConversationalVariable) -> None:
        self._by_id[variable.id] = variable

    def get(self, project_id: str, variable_id: str) -> Optional[ConversationalVariable]:
        variable = self._by_id.get(variable_id)
        return variable if variable and variable.project_id == project_id else None

    def list_for_project(self, project_id: str) -> list[ConversationalVariable]:
        return [v for v in self._by_id.values() if v.project_id == project_id]


class InMemoryGuardrailRuleRepository(GuardrailRuleRepository):
    def __init__(self):
        self._by_id: dict[str, GuardrailRule] = {}

    def save(self, rule: GuardrailRule) -> None:
        self._by_id[rule.id] = rule

    def get(self, project_id: str, rule_id: str) -> Optional[GuardrailRule]:
        rule = self._by_id.get(rule_id)
        return rule if rule and rule.project_id == project_id else None

    def list_for_project(self, project_id: str) -> list[GuardrailRule]:
        return [r for r in self._by_id.values() if r.project_id == project_id]

    def delete(self, project_id: str, rule_id: str) -> None:
        rule = self._by_id.get(rule_id)
        if rule is not None and rule.project_id == project_id:
            del self._by_id[rule_id]


class InMemoryChannelingSchemeRepository(ChannelingSchemeRepository):
    def __init__(self):
        self._by_id: dict[str, ChannelingScheme] = {}

    def save(self, scheme: ChannelingScheme) -> None:
        self._by_id[scheme.id] = scheme

    def get(self, project_id: str, scheme_id: str) -> Optional[ChannelingScheme]:
        scheme = self._by_id.get(scheme_id)
        return scheme if scheme and scheme.project_id == project_id else None

    def get_by_code(self, project_id: str, code: str) -> Optional[ChannelingScheme]:
        return next(
            (s for s in self._by_id.values() if s.project_id == project_id and s.code == code), None
        )

    def list_for_project(self, project_id: str) -> list[ChannelingScheme]:
        return [s for s in self._by_id.values() if s.project_id == project_id]
