"""Pruebas unitarias de apply_filters/apply_aggregation (Pista B.2b del
ADR-003, DSL cerrado de filtros y agregaciones sobre bloques
estructurados)."""
import pytest

from domain.rag.structured_query import (
    StructuredAggregation, StructuredFilter, StructuredQueryRow, apply_aggregation, apply_filters,
)


def _row(**values) -> StructuredQueryRow:
    return StructuredQueryRow(
        chunk_id="c1", source_id="s1", section_title="Programas", row_index=0, values=values,
    )


# ---------- apply_filters ----------

def test_filters_igual_case_insensitive_text():
    rows = [_row(codigo="ISC"), _row(codigo="LAE")]
    result = apply_filters(rows, [StructuredFilter(column="codigo", operator="==", value="isc")])
    assert [r.values["codigo"] for r in result] == ["ISC"]


def test_filters_distinto():
    rows = [_row(codigo="ISC"), _row(codigo="LAE")]
    result = apply_filters(rows, [StructuredFilter(column="codigo", operator="!=", value="ISC")])
    assert [r.values["codigo"] for r in result] == ["LAE"]


def test_filters_contiene_substring_case_insensitive():
    rows = [_row(nombre="Ingeniería en Sistemas"), _row(nombre="Licenciatura en Administración")]
    result = apply_filters(rows, [StructuredFilter(column="nombre", operator="contains", value="ingenieria")])
    # "Ingeniería" con acento vs "ingenieria" sin acento: contains es
    # substring literal (no normaliza acentos) -- se prueba el caso
    # exacto en minúsculas, no una búsqueda difusa.
    assert result == []
    result = apply_filters(rows, [StructuredFilter(column="nombre", operator="contains", value="Sistemas")])
    assert len(result) == 1


def test_filters_numeric_comparisons_coerce_text_to_number():
    rows = [_row(duracion="9"), _row(duracion="12")]
    assert [r.values["duracion"] for r in apply_filters(
        rows, [StructuredFilter(column="duracion", operator=">", value=10)]
    )] == ["12"]
    assert [r.values["duracion"] for r in apply_filters(
        rows, [StructuredFilter(column="duracion", operator="<=", value="9")]
    )] == ["9"]


def test_filters_relational_operator_on_non_numeric_value_never_matches():
    rows = [_row(nombre="ISC")]
    assert apply_filters(rows, [StructuredFilter(column="nombre", operator=">", value="1")]) == []


def test_filters_row_missing_column_never_matches():
    rows = [_row(codigo="ISC")]
    assert apply_filters(rows, [StructuredFilter(column="plantel", operator="==", value="Mérida")]) == []


def test_filters_combine_with_and():
    rows = [_row(codigo="ISC", plantel="Mérida"), _row(codigo="ISC", plantel="Progreso")]
    result = apply_filters(rows, [
        StructuredFilter(column="codigo", operator="==", value="ISC"),
        StructuredFilter(column="plantel", operator="==", value="Mérida"),
    ])
    assert len(result) == 1
    assert result[0].values["plantel"] == "Mérida"


def test_filters_empty_list_returns_all_rows():
    rows = [_row(codigo="ISC"), _row(codigo="LAE")]
    assert apply_filters(rows, []) == rows


# ---------- apply_aggregation ----------

def test_aggregation_count_without_group_by():
    rows = [_row(codigo="ISC"), _row(codigo="LAE"), _row(codigo="LDG")]
    buckets = apply_aggregation(rows, StructuredAggregation(function="count"))
    assert len(buckets) == 1
    assert buckets[0].group_value is None
    assert buckets[0].value == 3.0


def test_aggregation_sum_group_by():
    rows = [
        _row(plantel="Mérida", matricula="100"),
        _row(plantel="Mérida", matricula="50"),
        _row(plantel="Progreso", matricula="30"),
    ]
    buckets = apply_aggregation(
        rows, StructuredAggregation(function="sum", column="matricula", group_by="plantel"),
    )
    by_group = {b.group_value: b.value for b in buckets}
    assert by_group == {"Mérida": 150.0, "Progreso": 30.0}


def test_aggregation_avg_min_max():
    rows = [_row(duracion="9"), _row(duracion="12"), _row(duracion="6")]
    avg = apply_aggregation(rows, StructuredAggregation(function="avg", column="duracion"))[0]
    minimo = apply_aggregation(rows, StructuredAggregation(function="min", column="duracion"))[0]
    maximo = apply_aggregation(rows, StructuredAggregation(function="max", column="duracion"))[0]
    assert avg.value == pytest.approx(9.0)
    assert minimo.value == 6.0
    assert maximo.value == 12.0


def test_aggregation_sum_with_no_numeric_values_is_zero_but_avg_is_none():
    rows = [_row(matricula="no-disponible")]
    total = apply_aggregation(rows, StructuredAggregation(function="sum", column="matricula"))[0]
    promedio = apply_aggregation(rows, StructuredAggregation(function="avg", column="matricula"))[0]
    assert total.value == 0.0
    assert promedio.value is None


def test_aggregation_group_by_excludes_rows_missing_the_group_column():
    rows = [_row(plantel="Mérida", matricula="10"), _row(matricula="5")]  # sin "plantel"
    buckets = apply_aggregation(
        rows, StructuredAggregation(function="sum", column="matricula", group_by="plantel"),
    )
    assert len(buckets) == 1
    assert buckets[0].group_value == "Mérida"
    assert buckets[0].value == 10.0


def test_aggregation_requires_column_unless_count():
    with pytest.raises(ValueError):
        StructuredAggregation(function="sum")
    StructuredAggregation(function="count")  # no lanza


# ---------- row_index (Pista C.2a del ADR-003) ----------

def test_row_index_distinguishes_rows_with_identical_values():
    # Sin row_index, dos filas con los mismos valores eran
    # indistinguibles -- este es exactamente el caso que row_index
    # existe para resolver.
    first = StructuredQueryRow(
        chunk_id="c1", source_id="s1", section_title="Programas", row_index=0, values={"codigo": "ISC"},
    )
    second = StructuredQueryRow(
        chunk_id="c1", source_id="s1", section_title="Programas", row_index=1, values={"codigo": "ISC"},
    )
    assert first.values == second.values
    assert first.row_index != second.row_index
