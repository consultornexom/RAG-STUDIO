"""Configuración local de la instalación (ADR-001, sección 11:
empaquetado multiplataforma). Resuelve un directorio base por defecto
adecuado a Windows, macOS o Linux, sin depender de una librería externa.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

APP_FOLDER_NAME = "RAGStudio"
DATA_SUBFOLDER_NAME = "data"

# Ítem de la tercera ronda de madurez post-8-etapas (ver bitácora en
# README, 2026-07-28): permite fijar la ubicación de los datos sin
# tocar código, para instalaciones avanzadas (varias instalaciones en
# la misma máquina, disco compartido con otra ruta, etc.).
_HOME_ENV_VAR = "RAGSTUDIO_HOME"


def _installation_root() -> Path:
    """Carpeta que contiene esta instalación de RAG STUDIO.

    Antes, el directorio de datos por defecto vivía en la carpeta de
    perfil del sistema operativo (~/.local/share, %APPDATA%, ~/Library/
    Application Support), separada de dónde vive el propio código de la
    aplicación -- justo el problema que se pidió evitar: datos dispersos
    fuera de la carpeta de la aplicación. Ahora el directorio de datos
    por defecto es una subcarpeta ("data/") dentro de esta misma
    instalación, para que la aplicación quede autocontenida en una sola
    carpeta (útil, por ejemplo, para instalaciones en un disco externo o
    compartido).

    - Empaquetado con PyInstaller (`sys.frozen`): la raíz es la carpeta
      donde vive el ejecutable real (`dist/RAGStudio/`, modo *onedir*),
      NO `sys._MEIPASS` -- ese último es un directorio temporal de
      extracción que cambia en cada ejecución y nunca debe usarse para
      datos persistentes.
    - Ejecutando desde el código fuente: la raíz es la carpeta del
      proyecto (el padre de la carpeta `app/`, donde vive este archivo).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_base_dir() -> Path:
    env_override = os.environ.get(_HOME_ENV_VAR)
    if env_override:
        return Path(env_override)
    return _installation_root() / DATA_SUBFOLDER_NAME


_DEFAULT_EMBEDDING_PROFILE = "simetrico"


class AppSettings(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    base_dir: Path = Field(default_factory=default_base_dir)
    log_level: str = "INFO"
    embedding_profile: str = Field(
        default=_DEFAULT_EMBEDDING_PROFILE,
        description=(
            "Perfil de modelo de embeddings (ver "
            "infrastructure.embeddings.fastembed_provider.make_provider_for_profile): "
            "'simetrico' (default, ligero) o 'asimetrico_e5_large' (más pesado, mejor "
            "en preguntas de lenguaje natural contra contenido tipo lista -- ver README, "
            "bitácora 2026-07-26). Se resuelve, en orden de prioridad: parámetro explícito "
            "a load_settings/bootstrap/start, variable de entorno "
            "RAGSTUDIO_EMBEDDING_PROFILE, o el default -- así nadie que no lo pida se ve "
            "afectado por este cambio."
        ),
    )
    max_concurrent_jobs: Optional[int] = Field(
        default=None,
        description=(
            "Límite de trabajos en segundo plano ejecutándose de verdad al mismo tiempo "
            "(ítem 4 de la segunda evaluación de madurez post-8-etapas, ver bitácora en "
            "README) -- ver workers.jobs.ThreadJobRunner. `None` (default) es sin límite, "
            "el comportamiento de siempre: cada trabajo enviado arranca su propio hilo de "
            "inmediato. Un entero fija cuántos pueden estar EJECUTANDO a la vez; el resto "
            "se queda en PENDIENTE esperando un cupo libre, en vez de competir sin control "
            "por CPU/memoria/E-S. Se resuelve, en orden de prioridad: parámetro explícito a "
            "load_settings/bootstrap/start, variable de entorno "
            "RAGSTUDIO_MAX_CONCURRENT_JOBS, o `None`."
        ),
    )


def load_settings(
    base_dir: Optional[str | Path] = None, log_level: str = "INFO",
    embedding_profile: Optional[str] = None, max_concurrent_jobs: Optional[int] = None,
) -> AppSettings:
    resolved = Path(base_dir) if base_dir is not None else default_base_dir()
    resolved_profile = (
        embedding_profile
        or os.environ.get("RAGSTUDIO_EMBEDDING_PROFILE")
        or _DEFAULT_EMBEDDING_PROFILE
    )
    resolved_max_concurrent_jobs = max_concurrent_jobs
    if resolved_max_concurrent_jobs is None:
        env_value = os.environ.get("RAGSTUDIO_MAX_CONCURRENT_JOBS")
        if env_value:
            resolved_max_concurrent_jobs = int(env_value)
    return AppSettings(
        base_dir=resolved, log_level=log_level, embedding_profile=resolved_profile,
        max_concurrent_jobs=resolved_max_concurrent_jobs,
    )
