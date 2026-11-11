"""Fachada de application para el contexto Conversacional (Etapa 5,
"Diseño conversacional")."""
from __future__ import annotations

from typing import Optional

from application.rag.service import RagService
from domain.conversational.entities import (
    ChannelingScheme, ConversationalVariable, GuardrailRule, Intent, IntentResolutionMode, IntentRiskLevel,
    RuleActionType, RuleCondition, RuleType,
)
from domain.conversational.ports import (
    ChannelingSchemeRepository, ConversationalVariableRepository, GuardrailRuleRepository, IntentRepository,
)
from domain.documents.entities import AccessLevel
from domain.metadata.ports import SourceMetadataRepository

from .commands.create_channeling_scheme import CreateChannelingScheme
from .commands.create_conversational_variable import CreateConversationalVariable
from .commands.create_guardrail_rule import CreateGuardrailRule
from .commands.create_intent import CreateIntent
from .commands.delete_guardrail_rule import DeleteGuardrailRule
from .commands.delete_intent import DeleteIntent
from .commands.set_channeling_scheme_active import SetChannelingSchemeActive
from .commands.set_guardrail_rule_active import SetGuardrailRuleActive
from .commands.set_intent_active import SetIntentActive
from .commands.update_channeling_scheme import UpdateChannelingScheme
from .commands.update_conversational_variable import UpdateConversationalVariable
from .commands.update_guardrail_rule import UpdateGuardrailRule
from .commands.update_intent import UpdateIntent
from .queries.find_rules_referencing_intent import FindRulesReferencingIntent
from .queries.list_channeling_schemes import ListChannelingSchemes
from .queries.list_conversational_variables import ListConversationalVariables
from .queries.list_guardrail_rules import ListGuardrailRules
from .queries.list_intents import ListIntents
from .queries.simulate_conversation import SimulateConversation, SimulationTrace


