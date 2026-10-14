"""Puertos del contexto Conversacional. Implementados en infrastructure
(ADR-001, sección 4). project_id explícito en cada método -- mismo
criterio que domain.documents.ports/domain.metadata.ports: el
repositorio debe saber qué project.db abrir."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import ChannelingScheme, ConversationalVariable, GuardrailRule, Intent


class IntentRepository(ABC):
    @abstractmethod
    def save(self, intent: Intent) -> None: ...

    @abstractmethod
    def get(self, project_id: str, intent_id: str) -> Optional[Intent]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[Intent]: ...

    @abstractmethod
    def delete(self, project_id: str, intent_id: str) -> None:
        """Ajuste funcional del 2026-09-04 (hallazgo real de usuario:
        "en Guardrails sí permite tanto editar como eliminar y eso
        ayuda mucho en la operación... valide si en esta sección
        [Intenciones] es conveniente integrar la funcionalidad de
        Eliminar intención"), mismo criterio y misma conclusión que
        GuardrailRuleRepository.delete: sin chequeo de "en uso".
        Confirmado leyendo domain.quality.entities.TestCase
        (expected_intent), domain.runtime.entities (matched_intent) y
        el propio dominio de este contexto -- ninguna otra entidad de
        RAG STUDIO referencia una Intent por id; todas la referencian
        por nombre, como texto libre (mismo mecanismo ya documentado
        para find_rules_referencing_intent). Eliminar una intención
        tiene entonces la misma consecuencia -- y solo esa -- que
        renombrarla: una condición de guardrail "intencion = <nombre>"
        deja de cumplirse en silencio; por eso la interfaz reutiliza el
        mismo aviso de find_rules_referencing_intent antes de eliminar,
        no un chequeo de bloqueo nuevo."""
        ...


class ConversationalVariableRepository(ABC):
    @abstractmethod
    def save(self, variable: ConversationalVariable) -> None: ...

    @abstractmethod
    def get(self, project_id: str, variable_id: str) -> Optional[ConversationalVariable]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[ConversationalVariable]: ...


class GuardrailRuleRepository(ABC):
    @abstractmethod
    def save(self, rule: GuardrailRule) -> None: ...

    @abstractmethod
    def get(self, project_id: str, rule_id: str) -> Optional[GuardrailRule]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[GuardrailRule]: ...

    @abstractmethod
    def delete(self, project_id: str, rule_id: str) -> None:
        """Ajuste funcional del 2026-09-03 (hallazgo real de usuario,
        ver bitácora): el Manual del Usuario ya documentaba "eliminar y
        crear nuevamente" como la vía para cambiar tipo, condiciones,
        acción o prioridad de una regla, pero ni la interfaz ni esta
        capa tenían ningún método de borrado -- el usuario solo podía
        desactivarla. Sin chequeo de "en uso" (a diferencia de
        FieldDefinition o TestCase): ninguna otra entidad de este
        dominio referencia una GuardrailRule por id -- las condiciones
        de otras reglas y la evaluación del simulador solo comparan
        contra `intencion`/metadatos por texto libre, nunca contra el
        id de una regla."""
        ...


class ChannelingSchemeRepository(ABC):
    @abstractmethod
    def save(self, scheme: ChannelingScheme) -> None: ...

    @abstractmethod
    def get(self, project_id: str, scheme_id: str) -> Optional[ChannelingScheme]: ...

    @abstractmethod
    def get_by_code(self, project_id: str, code: str) -> Optional[ChannelingScheme]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[ChannelingScheme]: ...
