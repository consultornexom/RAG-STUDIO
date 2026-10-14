"""Flujo de decisiones de "Importar proyecto" (Ronda 88 + RAG-INC-01a,
decisión NEXOM D-1), separado de Qt para poder probarlo sin interfaz
gráfica. El panel solo aporta los diálogos.

D-1:
- Importación normal → ``identity_policy="preserve"``.
- "Importar como copia" → ``identity_policy="fork"`` con un id nuevo.
- Colisión de identidad con preserve (KnowledgeBaseIdentityCollisionError):
  se explica que el proyecto conserva una identidad que ya existe y se
  OFRECE importar como copia; nunca se hace fork sin que el usuario lo
  acepte.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Optional, TypeVar

from application.projects.errors import (
    IMPORT_POLICY_FORK,
    IMPORT_POLICY_PRESERVE,
    ImportNameCollisionError,
    ImportResidueError,
    KnowledgeBaseIdentityCollisionError,
    ProjectIdCollisionError,
)

T = TypeVar("T")

TITULO_COLISION_IDENTIDAD = "El proyecto ya existe en esta instalación (misma identidad)"
TITULO_COLISION_ID = "El proyecto ya está en esta instalación"
TITULO_RESIDUOS = "Restos de una importación anterior"
PREGUNTA_COPIA = (
    "¿Importarlo como copia? La copia recibe una identidad nueva (otra base de conocimiento) y el "
    "proyecto existente no se toca."
)

PreguntarSiNo = Callable[[str, str], bool]
PedirNombre = Callable[[str, str], Optional[str]]


def opciones_iniciales() -> dict[str, Any]:
    return {"identity_policy": IMPORT_POLICY_PRESERVE}


def opciones_como_copia(opciones: dict[str, Any]) -> dict[str, Any]:
    nuevas = dict(opciones)
    nuevas["identity_policy"] = IMPORT_POLICY_FORK
    nuevas["new_project_id"] = str(uuid.uuid4())
    return nuevas


def ejecutar_importacion(
    importar: Callable[..., T], ruta: str, preguntar_si_no: PreguntarSiNo, pedir_nombre: PedirNombre,
    max_intentos: int = 6,
) -> Optional[T]:
    """Llama a ``importar(ruta, **opciones)`` y resuelve cada colisión con la
    decisión del usuario. Devuelve el resultado o None si el usuario cancela.
    Cualquier otro error se propaga al llamador."""
    opciones = opciones_iniciales()
    for _ in range(max_intentos):
        try:
            return importar(ruta, **opciones)
        except ImportResidueError as exc:
            if not preguntar_si_no(TITULO_RESIDUOS, f"{exc}\n\n¿Apartarlos y continuar con la importación?"):
                return None
            opciones["set_aside_residue"] = True
        except KnowledgeBaseIdentityCollisionError as exc:
            if not preguntar_si_no(TITULO_COLISION_IDENTIDAD, f"{exc}\n\n{PREGUNTA_COPIA}"):
                return None
            opciones = opciones_como_copia(opciones)
        except ProjectIdCollisionError as exc:
            if not preguntar_si_no(TITULO_COLISION_ID, f"{exc}\n\n{PREGUNTA_COPIA}"):
                return None
            opciones = opciones_como_copia(opciones)
        except ImportNameCollisionError as exc:
            nombre = pedir_nombre(f"{exc}\n\nNombre para el proyecto importado:", exc.suggested_name)
            if not nombre or not nombre.strip():
                return None
            opciones["new_name"] = nombre.strip()
    return None
