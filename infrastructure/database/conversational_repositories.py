"""Implementación concreta de los 4 repositorios del contexto
Conversacional (ADR-001, sección 4)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select

from domain.conversational.entities import (
    ChannelingMedium, ChannelingScheme, ConversationalVariable, GuardrailRule, Intent, IntentResolutionMode,
    IntentRiskLevel, RuleActionType, RuleCondition, RuleOperator, RuleType,
)
from domain.conversational.ports import (
    ChannelingSchemeRepository, ConversationalVariableRepository, GuardrailRuleRepository, IntentRepository,
)
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import ChannelingSchemeRecord, ConversationalVariableRecord, GuardrailRuleRecord, IntentRecord


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyIntentRepository(IntentRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, intent: Intent) -> None:
        with _session_factory_for(self._paths, intent.project_id)() as session:
            record = session.get(IntentRecord, intent.id)
            if record is None:
                record = IntentRecord(id=intent.id, project_id=intent.project_id)
                session.add(record)
            record.name = intent.name
            record.description = intent.description
            record.positive_examples = json.dumps(intent.positive_examples)
            record.negative_examples = json.dumps(intent.negative_examples)
            record.priority = intent.priority
            record.risk_level = intent.risk_level.value
            record.required_variables = json.dumps(intent.required_variables)
            record.optional_variables = json.dumps(intent.optional_variables)
            record.clarifying_questions = json.dumps(intent.clarifying_questions)
            record.response_rule = intent.response_rule
            record.fallback_channeling_code = intent.fallback_channeling_code
            record.resolution_mode = intent.resolution_mode.value
            record.active = intent.active
            record.created_at = intent.created_at
            record.updated_at = intent.updated_at
            session.commit()

    def get(self, project_id: str, intent_id: str) -> Optional[Intent]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(IntentRecord, intent_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_intent(record)

    def list_for_project(self, project_id: str) -> list[Intent]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(IntentRecord).where(IntentRecord.project_id == project_id).order_by(IntentRecord.name)
            ).scalars().all()
            return [_record_to_intent(record) for record in records]

    def delete(self, project_id: str, intent_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(IntentRecord, intent_id)
            if record is not None and record.project_id == project_id:
                session.delete(record)
                session.commit()


class SqlAlchemyConversationalVariableRepository(ConversationalVariableRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, variable: ConversationalVariable) -> None:
        with _session_factory_for(self._paths, variable.project_id)() as session:
            record = session.get(ConversationalVariableRecord, variable.id)
            if record is None:
                record = ConversationalVariableRecord(id=variable.id, project_id=variable.project_id)
                session.add(record)
            record.code = variable.code
            record.label = variable.label
            record.description = variable.description
            record.metadata_field_id = variable.metadata_field_id
            record.structured_column = variable.structured_column
            record.created_at = variable.created_at
            record.updated_at = variable.updated_at
            session.commit()

    def get(self, project_id: str, variable_id: str) -> Optional[ConversationalVariable]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(ConversationalVariableRecord, variable_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_variable(record)

    def list_for_project(self, project_id: str) -> list[ConversationalVariable]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ConversationalVariableRecord)
                .where(ConversationalVariableRecord.project_id == project_id)
                .order_by(ConversationalVariableRecord.code)
            ).scalars().all()
            return [_record_to_variable(record) for record in records]


class SqlAlchemyGuardrailRuleRepository(GuardrailRuleRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, rule: GuardrailRule) -> None:
        with _session_factory_for(self._paths, rule.project_id)() as session:
            record = session.get(GuardrailRuleRecord, rule.id)
            if record is None:
                record = GuardrailRuleRecord(id=rule.id, project_id=rule.project_id)
                session.add(record)
            record.name = rule.name
            record.rule_type = rule.rule_type.value
            record.conditions = json.dumps([condition.model_dump(mode="json") for condition in rule.conditions])
            record.action = rule.action.value
            record.priority = rule.priority
            record.active = rule.active
            record.created_at = rule.created_at
            record.updated_at = rule.updated_at
            session.commit()

    def get(self, project_id: str, rule_id: str) -> Optional[GuardrailRule]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(GuardrailRuleRecord, rule_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_rule(record)

    def list_for_project(self, project_id: str) -> list[GuardrailRule]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(GuardrailRuleRecord)
                .where(GuardrailRuleRecord.project_id == project_id)
                .order_by(GuardrailRuleRecord.priority.desc())
            ).scalars().all()
            return [_record_to_rule(record) for record in records]

    def delete(self, project_id: str, rule_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(GuardrailRuleRecord, rule_id)
            if record is not None and record.project_id == project_id:
                session.delete(record)
                session.commit()


class SqlAlchemyChannelingSchemeRepository(ChannelingSchemeRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, scheme: ChannelingScheme) -> None:
        with _session_factory_for(self._paths, scheme.project_id)() as session:
            record = session.get(ChannelingSchemeRecord, scheme.id)
            if record is None:
                record = ChannelingSchemeRecord(id=scheme.id, project_id=scheme.project_id)
                session.add(record)
            record.code = scheme.code
            record.name = scheme.name
            record.reason = scheme.reason
            record.condition = scheme.condition
            record.target_area = scheme.target_area
            record.priority = scheme.priority
            record.required_data = json.dumps(scheme.required_data)
            record.allowed_data = json.dumps(scheme.allowed_data)
            record.forbidden_data = json.dumps(scheme.forbidden_data)
            record.summary_template = scheme.summary_template
            record.medium = scheme.medium.value
            record.user_message = scheme.user_message
            record.alternative_action = scheme.alternative_action
            record.active = scheme.active
            record.created_at = scheme.created_at
            record.updated_at = scheme.updated_at
            session.commit()

    def get(self, project_id: str, scheme_id: str) -> Optional[ChannelingScheme]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(ChannelingSchemeRecord, scheme_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_scheme(record)

    def get_by_code(self, project_id: str, code: str) -> Optional[ChannelingScheme]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(ChannelingSchemeRecord).where(
                    ChannelingSchemeRecord.project_id == project_id, ChannelingSchemeRecord.code == code,
                )
            ).scalars().first()
            if record is None:
                return None
            return _record_to_scheme(record)

    def list_for_project(self, project_id: str) -> list[ChannelingScheme]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ChannelingSchemeRecord)
                .where(ChannelingSchemeRecord.project_id == project_id)
                .order_by(ChannelingSchemeRecord.code)
            ).scalars().all()
            return [_record_to_scheme(record) for record in records]


def _record_to_intent(record: IntentRecord) -> Intent:
    return Intent(
        id=record.id, project_id=record.project_id, name=record.name, description=record.description,
        positive_examples=json.loads(record.positive_examples), negative_examples=json.loads(record.negative_examples),
        priority=record.priority, risk_level=IntentRiskLevel(record.risk_level),
        required_variables=json.loads(record.required_variables), optional_variables=json.loads(record.optional_variables),
        clarifying_questions=json.loads(record.clarifying_questions), response_rule=record.response_rule,
        fallback_channeling_code=record.fallback_channeling_code,
        resolution_mode=IntentResolutionMode(record.resolution_mode), active=record.active,
        created_at=record.created_at, updated_at=record.updated_at,
    )


def _record_to_variable(record: ConversationalVariableRecord) -> ConversationalVariable:
    return ConversationalVariable(
        id=record.id, project_id=record.project_id, code=record.code, label=record.label,
        description=record.description, metadata_field_id=record.metadata_field_id,
        structured_column=record.structured_column,
        created_at=record.created_at, updated_at=record.updated_at,
    )


def _record_to_rule(record: GuardrailRuleRecord) -> GuardrailRule:
    conditions = [
        RuleCondition(field=item["field"], operator=RuleOperator(item["operator"]), value=item["value"])
        for item in json.loads(record.conditions)
    ]
    return GuardrailRule(
        id=record.id, project_id=record.project_id, name=record.name, rule_type=RuleType(record.rule_type),
        conditions=conditions, action=RuleActionType(record.action), priority=record.priority,
        active=record.active, created_at=record.created_at, updated_at=record.updated_at,
    )


def _record_to_scheme(record: ChannelingSchemeRecord) -> ChannelingScheme:
    return ChannelingScheme(
        id=record.id, project_id=record.project_id, code=record.code, name=record.name,
        reason=record.reason, condition=record.condition, target_area=record.target_area,
        priority=record.priority, required_data=json.loads(record.required_data),
        allowed_data=json.loads(record.allowed_data), forbidden_data=json.loads(record.forbidden_data),
        summary_template=record.summary_template, medium=ChannelingMedium(record.medium),
        user_message=record.user_message, alternative_action=record.alternative_action,
        active=record.active, created_at=record.created_at, updated_at=record.updated_at,
    )
