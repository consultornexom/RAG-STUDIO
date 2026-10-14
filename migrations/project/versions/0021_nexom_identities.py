"""RAG-INC-01, hito 01a — identidades persistentes del contrato NEXOM
Knowledge Package v1.0.0 (Alcance firmado, sección 4, hito 01a).

Agrega:
- ``project.knowledge_base_id``: UUID4 por proyecto, único, NOT NULL.
- ``source.lineage_id``: UUID4 por familia de versiones, NOT NULL, indexado.

Reglas (Alcance, hito 01a, y decisión de NEXOM del 2026-09-24 sobre linaje
no lineal):
1. Una familia es el conjunto de fuentes conectadas por
   ``supersedes_source_id`` hacia una raíz común. Puede ramificarse
   (una fuente superseded por varias); nunca tiene ciclos. Todas sus
   fuentes comparten ``lineage_id``.
2. ``supersedes_source_id`` que apunta a un id inexistente: la fuente es
   raíz de su propia cadena y queda en el log de la migración.
3. Cualquier ciclo (incluido S→S) aborta la migración ANTES de modificar
   nada, sin asignar identidades.
4. Valores UUID4: el relleno no es determinista; se garantiza consistencia
   por familia y persistencia una vez escrito.
5. Todo ocurre en una sola transacción de SQLite (SAVEPOINT) que incluye la
   actualización de ``alembic_version``: o queda todo, o no queda nada.
6. ``downgrade()`` se niega: revertir y volver a aplicar generaría ids
   distintos y rompería la continuidad con paquetes exportados. Solo acepta
   la bandera de anulación de las pruebas sobre copias desechables
   (``RAGSTUDIO_PERMITIR_DOWNGRADE_0021=1``). La vuelta atrás real es
   restaurar un respaldo.

No toca ``project_id`` ni ningún id local de fuente o chunk.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-14
"""
from __future__ import annotations

import logging
import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

logger = logging.getLogger("ragstudio.migraciones.0021")

PERMITIR_DOWNGRADE_ENV = "RAGSTUDIO_PERMITIR_DOWNGRADE_0021"
FALLO_DE_PRUEBA_ENV = "RAGSTUDIO_0021_FALLO_DE_PRUEBA"
"""Solo pruebas: nombre de una etapa ("tras_relleno", "tras_not_null") en la
que la migración lanza un error a propósito, para comprobar el rollback."""

_SAVEPOINT = "nexom_0021"


class MigracionIdentidadesError(RuntimeError):
    """La migración 0021 no puede aplicarse sin asignar identidades
    arbitrarias (por ejemplo, hay un ciclo de supersesión)."""


def _fallo_de_prueba(etapa: str) -> None:
    if os.environ.get(FALLO_DE_PRUEBA_ENV) == etapa:
        raise MigracionIdentidadesError(f"Fallo inyectado por prueba en la etapa {etapa!r}")


def calcular_familias(fuentes: list[tuple[str, str | None]]) -> tuple[dict[str, str], dict]:
    """Agrupa fuentes en familias. ``fuentes`` = [(id, supersedes_source_id)].

    Devuelve (raiz_por_fuente, informe). Lanza MigracionIdentidadesError si hay
    ciclos. Puro: no toca la base (se prueba por separado)."""
    ids = {fid for fid, _ in fuentes}
    padre: dict[str, str | None] = {}
    rotas: list[tuple[str, str]] = []
    for fid, sup in fuentes:
        if sup is not None and sup not in ids:
            rotas.append((fid, sup))
            padre[fid] = None
        else:
            padre[fid] = sup

    # Ciclos: grafo funcional (cada fuente supersede a lo sumo una).
    estado: dict[str, int] = {}  # 1 = en recorrido, 2 = terminado
    en_ciclo: set[str] = set()
    for inicio in sorted(ids):
        if estado.get(inicio) == 2:
            continue
        camino: list[str] = []
        actual: str | None = inicio
        while actual is not None and estado.get(actual) is None:
            estado[actual] = 1
            camino.append(actual)
            actual = padre[actual]
        if actual is not None and estado.get(actual) == 1:
            en_ciclo.update(camino[camino.index(actual):])
        for nodo in camino:
            estado[nodo] = 2
    if en_ciclo:
        raise MigracionIdentidadesError(
            "Ciclo de supersesión en las fuentes " + ", ".join(sorted(en_ciclo))
            + ". 0021 no asigna identidades arbitrarias: corregir los datos y volver a ejecutar."
        )

    raiz: dict[str, str] = {}

    def raiz_de(fid: str) -> str:
        cadena = []
        actual = fid
        while actual not in raiz and padre[actual] is not None:
            cadena.append(actual)
            actual = padre[actual]  # type: ignore[assignment]
        r = raiz.get(actual, actual)
        raiz[actual] = r
        for nodo in cadena:
            raiz[nodo] = r
        return r

    for fid in ids:
        raiz_de(fid)

    hijos: dict[str, int] = {}
    for sup in padre.values():
        if sup is not None:
            hijos[sup] = hijos.get(sup, 0) + 1
    familias: dict[str, int] = {}
    for r in raiz.values():
        familias[r] = familias.get(r, 0) + 1
    informe = {
        "fuentes": len(ids),
        "familias": len(familias),
        "referencias_rotas": rotas,
        "ramificaciones": sorted(fid for fid, n in hijos.items() if n > 1),
    }
    return raiz, informe


