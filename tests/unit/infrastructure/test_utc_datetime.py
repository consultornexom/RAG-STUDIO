"""Pruebas unitarias del TypeDecorator compartido `UTCDateTime` (Ronda
83, hallazgo real de usuario: "TypeError: can't compare offset-naive and
offset-aware datetimes" en Calidad -> Evaluación, ver bitácora).

Prueban directamente `process_bind_param`/`process_result_value` --
sin pasar por SQLAlchemy ni SQLite -- para aislar el comportamiento de
normalización del resto de la infraestructura. Las pruebas de
integración reales contra SQLite viven en
tests/integration/test_quality_repositories.py."""
from datetime import datetime, timedelta, timezone

from infrastructure.database.utc_datetime import UTCDateTime


def _decorator() -> UTCDateTime:
    return UTCDateTime()


def test_process_bind_param_attaches_utc_to_a_naive_datetime():
    naive = datetime(2026, 9, 4, 18, 0, 0)
    result = _decorator().process_bind_param(naive, dialect=None)
    assert result.tzinfo == timezone.utc
    assert result.replace(tzinfo=None) == naive


def test_process_bind_param_converts_a_non_utc_aware_datetime_to_utc():
    minus_six = timezone(timedelta(hours=-6))
    aware_local = datetime(2026, 9, 4, 12, 0, 0, tzinfo=minus_six)
    result = _decorator().process_bind_param(aware_local, dialect=None)
    assert result.tzinfo == timezone.utc
    assert result == datetime(2026, 9, 4, 18, 0, 0, tzinfo=timezone.utc)


def test_process_bind_param_passes_through_none():
    assert _decorator().process_bind_param(None, dialect=None) is None


def test_process_result_value_attaches_utc_to_a_naive_datetime_read_back():
    # Este es el caso real: SQLite devuelve un datetime naive aunque la
    # columna esté declarada con DateTime(timezone=True) -- ver el
    # docstring de infrastructure/database/utc_datetime.py.
    naive_from_sqlite = datetime(2026, 8, 1, 9, 0, 0)
    result = _decorator().process_result_value(naive_from_sqlite, dialect=None)
    assert result.tzinfo == timezone.utc
    assert result.replace(tzinfo=None) == naive_from_sqlite


def test_process_result_value_passes_through_none():
    assert _decorator().process_result_value(None, dialect=None) is None


def _simulate_sqlite_round_trip(decorator: UTCDateTime, value: datetime) -> datetime:
    """`process_bind_param` normaliza a UTC-aware antes de escribir, pero
    el dialecto real de SQLite serializa por strftime e ignora tzinfo --
    el valor que de verdad vuelve a `process_result_value` en producción
    es naive, sin importar qué tan "aware" haya sido lo que se escribió."""
    bound = decorator.process_bind_param(value, dialect=None)
    naive_as_sqlite_would_return_it = bound.replace(tzinfo=None) if bound is not None else None
    return decorator.process_result_value(naive_as_sqlite_would_return_it, dialect=None)


def test_round_trip_naive_and_aware_inputs_are_comparable_after_bind_and_result():
    # Simula el escenario reportado: un valor "histórico" que se
    # escribió naive (antes de esta corrección) y uno "nuevo" que se
    # escribe aware -- ambos pasan por el mismo ciclo real de SQLite
    # (que ignora tzinfo al serializar) y deben poder compararse entre
    # sí sin TypeError después de pasar por UTCDateTime.
    decorator = _decorator()

    historic_naive = datetime(2026, 8, 1, 9, 0, 0)
    written_then_read_historic = _simulate_sqlite_round_trip(decorator, historic_naive)

    newest_aware = datetime.now(timezone.utc)
    written_then_read_newest = _simulate_sqlite_round_trip(decorator, newest_aware)

    assert written_then_read_historic < written_then_read_newest
