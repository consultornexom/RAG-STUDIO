"""Vocabularios que la UI necesita para construir formularios, sin
tener que importar domain directamente (ADR-001, sección 4)."""
from __future__ import annotations

from domain.conversational.entities import (
    ChannelingMedium, IntentResolutionMode, IntentRiskLevel, RuleActionType, RuleOperator, RuleType,
)
from domain.conversational.rule_evaluation import CONTEXT_FIELDS

INTENT_RISK_LEVEL_OPTIONS: list[str] = [level.value for level in IntentRiskLevel]
RULE_TYPE_OPTIONS: list[str] = [rule_type.value for rule_type in RuleType]
RULE_ACTION_OPTIONS: list[str] = [action.value for action in RuleActionType]
CHANNELING_MEDIUM_OPTIONS: list[str] = [medium.value for medium in ChannelingMedium]
RESOLUTION_MODE_OPTIONS: list[str] = [mode.value for mode in IntentResolutionMode]
"""Pista B.4 del ADR-003: vía de resolución de una intención -- ver
domain.conversational.entities.IntentResolutionMode."""

CONDITION_FIELDS: dict[str, str] = dict(CONTEXT_FIELDS)
"""Ronda 87: campos que una condición de guardrail puede usar, con su
descripción -- para la ayuda en pantalla y la validación antes de
guardar (ver ui.conversational.parsing.describe_condition_problems)."""
CONDITION_OPERATOR_OPTIONS: list[str] = [operator.value for operator in RuleOperator]
