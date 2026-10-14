"""Tipo SQLAlchemy compartido para columnas de fecha/hora (Ronda 83,
hallazgo real de usuario: "TypeError: can't compare offset-naive and
offset-aware datetimes" en Calidad -> Evaluación, ver bitácora).

Todas las entidades de dominio usan `_utcnow() == datetime.now(timezone.
utc)` (aware) como valor por defecto de sus campos de fecha (`started_at`,
`created_at`, etc. -- ver `domain/*/entities.py`). Sin embargo, SQLite no
preserva realmente el offset de un `datetime` aware al pasar por
`sqlalchemy.DateTime(timezone=True)`: el dialecto de SQLite serializa la
fecha por `strftime` de sus componentes (año, mes, día, hora...) e
IGNORA `tzinfo` al escribir; al releer, reconstruye un `datetime`
**naive** con esos mismos componentes -- sin lanzar ningún error ni
advertencia. Se confirmó empíricamente (round-trip real contra SQLite en
memoria) que un valor aware guardado y releído vuelve con
`tzinfo is None`.

Consecuencia real: un objeto de dominio recién creado en memoria (aware,
por el default `_utcnow()`) y ese mismo tipo de objeto releído de la base
de datos (naive, por la pérdida de offset de SQLite) no se pueden
comparar entre sí con `<`, `>`, resta, etc. -- exactamente lo que
reportó el usuario al comparar `EvaluationRun.started_at` de la corrida
recién terminada (en memoria, aware) contra las corridas "completas"
anteriores releídas de la base de datos (naive) en
`ui/quality/panel.py::_render_regression_comparison`.

`UTCDateTime` es un `TypeDecorator` que envuelve `DateTime(timezone=True)`
sin cambiar el tipo de columna real en SQLite (no hace falta ninguna
migración: el DDL sigue siendo `DATETIME`) y normaliza en las dos
direcciones:

- Al escribir (`process_bind_param`): si el valor es naive, se asume que
  ya representa UTC (todo el dominio usa `_utcnow()` como única fuente de
  "ahora") y se le adjunta `tzinfo=utc`; si ya es aware con otra zona, se
  convierte a UTC. Así toda fecha nueva se guarda de forma consistente.
- Al leer (`process_result_value`): si SQLite devuelve un valor naive
  (el caso normal, por la pérdida de offset ya descrita, incluida
  cualquier fila histórica guardada antes de esta corrección), se le
  reatribuye `tzinfo=utc` -- nunca se inventa una zona horaria distinta,
  solo se restaura la que el propio dominio siempre pretendió tener.

Con esto, cualquier `datetime` que salga de un repositorio de
infraestructura llega siempre aware en UTC, sin importar si la fila es
vieja (guardada antes de este arreglo) o nueva -- no hace falta
"parchar" cada sitio que compara u ordena fechas (`ui/quality/panel.py`,
`application/runtime/queries/evaluate_reopening_criteria.py`,
compuertas de liberación, tendencias, monitoreo...) ni recrear ningún
proyecto existente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """`DateTime(timezone=True)` que normaliza a UTC-aware en ambas
    direcciones -- ver el docstring del módulo para la causa raíz que
    esto corrige."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect: Dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect: Dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
