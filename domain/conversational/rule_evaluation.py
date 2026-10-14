"""Evaluación de guardrails (Etapa 5, "Diseño conversacional").

RAG STUDIO.odt pide poder "construir condiciones sin programar:
[Campo] [Operador] [Valor]" (ejemplos: "validation_status = VALIDATED",
"valid_to >= fecha_actual", "confidence < 0.70", "user_authenticated =
TRUE"). En vez de un intérprete de expresiones genérico, cada
GuardrailRule.conditions es una lista de comparaciones simples
(campo, operador, valor) que se combinan siempre con Y -- suficiente
para el catálogo de reglas del documento maestro sin necesitar un
lenguaje de reglas completo.

Los valores a comparar salen de un `context: dict[str, str]` que
construye SimulateConversation (ver application.conversational.queries.
simulate_conversation) a partir de la intención emparejada, la
confianza, las variables faltantes, etc. -- este módulo no sabe nada de
intenciones ni de RAG, solo evalúa condiciones sobre lo que se le pasa.
"""
from __future__ import annotations

import re

from .entities import ACTION_SEVERITY, GuardrailRule, RuleActionType, RuleCondition, RuleOperator
from .text_normalization import normalize_field_name, normalize_text

CONTEXT_FIELDS: dict[str, str] = {
    "intencion": "Nombre de la intención reconocida (texto; sin distinguir mayúsculas ni acentos).",
    "confianza": (
        "Similitud de la consulta con el ejemplo más parecido de la intención reconocida, "
        "número entre 0 y 1 (p. ej. 0.50)."
    ),
    "nivel_riesgo": "Nivel de riesgo de la intención reconocida: bajo, medio o alto.",
    "variables_faltantes": "1 si falta algún dato mínimo de la intención, 0 si no falta ninguno.",
}
"""Ronda 87 (2026-10-02): los ÚNICOS campos que una condición de
guardrail puede consultar -- son las claves del `context` que arma
SimulateConversation (el mismo motor del Simulador y del runtime). Una
condición sobre cualquier otro nombre nunca se cumple (ver
evaluate_condition); la interfaz lo advierte antes de guardar. Se
documentan aquí, en un solo lugar, para que la UI, la validación y el
Manual del Usuario no puedan divergir."""


_NUMERO_CON_COMA = re.compile(r"^\s*[-+]?\d+,\d+\s*$")


def _as_number(value: str) -> float:
    """float() que acepta también coma decimal ("0,70"), habitual al
    escribir en español (Ronda 87). Antes "confianza < 0,70" se trataba
    como texto y la condición nunca se cumplía."""
    texto = str(value)
    if _NUMERO_CON_COMA.match(texto):
        texto = texto.replace(",", ".")
    return float(texto)


def _coerce_pair(actual: str, expected: str) -> tuple:
    """Compara como números si ambos lados lo permiten (para que
    "confianza < 0.70" funcione con comparaciones numéricas reales),
    si no como texto en minúsculas (para que "intencion = Consultar
    Requisitos" no dependa de mayúsculas/acentos exactos)."""
    try:
        return _as_number(actual), _as_number(expected)
    except (TypeError, ValueError):
        # Ronda 87: además de minúsculas, sin acentos -- lo que este
        # docstring siempre prometió pero el código no hacía.
        return normalize_text(actual), normalize_text(expected)


def evaluate_condition(condition: RuleCondition, context: dict[str, str]) -> bool:
    field = normalize_field_name(condition.field)
    if field not in context:
        # Un campo que el contexto no conoce nunca cumple la
        # condición -- se prefiere que la regla no dispare (falso
        # negativo, revisable a simple vista en el reporte del
        # simulador) a que dispare por un campo mal escrito sin avisar.
        return False
    actual, expected = _coerce_pair(context[field], condition.value)

    if condition.operator == RuleOperator.IGUAL:
        return actual == expected
    if condition.operator == RuleOperator.DISTINTO:
        return actual != expected
    if condition.operator == RuleOperator.CONTIENE:
        # Siempre como texto (Ronda 87): si ambos lados parecían
        # números, _coerce_pair los convertía a float y "contiene"
        # comparaba sus representaciones ("2026" -> "2026.0").
        return normalize_text(condition.value) in normalize_text(context[field])
    # El resto de los operadores solo tienen sentido si ambos lados se
    # pudieron interpretar como número -- si no, se tratan como "no
    # cumple" en vez de comparar strings lexicográficamente (que daría
    # resultados sin sentido para el usuario, p. ej. "9" < "80").
    if not isinstance(actual, float) or not isinstance(expected, float):
        return False
    if condition.operator == RuleOperator.MENOR:
        return actual < expected
    if condition.operator == RuleOperator.MENOR_IGUAL:
        return actual <= expected
    if condition.operator == RuleOperator.MAYOR:
        return actual > expected
    if condition.operator == RuleOperator.MAYOR_IGUAL:
        return actual >= expected
    return False  # pragma: no cover - todos los RuleOperator están cubiertos arriba


def evaluate_rule(rule: GuardrailRule, context: dict[str, str]) -> bool:
    """Una regla sin condiciones se considera siempre activa
    (guardrail incondicional) -- por ejemplo, una regla de "tono" que
    aplique a toda respuesta sin excepción."""
    if not rule.active:
        return False
    return all(evaluate_condition(condition, context) for condition in rule.conditions)


def select_firing_action(
    rules: list[GuardrailRule], context: dict[str, str],
) -> tuple[RuleActionType, list[GuardrailRule]]:
    """Evalúa todas las reglas activas contra `context` y devuelve la
    acción más severa entre las que dispararon (ver
    domain.conversational.entities.ACTION_SEVERITY), junto con la
    lista de reglas que dispararon (para el reporte del simulador:
    "Reglas activadas"). RESPONDER + lista vacía si ninguna regla
    dispara -- no hay ningún guardrail que impida responder."""
    fired = [rule for rule in rules if evaluate_rule(rule, context)]
    if not fired:
        return RuleActionType.RESPONDER, []
    most_severe = max(fired, key=lambda rule: ACTION_SEVERITY[rule.action])
    return most_severe.action, fired
