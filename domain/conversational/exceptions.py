"""Excepciones del contexto Conversacional."""
from __future__ import annotations


class ConversationalDomainError(Exception):
    """Base de las excepciones del contexto Conversacional."""


class IntentNotFoundError(ConversationalDomainError):
    def __init__(self, project_id: str, intent_id: str):
        super().__init__(f"No existe la intención {intent_id!r} en el proyecto {project_id!r}.")


class ConversationalVariableNotFoundError(ConversationalDomainError):
    def __init__(self, project_id: str, variable_id: str):
        super().__init__(f"No existe la variable conversacional {variable_id!r} en el proyecto {project_id!r}.")


class GuardrailRuleNotFoundError(ConversationalDomainError):
    def __init__(self, project_id: str, rule_id: str):
        super().__init__(f"No existe la regla {rule_id!r} en el proyecto {project_id!r}.")


class ChannelingSchemeNotFoundError(ConversationalDomainError):
    def __init__(self, project_id: str, scheme_id: str):
        super().__init__(f"No existe el esquema de canalización {scheme_id!r} en el proyecto {project_id!r}.")


class DuplicateConversationalCodeError(ConversationalDomainError):
    """Ronda 87 (2026-10-02): el código de un esquema de canalización o
    de una variable conversacional ya existe en el proyecto. Antes la
    interfaz mostraba el error crudo de SQLite ("UNIQUE constraint
    failed: channeling_scheme.project_id, channeling_scheme.code")."""

    def __init__(self, kind: str, code: str):
        super().__init__(
            f"Ya existe {kind} con el código {code!r} en este proyecto. Use otro código o edite el existente."
        )
        self.kind = kind
        self.code = code
