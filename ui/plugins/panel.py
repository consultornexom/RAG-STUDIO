"""Panel de Complementos (Etapa 8): registro global de plantillas,
nuevos proveedores, importadores y evaluadores personalizados.

Regla de capa: solo llama a application (plugin_service). Nunca importa
domain ni infrastructure directamente (ADR-001, sección 4) -- el
vocabulario de tipos viene de application.plugins.options. Los objetos
que devuelve plugin_service (Plugin) se leen solo por sus atributos.

A diferencia de TODAS las demás pestañas de la aplicación, este panel
NO opera sobre un proyecto activo: el registro de complementos es
global a la instalación (`application.db`), no por proyecto -- por eso
no tiene `set_active_project` y está siempre habilitado, incluso sin
ningún proyecto seleccionado.

Ronda 4 (punto 3 de Validacion_observaciones_RAG_STUDIO.md): antes,
este panel solo permitía Registrar y Activar/Desactivar -- ni la
interfaz ni la capa de aplicación ni el dominio tenían edición o baja
de un complemento ya registrado. Se agregan "Editar…" (reutiliza el
mismo formulario de captura vía `_EditPluginDialog`) y "Eliminar"."""
from __future__ import annotations

from html import escape as html_escape
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QComboBox

from application.plugins.options import PLUGIN_KIND_OPTIONS, plugin_kind_contract_label
from ui.conversational.parsing import parse_provided_variables
from ui.errors import describe_error


def _format_config(config: dict) -> str:
    """Inverso aproximado de `parse_provided_variables`, para precargar
    el config ya guardado de un complemento en el formulario de
    edición (mismo formato "clave=valor, clave2=valor2" que se usa al
    registrar)."""
    return ", ".join(f"{key}={value}" for key, value in config.items())


class _EditPluginDialog(QDialog):
    """Formulario de edición de un complemento ya registrado -- mismos
    campos que "Registrar complemento" salvo tipo y código, que no son
    editables (ver docstring de `application.plugins.commands.
    update_plugin`)."""

    def __init__(self, plugin, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar complemento — {plugin.code}")
        layout = QFormLayout(self)

        self._name = QLineEdit(plugin.name, self)
        self._description = QLineEdit(plugin.description, self)
        self._version = QLineEdit(plugin.version, self)
        self._entry_point = QLineEdit(plugin.entry_point or "", self)
        self._config = QLineEdit(_format_config(plugin.config), self)

        layout.addRow("Nombre:", self._name)
        layout.addRow("Descripción:", self._description)
        layout.addRow("Versión:", self._version)
        layout.addRow("entry_point:", self._entry_point)
        layout.addRow("Configuración:", self._config)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._description.text().strip(),
            "version": self._version.text().strip() or "0.1.0",
            "entry_point": self._entry_point.text().strip() or None,
            "config": parse_provided_variables(self._config.text()),
        }


