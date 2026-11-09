"""Panel de metadatos: esquema activo, catálogos y cobertura (Módulo 3).

Regla de capa: solo llama a application.metadata_service. Los tipos de
dato de campo y el conjunto "requiere catálogo" vienen de
application.metadata.options, nunca de domain.metadata.entities.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from application.metadata.options import (
    CATALOG_BACKED_TYPE_VALUES,
    FIELD_DATA_TYPE_OPTIONS,
    FIELD_DATA_TYPE_VALUE_HINTS,
    VALUE_ASSIGNMENT_ADD,
    VALUE_ASSIGNMENT_REPLACE,
    stored_values_list,
)
from ui.release.gate_status import GateStatusLabel
from ui.errors import describe_error

# Ronda 97: en "Valores actuales", cada valor de un campo de varios
# valores es una fila propia; este rol guarda el código concreto de la
# fila (None en campos de un solo valor), para que "Quitar valor" quite
# solo ese valor y conserve los demás.
_ITEM_VALUE_ROLE = Qt.ItemDataRole.UserRole + 1


class _FieldDialog(QDialog):
    """Diálogo de alta y edición de campo. En modo edición, field_id y
    tipo de dato se muestran pero no se pueden cambiar (RAG STUDIO.odt:
    field_id es estable; cambiar el tipo podría invalidar valores ya
    guardados sin aviso)."""

    def __init__(self, catalogs: list[tuple[str, str]], parent: Optional[QWidget] = None, existing=None):
        """`catalogs` es una lista de pares (id, nombre) -- se muestra
        el nombre (legible) y se guarda el id como itemData, igual que
        el selector de catálogos del panel principal. Antes se pasaba
        solo una lista de ids y se mostraban tal cual en el combo
        (hallazgo real de validación visual: el código de catálogo no
        es representativo para el usuario, sobre todo con varios
        catálogos creados)."""
        super().__init__(parent)
        editing = existing is not None
        self.setWindowTitle("Editar campo" if editing else "Agregar campo")

        self._field_id = QLineEdit(self)
        self._label = QLineEdit(self)
        self._data_type = QComboBox(self)
        self._data_type.addItems(FIELD_DATA_TYPE_OPTIONS)
        self._catalog_id = QComboBox(self)
        self._catalog_id.addItem("", "")
        for catalog_id, catalog_name in catalogs:
            self._catalog_id.addItem(catalog_name, catalog_id)
        self._catalog_count = len(catalogs)
        # Hallazgo real de validación visual: el combo de Tipo de dato
        # abre por defecto en "texto" (el primer valor del enum), que
        # no usa catálogo -- así que este selector siempre aparecía
        # deshabilitado/gris al abrir el diálogo, aunque ya tuviera los
        # catálogos del proyecto cargados adentro. Se percibía como "no
        # me muestra los catálogos existentes" cuando en realidad el
        # dato sí estaba ahí, solo bloqueado por el tipo elegido. Esta
        # etiqueta hace explícito el motivo en todo momento (ver
        # _update_catalog_requirement).
        self._catalog_hint = QLabel(self)
        self._catalog_hint.setWordWrap(True)
        self._required = QComboBox(self)
        self._required.addItems(["no", "sí"])
        # multiple/filterable/inherited_by_chunks (hallazgo real, ver
        # Validacion_observaciones_RAG_STUDIO.md): domain.metadata.entities.
        # FieldDefinition define los tres, y application/metadata/commands/
        # add_field_definition.py y update_field_definition.py ya los
        # aceptan y persisten de punta a punta -- pero este diálogo nunca
        # ofreció ningún control para activarlos, así que todo campo
        # creado desde la interfaz quedaba forzosamente con los tres en
        # False. El Manual del Usuario (6.1) ya documentaba esto
        # explícitamente como "limitación real de esta versión" solo para
        # "valor múltiple"; los otros dos tenían la misma brecha sin
        # documentar.
        self._multiple = QCheckBox("Permite varios valores (al asignarlo, se separan con comas)", self)
        self._filterable = QCheckBox("Filtrable", self)
        self._filterable.setToolTip(
            "Marca este campo como pensado para filtrar -- se refleja en el reporte de entregables "
            "(pestaña Liberación); todavía no cambia por sí solo el comportamiento de Búsqueda RAG."
        )
        self._inherited_by_chunks = QCheckBox("Heredar este valor a los fragmentos (chunks) al indexar", self)
        self._inherited_by_chunks.setToolTip(
            "Si se marca, el valor asignado a la fuente se copia a cada fragmento generado al "
            "fragmentarla -- útil para poder filtrar la búsqueda por este campo a nivel de fragmento, "
            "no solo de fuente completa."
        )
        # Punto 10 de Validacion_observaciones_RAG_STUDIO.md: antes todo
        # campo aplicaba a todas las fuentes del proyecto por igual, sin
        # ninguna forma de acotarlo a un tipo de documento concreto (p.
        # ej. "contactos" vs. "requisitos de admisión"). Vacío = campo
        # genérico (aplica a toda fuente), igual que el comportamiento de
        # siempre -- no es obligatorio llenarlo. A diferencia de field_id/
        # Tipo de dato, este campo SÍ es editable después de creado: no
        # afecta el formato de los valores ya guardados, solo en qué
        # fuentes se sigue pidiendo de aquí en adelante (ver
        # UpdateFieldDefinition).
        self._document_type_code = QLineEdit(self)
        self._document_type_code.setPlaceholderText("vacío = aplica a todas las fuentes")

        if editing:
            self._field_id.setText(existing.field_id)
            self._field_id.setEnabled(False)
            self._label.setText(existing.display_name)
            data_type_value = getattr(existing.data_type, "value", existing.data_type)
            idx = self._data_type.findText(data_type_value)
            if idx >= 0:
                self._data_type.setCurrentIndex(idx)
            self._data_type.setEnabled(False)
            if existing.catalog_id:
                idx = self._catalog_id.findData(existing.catalog_id)
                if idx >= 0:
                    self._catalog_id.setCurrentIndex(idx)
            if existing.required:
                self._required.setCurrentText("sí")
            if existing.document_type_code:
                self._document_type_code.setText(existing.document_type_code)
            self._multiple.setChecked(existing.multiple)
            self._filterable.setChecked(existing.filterable)
            self._inherited_by_chunks.setChecked(existing.inherited_by_chunks)

        form = QFormLayout()
        form.addRow(
            "field_id* (solo letras/números/_)" + (" (no editable)" if editing else ""), self._field_id,
        )
        form.addRow("Etiqueta*", self._label)
        form.addRow("Tipo de dato*" + (" (no editable)" if editing else ""), self._data_type)
        form.addRow(
            "Catálogo (solo aplica a selección única, selección múltiple o catálogo jerárquico)",
            self._catalog_id,
        )
        form.addRow("", self._catalog_hint)
        form.addRow("Tipo de documento (opcional, ej. \"contactos\")", self._document_type_code)
        form.addRow("Obligatorio", self._required)
        form.addRow("", self._multiple)
        form.addRow("", self._filterable)
        form.addRow("", self._inherited_by_chunks)

        if editing:
            # Ronda 5 (video 2, hallazgo real de usuario): se percibió
            # Obligatorio y Tipo de documento como "no editables" al ver
            # field_id/Tipo de dato bloqueados justo arriba -- ambos SÍ
            # son editables y el cambio se guarda (ver
            # application.metadata.commands.update_field_definition).
            # Esta nota lo deja explícito en vez de que quien edita tenga
            # que adivinarlo por el estado visual de los controles.
            edit_note = QLabel(
                "Solo field_id y Tipo de dato quedan bloqueados una vez creado el campo. Etiqueta, "
                "Catálogo, Tipo de documento, Obligatorio, \"Permite varios valores\", Filtrable y "
                "\"Heredar a fragmentos\" sí se pueden corregir aquí.",
                self,
            )
            edit_note.setWordWrap(True)
            form.addRow("", edit_note)

        self._data_type.currentTextChanged.connect(self._update_catalog_requirement)
        self._update_catalog_requirement(self._data_type.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _update_catalog_requirement(self, data_type: str) -> None:
        # Solo se fuerza la habilitación cuando el combo de tipo es
        # editable (alta); en edición el catálogo siempre queda
        # disponible para poder cambiarlo aunque el tipo ya no se toque.
        catalog_backed = data_type in CATALOG_BACKED_TYPE_VALUES
        if self._data_type.isEnabled():
            self._catalog_id.setEnabled(catalog_backed)

        if self._data_type.isEnabled() and not catalog_backed:
            self._catalog_hint.setText(
                f"El tipo de dato \"{data_type}\" no usa catálogo -- por eso el selector de arriba está "
                "deshabilitado. Cambia el Tipo de dato a selección única, selección múltiple o catálogo "
                "jerárquico para poder elegir uno de tus catálogos."
            )
        elif self._catalog_count == 0:
            self._catalog_hint.setText(
                "Este proyecto todavía no tiene catálogos creados. Ve a la pestaña Catálogos para dar de "
                "alta uno antes de vincularlo aquí."
            )
        else:
            self._catalog_hint.setText(f"{self._catalog_count} catálogo(s) disponible(s) en el selector de arriba.")

    def values(self) -> dict:
        return {
            "field_id": self._field_id.text().strip(),
            "label": self._label.text().strip(),
            "data_type": self._data_type.currentText(),
            "catalog_id": self._catalog_id.currentData() or None,
            "required": self._required.currentText() == "sí",
            "document_type_code": self._document_type_code.text().strip() or None,
            "multiple": self._multiple.isChecked(),
            "filterable": self._filterable.isChecked(),
            "inherited_by_chunks": self._inherited_by_chunks.isChecked(),
        }


class _TextInputDialog(QDialog):
    """Diálogo simple de un solo campo de texto, reutilizado para
    renombrar catálogos y entradas."""

    def __init__(self, title: str, label_text: str, initial_text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._value = QLineEdit(self)
        self._value.setText(initial_text)

        form = QFormLayout()
        form.addRow(label_text, self._value)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self._value.text().strip()


class _EditCatalogEntryDialog(QDialog):
    """Ronda 3/4 (punto 13): antes "Editar entrada" solo permitía la
    etiqueta -- el código (value_code) era inmutable por diseño, mismo
    síntoma reportado para "Editar campo" en Metadatos. Ahora también se
    puede corregir el código, pero solo cuando UpdateCatalogEntry
    confirme que ninguna fuente ya lo tiene guardado (CatalogEntryInUseError
    si no); este diálogo no valida eso -- solo recoge los valores.

    Ronda 4 (punto 4c): se agrega el selector de "Entrada padre" --
    dominio (CatalogEntry.parent_entry_id) y aplicación
    (UpdateCatalogEntry/AddCatalogEntry) ya soportaban catálogos
    jerárquicos desde antes (RAG STUDIO INVESTIGACION.odt, A5, ej.
    Admisiones -> Requisitos -> Fechas), pero la interfaz nunca
    ofrecía ninguna forma de capturarla: toda entrada quedaba siempre
    en el nivel raíz. `other_entries` excluye a la propia entrada (no
    puede ser su propio padre) -- no valida ciclos más profundos (p.
    ej. A->B->A), igual que UpdateCatalogEntry.execute, que solo
    verifica que el id exista en el catálogo."""

    def __init__(
        self, initial_label: str, initial_value_code: str, other_entries: list,
        initial_parent_entry_id: Optional[str] = None, parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Editar entrada")
        self._value_code = QLineEdit(self)
        self._value_code.setText(initial_value_code)
        self._label = QLineEdit(self)
        self._label.setText(initial_label)

        self._parent_entry = QComboBox(self)
        self._parent_entry.addItem("(sin padre)", None)
        for entry in other_entries:
            self._parent_entry.addItem(f"{entry.value_code} — {entry.label}", entry.id)
        if initial_parent_entry_id is not None:
            idx = self._parent_entry.findData(initial_parent_entry_id)
            if idx >= 0:
                self._parent_entry.setCurrentIndex(idx)

        form = QFormLayout()
        form.addRow("Código de valor:", self._value_code)
        form.addRow("Etiqueta:", self._label)
        form.addRow("Entrada padre:", self._parent_entry)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def value_code(self) -> str:
        return self._value_code.text().strip()

    def label(self) -> str:
        return self._label.text().strip()

    def parent_entry_id(self) -> Optional[str]:
        return self._parent_entry.currentData()


class _AddCatalogEntryDialog(QDialog):
    """Diálogo de alta de entrada de catálogo (Ronda 4, punto 4c):
    antes, "Agregar entrada" era una cadena de QInputDialog.getText
    (código, etiqueta) sin ninguna forma de indicar una entrada padre
    -- se reemplaza por un formulario único, mismo criterio de
    selector de padre que _EditCatalogEntryDialog."""

    def __init__(self, existing_entries: list, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Agregar entrada")
        self._value_code = QLineEdit(self)
        self._label = QLineEdit(self)

        self._parent_entry = QComboBox(self)
        self._parent_entry.addItem("(sin padre)", None)
        for entry in existing_entries:
            self._parent_entry.addItem(f"{entry.value_code} — {entry.label}", entry.id)

        form = QFormLayout()
        form.addRow("Código de valor:", self._value_code)
        form.addRow("Etiqueta:", self._label)
        form.addRow("Entrada padre:", self._parent_entry)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def value_code(self) -> str:
        return self._value_code.text().strip()

    def label(self) -> str:
        return self._label.text().strip()

    def parent_entry_id(self) -> Optional[str]:
        return self._parent_entry.currentData()


class _MultiSourceSelectionDialog(QDialog):
    """Selección múltiple de fuentes para "Aplicar a varias fuentes…"
    (Ronda 5, punto 21 de Validacion_observaciones_RAG_STUDIO.md).

    Observación real de usuario (vídeo 2): describir metadatos fuente
    por fuente es tedioso cuando muchas comparten el mismo valor en un
    campo. Mismo gesto de selección (Ctrl/Shift-click) que ya usa la
    pestaña Fuentes para corregir document_type_code en bloque
    (ver ui/sources/panel.py, _selected_source_ids) -- aquí en un
    diálogo aparte porque "Fuente:" en esta pestaña es un QComboBox de
    selección única, reutilizado también para ver valores actuales e
    historial de una sola fuente a la vez."""

    def __init__(self, sources: list, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar fuentes")
        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for source in sources:
            self._list.addItem(source.title)
            self._list.item(self._list.count() - 1).setData(Qt.ItemDataRole.UserRole, source.id)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Elige una o más fuentes (Ctrl/Shift-click):", self))
        layout.addWidget(self._list)
        layout.addWidget(buttons)

    def selected_source_ids(self) -> list:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self._list.selectedItems()]


class MetadataPanel(QWidget):
    """Ver también sources_changed en ui/sources/panel.py -- mismo
    patrón. Emite schema_changed() cada vez que el esquema activo (o
    sus campos) se reconstruye en _refresh_schema(), para que otros
    paneles que dependen de la lista de campos de metadatos (por
    ejemplo, el selector "Campo de metadatos ligado" de Diseño
    conversacional -> Variables) puedan refrescarse sin depender de
    un cambio de proyecto activo.

    Auditoría posterior a la Ronda 78 (hallazgo real de usuario, ver
    bitácora): ConversationalPanel.set_active_project ya llamaba a
    _populate_metadata_fields() una vez, pero nada disparaba un
    refresco cuando el esquema se creaba o se le agregaban campos
    DESPUÉS de seleccionar el proyecto -- exactamente el mismo tipo de
    problema ya corregido para sources_changed en la Ronda 4 (punto
    4b), nunca aplicado a este puente."""

    schema_changed = Signal()

    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None
        self._schema_id: Optional[str] = None
        self._fields_by_id: dict = {}
        self._entries_by_id: dict = {}

        layout = QVBoxLayout(self)
        self._project_label = QLabel("Selecciona un proyecto en la pestaña Proyectos.", self)
        layout.addWidget(self._project_label)

        # Aviso temprano (no bloqueante) de la compuerta de Liberación
        # "Metadatos" -- ver ui/release/gate_status.py. Solo lectura:
        # nunca impide crear/editar esquema, catálogos o valores.
        self._gate_status_label = GateStatusLabel("Metadatos", self)
        layout.addWidget(self._gate_status_label)

        tabs = QTabWidget(self)
        layout.addWidget(tabs)

        # --- pestaña esquema ---
        schema_tab = QWidget(self)
        schema_layout = QVBoxLayout(schema_tab)
        self._field_list = QListWidget(schema_tab)
        schema_layout.addWidget(self._field_list)
        schema_buttons = QHBoxLayout()
        self._btn_create_schema = QPushButton("Crear esquema")
        self._btn_add_field = QPushButton("Agregar campo")
        self._btn_edit_field = QPushButton("Editar campo")
        # Punto 11 de Validacion_observaciones_RAG_STUDIO.md: antes no había
        # ninguna forma de deshacer un campo dado de alta por error (solo se
        # podía corregir la Etiqueta desde "Editar campo") -- ver
        # DeleteFieldDefinition, bloqueado si el campo ya tiene valores.
        self._btn_delete_field = QPushButton("Eliminar campo")
        schema_buttons.addWidget(self._btn_create_schema)
        schema_buttons.addWidget(self._btn_add_field)
        schema_buttons.addWidget(self._btn_edit_field)
        schema_buttons.addWidget(self._btn_delete_field)
        schema_layout.addLayout(schema_buttons)
        tabs.addTab(schema_tab, "Esquema")

        # --- pestaña catálogos ---
        catalog_tab = QWidget(self)
        catalog_layout = QVBoxLayout(catalog_tab)

        self._catalog_selector = QComboBox(catalog_tab)
        catalog_layout.addWidget(self._catalog_selector)

        catalog_manage_buttons = QHBoxLayout()
        self._btn_create_catalog = QPushButton("Crear catálogo")
        self._btn_rename_catalog = QPushButton("Renombrar catálogo")
        self._btn_delete_catalog = QPushButton("Eliminar catálogo")
        catalog_manage_buttons.addWidget(self._btn_create_catalog)
        catalog_manage_buttons.addWidget(self._btn_rename_catalog)
        catalog_manage_buttons.addWidget(self._btn_delete_catalog)
        catalog_layout.addLayout(catalog_manage_buttons)

        self._catalog_entry_list = QListWidget(catalog_tab)
        catalog_layout.addWidget(self._catalog_entry_list)

        entry_buttons = QHBoxLayout()
        self._btn_add_entry = QPushButton("Agregar entrada")
        self._btn_edit_entry = QPushButton("Editar entrada")
        self._btn_delete_entry = QPushButton("Eliminar entrada")
        entry_buttons.addWidget(self._btn_add_entry)
        entry_buttons.addWidget(self._btn_edit_entry)
        entry_buttons.addWidget(self._btn_delete_entry)
        catalog_layout.addLayout(entry_buttons)

        tabs.addTab(catalog_tab, "Catálogos")

        # --- pestaña cobertura ---
        coverage_tab = QWidget(self)
        coverage_layout = QVBoxLayout(coverage_tab)
        self._coverage_label = QLabel("Sin datos todavía.", coverage_tab)
        coverage_layout.addWidget(self._coverage_label)
        self._btn_refresh_coverage = QPushButton("Ver reporte de cobertura")
        coverage_layout.addWidget(self._btn_refresh_coverage)
        coverage_layout.addStretch(1)
        tabs.addTab(coverage_tab, "Cobertura")

        # --- pestaña valores por fuente ---
        # Asigna a una fuente concreta los valores de los campos del
        # esquema activo -- sin esto, un valor de metadatos solo se
        # podía asignar llamando a application directamente (pruebas o
        # scripts), nunca desde la interfaz.
        values_tab = QWidget(self)
        values_layout = QVBoxLayout(values_tab)

        # Ronda 5 (video 2, hallazgo real de usuario): duda conceptual
        # sobre por qué hay que escribir un valor a mano si "la
        # información ya vive dentro del documento". Aclaración: estos
        # valores son metadatos estructurados para filtrar/organizar
        # fuentes (p. ej. plantel = "Campus Norte"), independientes del
        # contenido de texto completo -- ese se extrae y se indexa por
        # separado (pestaña Ingesta) para la búsqueda semántica. Ninguno
        # de los dos sustituye al otro: un valor de metadato nunca se
        # deriva automáticamente del texto extraído.
        values_intro = QLabel(
            "Estos valores son metadatos estructurados (para filtrar y organizar fuentes, p. ej. "
            "\"plantel = Campus Norte\"), independientes del contenido de texto completo del documento: "
            "ese se extrae, fragmenta e indexa por separado en la pestaña Ingesta para la búsqueda "
            "semántica. Ningún valor se llena solo a partir del texto -- si un campo aplica a esta "
            "fuente (ver 6.1), hay que capturarlo aquí a mano.",
            values_tab,
        )
        values_intro.setWordWrap(True)
        values_layout.addWidget(values_intro)

        self._value_source_selector = QComboBox(values_tab)
        # Ronda 5 (hallazgo real de usuario): lista TODAS las fuentes del
        # proyecto sin importar su estado de validación (borrador,
        # sustituido, etc.) a propósito -- describir una fuente con
        # metadatos es un paso previo a validarla, no algo que dependa de
        # que ya esté validada. Ver también el tooltip de "Cambiar estado
        # de validación" en la pestaña Fuentes.
        self._value_source_selector.setToolTip(
            "Incluye fuentes de cualquier estado de validación (borrador, en revisión, validado, "
            "sustituido, vencido, rechazado): el estado de validación no restringe si se le pueden "
            "asignar metadatos a una fuente."
        )
        values_layout.addWidget(QLabel("Fuente:", values_tab))
        values_layout.addWidget(self._value_source_selector)

        self._current_values_list = QListWidget(values_tab)
        values_layout.addWidget(QLabel("Valores actuales:", values_tab))
        values_layout.addWidget(self._current_values_list)

        # Ronda 6, punto 23 (hallazgo real de usuario, vídeo 3): antes
        # no había ninguna forma de desasociar un valor ya guardado --
        # solo "Guardar valor" (que sobrescribe, nunca quita). Elegir
        # un valor de la lista de arriba y pulsar este botón lo quita.
        self._btn_delete_source_value = QPushButton("Quitar valor", values_tab)
        self._btn_delete_source_value.setToolTip(
            "Elige un valor en \"Valores actuales\" y pulsa aquí para desasociarlo de esta fuente "
            "(por ejemplo, si se asignó por error)."
        )
        values_layout.addWidget(self._btn_delete_source_value)

        form_row = QHBoxLayout()
        self._value_field_selector = QComboBox(values_tab)
        self._value_input_text = QLineEdit(values_tab)
        self._value_input_text.setPlaceholderText(
            "Valor (varios valores separados por coma si el campo lo permite)"
        )
        self._value_input_catalog = QComboBox(values_tab)
        self._value_input_catalog.setVisible(False)
        form_row.addWidget(QLabel("Campo:", values_tab))
        form_row.addWidget(self._value_field_selector)
        form_row.addWidget(self._value_input_text)
        form_row.addWidget(self._value_input_catalog)
        values_layout.addLayout(form_row)

        # Ronda 97 (hallazgo real de NEXOM, AGENTE UDL): el selector de
        # catálogo era de selección única también para campos de varios
        # valores -- guardar "torres_landa" sustituía a "hilario_medina".
        # Para esos campos se usa esta lista con casillas: muestra marcadas
        # las entradas que la fuente ya tiene y "Guardar valor" guarda
        # exactamente las marcadas.
        self._value_input_catalog_multi = QListWidget(values_tab)
        self._value_input_catalog_multi.setVisible(False)
        self._value_input_catalog_multi.setMaximumHeight(140)
        self._value_input_catalog_multi.setToolTip(
            "Marca todas las entradas del catálogo que aplican a esta fuente."
        )
        values_layout.addWidget(self._value_input_catalog_multi)
        self._value_bulk_add_mode = QCheckBox(
            "Al aplicar a varias fuentes, agregar a los valores que cada fuente ya tiene (no reemplazar)",
            values_tab,
        )
        self._value_bulk_add_mode.setChecked(True)
        self._value_bulk_add_mode.setVisible(False)
        values_layout.addWidget(self._value_bulk_add_mode)

        # Hallazgo real de validación visual: el campo "Valor" no
        # aclaraba qué formato se esperaba (fecha, número, texto
        # libre...) cuando el campo del esquema no usa catálogo -- el
        # usuario terminaba adivinando. Esta etiqueta muestra el
        # formato esperado según el tipo de dato del campo elegido
        # (ver _on_value_field_changed) y si admite varios valores.
        self._value_type_hint = QLabel(values_tab)
        self._value_type_hint.setWordWrap(True)
        values_layout.addWidget(self._value_type_hint)

        self._btn_save_value = QPushButton("Guardar valor", values_tab)
        values_layout.addWidget(self._btn_save_value)

        # Ronda 5, punto 21 (hallazgo real de usuario, vídeo 2):
        # capturar el mismo valor fuente por fuente es tedioso cuando
        # varias comparten el mismo valor en un campo -- reutiliza el
        # campo y el valor ya escritos arriba y los aplica a varias
        # fuentes elegidas en _MultiSourceSelectionDialog.
        self._btn_apply_value_to_multiple = QPushButton("Aplicar a varias fuentes…", values_tab)
        self._btn_apply_value_to_multiple.setToolTip(
            "Asigna el campo y valor de arriba a varias fuentes a la vez, en vez de una por una."
        )
        values_layout.addWidget(self._btn_apply_value_to_multiple)

        # Historial de cambios (ítem 5 de la evaluación de madurez
        # post-8-etapas): antes, sobrescribir un valor no dejaba
        # ningún rastro de cuál era el valor anterior ni cuándo
        # cambió -- ver domain.metadata.entities.MetadataValueChange.
        self._btn_view_value_history = QPushButton("Ver historial de cambios", values_tab)
        values_layout.addWidget(self._btn_view_value_history)

        tabs.addTab(values_tab, "Valores por fuente")
        self._values_tab = values_tab
        # Ronda 89 (2026-10-03, hallazgo real de usuario): al entrar a
        # "Valores por fuente" se recargan las opciones del catálogo del
        # campo seleccionado -- ver _reload_value_catalog_options.
        tabs.currentChanged.connect(self._on_metadata_subtab_changed)

        self._value_source_selector.currentIndexChanged.connect(self._on_value_source_changed)
        self._value_field_selector.currentIndexChanged.connect(self._on_value_field_changed)
        self._btn_save_value.clicked.connect(self._on_save_source_value)
        self._btn_apply_value_to_multiple.clicked.connect(self._on_apply_value_to_multiple_sources)
        self._btn_delete_source_value.clicked.connect(self._on_delete_source_value)
        self._btn_view_value_history.clicked.connect(self._on_view_value_history)

        self._btn_create_schema.clicked.connect(self._on_create_schema)
        self._btn_add_field.clicked.connect(self._on_add_field)
        self._btn_edit_field.clicked.connect(self._on_edit_field)
        self._btn_delete_field.clicked.connect(self._on_delete_field)
        self._btn_create_catalog.clicked.connect(self._on_create_catalog)
        self._btn_rename_catalog.clicked.connect(self._on_rename_catalog)
        self._btn_delete_catalog.clicked.connect(self._on_delete_catalog)
        self._btn_add_entry.clicked.connect(self._on_add_entry)
        self._btn_edit_entry.clicked.connect(self._on_edit_entry)
        self._btn_delete_entry.clicked.connect(self._on_delete_entry)
        self._catalog_selector.currentIndexChanged.connect(self._on_catalog_selection_changed)
        self._btn_refresh_coverage.clicked.connect(self._on_refresh_coverage)

        self._tabs = tabs
        self._set_enabled(False)

    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._schema_id = None
        self._set_enabled(self._project_id is not None)
        if self._project_id:
            self._project_label.setText(f"Proyecto activo: {self._project_id}")
            # Catálogos primero: _refresh_schema() necesita el selector
            # de catálogos ya poblado para poder mostrar el NOMBRE del
            # catálogo de cada campo en vez de su id crudo (ver
            # _catalog_name).
            self._refresh_catalog_selector()
            self._refresh_schema()
            self._refresh_value_source_selector()
            self._gate_status_label.refresh(self._context.release_service, self._project_id)
        else:
            self._project_label.setText("Selecciona un proyecto en la pestaña Proyectos.")
            self._gate_status_label.clear_status()
            self._field_list.clear()
            self._fields_by_id = {}
            self._catalog_selector.clear()
            self._catalog_entry_list.clear()
            self._entries_by_id = {}
            self._coverage_label.setText("Sin datos todavía.")
            self._value_source_selector.clear()
            self._value_field_selector.clear()
            self._current_values_list.clear()

    def _set_enabled(self, enabled: bool) -> None:
        self._tabs.setEnabled(enabled)

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _all_catalogs(self) -> list[tuple[str, str]]:
        # (id, nombre) de todos los catálogos cargados en el selector,
        # en el mismo orden en que aparecen (excluye el ítem vacío "").
        return [
            (self._catalog_selector.itemData(i), self._catalog_selector.itemText(i))
            for i in range(self._catalog_selector.count())
            if self._catalog_selector.itemData(i)
        ]

    def _catalog_name(self, catalog_id: Optional[str]) -> Optional[str]:
        if not catalog_id:
            return None
        idx = self._catalog_selector.findData(catalog_id)
        return self._catalog_selector.itemText(idx) if idx >= 0 else catalog_id

    # ---------- esquema ----------
    # Nota: hay un único esquema activo por proyecto (sin nombre propio,
    # ver application/metadata/service.py); "Crear esquema" no pide datos.
    def _refresh_schema(self) -> None:
        self._field_list.clear()
        self._fields_by_id = {}
        if self._project_id is None:
            return
        try:
            schema, fields = self._context.metadata_service.get_schema(self._project_id)
        except Exception:
            # Todavía no hay esquema activo para este proyecto.
            self._schema_id = None
            self.schema_changed.emit()
            return
        self._schema_id = schema.id
        for field in fields:
            self._fields_by_id[field.field_id] = field
            required = "obligatorio" if field.required else "opcional"
            # Nombre del catálogo, no su id crudo (hallazgo real de
            # validación visual: el código no es representativo para
            # el usuario -- ver _catalog_name).
            catalog_suffix = (
                f", catálogo={self._catalog_name(field.catalog_id)}" if field.catalog_id else ""
            )
            # Punto 10 de Validacion_observaciones_RAG_STUDIO.md: mostrar a
            # qué tipo de fuente aplica el campo (o que aplica a todas),
            # para que no haya que abrir "Editar campo" solo para saberlo.
            type_suffix = f", tipo de documento={field.document_type_code}" if field.document_type_code else ""
            self._field_list.addItem(
                f"{field.field_id} — {field.display_name} "
                f"[{field.data_type.value}, {required}{catalog_suffix}{type_suffix}]"
            )
        self._refresh_value_field_selector()
        self.schema_changed.emit()

    def _selected_field_id(self) -> Optional[str]:
        item = self._field_list.currentItem()
        if item is None:
            return None
        text = item.text()
        return text.split(" — ", 1)[0].strip()

    def _on_create_schema(self) -> None:
        if self._project_id is None:
            return
        try:
            schema = self._context.metadata_service.create_schema(self._project_id)
            self._schema_id = schema.id
            self._refresh_schema()
            self._gate_status_label.refresh(self._context.release_service, self._project_id)
            QMessageBox.information(self, "Esquema creado", "Se creó el esquema de metadatos del proyecto.")
        except Exception as exc:  # noqa: BLE001 - incluye "ya existe esquema activo"
            self._report_error(exc)

    def _on_add_field(self) -> None:
        if self._project_id is None or self._schema_id is None:
            QMessageBox.warning(self, "Falta esquema", "Crea primero un esquema activo.")
            return
        dialog = _FieldDialog(self._all_catalogs(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["field_id"] or not values["label"]:
            QMessageBox.warning(self, "Falta información", "field_id y etiqueta son obligatorios.")
            return
        try:
            self._context.metadata_service.add_field_definition(
                self._project_id, self._schema_id, values["field_id"], values["label"],
                values["data_type"], catalog_id=values["catalog_id"], required=values["required"],
                document_type_code=values["document_type_code"], multiple=values["multiple"],
                filterable=values["filterable"], inherited_by_chunks=values["inherited_by_chunks"],
            )
            self._refresh_schema()
            self._gate_status_label.refresh(self._context.release_service, self._project_id)
        except Exception as exc:  # noqa: BLE001 - incluye catálogo faltante en tipos catálogo
            self._report_error(exc)

    def _on_edit_field(self) -> None:
        field_id = self._selected_field_id()
        if field_id is None or self._project_id is None or self._schema_id is None:
            return
        existing = self._fields_by_id.get(field_id)
        if existing is None:
            return
        dialog = _FieldDialog(self._all_catalogs(), self, existing=existing)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["label"]:
            QMessageBox.warning(self, "Falta información", "La etiqueta es obligatoria.")
            return
        try:
            self._context.metadata_service.update_field_definition(
                self._project_id, self._schema_id, field_id, values["label"],
                catalog_id=values["catalog_id"], required=values["required"],
                document_type_code=values["document_type_code"], multiple=values["multiple"],
                filterable=values["filterable"], inherited_by_chunks=values["inherited_by_chunks"],
            )
            self._refresh_schema()
        except Exception as exc:  # noqa: BLE001 - incluye catálogo faltante en tipos catálogo
            self._report_error(exc)

    def _on_delete_field(self) -> None:
        field_id = self._selected_field_id()
        if field_id is None or self._project_id is None or self._schema_id is None:
            return
        confirm = QMessageBox.question(self, "Eliminar campo", f"¿Eliminar el campo {field_id!r}?")
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.metadata_service.delete_field_definition(self._project_id, self._schema_id, field_id)
            self._refresh_schema()
            self._gate_status_label.refresh(self._context.release_service, self._project_id)
        except Exception as exc:  # noqa: BLE001 - incluye FieldInUseError si ya tiene valores asignados
            self._report_error(exc)

    # ---------- catálogos ----------
    def _refresh_catalog_selector(self, select_catalog_id: Optional[str] = None) -> None:
        self._catalog_selector.clear()
        if self._project_id is None:
            return
        self._catalog_selector.addItem("", "")
        target_index = 0
        for i, catalog in enumerate(self._context.metadata_service.list_catalogs(self._project_id), start=1):
            self._catalog_selector.addItem(catalog.name, catalog.id)
            if select_catalog_id and catalog.id == select_catalog_id:
                target_index = i
        self._catalog_selector.setCurrentIndex(target_index)
        self._on_catalog_selection_changed(target_index)

    def _selected_catalog_id(self) -> Optional[str]:
        data = self._catalog_selector.currentData()
        return data or None

    def _on_catalog_selection_changed(self, _index: int) -> None:
        catalog_id = self._selected_catalog_id()
        if catalog_id:
            self._refresh_catalog_entries(catalog_id)
        else:
            self._catalog_entry_list.clear()
            self._entries_by_id = {}

    def _on_create_catalog(self) -> None:
        if self._project_id is None:
            return
        name, ok = QInputDialog.getText(self, "Crear catálogo", "Nombre del catálogo:")
        if not ok or not name.strip():
            return
        try:
            catalog = self._context.metadata_service.create_catalog(self._project_id, name.strip())
            self._refresh_catalog_selector(select_catalog_id=catalog.id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def _on_rename_catalog(self) -> None:
        catalog_id = self._selected_catalog_id()
        if catalog_id is None or self._project_id is None:
            return
        current_name = self._catalog_selector.currentText()
        dialog = _TextInputDialog("Renombrar catálogo", "Nuevo nombre:", current_name, self)
        if dialog.exec() != QDialog.Accepted or not dialog.text():
            return
        try:
            self._context.metadata_service.update_catalog(self._project_id, catalog_id, dialog.text())
            self._refresh_catalog_selector(select_catalog_id=catalog_id)
            self._refresh_schema()  # los campos que referencian este catálogo muestran su nombre nuevo
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def _on_delete_catalog(self) -> None:
        catalog_id = self._selected_catalog_id()
        if catalog_id is None or self._project_id is None:
            return
        confirm = QMessageBox.question(
            self, "Eliminar catálogo",
            f"¿Eliminar el catálogo {self._catalog_selector.currentText()!r} y todas sus entradas?",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.metadata_service.delete_catalog(self._project_id, catalog_id)
            self._refresh_catalog_selector()
        except Exception as exc:  # noqa: BLE001 - incluye "catálogo en uso por un campo"
            self._report_error(exc)

    def _refresh_catalog_entries(self, catalog_id: str) -> None:
        self._catalog_entry_list.clear()
        self._entries_by_id = {}
        if self._project_id is None:
            return
        for entry in self._context.metadata_service.list_catalog_entries(self._project_id, catalog_id):
            self._entries_by_id[entry.id] = entry
            self._catalog_entry_list.addItem(f"{entry.value_code} — {entry.label}  ({entry.id})")
        # Ronda 89: este método corre después de agregar, editar o
        # eliminar una entrada; el selector de "Valores por fuente" debe
        # reflejarlo sin reiniciar la aplicación.
        self._reload_value_catalog_options()

    def _on_metadata_subtab_changed(self, index: int) -> None:
        if self._tabs.widget(index) is self._values_tab:
            self._reload_value_catalog_options()

    def _reload_value_catalog_options(self) -> None:
        """Ronda 89 (2026-10-03, hallazgo real de usuario): "agregué un
        valor (presencial) en Catálogos, me cambié a Valores por fuente y
        no me muestra el valor; tuve que cerrar la app". Las entradas del
        selector de catálogo de "Valores por fuente" solo se cargaban al
        CAMBIAR de campo (_on_value_field_changed); si el campo ya estaba
        seleccionado, una entrada nueva no aparecía nunca. Se recargan aquí
        conservando la entrada elegida, si sigue existiendo."""
        if not hasattr(self, "_value_input_catalog"):
            return  # todavía construyendo la interfaz
        anterior = self._value_input_catalog.currentData()
        # Ronda 97: también se conservan las casillas marcadas (sin guardar)
        # de un campo de varios valores.
        marcadas = self._checked_catalog_codes() if not self._value_input_catalog_multi.isHidden() else None
        self._on_value_field_changed(self._value_field_selector.currentIndex())
        if anterior is not None:
            indice = self._value_input_catalog.findData(anterior)
            if indice >= 0:
                self._value_input_catalog.setCurrentIndex(indice)
        if marcadas is not None and not self._value_input_catalog_multi.isHidden():
            self._set_checked_catalog_codes(marcadas)

    def _selected_entry_id(self) -> Optional[str]:
        item = self._catalog_entry_list.currentItem()
        if item is None:
            return None
        return item.text().rsplit("(", 1)[-1].rstrip(")")

    def _on_add_entry(self) -> None:
        catalog_id = self._selected_catalog_id()
        if self._project_id is None or catalog_id is None:
            QMessageBox.warning(self, "Falta catálogo", "Selecciona o crea primero un catálogo.")
            return
        dialog = _AddCatalogEntryDialog(list(self._entries_by_id.values()), self)
        if dialog.exec() != QDialog.Accepted or not dialog.value_code() or not dialog.label():
            return
        try:
            self._context.metadata_service.add_catalog_entry(
                self._project_id, catalog_id, dialog.value_code(), dialog.label(),
                parent_entry_id=dialog.parent_entry_id(),
            )
            self._refresh_catalog_entries(catalog_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def _on_edit_entry(self) -> None:
        catalog_id = self._selected_catalog_id()
        entry_id = self._selected_entry_id()
        if self._project_id is None or catalog_id is None or entry_id is None:
            return
        existing = self._entries_by_id.get(entry_id)
        if existing is None:
            return
        # La propia entrada se excluye de las opciones de padre -- no
        # puede convertirse en su propio padre (Ronda 4, punto 4c).
        other_entries = [e for e in self._entries_by_id.values() if e.id != entry_id]
        dialog = _EditCatalogEntryDialog(
            existing.label, existing.value_code, other_entries,
            initial_parent_entry_id=existing.parent_entry_id, parent=self,
        )
        if dialog.exec() != QDialog.Accepted or not dialog.label() or not dialog.value_code():
            return
        try:
            self._context.metadata_service.update_catalog_entry(
                self._project_id, catalog_id, entry_id, dialog.label(),
                parent_entry_id=dialog.parent_entry_id(), value_code=dialog.value_code(),
            )
            self._refresh_catalog_entries(catalog_id)
        except Exception as exc:  # noqa: BLE001 - incluye "no se puede editar el código: en uso"
            self._report_error(exc)

    def _on_delete_entry(self) -> None:
        catalog_id = self._selected_catalog_id()
        entry_id = self._selected_entry_id()
        if self._project_id is None or catalog_id is None or entry_id is None:
            return
        existing = self._entries_by_id.get(entry_id)
        label = existing.value_code if existing else entry_id
        confirm = QMessageBox.question(self, "Eliminar entrada", f"¿Eliminar la entrada {label!r}?")
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.metadata_service.delete_catalog_entry(self._project_id, catalog_id, entry_id)
            self._refresh_catalog_entries(catalog_id)
        except Exception as exc:  # noqa: BLE001 - incluye "entrada en uso por una fuente"
            self._report_error(exc)

    # ---------- cobertura ----------
    def _on_refresh_coverage(self) -> None:
        if self._project_id is None:
            return
        try:
            report = self._context.metadata_service.get_coverage_report(self._project_id)
            if report["total_sources"] == 0:
                self._coverage_label.setText("El proyecto todavía no tiene fuentes registradas.")
                return
            ratio = report["coverage_ratio"]
            meets = "cumple" if report["meets_acceptance_threshold"] else "no cumple"
            self._coverage_label.setText(
                f"{report['sources_fully_described']}/{report['total_sources']} fuentes "
                f"con todos sus campos obligatorios completos ({ratio:.0%}) — "
                f"umbral de aceptación 95% [{meets}]"
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    # ---------- valores por fuente ----------
    def refresh_value_source_selector(self) -> None:
        """Punto público, análogo a IngestionPanel.refresh_document_type_options
        (hallazgo real de usuario, ver Validacion_observaciones_RAG_STUDIO.md,
        Ronda 5): antes, el selector de fuentes de "Valores por fuente" solo se
        refrescaba al llamar set_active_project -- registrar o importar fuentes
        nuevas dentro de la misma sesión (sin cambiar de proyecto) dejaba el
        selector desactualizado hasta reiniciar la aplicación. Se conecta a
        SourcesPanel.sources_changed en ui/projects/main_window.py."""
        self._refresh_value_source_selector()

    def _refresh_value_source_selector(self) -> None:
        self._value_source_selector.clear()
        if self._project_id is None:
            return
        for source in self._context.document_service.list_sources(self._project_id):
            self._value_source_selector.addItem(source.title, source.id)
        self._on_value_source_changed(self._value_source_selector.currentIndex())

    def _refresh_value_field_selector(self) -> None:
        self._value_field_selector.clear()
        fields = self._fields_for_active_value_source()
        for field in fields:
            self._value_field_selector.addItem(f"{field.field_id} — {field.display_name}", field.field_id)
        self._on_value_field_changed(self._value_field_selector.currentIndex())

    def _fields_for_active_value_source(self) -> list:
        # Sin fuente seleccionada todavía (p. ej. proyecto sin fuentes
        # registradas) se muestran todos los campos del esquema, para no
        # dejar el selector vacío sin necesidad -- MetadataService.
        # list_applicable_fields requiere un document_type_code real.
        source_id = self._selected_value_source_id()
        if self._project_id is None or source_id is None:
            return list(self._fields_by_id.values())
        try:
            source = self._context.document_service.get_source(self._project_id, source_id)
        except Exception:  # noqa: BLE001 - la fuente pudo eliminarse entre listar y seleccionar
            return list(self._fields_by_id.values())
        try:
            # Hallazgo real de usuario (Auditoria 2026-09-02, evidencia
            # RAG_STUDIO_01.mov / RAG_STUDIO_01_consola.txt): a diferencia de
            # `_refresh_schema()` (que ya protege su propia llamada a
            # `get_schema()` mas arriba en este archivo), esta llamada a
            # `list_applicable_fields()` -- que internamente tambien
            # llama a `get_schema()` -- no estaba protegida. Un proyecto
            # sin esquema de metadatos activo todavia (MetadataDomainError,
            # "No hay esquema de metadatos activo para ...") hacia que
            # simplemente seleccionar una fuente en "Valores por fuente"
            # tumbara la aplicacion entera con una excepcion no
            # capturada, en un bucle que se repetia cada vez que Qt volvia
            # a disparar el mismo evento de seleccion.
            return self._context.metadata_service.list_applicable_fields(self._project_id, source.document_type_code)
        except Exception:  # noqa: BLE001 - mismo criterio que el try anterior: sin esquema activo, sin campos
            return list(self._fields_by_id.values())

    def _selected_value_source_id(self) -> Optional[str]:
        return self._value_source_selector.currentData() or None

    def _selected_value_field_id(self) -> Optional[str]:
        return self._value_field_selector.currentData() or None

    def _on_value_source_changed(self, _index: int) -> None:
        self._refresh_current_values()
        # Punto 10 de Validacion_observaciones_RAG_STUDIO.md: los campos
        # ofrecidos dependen de la fuente activa (genéricos + los de su
        # mismo document_type_code), así que hay que recalcularlos cada
        # vez que cambia la fuente seleccionada, no solo al abrir el
        # esquema.
        self._refresh_value_field_selector()

    def _refresh_current_values(self) -> None:
        # Ronda 3/4 (punto 12 de Validacion_observaciones_RAG_STUDIO.md):
        # nada impide que una fuente cambie de document_type_code (al
        # editarla) o que un campo cambie el suyo (al editarlo) después
        # de que ya se capturaron valores para esa combinación. El valor
        # sigue existiendo -- Cobertura ya lo excluye correctamente del
        # cálculo -- pero antes esta lista lo mostraba igual que a
        # cualquier otro, sin ninguna indicación de que ya no aplica al
        # tipo vigente de la fuente. Se marca explícitamente en vez de
        # ocultarlo (ocultarlo sin aviso sería peor: el usuario no
        # entendería por qué "desapareció" un valor que sí capturó).
        self._current_values_list.clear()
        source_id = self._selected_value_source_id()
        if self._project_id is None or source_id is None:
            return
        source_document_type_code = None
        try:
            source_document_type_code = self._context.document_service.get_source(
                self._project_id, source_id
            ).document_type_code
        except Exception:  # noqa: BLE001 - la fuente pudo eliminarse entre selección y consulta
            pass
        for value in self._context.metadata_service.list_source_metadata_values(self._project_id, source_id):
            field = self._fields_by_id.get(value.field_id)
            label = field.display_name if field else value.field_id
            campo_no_aplica = (
                field is not None
                and field.document_type_code is not None
                and source_document_type_code is not None
                and field.document_type_code != source_document_type_code
            )
            aviso = "  [no aplica al tipo de documento actual de esta fuente]" if campo_no_aplica else ""
            # Ronda 97: en un campo de varios valores, una fila por valor
            # (con su etiqueta de catálogo), para verlos todos con claridad
            # y poder quitar uno solo.
            if field is not None and field.multiple:
                codigos = stored_values_list(value.value)
                etiquetas = self._catalog_labels(field.catalog_id) if field.catalog_id else {}
                for posicion, codigo in enumerate(codigos, start=1):
                    mostrado = f"{codigo} — {etiquetas[codigo]}" if codigo in etiquetas else codigo
                    self._add_current_value_row(
                        f"{label} ({value.field_id}) [{posicion}/{len(codigos)}]: {mostrado}{aviso}",
                        value.field_id, codigo,
                    )
                continue
            self._add_current_value_row(f"{label} ({value.field_id}): {value.value}{aviso}", value.field_id, None)

    def _add_current_value_row(self, text: str, field_id: str, item_code: Optional[str]) -> None:
        # Ronda 6, punto 23: se guarda field_id en el item (rol 1,
        # mismo que usa _MultiSourceSelectionDialog para source_id)
        # para que _on_delete_source_value sepa qué campo quitar sin
        # tener que re-parsear el texto mostrado. Ronda 97: y el código
        # concreto en _ITEM_VALUE_ROLE si el campo es de varios valores.
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, field_id)
        item.setData(_ITEM_VALUE_ROLE, item_code)
        self._current_values_list.addItem(item)

    def _catalog_labels(self, catalog_id: str) -> dict[str, str]:
        if self._project_id is None:
            return {}
        try:
            return {e.value_code: e.label for e in self._context.metadata_service.list_catalog_entries(
                self._project_id, catalog_id)}
        except Exception:  # noqa: BLE001 - catálogo borrado entre listar y mostrar: se muestra solo el código
            return {}

    def _stored_values_for(self, field_id: str) -> list[str]:
        source_id = self._selected_value_source_id()
        if self._project_id is None or source_id is None:
            return []
        for value in self._context.metadata_service.list_source_metadata_values(self._project_id, source_id):
            if value.field_id == field_id:
                return stored_values_list(value.value)
        return []

    def _checked_catalog_codes(self) -> list[str]:
        lista = self._value_input_catalog_multi
        return [
            lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lista.count())
            if lista.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _set_checked_catalog_codes(self, codes: list[str]) -> None:
        lista = self._value_input_catalog_multi
        for i in range(lista.count()):
            item = lista.item(i)
            item.setCheckState(
                Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in codes else Qt.CheckState.Unchecked
            )

    def _is_multi_catalog_field(self, field) -> bool:
        return field is not None and field.catalog_id is not None and bool(getattr(field, "multiple", False))

    def _on_value_field_changed(self, _index: int) -> None:
        field_id = self._selected_value_field_id()
        field = self._fields_by_id.get(field_id) if field_id else None
        is_catalog_backed = field is not None and field.catalog_id is not None
        is_multi_catalog = self._is_multi_catalog_field(field)
        self._value_input_catalog.setVisible(is_catalog_backed and not is_multi_catalog)
        self._value_input_catalog_multi.setVisible(is_multi_catalog)
        self._value_input_text.setVisible(not is_catalog_backed)
        self._value_bulk_add_mode.setVisible(bool(field is not None and getattr(field, "multiple", False)))
        if is_multi_catalog and field is not None:
            # Ronda 97: lista con casillas; se marcan las entradas que la
            # fuente ya tiene guardadas, así se ven y se editan juntas.
            self._value_input_catalog_multi.clear()
            guardados = self._stored_values_for(field.field_id)
            if self._project_id is not None:
                for entry in self._context.metadata_service.list_catalog_entries(self._project_id, field.catalog_id):
                    item = QListWidgetItem(f"{entry.value_code} — {entry.label}")
                    item.setData(Qt.ItemDataRole.UserRole, entry.value_code)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked if entry.value_code in guardados else Qt.CheckState.Unchecked
                    )
                    self._value_input_catalog_multi.addItem(item)
            self._value_type_hint.setText(
                "Campo de varios valores con catálogo -- marca TODAS las entradas que apliquen a esta fuente. "
                "\"Guardar valor\" guarda exactamente las marcadas (desmarcar una la quita). "
                "\"Aplicar a varias fuentes…\" usa las marcadas; con la casilla de abajo activada se suman "
                "a los valores que cada fuente ya tiene."
            )
        elif is_catalog_backed and field is not None:
            self._value_input_catalog.clear()
            if self._project_id is not None:
                for entry in self._context.metadata_service.list_catalog_entries(self._project_id, field.catalog_id):
                    self._value_input_catalog.addItem(f"{entry.value_code} — {entry.label}", entry.value_code)
            hint = "Este campo usa catálogo -- elige una de las entradas del selector de arriba."
            if getattr(field.data_type, "value", field.data_type) == "seleccion_multiple":
                # Ronda 97: tipo "selección múltiple" sin "Permite varios
                # valores" solo admite un valor; se avisa en vez de dejar
                # que el usuario descubra la sustitución al guardar.
                hint += (
                    " Atención: el campo es de tipo selección múltiple pero no tiene activado "
                    "\"Permite varios valores\" (Esquema > Editar campo); mientras tanto solo admite uno."
                )
            self._value_type_hint.setText(hint)
        elif field is not None:
            data_type_value = getattr(field.data_type, "value", field.data_type)
            hint = FIELD_DATA_TYPE_VALUE_HINTS.get(data_type_value, "Texto libre.")
            if getattr(field, "multiple", False):
                hint += " Admite varios valores separados por coma."
            self._value_type_hint.setText(hint)
        else:
            self._value_type_hint.setText("")

    def _read_value_input(self):
        """Campo y valor tal como están escritos en el formulario de
        "Valores por fuente" -- lo usan tanto _on_save_source_value
        (una fuente) como _on_apply_value_to_multiple_sources (varias
        fuentes, Ronda 5, punto 21), para no duplicar la lógica de
        texto libre vs. selector de catálogo."""
        field_id = self._selected_value_field_id()
        field = self._fields_by_id.get(field_id) if field_id else None
        raw_value: object
        if self._is_multi_catalog_field(field):
            raw_value = self._checked_catalog_codes()
        elif field is not None and field.catalog_id is not None:
            raw_value = self._value_input_catalog.currentData()
        else:
            text = self._value_input_text.text().strip()
            raw_value = [v.strip() for v in text.split(",") if v.strip()] if (field and field.multiple) else text
        return field_id, raw_value

    def _on_save_source_value(self) -> None:
        if self._project_id is None or self._schema_id is None:
            QMessageBox.warning(self, "Falta esquema", "Crea primero un esquema activo con al menos un campo.")
            return
        source_id = self._selected_value_source_id()
        field_id, raw_value = self._read_value_input()
        if source_id is None or field_id is None:
            QMessageBox.warning(self, "Faltan datos", "Elige una fuente y un campo.")
            return
        if self._is_multi_catalog_field(self._fields_by_id.get(field_id)) and not raw_value:
            QMessageBox.information(
                self, "Sin valores marcados",
                "Marca al menos una entrada del catálogo. Para quitar todos los valores del campo, "
                "elígelo en \"Valores actuales\" y usa \"Quitar valor\".",
            )
            return
        try:
            self._context.metadata_service.set_source_metadata_value(
                self._project_id, self._schema_id, source_id, field_id, raw_value,
            )
        except Exception as exc:  # noqa: BLE001 - incluye valor fuera de catálogo, campo obligatorio vacío
            self._report_error(exc)
            return
        self._value_input_text.clear()
        self._refresh_current_values()
        self._on_value_field_changed(self._value_field_selector.currentIndex())

    def _on_apply_value_to_multiple_sources(self) -> None:
        # Ronda 5, punto 21 (hallazgo real de usuario, vídeo 2): extiende
        # a "Valores por fuente" el mismo patrón de selección múltiple ya
        # usado en Fuentes para corregir document_type_code en bloque
        # (ver ui/sources/panel.py, _on_bulk_set_document_type_code) --
        # aquí a través de un diálogo aparte porque el selector "Fuente:"
        # de esta pestaña es de selección única (también se usa para ver
        # valores actuales e historial de una sola fuente).
        if self._project_id is None or self._schema_id is None:
            QMessageBox.warning(self, "Falta esquema", "Crea primero un esquema activo con al menos un campo.")
            return
        field_id, raw_value = self._read_value_input()
        if field_id is None:
            QMessageBox.warning(self, "Faltan datos", "Elige un campo y escribe (o elige) el valor a aplicar.")
            return
        field = self._fields_by_id.get(field_id)
        es_multiple = bool(field is not None and getattr(field, "multiple", False))
        if self._is_multi_catalog_field(field) and not raw_value:
            QMessageBox.information(self, "Sin valores marcados", "Marca al menos una entrada del catálogo.")
            return
        # Ronda 97: en campos de varios valores, por defecto se AGREGA a lo
        # que cada fuente ya tiene (no se pierde, p. ej., un plantel ya
        # asignado); desmarcando la casilla se reemplaza.
        modo = (
            VALUE_ASSIGNMENT_ADD if es_multiple and self._value_bulk_add_mode.isChecked() else VALUE_ASSIGNMENT_REPLACE
        )
        sources = self._context.document_service.list_sources(self._project_id)
        if not sources:
            QMessageBox.information(self, "Sin fuentes", "Este proyecto todavía no tiene fuentes registradas.")
            return
        dialog = _MultiSourceSelectionDialog(sources, self)
        if dialog.exec() != QDialog.Accepted:
            return
        source_ids = dialog.selected_source_ids()
        if not source_ids:
            QMessageBox.information(self, "Selecciona fuentes", "No se eligió ninguna fuente.")
            return
        try:
            result = self._context.metadata_service.bulk_set_source_metadata_value(
                self._project_id, self._schema_id, source_ids, field_id, raw_value, modo,
            )
        except Exception as exc:  # noqa: BLE001 - incluye valor fuera de catálogo, campo obligatorio vacío
            self._report_error(exc)
            return
        self._value_input_text.clear()
        self._refresh_current_values()
        self._on_value_field_changed(self._value_field_selector.currentIndex())
        detalle = ""
        if es_multiple:
            detalle = (
                " Los valores se agregaron a los que cada fuente ya tenía."
                if modo == VALUE_ASSIGNMENT_ADD else " Cada fuente quedó exactamente con los valores indicados."
            )
        QMessageBox.information(
            self, "Valor aplicado a varias fuentes",
            f"Actualizadas: {result.updated_count}. Omitidas: {result.skipped_count}.{detalle}",
        )

    def _on_delete_source_value(self) -> None:
        # Ronda 6, punto 23 (hallazgo real de usuario, vídeo 3): antes
        # no había ninguna forma de desasociar un valor ya guardado --
        # mismo estilo de confirmación que _on_delete_field/_on_delete_entry.
        source_id = self._selected_value_source_id()
        if self._project_id is None or source_id is None:
            QMessageBox.warning(self, "Falta información", "Elige una fuente primero.")
            return
        item = self._current_values_list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Selecciona un valor", "Elige un valor en \"Valores actuales\" antes de quitarlo.",
            )
            return
        field_id = item.data(Qt.ItemDataRole.UserRole)
        field = self._fields_by_id.get(field_id)
        label = field.display_name if field else field_id
        codigo = item.data(_ITEM_VALUE_ROLE)
        if codigo is not None:
            # Ronda 97: en un campo de varios valores se quita solo el valor
            # elegido; los demás se conservan.
            confirm = QMessageBox.question(
                self, "Quitar valor",
                f"¿Quitar \"{codigo}\" de \"{label}\" ({field_id}) en esta fuente? Los demás valores se conservan.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                self._context.metadata_service.remove_source_metadata_value_item(
                    self._project_id, self._schema_id, source_id, field_id, codigo,
                )
            except Exception as exc:  # noqa: BLE001 - incluye el caso en que el valor ya no estaba asignado
                self._report_error(exc)
                return
            self._refresh_current_values()
            self._on_value_field_changed(self._value_field_selector.currentIndex())
            return
        confirm = QMessageBox.question(
            self, "Quitar valor", f"¿Quitar el valor de \"{label}\" ({field_id}) de esta fuente?",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.metadata_service.delete_source_metadata_value(self._project_id, source_id, field_id)
        except Exception as exc:  # noqa: BLE001 - incluye el caso en que el valor ya no existía
            self._report_error(exc)
            return
        self._refresh_current_values()
        self._on_value_field_changed(self._value_field_selector.currentIndex())

    def _on_view_value_history(self) -> None:
        source_id = self._selected_value_source_id()
        if self._project_id is None or source_id is None:
            QMessageBox.warning(self, "Falta información", "Elige una fuente primero.")
            return
        history = self._context.metadata_service.list_value_history(self._project_id, source_id)
        if not history:
            QMessageBox.information(
                self, "Historial de cambios", "Esta fuente todavía no tiene ningún valor de metadatos asignado.",
            )
            return
        lines = []
        for change in history:
            field = self._fields_by_id.get(change.field_id)
            label = field.display_name if field else change.field_id
            previous = change.previous_value if change.previous_value is not None else "(sin asignar)"
            # Ronda 6, punto 23: new_value=None identifica un borrado
            # (DeleteSourceMetadataValue) -- mismo texto "(sin asignar)"
            # que ya se usaba para previous_value=None, pero como
            # estado de llegada en vez de partida.
            new = change.new_value if change.new_value is not None else "(sin asignar)"
            lines.append(
                f"{change.changed_at:%Y-%m-%d %H:%M} — {label} ({change.field_id}): "
                f"{previous} → {new}"
            )
        QMessageBox.information(self, "Historial de cambios", "\n".join(lines))
