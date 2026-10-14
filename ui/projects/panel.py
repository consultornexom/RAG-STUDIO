"""Panel de administración de proyectos (Módulo 1).

Regla de capa (ADR-001, sección 4): solo llama a application
(project_service, jobs). Nunca importa domain ni infrastructure
directamente, y nunca ejecuta trabajo pesado en el hilo de la
interfaz — toda tarea larga se delega a application.jobs.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.projects.import_flow import ejecutar_importacion
from ui.theme import aplicar_color_estado_item
from ui.errors import describe_error


class _ProjectDetailsDialog(QDialog):
    """Formulario para los siete campos descriptivos de Project (Ronda
    15, punto 48). Se usa tanto en el alta (junto con el nombre) como en
    la edición posterior -- ambos casos comparten exactamente los mismos
    campos, así que un solo diálogo evita mantener dos formularios que
    podrían divergir.

    No valida ningún valor de estos campos más allá de dejarlos vacíos:
    domain/projects/entities.py los declara deliberadamente genéricos
    (sin enum, sin formato fijo), y este diálogo respeta eso -- no le
    corresponde a la UI inventar restricciones que el dominio no impone.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        incluir_nombre: bool = False,
        valores: Optional[dict] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Detalles del proyecto")
        valores = valores or {}

        layout = QFormLayout(self)

        self._campo_nombre: Optional[QLineEdit] = None
        if incluir_nombre:
            self._campo_nombre = QLineEdit(valores.get("name", ""))
            layout.addRow("Nombre:", self._campo_nombre)

        self._campo_agent_type_hint = QLineEdit(valores.get("agent_type_hint") or "")
        layout.addRow("Tipo de agente (orientativo):", self._campo_agent_type_hint)

        self._campo_description = QTextEdit()
        self._campo_description.setPlainText(valores.get("description") or "")
        self._campo_description.setFixedHeight(80)
        layout.addRow("Descripción:", self._campo_description)

        self._campo_domain = QLineEdit(valores.get("domain") or "")
        layout.addRow("Dominio:", self._campo_domain)

        self._campo_target_users = QLineEdit(valores.get("target_users") or "")
        layout.addRow("Usuarios objetivo:", self._campo_target_users)

        self._campo_language = QLineEdit(valores.get("language") or "es")
        layout.addRow("Idioma:", self._campo_language)

        self._campo_risk_level = QLineEdit(valores.get("risk_level") or "")
        layout.addRow("Nivel de riesgo:", self._campo_risk_level)

        self._campo_template_id = QLineEdit(valores.get("template_id") or "")
        layout.addRow("Plantilla (id):", self._campo_template_id)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addRow(botones)

    def valores(self) -> dict:
        """Strings, nunca vacíos convertidos a None salvo donde el
        dominio ya usa "" como valor por defecto (description)."""
        datos = {
            "agent_type_hint": self._campo_agent_type_hint.text().strip() or None,
            "description": self._campo_description.toPlainText().strip(),
            "domain": self._campo_domain.text().strip() or None,
            "target_users": self._campo_target_users.text().strip() or None,
            "language": self._campo_language.text().strip() or "es",
            "risk_level": self._campo_risk_level.text().strip() or None,
            "template_id": self._campo_template_id.text().strip() or None,
        }
        if self._campo_nombre is not None:
            datos["name"] = self._campo_nombre.text().strip()
        return datos


