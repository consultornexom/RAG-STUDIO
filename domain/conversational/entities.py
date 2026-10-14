"""Entidades del contexto Conversacional (Etapa 5, "Diseño conversacional":
documento maestro, correspondencia "Fuentes → Metadatos → Fragmentos →
Índice → Intenciones → Variables → Filtros → Guardrails → Canalización
→ Pruebas → Evidencias → Liberación").

"La pieza central no es el modelo generativo ni la base vectorial. Es
la correspondencia controlada entre intención, datos mínimos,
metadatos, fuentes autorizadas, reglas de respuesta y canalización."
(RAG STUDIO.odt). Etapa 5 modela esa correspondencia como configuración
por proyecto -- nunca campos ni flujos rígidos por sector (documento
maestro, "no crear campos específicos en el código", "no construir un
flujo diferente por agente").

Alcance deliberado de esta iteración (documentado también en el README,
"Limitaciones conocidas"): el catálogo de acciones sobre reglas que
pide el documento ("Crear. Duplicar. Activar. Desactivar. Priorizar.
Agrupar. Simular. Detectar conflictos. Aprobar. Versionar. Exportar.")
se cubre con Crear + Activar/Desactivar + el propio Simulador -- el
resto (duplicar, agrupar, detectar conflictos automáticamente,
aprobación formal, versionado explícito, exportación) queda para una
iteración posterior, no bloquea poder diseñar y probar un agente
conversacional completo.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .text_normalization import normalize_field_name, strip_matching_quotes


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntentRiskLevel(str, Enum):
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"


class IntentResolutionMode(str, Enum):
    """Pista B.4 del ADR-003 (enrutamiento multi-índice determinista,
    docs proyecto/RAG_STUDIO_Propuesta_B4_Enrutamiento_Multiindice.docx):
    por cuál camino de application.rag.RagService se resuelve una
    intención cuando la acción final es RESPONDER. SEMANTICO (default,
    sin cambio de comportamiento respecto de antes de esta pista) usa
    search_hybrid, igual que siempre. ESTRUCTURADO usa primero
    query_structured (Pista B.2b) sobre los ChunkType.ESTRUCTURADO del
    proyecto -- si no encuentra filas, SimulateConversation degrada
    automáticamente a SEMANTICO antes de abstenerse (ver su docstring):
    marcar una intención como ESTRUCTURADO nunca debe dejarla peor que
    si hubiera quedado en SEMANTICO."""

    SEMANTICO = "semantico"
    ESTRUCTURADO = "estructurado"


class Intent(BaseModel):
    """Una intención conversacional (RAG STUDIO.odt: "Cada intención
    debe incluir: Nombre, Descripción, Ejemplos positivos, Ejemplos
    negativos, Prioridad, Nivel de riesgo, Datos mínimos, Datos
    opcionales, Preguntas aclaratorias, Filtros derivados, Regla de
    respuesta, Canalización alternativa")."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    description: str = ""
    positive_examples: list[str] = Field(default_factory=list)
    negative_examples: list[str] = Field(default_factory=list)
    priority: int = 0
    risk_level: IntentRiskLevel = IntentRiskLevel.BAJO
    required_variables: list[str] = Field(default_factory=list)
    """Códigos de ConversationalVariable ("datos mínimos") -- si
    faltan al simular, la conversación se detiene en "aclarar" antes
    de poder responder (ver application.conversational.queries.
    simulate_conversation)."""
    optional_variables: list[str] = Field(default_factory=list)
    clarifying_questions: dict[str, str] = Field(default_factory=dict)
    """Código de variable -> pregunta a hacer si falta ese dato."""
    response_rule: str = ""
    """Descripción libre de cómo debe responder el agente para esta
    intención -- no es código ejecutable, es la referencia que el
    simulador muestra en su reporte para que la persona diseñadora
    verifique que la respuesta generada respeta lo esperado."""
    fallback_channeling_code: Optional[str] = None
    """Código del ChannelingScheme a usar si esta intención termina
    canalizándose (por regla de guardrail o por falta de resultados)."""
    resolution_mode: IntentResolutionMode = IntentResolutionMode.SEMANTICO
    """Pista B.4 del ADR-003 -- ver IntentResolutionMode. Default
    SEMANTICO a propósito: toda intención ya existente (creada antes de
    esta capacidad) sigue resolviendo exactamente igual que siempre."""
    active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConversationalVariable(BaseModel):
    """Una "variable conversacional" (RAG STUDIO INVESTIGACION.odt:
    "Cada agente conversacional debe administrarse como un proyecto
    independiente" con sus propias variables -- nunca campos rígidos
    como "plantel" o "programa" fijos en el código).

    metadata_field_id es el puente documentado explícitamente:
    "Dato conversacional → Campo de metadatos → Filtro de recuperación"
    -- si se define, un valor proporcionado para esta variable durante
    la simulación se usa para filtrar los resultados de búsqueda a solo
    las fuentes cuyo metadato coincida (ver _metadata_filtering en
    application.conversational)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    code: str
    label: str
    description: str = ""
    metadata_field_id: Optional[str] = None
    structured_column: Optional[str] = None
    """Pista B.4 del ADR-003 -- mismo puente documentado arriba para
    metadata_field_id ("Dato conversacional → Campo → Filtro"), pero
    apuntando a la vía estructurada de B.2 en vez de a los metadatos de
    fuente: si se define, un valor proporcionado para esta variable se
    usa como filtro de igualdad contra esta columna de los bloques
    estructurados (domain.rag.structured_query.StructuredFilter) al
    resolver una intención con resolution_mode == ESTRUCTURADO. Es
    texto libre (el nombre de columna real del XLSX/CSV, ver
    Chunk.structured_content) -- a propósito no es una referencia a
    ningún catálogo, porque las columnas de un bloque estructurado no
    tienen ningún registro propio en el esquema, a diferencia de los
    campos de metadatos."""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class RuleType(str, Enum):
    """Los 13 tipos de regla del catálogo de guardrails (RAG STUDIO.odt:
    "Regla de elegibilidad/vigencia/validación/privacidad/seguridad/
    autoridad/aclaración/abstención/canalización/formato/citación/
    tono/límite operativo")."""

    ELEGIBILIDAD = "elegibilidad"
    VIGENCIA = "vigencia"
    VALIDACION = "validacion"
    PRIVACIDAD = "privacidad"
    SEGURIDAD = "seguridad"
    AUTORIDAD = "autoridad"
    ACLARACION = "aclaracion"
    ABSTENCION = "abstencion"
    CANALIZACION = "canalizacion"
    FORMATO = "formato"
    CITACION = "citacion"
    TONO = "tono"
    LIMITE_OPERATIVO = "limite_operativo"


class RuleOperator(str, Enum):
    """Operadores de condición ("[Campo] [Operador] [Valor]", RAG
    STUDIO.odt: "validation_status = VALIDATED", "valid_to >=
    fecha_actual", "confidence < 0.70", "user_authenticated = TRUE")."""

    IGUAL = "="
    DISTINTO = "!="
    MENOR = "<"
    MENOR_IGUAL = "<="
    MAYOR = ">"
    MAYOR_IGUAL = ">="
    CONTIENE = "contiene"


class RuleCondition(BaseModel):
    """Una comparación "campo operador valor" de una GuardrailRule.

    Ronda 87 (2026-10-02, hallazgo real de usuario): el campo se guarda
    en forma canónica (minúsculas, sin acentos, espacios → "_"), para que
    "Intención" o "nivel riesgo" se reconozcan como `intencion` /
    `nivel_riesgo`, y el valor pierde un par de comillas envolventes
    (`"Campus Norte"` → `Campus Norte`). Los campos que el motor conoce
    están en `domain.conversational.rule_evaluation.CONTEXT_FIELDS`."""

    field: str
    operator: RuleOperator
    value: str

    # Los validadores normalizan pero nunca rechazan: también se aplican
    # al LEER reglas ya guardadas, y una regla antigua con datos raros no
    # debe impedir abrir el proyecto. La validación de formato que sí
    # bloquea vive antes de guardar (ui.conversational.parsing.
    # describe_condition_problems).
    @field_validator("field")
    @classmethod
    def _campo_canonico(cls, v: str) -> str:
        return normalize_field_name(v)

    @field_validator("value")
    @classmethod
    def _valor_sin_comillas(cls, v: str) -> str:
        return strip_matching_quotes(v)


class RuleActionType(str, Enum):
    """La decisión que produce una regla cuando sus condiciones se
    cumplen -- vocabulario tomado directamente del documento maestro
    ("El agente debe preguntar. El agente debe abstenerse. O debe
    canalizar.")."""

    RESPONDER = "responder"
    ACLARAR = "aclarar"
    ABSTENERSE = "abstenerse"
    CANALIZAR = "canalizar"


ACTION_SEVERITY: dict[RuleActionType, int] = {
    RuleActionType.RESPONDER: 0,
    RuleActionType.ACLARAR: 1,
    RuleActionType.ABSTENERSE: 2,
    RuleActionType.CANALIZAR: 3,
}
"""Cuando varias reglas activas disparan a la vez, gana la más severa
(nunca la primera por casualidad de orden) -- canalizar es más severo
que abstenerse, que a su vez es más severo que solo aclarar. Ver
domain.conversational.rule_evaluation.select_firing_action."""


class GuardrailRule(BaseModel):
    """Una regla del catálogo de guardrails (RAG STUDIO.odt, ejemplo:
    SI intención=consultar procedimiento Y confianza<0.70 ENTONCES no
    responder, solicitar aclaración). `conditions` se combinan siempre
    con Y (todas deben cumplirse) -- una regla sin condiciones se
    considera siempre activa (guardrail incondicional, por ejemplo
    "toda intención de riesgo alto se canaliza")."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    rule_type: RuleType
    conditions: list[RuleCondition] = Field(default_factory=list)
    action: RuleActionType = RuleActionType.RESPONDER
    priority: int = 0
    active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ChannelingMedium(str, Enum):
    """RAG STUDIO.odt: "Correo. Archivo. Ticket. API. CRM. Mesa de
    ayuda. Operador. Registro manual."""

    CORREO = "correo"
    ARCHIVO = "archivo"
    TICKET = "ticket"
    API = "api"
    CRM = "crm"
    MESA_AYUDA = "mesa_ayuda"
    OPERADOR = "operador"
    REGISTRO_MANUAL = "registro_manual"


class ChannelingScheme(BaseModel):
    """Un esquema de canalización (RAG STUDIO.odt: "Motivo. Condición.
    Área destino. Prioridad. Datos obligatorios. Datos permitidos.
    Datos prohibidos. Resumen. Medio. Mensaje al usuario. Acción
    alternativa. Evidencia.").

    Para esta primera versión, la herramienta SIMULA la canalización y
    genera el paquete estructurado (ver SimulationTrace.channeling) en
    vez de integrarse con sistemas externos reales (correo, CRM,
    ticket...) -- decisión explícita del documento maestro: "la
    herramienta puede simular la canalización y generar el paquete
    estructurado, sin necesidad de integrar todos los sistemas
    externos"."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    code: str
    name: str
    reason: str = ""
    condition: str = ""
    target_area: str = ""
    priority: int = 0
    required_data: list[str] = Field(default_factory=list)
    allowed_data: list[str] = Field(default_factory=list)
    forbidden_data: list[str] = Field(default_factory=list)
    summary_template: str = ""
    medium: ChannelingMedium = ChannelingMedium.REGISTRO_MANUAL
    user_message: str = ""
    alternative_action: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
