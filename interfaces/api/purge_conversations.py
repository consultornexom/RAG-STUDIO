"""CLI de mantenimiento: purga la bitácora de conversaciones reales
más antigua que N días (Ronda 12, ver
Validacion_observaciones_RAG_STUDIO.md -- brecha de retención de
datos). Pensado para automatizarse (cron, tarea programada del
sistema, systemd timer) contra un `runtime.db` desplegado -- no
requiere que el proceso `interfaces/api/` esté corriendo (mismo
criterio que la pestaña Monitoreo de la app de escritorio: es un
SQLite normal en modo WAL, se puede leer/escribir aunque el runtime
esté apagado).

Uso:

    python -m interfaces.api.purge_conversations --retention-days 90
    python -m interfaces.api.purge_conversations --retention-days 90 --dry-run

Ubicación de `runtime.db` resuelta con las mismas variables de entorno
que `create_app_from_env` (ver `interfaces/api/app.py`):
RAGSTUDIO_HOME / RAGSTUDIO_RUNTIME_DB_PATH. `RAGSTUDIO_LOG_LEVEL`
también aplica -- la purga real (no `--dry-run`) queda registrada en
`logs/ragstudio-api.log`, igual que el resto del runtime.

Cuántos días retener es una decisión del operador/cliente, no de RAG
STUDIO -- este script no trae ningún valor por defecto a propósito
(`--retention-days` es obligatorio), para no borrar nada por una
suposición implícita. Cifrado en reposo de `runtime.db` sigue siendo
responsabilidad de la capa de hospedaje (ver docstring de
`application/runtime/commands/purge_old_conversations.py`); este
script resuelve la retención, no el cifrado."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from app.logging_setup import configure_logging
from application.runtime.commands.purge_old_conversations import InvalidRetentionWindowError, PurgeOldConversations
from infrastructure.database.runtime_repositories import SqlAlchemyConversationLogRepository
from infrastructure.filesystem.paths import InstallationPaths

logger = logging.getLogger(__name__)


def _resolve_installation_dir() -> str:
    from app.configuration import default_base_dir

    return os.environ.get("RAGSTUDIO_HOME") or str(default_base_dir())


def _resolve_runtime_db_path(installation_dir: str) -> Path:
    override = os.environ.get("RAGSTUDIO_RUNTIME_DB_PATH")
    if override:
        return Path(override)
    return InstallationPaths(installation_dir).runtime_db_path()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Purga conversaciones reales más antiguas que N días de runtime.db (Ronda 12).",
    )
    parser.add_argument(
        "--retention-days", type=int, required=True,
        help="Conservar solo las conversaciones de los últimos N días; borra el resto.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo cuenta cuántas conversaciones se borrarían, sin borrar nada.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    installation_dir = _resolve_installation_dir()
    configure_logging(
        InstallationPaths(installation_dir).logs_dir(),
        level=os.environ.get("RAGSTUDIO_LOG_LEVEL", "INFO"), filename="ragstudio-api.log",
    )
    runtime_db_path = _resolve_runtime_db_path(installation_dir)
    purge = PurgeOldConversations(SqlAlchemyConversationLogRepository(runtime_db_path))

    try:
        if args.dry_run:
            count = purge.count_eligible(args.retention_days)
            print(
                f"Se borrarían {count} conversación(es) de más de {args.retention_days} día(s) "
                f"en {runtime_db_path} -- nada se borró (--dry-run)."
            )
        else:
            count = purge.execute(args.retention_days)
            logger.info(
                "Purga de conversaciones ejecutada: %s filas borradas (retención=%s días, db=%s).",
                count, args.retention_days, runtime_db_path,
            )
            print(f"Se borraron {count} conversación(es) de más de {args.retention_days} día(s) en {runtime_db_path}.")
    except InvalidRetentionWindowError as exc:
        print(f"Error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