def _upgrade_en_transaccion(bind) -> None:
    # 1. Validar y calcular ANTES de cualquier cambio.
    fuentes = [(r[0], r[1]) for r in bind.execute(sa.text("SELECT id, supersedes_source_id FROM source"))]
    raiz, informe = calcular_familias(fuentes)
    proyectos = [r[0] for r in bind.execute(sa.text("SELECT id FROM project"))]

    # 2. Columnas anulables.
    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("knowledge_base_id", sa.String(), nullable=True))
    with op.batch_alter_table("source") as batch:
        batch.add_column(sa.Column("lineage_id", sa.String(), nullable=True))

    # 3. Relleno.
    for pid in proyectos:
        bind.execute(
            sa.text("UPDATE project SET knowledge_base_id = :k WHERE id = :p"),
            {"k": str(uuid.uuid4()), "p": pid},
        )
    linaje_por_raiz = {r: str(uuid.uuid4()) for r in set(raiz.values())}
    if raiz:
        bind.execute(
            sa.text("UPDATE source SET lineage_id = :l WHERE id = :s"),
            [{"l": linaje_por_raiz[r], "s": fid} for fid, r in raiz.items()],
        )
    _fallo_de_prueba("tras_relleno")
    _verificar(bind)

    # 4. NOT NULL, unicidad e índice (SQLite: recrear tabla con batch_alter_table).
    with op.batch_alter_table("project") as batch:
        batch.alter_column("knowledge_base_id", existing_type=sa.String(), nullable=False)
        batch.create_unique_constraint("uq_project_knowledge_base_id", ["knowledge_base_id"])
    with op.batch_alter_table("source") as batch:
        batch.alter_column("lineage_id", existing_type=sa.String(), nullable=False)
        batch.create_index("ix_source_lineage_id", ["lineage_id"])
    _fallo_de_prueba("tras_not_null")

    # 5. Comprobación final sobre el esquema definitivo.
    _verificar(bind)
    logger.info(
        "0021 aplicada: proyectos=%d fuentes=%d familias=%d referencias_rotas=%d ramificaciones=%d",
        len(proyectos), informe["fuentes"], informe["familias"], len(informe["referencias_rotas"]),
        len(informe["ramificaciones"]),
    )
    for fid, sup in informe["referencias_rotas"]:
        logger.warning("0021: la fuente %s supersede a %s, que no existe; se trata como raíz.", fid, sup)
    for fid in informe["ramificaciones"]:
        logger.warning("0021: la fuente %s es superseded por más de una fuente (ramificación).", fid)


def _verificar(bind) -> None:
    nulos_kb = bind.execute(sa.text("SELECT COUNT(*) FROM project WHERE knowledge_base_id IS NULL")).scalar_one()
    nulos_lin = bind.execute(sa.text("SELECT COUNT(*) FROM source WHERE lineage_id IS NULL")).scalar_one()
    rotas_de_cadena = bind.execute(sa.text(
        "SELECT COUNT(*) FROM source s JOIN source p ON p.id = s.supersedes_source_id "
        "WHERE s.lineage_id <> p.lineage_id"
    )).scalar_one()
    duplicados_kb = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT knowledge_base_id FROM project GROUP BY knowledge_base_id HAVING COUNT(*) > 1)"
    )).scalar_one()
    if nulos_kb or nulos_lin or rotas_de_cadena or duplicados_kb:
        raise MigracionIdentidadesError(
            f"Verificación de 0021 fallida: knowledge_base_id nulos={nulos_kb}, lineage_id nulos={nulos_lin}, "
            f"cadenas con lineage distinto={rotas_de_cadena}, knowledge_base_id repetidos={duplicados_kb}"
        )


def upgrade() -> None:
    bind = op.get_bind()
    # Transacción propia: en SQLite, Alembic no envuelve el DDL. El SAVEPOINT
    # abre una transacción real que incluye el UPDATE de alembic_version que
    # Alembic ejecuta al terminar; el commit de Alembic la confirma completa.
    bind.exec_driver_sql(f"SAVEPOINT {_SAVEPOINT}")
    try:
        _upgrade_en_transaccion(bind)
    except BaseException:
        bind.exec_driver_sql(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT}")
        bind.exec_driver_sql(f"RELEASE SAVEPOINT {_SAVEPOINT}")
        raise


def downgrade() -> None:
    if os.environ.get(PERMITIR_DOWNGRADE_ENV) != "1":
        raise MigracionIdentidadesError(
            "0021 no se revierte con alembic downgrade: borraría knowledge_base_id y lineage_id, y "
            "volver a aplicarla generaría identidades distintas. Restaurar un respaldo completo."
        )
    with op.batch_alter_table("source") as batch:
        batch.drop_index("ix_source_lineage_id")
        batch.drop_column("lineage_id")
    with op.batch_alter_table("project") as batch:
        batch.drop_constraint("uq_project_knowledge_base_id", type_="unique")
        batch.drop_column("knowledge_base_id")
