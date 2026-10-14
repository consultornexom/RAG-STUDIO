"""Ciclo de vida de la aplicación: arranque y apagado ordenados."""
from __future__ import annotations

from .bootstrap import AppContext, bootstrap


def start(
    base_dir=None, log_level: str = "INFO", embedding_profile: str | None = None,
    max_concurrent_jobs: int | None = None,
) -> AppContext:
    return bootstrap(
        base_dir=base_dir, log_level=log_level, embedding_profile=embedding_profile,
        max_concurrent_jobs=max_concurrent_jobs,
    )


def shutdown(context: AppContext) -> None:
    context.logger.info("Apagando RAG STUDIO.")
    for handler in list(context.logger.handlers):
        handler.flush()