class PluginsPanel(QWidget):
    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._plugins_cache: list = []

        layout = QVBoxLayout(self)

        form = QGroupBox("Registrar complemento", self)
        form_layout = QVBoxLayout(form)

        self._kind = QComboBox(form)
        self._kind.addItems(PLUGIN_KIND_OPTIONS)
        self._kind.currentTextChanged.connect(self._on_kind_changed)
        self._contract_label = QLabel("", form)
        self._contract_label.setWordWrap(True)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Tipo:", form))
        row1.addWidget(self._kind)
        form_layout.addLayout(row1)
        form_layout.addWidget(self._contract_label)

        self._code = QLineEdit(form)
        self._code.setPlaceholderText("Código único (p. ej. proveedor_openai_embeddings)")
        self._name = QLineEdit(form)
        self._name.setPlaceholderText("Nombre")
        row2 = QHBoxLayout()
        row2.addWidget(self._code)
        row2.addWidget(self._name)
        form_layout.addLayout(row2)

        self._description = QLineEdit(form)
        self._description.setPlaceholderText("Descripción (opcional)")
        form_layout.addWidget(self._description)

        self._version = QLineEdit(form)
        self._version.setPlaceholderText("Versión (por defecto 0.1.0)")
        self._entry_point = QLineEdit(form)
        self._entry_point.setPlaceholderText("entry_point: paquete.modulo:NombreDeClase (no aplica a plantillas)")
        row3 = QHBoxLayout()
        row3.addWidget(self._version)
        row3.addWidget(self._entry_point)
        form_layout.addLayout(row3)

        self._config = QLineEdit(form)
        self._config.setPlaceholderText("Configuración (opcional): clave=valor, clave2=valor2")
        form_layout.addWidget(self._config)

        self._btn_register = QPushButton("Registrar complemento", form)
        self._btn_register.clicked.connect(self._on_register)
        form_layout.addWidget(self._btn_register)
        layout.addWidget(form)

        action_row = QHBoxLayout()
        self._btn_toggle = QPushButton("Activar/Desactivar seleccionado", self)
        self._btn_toggle.clicked.connect(self._on_toggle)
        self._btn_validate = QPushButton("Validar seleccionado", self)
        self._btn_validate.clicked.connect(self._on_validate)
        self._btn_edit = QPushButton("Editar…", self)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete = QPushButton("Eliminar", self)
        self._btn_delete.clicked.connect(self._on_delete)
        action_row.addWidget(self._btn_toggle)
        action_row.addWidget(self._btn_validate)
        action_row.addWidget(self._btn_edit)
        action_row.addWidget(self._btn_delete)
        layout.addLayout(action_row)

        self._plugin_list = QListWidget(self)
        self._plugin_list.itemSelectionChanged.connect(self._apply_button_states)
        layout.addWidget(self._plugin_list)

        self._report = QTextBrowser(self)
        self._report.setReadOnly(True)
        layout.addWidget(self._report)

        self._on_kind_changed(self._kind.currentText())
        self._apply_button_states()
        self._refresh_plugins()

    def _apply_button_states(self) -> None:
        # Auditoría posterior a la Ronda 77 (hallazgo real de usuario en
        # otra confusión de "Importar…", ver bitácora): estos cuatro
        # botones ya retornaban en silencio sin selección
        # (`_selected_plugin() is None`), pero seguían pintados como
        # disponibles -- mismo patrón que ya evita correctamente
        # ui/monitoring/panel.py. "Registrar complemento" no depende de
        # ninguna selección, así que queda fuera de este método.
        tiene_seleccion = self._selected_plugin() is not None
        for boton in (self._btn_toggle, self._btn_validate, self._btn_edit, self._btn_delete):
            boton.setEnabled(tiene_seleccion)

    # ---------- registro ----------
    def _on_kind_changed(self, kind: str) -> None:
        self._contract_label.setText(f"Contrato esperado: {plugin_kind_contract_label(kind)}")
        self._entry_point.setEnabled(kind != "plantilla")

    def _on_register(self) -> None:
        code = self._code.text().strip()
        name = self._name.text().strip()
        if not code or not name:
            QMessageBox.warning(self, "Faltan datos", "El complemento necesita código y nombre.")
            return
        try:
            self._context.plugin_service.register_plugin(
                self._kind.currentText(), code, name,
                description=self._description.text().strip(),
                version=self._version.text().strip() or "0.1.0",
                entry_point=self._entry_point.text().strip() or None,
                config=parse_provided_variables(self._config.text()),
            )
        except Exception as exc:  # noqa: BLE001 - incluye código duplicado / entry_point faltante
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        for field in (self._code, self._name, self._description, self._version, self._entry_point, self._config):
            field.clear()
        self._refresh_plugins()

    # ---------- lista ----------
    def _refresh_plugins(self) -> None:
        self._plugin_list.clear()
        self._plugins_cache = self._context.plugin_service.list_plugins()
        for plugin in self._plugins_cache:
            estado = "habilitado" if plugin.enabled else "deshabilitado"
            self._plugin_list.addItem(
                f"[{plugin.kind.value}] {plugin.code} — {plugin.name} — {estado} (v{plugin.version})"
            )
        self._apply_button_states()

    def _selected_plugin(self):
        row = self._plugin_list.currentRow()
        if row < 0 or row >= len(self._plugins_cache):
            return None
        return self._plugins_cache[row]

    def _on_toggle(self) -> None:
        plugin = self._selected_plugin()
        if plugin is None:
            return
        try:
            self._context.plugin_service.set_plugin_enabled(plugin.id, not plugin.enabled)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        self._refresh_plugins()

    def _on_validate(self) -> None:
        plugin = self._selected_plugin()
        if plugin is None:
            return
        try:
            result = self._context.plugin_service.validate_plugin(plugin.id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        marca = "✔" if result["ok"] else "✘"
        self._report.setHtml(
            f"<p><b>{html_escape(plugin.code)}</b> [{marca}] {html_escape(result['message'])}</p>"
        )

    def _on_edit(self) -> None:
        plugin = self._selected_plugin()
        if plugin is None:
            return
        dialog = _EditPluginDialog(plugin, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            QMessageBox.warning(self, "Falta el nombre", "El complemento necesita un nombre.")
            return
        try:
            self._context.plugin_service.update_plugin(plugin.id, **values)
        except Exception as exc:  # noqa: BLE001 - incluye entry_point faltante
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        self._refresh_plugins()

    def _on_delete(self) -> None:
        plugin = self._selected_plugin()
        if plugin is None:
            return
        confirm = QMessageBox.question(
            self, "Eliminar complemento", f"¿Eliminar el complemento {plugin.code!r}?"
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.plugin_service.unregister_plugin(plugin.id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        self._refresh_plugins()
