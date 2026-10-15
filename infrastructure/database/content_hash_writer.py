"""Escritura atómica y condicional de `source.content_hash` (RAG-INC-01,
relleno de huellas; decisión NEXOM sobre INC01-R1).

Una sola transacción SQLite `BEGIN IMMEDIATE` (toma el bloqueo de escritura
de la base desde el principio, así que dos rellenos o un alta concurrente se
serializan con `busy_timeout`):

1. `UPDATE source SET content_hash = ? WHERE id = ? AND project_id = ? AND
   content_hash IS NULL` por cada fuente: nunca sobrescribe;
2. comprobación final: ninguna fuente escrita puede compartir
   (lineage_id, content_hash) con otra (tendrían el mismo `source.id`
   portable). Si ocurre, ROLLBACK y ContentHashBackfillConflictError;
3. COMMIT. Cualquier excepción → ROLLBACK: no queda nada escrito.

`updated_at` no se toca: rellenar la huella no es una edición de la fuente.
"""
from __future__ import annotations

import sqlite3

from domain.documents.exceptions import ContentHashBackfillConflictError
from domain.documents.ports import SourceContentHashWriter
from infrastructure.filesystem.paths import InstallationPaths

from .migrations import ensure_project_db

_TIMEOUT_S = 30.0


def _actualizar(con: sqlite3.Connection, project_id: str, source_id: str, content_hash: str) -> bool:
    cur = con.execute(
        "UPDATE source SET content_hash = ? WHERE id = ? AND project_id = ? AND content_hash IS NULL",
        (content_hash, source_id, project_id),
    )
    return cur.rowcount == 1


class SqliteSourceContentHashWriter(SourceContentHashWriter):
    def __init__(self, paths: InstallationPaths, timeout_s: float = _TIMEOUT_S):
        self._paths = paths
        self._timeout_s = timeout_s

    def fill_missing(self, project_id: str, hashes: dict[str, str]) -> set[str]:
        if not hashes:
            return set()
        db_path = ensure_project_db(self._paths, project_id)
        con = sqlite3.connect(db_path, timeout=self._timeout_s, isolation_level=None)
        try:
            con.execute(f"PRAGMA busy_timeout={int(self._timeout_s * 1000)}")
            con.execute("BEGIN IMMEDIATE")
            try:
                escritos = {
                    sid for sid, h in sorted(hashes.items()) if _actualizar(con, project_id, sid, h)
                }
                if escritos:
                    marcadores = ",".join("?" * len(escritos))
                    choques = [r[0] for r in con.execute(
                        f"SELECT DISTINCT s.id FROM source s JOIN source o "
                        f"ON o.project_id = s.project_id AND o.lineage_id = s.lineage_id "
                        f"AND o.content_hash = s.content_hash AND o.id <> s.id "
                        f"WHERE s.project_id = ? AND s.id IN ({marcadores})",
                        (project_id, *sorted(escritos)),
                    )]
                    if choques:
                        raise ContentHashBackfillConflictError(choques)
                con.execute("COMMIT")
                return escritos
            except BaseException:
                con.execute("ROLLBACK")
                raise
        finally:
            con.close()