class ProjectsPanel(QWidget):
    """Emite project_selected(project_id) cada vez que cambia la
    selección, para que otros paneles (Fuentes, Metadatos) sepan sobre
    qué proyecto operar. Emite cadena vacía si no hay selección."""

    project_selected = Signal(str)

    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context

        layout = QVBoxLayout(self)

        self._project_list = QListWidget(self)
        layout.addWidget(self._project_list)

        buttons = QHBoxLayout()
        self._btn_new = QPushButton("Nuevo proyecto")
        self._btn_edit_name = QPushButton("Editar nombre…")
        self._btn_edit_details = QPushButton("Editar detalles…")
        self._btn_change_status = QPushButton("Cambiar estado…")
        self._btn_archive = QPushButton("Archivar")
        self._btn_delete = QPushButton("Eliminar")
        self._btn_export = QPushButton("Exportar proyecto (.agentproj)…")
        self._btn_import = QPushButton("Importar proyecto (.agentproj)…")
        # Hallazgo real de usuario (auditoría posterior a la Ronda 77,
        # ver bitácora): un usuario con un paquete de RAG CONTENT STUDIO
        # ya generado (14_entrega_rag_studio/) creó un proyecto y pulsó
        # este botón esperando importar esa carpeta -- pero este botón
        # importa un PROYECTO de RAG STUDIO completo, ya exportado antes
        # en su propio formato de archivo único (.agentproj, ver 4.3 del
        # manual), no una entrega de documentos. Como el selector queda
        # filtrado a *.agentproj, una carpeta nunca puede seleccionarse
        # y "Open"/"Abrir" nunca se habilita -- sin ningún mensaje de la
        # aplicación que explique por qué, porque el diálogo es nativo
        # del sistema operativo y RAG STUDIO no participa en él. La
        # función para lo que el usuario buscaba ya existe y funciona
        # (pestaña Fuentes, "Importar carpeta de RAG CONTENT…", ver
        # ui/sources/panel.py); el problema real era que este botón, con
        # el nombre genérico "Importar…", se prestaba a confundirse con
        # ese otro flujo estando en la primera pestaña que ve cualquiera
        # después de crear un proyecto. La etiqueta ahora incluye la
        # extensión de archivo, y el tooltip cruza explícitamente hacia
        # el flujo correcto.
        self._btn_export.setToolTip(
            "Exporta este proyecto de RAG STUDIO completo (fuentes, metadatos, índice, diseño "
            "conversacional, pruebas y liberaciones) a un solo archivo .agentproj -- para "
            "respaldarlo o llevarlo a otra instalación. No es lo mismo que traer documentos "
            "nuevos desde RAG CONTENT STUDIO."
        )
        self._btn_import.setToolTip(
            "Importa un proyecto de RAG STUDIO ya exportado antes a un archivo .agentproj -- solo "
            "acepta ese tipo de archivo, nunca una carpeta.\n\n"
            "¿Buscas importar una carpeta de entrega de RAG CONTENT STUDIO "
            "(14_entrega_rag_studio/)? Ese flujo está en la pestaña Fuentes, botón "
            '"Importar carpeta de RAG CONTENT…" -- ahí sí se elige una carpeta.'
        )
        for button in (
            self._btn_new, self._btn_edit_name, self._btn_edit_details, self._btn_change_status,
            self._btn_archive, self._btn_delete, self._btn_export, self._btn_import,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self._btn_new.clicked.connect(self._on_new_project)
        self._btn_edit_name.clicked.connect(self._on_edit_name)
        self._btn_edit_details.clicked.connect(self._on_edit_details)
        self._btn_change_status.clicked.connect(self._on_change_status)
        self._btn_archive.clicked.connect(self._on_archive)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_import.clicked.connect(self._on_import)
        self._project_list.currentItemChanged.connect(self._on_selection_changed)

        self._apply_button_states()
        self._refresh_projects()

    # ---------- helpers ----------

    def _apply_button_states(self) -> None:
        # Auditoría posterior a la Ronda 77 (hallazgo real de usuario en
        # otra confusión de "Importar…", ver bitácora): estos seis
        # botones ya retornaban en silencio sin selección
        # (`_selected_project_id() is None`), pero seguían pintados como
        # disponibles -- mismo patrón que ya evita correctamente
        # ui/monitoring/panel.py con "Promover…"/"Ver conversación…"
        # según `currentRow() >= 0`. "Nuevo proyecto" e "Importar
        # proyecto (.agentproj)…" no dependen de ninguna selección, así
        # que quedan fuera de este método a propósito.
        tiene_seleccion = self._project_list.currentItem() is not None
        for boton in (
            self._btn_edit_name, self._btn_edit_details, self._btn_change_status,
            self._btn_archive, self._btn_delete, self._btn_export,
        ):
            boton.setEnabled(tiene_seleccion)

    def _refresh_projects(self, select_project_id: Optional[str] = None) -> None:
        self._project_list.clear()
        item_to_select = None
        for project in self._context.project_service.list_projects():
            self._project_list.addItem(
                f"{project.name}  [{project.status.value}]  ({project.id})"
            )
            aplicar_color_estado_item(
                self._project_list.item(self._project_list.count() - 1), project.status.value,
            )
            if select_project_id and project.id == select_project_id:
                item_to_select = self._project_list.item(self._project_list.count() - 1)
        if item_to_select is not None:
            self._project_list.setCurrentItem(item_to_select)

    def _selected_project_id(self) -> Optional[str]:
        item = self._project_list.currentItem()
        if item is None:
            return None
        text = item.text()
        return text.rsplit("(", 1)[-1].rstrip(")")

    def _on_selection_changed(self, current, previous) -> None:
        self._apply_button_states()
        if current is None:
            self.project_selected.emit("")
            return
        text = current.text()
        project_id = text.rsplit("(", 1)[-1].rstrip(")")
        self.project_selected.emit(project_id)

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    # ---------- acciones ----------

    def _on_new_project(self) -> None:
        # Ronda 15 (punto 48): antes el alta era un único QInputDialog
        # que solo pedía "Nombre" -- CreateProject.execute() ya aceptaba
        # los siete campos descriptivos como kwargs desde su implemen-
        # tación original, pero la interfaz nunca los ofrecía. Ahora se
        # usa el mismo formulario que la edición posterior.
        dialogo = _ProjectDetailsDialog(self, incluir_nombre=True)
        if dialogo.exec() != QDialog.Accepted:
            return
        datos = dialogo.valores()
        nombre = datos.pop("name")
        if not nombre:
            # Antes se ignoraba en silencio -- el usuario no tenía
            # forma de saber si el proyecto se creó o no (hallazgo real
            # de validación visual).
            QMessageBox.warning(self, "Falta información", "El nombre del proyecto no puede estar vacío.")
            return
        try:
            project = self._context.project_service.create_project(nombre, **datos)
            self._refresh_projects(select_project_id=project.id)
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario, no se oculta
            self._report_error(exc)

    def _on_edit_details(self) -> None:
        # Ronda 15 (punto 48): antes no había ninguna forma de corregir
        # estos siete campos después del alta -- ni siquiera existían
        # en el formulario de alta. Mismo diálogo que _on_new_project,
        # precargado con los valores actuales.
        project_id = self._selected_project_id()
        if project_id is None:
            return
        try:
            current = self._context.project_service.get_project(project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        dialogo = _ProjectDetailsDialog(self, incluir_nombre=False, valores=current.model_dump())
        if dialogo.exec() != QDialog.Accepted:
            return
        try:
            self._context.project_service.update_project_details(project_id, **dialogo.valores())
            self._refresh_projects(select_project_id=project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def _on_change_status(self) -> None:
        # Ronda 15 (punto 48): "Archivar" era la única transición de
        # estado con un control propio en la interfaz, aunque el dominio
        # (Project._ALLOWED_TRANSITIONS) ya valida varias más. Este botón
        # no agrega ninguna regla nueva: solo ofrece, para el estado
        # actual del proyecto seleccionado, las transiciones que
        # allowed_next_statuses() ya reporta como válidas.
        project_id = self._selected_project_id()
        if project_id is None:
            return
        try:
            current = self._context.project_service.get_project(project_id)
            siguientes = self._context.project_service.get_allowed_next_statuses(project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        if not siguientes:
            QMessageBox.information(
                self, "Cambiar estado",
                f"El proyecto está en «{current.status.value}» y no tiene transiciones disponibles.",
            )
            return
        estado, ok = QInputDialog.getItem(
            self, "Cambiar estado",
            f"Estado actual: {current.status.value}\nNuevo estado:",
            siguientes, editable=False,
        )
        if not ok:
            return
        try:
            self._context.project_service.change_project_status(project_id, estado)
            self._refresh_projects(select_project_id=project_id)
        except Exception as exc:  # noqa: BLE001 - incluye InvalidStatusTransitionError
            self._report_error(exc)

    def _on_edit_name(self) -> None:
        # Ronda 3 (punto 13): antes no había forma de corregir un error
        # de escritura en el nombre del proyecto desde la interfaz -- el
        # alta solo lo pedía una vez y no existía ningún "Editar
        # proyecto". Se resuelve con el mínimo necesario: renombrar.
        project_id = self._selected_project_id()
        if project_id is None:
            return
        try:
            current = self._context.project_service.get_project(project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        new_name, ok = QInputDialog.getText(
            self, "Editar nombre del proyecto", "Nombre:", text=current.name,
        )
        if not ok:
            return
        if not new_name.strip():
            QMessageBox.warning(self, "Falta información", "El nombre del proyecto no puede estar vacío.")
            return
        try:
            self._context.project_service.update_project_name(project_id, new_name.strip())
            self._refresh_projects(select_project_id=project_id)
        except Exception as exc:  # noqa: BLE001 - incluye DuplicateProjectError
            self._report_error(exc)

    def _on_delete(self) -> None:
        # Ronda 3 (punto 13): "Archivar" es la única operación existente
        # sobre un proyecto, y es una transición permanente -- no sirve
        # para deshacer un proyecto creado por error. Eliminar aquí solo
        # se permite si el proyecto no tiene fuentes registradas
        # (ProjectInUseError si ya las tiene); un proyecto con trabajo
        # real sigue teniendo que archivarse, no eliminarse.
        project_id = self._selected_project_id()
        if project_id is None:
            return
        confirm = QMessageBox.question(
            self, "Eliminar proyecto",
            "¿Eliminar este proyecto? Solo es posible si todavía no tiene fuentes registradas. "
            "Esta acción no se puede deshacer.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.project_service.delete_project(project_id)
            self._refresh_projects()
        except Exception as exc:  # noqa: BLE001 - incluye ProjectInUseError
            self._report_error(exc)

    def _on_archive(self) -> None:
        project_id = self._selected_project_id()
        if project_id is None:
            return
        # Ronda 88 (auditoría): archivar es definitivo (ARCHIVADO no tiene
        # ninguna transición de salida, ver domain.projects.entities) y
        # antes se aplicaba con un solo clic, sin confirmación.
        confirm = QMessageBox.question(
            self, "Archivar proyecto",
            "¿Archivar este proyecto? Es definitivo: no se puede volver a otro estado. "
            "Sus datos no se borran y el proyecto puede seguir exportándose, pero su nombre "
            "sigue ocupado en esta instalación.",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.project_service.archive_project(project_id)
            self._refresh_projects(select_project_id=project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def _on_export(self) -> None:
        project_id = self._selected_project_id()
        if project_id is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar proyecto a .agentproj", filter="*.agentproj")
        if not path:
            return
        # Ronda 88 (auditoría): si se escribe el nombre sin extensión, el
        # diálogo nativo no siempre la agrega (macOS), y el archivo no
        # aparecía después en "Importar proyecto", que filtra *.agentproj.
        if not path.lower().endswith(".agentproj"):
            path += ".agentproj"
        # Cursor de espera (auditoría profunda, ronda posterior a la 76,
        # hallazgo N -- mismo criterio y misma mitigación mínima que
        # ui/release/panel.py _on_publish_snapshot/_on_export_deployment_
        # package, ver bitácora Ronda 10 punto B13): esto copia/comprime
        # archivos completos del proyecto de forma síncrona en el hilo de
        # la interfaz. Mover esto a application.jobs (como pide el
        # docstring de este módulo) queda para una ronda futura; mientras
        # tanto, al menos la ventana no debe parecer congelada sin razón.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            manifest = self._context.project_service.export_project(project_id, path)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        finally:
            QApplication.restoreOverrideCursor()
        QMessageBox.information(
            self, "Exportado", f"{len(manifest.files)} archivo(s) exportados a {path}."
        )

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar proyecto desde .agentproj (no una carpeta)", filter="*.agentproj",
        )
        if not path:
            return
        # Ronda 88: cada colisión se detecta antes de copiar nada y se ofrece
        # la salida correspondiente. RAG-INC-01a (decisión NEXOM D-1): la
        # importación normal usa identity_policy="preserve"; "Importar como
        # copia" usa "fork"; una colisión de identidad se explica y se ofrece
        # la copia, sin hacerla nunca sin la aceptación del usuario. La lógica
        # vive en ui/projects/import_flow.py (probada sin interfaz gráfica).

        def _importar(ruta: str, **opciones):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                return self._context.project_service.import_project(ruta, **opciones)
            finally:
                QApplication.restoreOverrideCursor()

        def _preguntar(titulo: str, texto: str) -> bool:
            respuesta = QMessageBox.question(self, titulo, texto, QMessageBox.Yes | QMessageBox.Cancel)
            return respuesta == QMessageBox.Yes

        def _pedir_nombre(texto: str, sugerido: str) -> Optional[str]:
            nombre, ok = QInputDialog.getText(
                self, "Nombre del proyecto importado", texto, QLineEdit.Normal, sugerido,
            )
            return nombre if ok else None

        try:
            imported = ejecutar_importacion(_importar, path, _preguntar, _pedir_nombre)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        if imported is None:
            return
        self._refresh_projects(select_project_id=imported.id)
        QMessageBox.information(
            self, "Proyecto importado",
            f"Se importó el proyecto {imported.name!r}.",
        )