class ConversationalService:
    def __init__(
        self,
        intent_repository: IntentRepository,
        variable_repository: ConversationalVariableRepository,
        guardrail_repository: GuardrailRuleRepository,
        channeling_repository: ChannelingSchemeRepository,
        source_metadata_repository: SourceMetadataRepository,
        rag_service: RagService,
        *,
        source_repository=None,
        schema_repository=None,
        catalog_repository=None,
        agent_reranking=None,
    ):
        """source_repository/schema_repository/catalog_repository: ver
        SimulateConversation (Ronda 89) -- detección de variables en la
        consulta y filtro de metadatos previo a la búsqueda.
        agent_reranking (Ronda 102, C4): ajuste "Reranking en el agente"
        del proyecto, ver SimulateConversation."""
        self._create_intent = CreateIntent(intent_repository)
        self._set_intent_active = SetIntentActive(intent_repository)
        self._update_intent = UpdateIntent(intent_repository)
        self._delete_intent = DeleteIntent(intent_repository)
        self._list_intents = ListIntents(intent_repository)

        self._create_variable = CreateConversationalVariable(variable_repository)
        self._update_variable = UpdateConversationalVariable(variable_repository)
        self._list_variables = ListConversationalVariables(variable_repository)

        self._create_rule = CreateGuardrailRule(guardrail_repository)
        self._set_rule_active = SetGuardrailRuleActive(guardrail_repository)
        self._update_rule = UpdateGuardrailRule(guardrail_repository)
        self._delete_rule = DeleteGuardrailRule(guardrail_repository)
        self._list_rules = ListGuardrailRules(guardrail_repository)
        self._find_rules_referencing_intent = FindRulesReferencingIntent(guardrail_repository)

        self._create_scheme = CreateChannelingScheme(channeling_repository)
        self._set_scheme_active = SetChannelingSchemeActive(channeling_repository)
        self._update_scheme = UpdateChannelingScheme(channeling_repository)
        self._list_schemes = ListChannelingSchemes(channeling_repository)

        self._simulate = SimulateConversation(
            intent_repository, variable_repository, guardrail_repository, channeling_repository,
            source_metadata_repository, rag_service,
            source_repository=source_repository, schema_repository=schema_repository,
            catalog_repository=catalog_repository, agent_reranking=agent_reranking,
        )

    # ---------- intenciones ----------
    def create_intent(self, project_id: str, name: str, **kwargs) -> Intent:
        return self._create_intent.execute(project_id, name, **kwargs)

    def set_intent_active(self, project_id: str, intent_id: str, active: bool) -> Intent:
        return self._set_intent_active.execute(project_id, intent_id, active)

    def update_intent(
        self, project_id: str, intent_id: str, name: str, description: Optional[str] = None,
        resolution_mode: Optional[IntentResolutionMode] = None,
        positive_examples: Optional[list[str]] = None, negative_examples: Optional[list[str]] = None,
        priority: Optional[int] = None, risk_level: Optional[IntentRiskLevel] = None,
        required_variables: Optional[list[str]] = None, optional_variables: Optional[list[str]] = None,
        clarifying_questions: Optional[dict[str, str]] = None, response_rule: Optional[str] = None,
        fallback_channeling_code: Optional[str] = None,
    ) -> Intent:
        """Ronda 3 (punto 13): edición básica (nombre/descripción) --
        antes solo existía Activar/Desactivar, sin ninguna forma de
        corregir un error de escritura al crear la intención.
        resolution_mode (Pista B.4 del ADR-003): reclasificar una
        intención ya creada entre semántica y estructurada. Ampliado en
        el ajuste funcional del 2026-09-03 (hallazgo real de usuario,
        ver bitácora) a la ficha completa -- ver UpdateIntent."""
        return self._update_intent.execute(
            project_id, intent_id, name, description=description, resolution_mode=resolution_mode,
            positive_examples=positive_examples, negative_examples=negative_examples,
            priority=priority, risk_level=risk_level,
            required_variables=required_variables, optional_variables=optional_variables,
            clarifying_questions=clarifying_questions, response_rule=response_rule,
            fallback_channeling_code=fallback_channeling_code,
        )

    def delete_intent(self, project_id: str, intent_id: str) -> None:
        """Ajuste funcional del 2026-09-04 (hallazgo real de usuario,
        ver bitácora): mismo criterio que delete_guardrail_rule -- ver
        DeleteIntent y domain.conversational.ports.IntentRepository.
        delete sobre por qué no hace falta ningún chequeo de "en uso"."""
        self._delete_intent.execute(project_id, intent_id)

    def find_rules_referencing_intent(self, project_id: str, intent_name: str) -> list[GuardrailRule]:
        """Ronda 4: qué reglas de guardrail quedarían "sordas" en
        silencio si se renombra la intención `intent_name` -- ver
        FindRulesReferencingIntent. Pensado para avisar antes de
        confirmar un renombrado, no para bloquearlo."""
        return self._find_rules_referencing_intent.execute(project_id, intent_name)

    def list_intents(self, project_id: str) -> list[Intent]:
        return self._list_intents.execute(project_id)

    # ---------- variables conversacionales ----------
    def create_variable(
        self, project_id: str, code: str, label: str, description: str = "",
        metadata_field_id: Optional[str] = None, structured_column: Optional[str] = None,
    ) -> ConversationalVariable:
        return self._create_variable.execute(
            project_id, code, label, description=description, metadata_field_id=metadata_field_id,
            structured_column=structured_column,
        )

    def update_variable(
        self, project_id: str, variable_id: str, label: str, description: Optional[str] = None,
    ) -> ConversationalVariable:
        """Ronda 3 (punto 13): edición básica (etiqueta/descripción);
        `code` no es editable -- ver UpdateConversationalVariable."""
        return self._update_variable.execute(project_id, variable_id, label, description=description)

    def list_variables(self, project_id: str) -> list[ConversationalVariable]:
        return self._list_variables.execute(project_id)

    # ---------- guardrails ----------
    def create_guardrail_rule(
        self, project_id: str, name: str, rule_type: RuleType,
        conditions: Optional[list[RuleCondition]] = None,
        action: RuleActionType = RuleActionType.RESPONDER, priority: int = 0,
    ) -> GuardrailRule:
        return self._create_rule.execute(
            project_id, name, rule_type, conditions=conditions, action=action, priority=priority,
        )

    def set_guardrail_rule_active(self, project_id: str, rule_id: str, active: bool) -> GuardrailRule:
        return self._set_rule_active.execute(project_id, rule_id, active)

    def update_guardrail_rule(
        self, project_id: str, rule_id: str, name: str,
        rule_type: Optional[RuleType] = None,
        conditions: Optional[list] = None,
        action: Optional[RuleActionType] = None,
        priority: Optional[int] = None,
    ) -> GuardrailRule:
        """Ronda 3 (punto 13): solo el nombre. Ampliado en el ajuste
        funcional del 2026-09-03 (hallazgo real de usuario, ver
        bitácora) a la ficha completa -- ver UpdateGuardrailRule."""
        return self._update_rule.execute(
            project_id, rule_id, name, rule_type=rule_type, conditions=conditions,
            action=action, priority=priority,
        )

    def delete_guardrail_rule(self, project_id: str, rule_id: str) -> None:
        """Ajuste funcional del 2026-09-03 (hallazgo real de usuario,
        ver bitácora): el Manual del Usuario ya documentaba "eliminar y
        crear nuevamente" para cambiar la lógica de una regla, pero la
        interfaz nunca ofreció esta opción -- ver DeleteGuardrailRule."""
        self._delete_rule.execute(project_id, rule_id)

    def list_guardrail_rules(self, project_id: str) -> list[GuardrailRule]:
        return self._list_rules.execute(project_id)

    # ---------- canalización ----------
    def create_channeling_scheme(self, project_id: str, code: str, name: str, **kwargs) -> ChannelingScheme:
        return self._create_scheme.execute(project_id, code, name, **kwargs)

    def set_channeling_scheme_active(self, project_id: str, scheme_id: str, active: bool) -> ChannelingScheme:
        return self._set_scheme_active.execute(project_id, scheme_id, active)

    def update_channeling_scheme(self, project_id: str, scheme_id: str, name: str, **kwargs) -> ChannelingScheme:
        """Ronda 4 (punto 1): edición de la ficha completa (motivo,
        condición, área destino, datos requeridos/permitidos/
        prohibidos, plantilla, medio, mensaje, acción alternativa) --
        `code` no es editable, ver UpdateChannelingScheme."""
        return self._update_scheme.execute(project_id, scheme_id, name, **kwargs)

    def list_channeling_schemes(self, project_id: str) -> list[ChannelingScheme]:
        return self._list_schemes.execute(project_id)

    # ---------- simulador ----------
    def simulate(
        self, project_id: str, query_text: str, provided_variables: Optional[dict[str, str]] = None,
        source_id: Optional[str] = None, limit: int = 5,
        max_access_level: Optional[AccessLevel] = None,
    ) -> SimulationTrace:
        """max_access_level (Pista B.3 del ADR-003): ver
        SimulateConversation.execute -- None (default) preserva el
        comportamiento de siempre; `HandleIncomingMessage` es el único
        llamador real que lo pasa."""
        return self._simulate.execute(
            project_id, query_text, provided_variables=provided_variables, source_id=source_id, limit=limit,
            max_access_level=max_access_level,
        )
