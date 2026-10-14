"""RAG-INC-01a, decisión NEXOM D-1: flujo de "Importar proyecto" en la UI.

- importación normal → identity_policy="preserve";
- "Importar como copia" → identity_policy="fork" con id nuevo;
- KnowledgeBaseIdentityCollisionError → explicación específica y oferta de
  copia; nunca fork sin la aceptación del usuario."""
from __future__ import annotations

import os
import uuid

import pytest

from domain.projects.exceptions import (
    ImportNameCollisionError,
    ImportResidueError,
    KnowledgeBaseIdentityCollisionError,
    ProjectIdCollisionError,
)
from ui.projects import import_flow
from ui.projects.import_flow import ejecutar_importacion


class _Importador:
    """Lanza los errores indicados, en orden, y luego devuelve 'ok'."""

    def __init__(self, *errores):
        self.errores = list(errores)
        self.llamadas: list[dict] = []

    def __call__(self, ruta, **opciones):
        self.llamadas.append(dict(opciones))
        if self.errores:
            raise self.errores.pop(0)
        return "ok"


class _Usuario:
    def __init__(self, responde: bool = True, nombre: str | None = "Nombre nuevo"):
        self.responde = responde
        self.nombre = nombre
        self.preguntas: list[tuple[str, str]] = []

    def si_no(self, titulo, texto):
        self.preguntas.append((titulo, texto))
        return self.responde

    def pedir_nombre(self, texto, sugerido):
        return self.nombre


def _colision_kb():
    return KnowledgeBaseIdentityCollisionError("kb-1", "p-existente", "AGENTE UDL")


def test_importacion_normal_usa_preserve_y_no_pregunta():
    importar, usuario = _Importador(), _Usuario()
    assert ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre) == "ok"
    assert importar.llamadas == [{"identity_policy": "preserve"}]
    assert usuario.preguntas == []


def test_colision_de_identidad_explica_y_ofrece_copia_que_usa_fork():
    importar, usuario = _Importador(_colision_kb()), _Usuario(responde=True)
    assert ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre) == "ok"

    titulo, texto = usuario.preguntas[0]
    assert titulo == import_flow.TITULO_COLISION_IDENTIDAD
    assert "identidad" in texto and "ya existe" in texto  # explica, no es un error genérico
    assert "AGENTE UDL" in texto
    assert "como copia" in texto  # ofrece explícitamente la copia
    assert importar.llamadas[0] == {"identity_policy": "preserve"}
    segunda = importar.llamadas[1]
    assert segunda["identity_policy"] == "fork"
    uuid.UUID(segunda["new_project_id"])


def test_colision_de_identidad_sin_aceptacion_no_hace_fork():
    importar, usuario = _Importador(_colision_kb()), _Usuario(responde=False)
    assert ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre) is None
    assert importar.llamadas == [{"identity_policy": "preserve"}]  # nunca se intentó fork


def test_colision_de_id_ofrece_copia_con_fork():
    importar, usuario = _Importador(ProjectIdCollisionError("p1", "AGENTE UDL")), _Usuario()
    ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre)
    assert usuario.preguntas[0][0] == import_flow.TITULO_COLISION_ID
    assert importar.llamadas[1]["identity_policy"] == "fork"
    assert importar.llamadas[1]["new_project_id"] != "p1"


def test_copia_con_nombre_repetido_conserva_fork_y_pide_nombre():
    importar = _Importador(_colision_kb(), ImportNameCollisionError("AGENTE UDL", "AGENTE UDL (importado)"))
    usuario = _Usuario(nombre="  AGENTE UDL (copia)  ")
    ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre)
    ultima = importar.llamadas[-1]
    assert ultima["identity_policy"] == "fork" and ultima["new_name"] == "AGENTE UDL (copia)"
    assert ultima["new_project_id"] == importar.llamadas[1]["new_project_id"]


def test_residuos_y_nombre_mantienen_preserve():
    importar = _Importador(ImportResidueError("p1"), ImportNameCollisionError("A", "A (importado)"))
    usuario = _Usuario()
    ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre)
    assert importar.llamadas[-1] == {"identity_policy": "preserve", "set_aside_residue": True,
                                     "new_name": "Nombre nuevo"}


def test_otros_errores_se_propagan():
    importar, usuario = _Importador(RuntimeError("disco lleno")), _Usuario()
    with pytest.raises(RuntimeError):
        ejecutar_importacion(importar, "x.agentproj", usuario.si_no, usuario.pedir_nombre)


# ------------------------------------------------- panel real (PySide6)

def _qt():
    try:
        import PySide6.QtWidgets  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"Qt no disponible ({exc})")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_panel_colision_de_identidad_ofrece_copia_y_crea_fork(app_context, tmp_path, monkeypatch):
    _qt()
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from ui.projects.panel import ProjectsPanel

    service = app_context.project_service
    original = service.create_project("AGENTE UDL")
    package = tmp_path / "agente.agentproj"
    service.export_project(original.id, str(package))

    panel = ProjectsPanel(app_context)
    preguntas: list[tuple[str, str]] = []
    errores: list[Exception] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(package), "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(panel, "_report_error", lambda exc: errores.append(exc))

    # 1) El usuario cancela: no se crea nada.
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda _p, t, x, *a: (preguntas.append((t, x)), QMessageBox.Cancel)[1]))
    panel._on_import()
    assert preguntas[0][0] == import_flow.TITULO_COLISION_IDENTIDAD
    assert errores == []  # no se presenta como error genérico
    assert [p.id for p in service.list_projects()] == [original.id]

    # 2) Acepta la copia: fork con identidad nueva; luego se le pide nombre.
    preguntas.clear()
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda _p, t, x, *a: (preguntas.append((t, x)), QMessageBox.Yes)[1]))
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("AGENTE UDL (copia)", True)))
    panel._on_import()
    assert errores == []
    proyectos = {p.id: p for p in service.list_projects()}
    assert len(proyectos) == 2
    copia = next(p for pid, p in proyectos.items() if pid != original.id)
    assert copia.name == "AGENTE UDL (copia)"
    assert copia.knowledge_base_id != service.get_project(original.id).knowledge_base_id
