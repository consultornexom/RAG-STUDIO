"""Pista B.2b del ADR-003 (docs proyecto/
RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx, sección 3.3): DSL cerrado
y determinista de filtros y agregaciones sobre chunks
ChunkType.ESTRUCTURADO -- nunca una consulta libre tipo SQL ni eval() de
expresiones, mismo espíritu que RuleCondition/evaluate_condition en
domain.conversational.rule_evaluation (un conjunto fijo y explícito de
operaciones, no una superficie abierta).

Este módulo es puro dominio: no sabe nada de ChunkRepository ni de
proyectos -- application.rag.queries.structured_query es quien reúne las
filas reales (desde Chunk.structured_content) y llama a
apply_filters/apply_aggregation."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class StructuredFilterOperator(str, Enum):
    """Conjunto cerrado de operadores de comparación -- ver sección 3.3
    del documento de diseño. CONTIENE es la única operación de texto
    libre permitida (substring, sin distinguir mayúsculas); el resto
    exige que ambos lados se puedan interpretar como número para
    MAYOR/MAYOR_IGUAL/MENOR/MENOR_IGUAL (ver `_coerce_pair`)."""

    IGUAL = "=="
    DISTINTO = "!="
    MAYOR = ">"
    MAYOR_IGUAL = ">="
    MENOR = "<"
    MENOR_IGUAL = "<="
    CONTIENE = "contains"


class StructuredAggregationFunction(str, Enum):
    """Conjunto cerrado de funciones de agregación -- ver sección 3.3
    del documento de diseño."""

    CONTEO = "count"
    SUMA = "sum"
    PROMEDIO = "avg"
    MINIMO = "min"
    MAXIMO = "max"


class StructuredFilter(BaseModel):
    """Una comparación (columna, operador, valor) -- las filas que no
    tienen `column` nunca cumplen el filtro (mismo criterio que
    evaluate_condition: un campo que la fila no conoce no dispara falso
    positivo, ver domain.conversational.rule_evaluation)."""

    column: str
    operator: StructuredFilterOperator
    value: Any


class StructuredAggregation(BaseModel):
    """Agregación opcional sobre las filas ya filtradas: `group_by`
    (columna, opcional -- sin ella se agrega todo en un solo total) +
    `function` sobre `column` (obligatoria salvo para CONTEO, que
    cuenta filas sin necesitar ninguna columna numérica)."""

    function: StructuredAggregationFunction
    column: Optional[str] = None
    group_by: Optional[str] = None

    @model_validator(mode="after")
    def _column_requerida_salvo_conteo(self) -> "StructuredAggregation":
        if self.function != StructuredAggregationFunction.CONTEO and self.column is None:
            raise ValueError(
                f"La función de agregación '{self.function.value}' requiere 'column' "
                "-- solo 'count' puede omitirla."
            )
        return self


class StructuredQueryRow(BaseModel):
    """Una fila de un bloque estructurado (Chunk.structured_content),
    con la trazabilidad mínima para saber de dónde vino -- mismo
    criterio de trazabilidad que INVESTIGACION.odt exige para
    resultados de búsqueda (documento/sección/página), adaptado aquí a
    chunk_id/source_id/section_title (el nombre de hoja o "datos" para
    CSV, ver ExtractionRecord.structured_blocks).

    row_index (Pista C.2a del ADR-003, docs proyecto/
    RAG_STUDIO_Propuesta_C2_Procedencia_Temporalidad.docx): posición
    (0-based) de esta fila dentro de
    chunk.structured_content["filas"] -- cierra la cadena
    archivo→hoja→fila→celda (la "celda" ya era direccionable como
    (columna, valor) vía `values`; sin row_index, dos filas con los
    mismos valores eran indistinguibles). Estable solo dentro de una
    misma extracción -- si la fuente se vuelve a extraer y las filas
    cambian de orden, el row_index de una fila puede cambiar entre una
    consulta y otra (mismo criterio que el resto de este proyecto:
    los chunks reflejan siempre el estado vigente, no un historial
    fila por fila)."""

    chunk_id: str
    source_id: str
    section_title: Optional[str] = None
    row_index: int
    values: dict[str, Any] = Field(default_factory=dict)


class StructuredAggregationBucket(BaseModel):
    """Un grupo del resultado de agregación. `group_value` es `None`
    cuando la agregación no pidió `group_by` (un solo total, sin
    agrupar) -- nunca cuando una fila simplemente no tenía la columna
    de agrupación: esas filas se excluyen de la agregación por
    completo (ver `apply_aggregation`), no forman su propio grupo
    "vacío" para no mezclar dos significados distintos de "sin dato"
    en la misma clave."""

    group_value: Optional[str] = None
    value: Optional[float] = None
    """None cuando el grupo no tiene ningún valor numérico interpretable
    en `column` (p. ej. todas las celdas vacías o no numéricas) y la
    función no es SUMA -- SUMA de cero valores numéricos es 0.0 (la
    suma vacía matemáticamente correcta), pero PROMEDIO/MINIMO/MAXIMO
    de cero valores no tienen una respuesta numérica razonable."""


class StructuredQueryResult(BaseModel):
    """`rows` son siempre las filas filtradas (antes de agrupar) --
    útiles para inspeccionar el detalle incluso cuando también se pidió
    `aggregation`. `aggregation` es `None` si no se pidió ninguna."""

    rows: list[StructuredQueryRow] = Field(default_factory=list)
    aggregation: Optional[list[StructuredAggregationBucket]] = None


def _coerce_pair(actual: Any, expected: Any) -> tuple:
    """Mismo criterio que domain.conversational.rule_evaluation._coerce_pair:
    compara como números si ambos lados lo permiten, si no como texto
    en minúsculas -- los valores de un bloque estructurado llegan como
    texto plano (ver infrastructure.extraction.text_extractors._cell_to_text),
    así que "12" debe poder compararse numéricamente contra 12 o "12.0"."""
    try:
        return float(actual), float(expected)
    except (TypeError, ValueError):
        return str(actual).strip().lower(), str(expected).strip().lower()


def _matches(values: dict[str, Any], filt: StructuredFilter) -> bool:
    if filt.column not in values:
        return False
    actual = values[filt.column]
    if filt.operator == StructuredFilterOperator.CONTIENE:
        return str(filt.value).strip().lower() in str(actual).strip().lower()
    actual_c, expected_c = _coerce_pair(actual, filt.value)
    if filt.operator == StructuredFilterOperator.IGUAL:
        return actual_c == expected_c
    if filt.operator == StructuredFilterOperator.DISTINTO:
        return actual_c != expected_c
    # MAYOR/MAYOR_IGUAL/MENOR/MENOR_IGUAL solo tienen sentido si ambos
    # lados se pudieron interpretar como número -- si no, "no cumple"
    # en vez de comparar texto lexicográficamente sin sentido para el
    # usuario (mismo criterio que evaluate_condition).
    if not isinstance(actual_c, float) or not isinstance(expected_c, float):
        return False
    if filt.operator == StructuredFilterOperator.MENOR:
        return actual_c < expected_c
    if filt.operator == StructuredFilterOperator.MENOR_IGUAL:
        return actual_c <= expected_c
    if filt.operator == StructuredFilterOperator.MAYOR:
        return actual_c > expected_c
    if filt.operator == StructuredFilterOperator.MAYOR_IGUAL:
        return actual_c >= expected_c
    return False  # pragma: no cover - todos los StructuredFilterOperator están cubiertos arriba


def apply_filters(rows: list[StructuredQueryRow], filters: list[StructuredFilter]) -> list[StructuredQueryRow]:
    """Filtro Y de todas las condiciones (mismo criterio que
    evaluate_rule: una lista de comparaciones simples, combinadas
    siempre con Y -- sin filtros, todas las filas pasan)."""
    if not filters:
        return list(rows)
    return [row for row in rows if all(_matches(row.values, f) for f in filters)]


def _numeric_values(rows: list[StructuredQueryRow], column: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        if column not in row.values:
            continue
        try:
            values.append(float(row.values[column]))
        except (TypeError, ValueError):
            continue
    return values


def _aggregate_value(rows: list[StructuredQueryRow], aggregation: StructuredAggregation) -> Optional[float]:
    if aggregation.function == StructuredAggregationFunction.CONTEO:
        return float(len(rows))
    # column no es None aquí -- lo garantiza el model_validator de
    # StructuredAggregation para cualquier función que no sea CONTEO.
    numeric = _numeric_values(rows, aggregation.column)  # type: ignore[arg-type]
    if not numeric:
        return 0.0 if aggregation.function == StructuredAggregationFunction.SUMA else None
    if aggregation.function == StructuredAggregationFunction.SUMA:
        return sum(numeric)
    if aggregation.function == StructuredAggregationFunction.PROMEDIO:
        return sum(numeric) / len(numeric)
    if aggregation.function == StructuredAggregationFunction.MINIMO:
        return min(numeric)
    if aggregation.function == StructuredAggregationFunction.MAXIMO:
        return max(numeric)
    return None  # pragma: no cover - todos los StructuredAggregationFunction están cubiertos arriba


def apply_aggregation(
    rows: list[StructuredQueryRow], aggregation: StructuredAggregation,
) -> list[StructuredAggregationBucket]:
    """Sin `group_by`: un solo bucket (`group_value=None`) sobre todas
    las filas. Con `group_by`: un bucket por valor distinto de esa
    columna -- las filas que no tienen esa columna se EXCLUYEN de la
    agregación por completo (no forman su propio grupo "sin dato"), ver
    docstring de StructuredAggregationBucket."""
    if aggregation.group_by is None:
        return [StructuredAggregationBucket(group_value=None, value=_aggregate_value(rows, aggregation))]
    groups: dict[str, list[StructuredQueryRow]] = {}
    for row in rows:
        if aggregation.group_by not in row.values:
            continue
        key = str(row.values[aggregation.group_by])
        groups.setdefault(key, []).append(row)
    return [
        StructuredAggregationBucket(group_value=key, value=_aggregate_value(group_rows, aggregation))
        for key, group_rows in groups.items()
    ]
