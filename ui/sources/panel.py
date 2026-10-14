"""Panel de inventario de fuentes (Módulo 2).

Regla de capa: solo llama a application.document_service. Nunca
importa domain directamente — los vocabularios de opciones (tipos de
fuente, niveles de acceso, estados) vienen de
application.documents.options, no de domain.documents.entities.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional

from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.theme import aplicar_color_estado_item

from .image_source_logic import image_file_dialog_filter, image_preview_placeholder_text

from application.documents.options import (
    ACCESS_LEVEL_OPTIONS, NON_FILE_SOURCE_TYPE_VALUES, SOURCE_TYPE_OPTIONS,
    TERMINAL_VALIDATION_STATUS_VALUES, VALIDATION_STATUS_OPTIONS,
)
from ui.errors import describe_error


class _RegisterSourceDialog(QDialog):
    """Diálogo de alta y edición de fuente.

    En modo edición (`existing` no es None), los campos se pre-llenan
    con los valores actuales -- antes de esto, seleccionar una fuente
    no mostraba en ningún lado lo que ya se había capturado, así que
    corregir un error (p. ej. el hallazgo real de validación visual:
    registrar con la carpeta en "Ubicación" en vez de la ruta completa
    del archivo) obligaba a registrar una fuente nueva en vez de
    corregir la existente.

    `location_locked=True` deshabilita Ubicación/Tipo (con una nota
    explicando por qué): una vez que la fuente ya tiene texto extraído,
    cambiar el archivo o tipo detrás en silencio invalidaría la
    extracción/fragmentos/índice ya construidos sin ningún aviso -- ver
    domain.documents.exceptions.SourceStructuralFieldsLockedError. El
    título, área propietaria, nivel de acceso, vigencia, autoridad y
    tipo de documento siguen editables siempre: son descriptivos, nada
    se construye a partir de ellos.

    Tipo de documento (document_type_code) se agregó para poder acotar
    qué campos del esquema de metadatos aplican a esta fuente (ver
    ui/metadata/panel.py, "Valores por fuente") -- observación real de
    usuario, ver docs proyecto/Validacion_observaciones_RAG_STUDIO.md,
    punto 10.

    Vigencia (vigente desde/hasta) y autoridad se agregaron para cerrar
    la discrepancia reportada entre el manual de usuario (secciones 5.2
    y 5.4, que ya describían estos datos) y la interfaz, que hasta
    ahora solo los mostraba en el panel de detalle en modo lectura (ver
    SourcesPanel._refresh_detail) sin ninguna forma de capturarlos.

    Idioma y "esta fuente sustituye a" se agregaron por el mismo motivo
    (análisis de brechas dominio/UI a raíz de la nota de "valor
    múltiple" del Manual del Usuario, sección 6.1): domain.documents.
    entities.Source y application.documents.commands.register_source
    ya soportan `language` y `supersedes_source_id` -- incluida la
    detección real de duplicados por huella de contenido
    (DuplicateSourceError) y la transición automática de la fuente
    anterior a SUSTITUIDO -- pero, hasta ahora, ningún control de esta
    ventana permitía capturarlos: `language` quedaba fijo en "es" para
    toda fuente registrada desde la interfaz, y no había forma de
    declarar que una fuente nueva sustituye a una anterior sin editar
    la base de datos a mano. "Esta fuente sustituye a" solo aplica al
    registrar (no tiene sentido declarar una sustitución retroactiva al
    editar una fuente ya existente), así que solo aparece cuando
    `editing` es False y se recibieron `candidates`.

    La huella de contenido (content_hash) NO se captura aquí a mano:
    SourcesPanel._on_register_source la calcula sola (SHA-256 del
    archivo elegido en "Ubicación"), igual que ya hace
    register_sources_from_folder con la columna hash_contenido del
    manifiesto -- pedirla a mano solo invitaría a errores de captura
    en un dato que existe justo para detectar errores de captura.

    Vista previa de imagen (Fase 4 de multimodalidad nativa, RAG 3, ver
    docs proyecto/RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx,
    sección 3.6): cuando el tipo elegido es Imagen, "Elegir archivo…"
    filtra por extensiones de imagen y aparece una miniatura del
    archivo elegido -- así se confirma visualmente que se seleccionó el
    archivo correcto antes de registrar la fuente. No es una validación
    real (una extensión de imagen no garantiza contenido válido);
    IndexImageSource ya reporta con claridad si el archivo resulta no
    ser una imagen legible al intentar embeberlo. La decisión de qué
    texto/filtro mostrar vive en ui.sources.image_source_logic (sin
    Qt, con pruebas propias) -- este diálogo solo la usa y decide qué
    hacer con un QPixmap real."""

    def __init__(
        self, parent: Optional[QWidget] = None, existing=None, location_locked: bool = False,
        candidates: Optional[list] = None,
    ):
        super().__init__(parent)
        editing = existing is not None
        self.setWindowTitle("Editar fuente" if editing else "Registrar fuente")

        self._title = QLineEdit(self)
        self._source_type = QComboBox(self)
        self._source_type.addItems(SOURCE_TYPE_OPTIONS)
        self._location = QLineEdit(self)
        self._btn_browse = QPushButton("Elegir archivo…", self)
        self._btn_browse.clicked.connect(self._on_browse)
        self._owner_area = QLineEdit(self)
        self._access_level = QComboBox(self)
        self._access_level.addItems(ACCESS_LEVEL_OPTIONS)

        # Vigencia: casilla "Sin definir" marcada por defecto (la
        # mayoría de las fuentes no necesitan acotar vigencia al
        # registrarse) -- al desmarcarla se habilita el QDateEdit
        # correspondiente. Sin esto, un QDateEdit no tiene forma nativa
        # de representar "sin fecha" (None), y ese es justo el estado
        # por defecto de valid_from/valid_to en domain.
        self._valid_from_undefined = QCheckBox("Sin definir", self)
        self._valid_from = QDateEdit(self)
        self._valid_from.setCalendarPopup(True)
        self._valid_from.setDisplayFormat("yyyy-MM-dd")
        self._valid_from.setDate(QDate.currentDate())
        self._valid_from_undefined.toggled.connect(lambda checked: self._valid_from.setEnabled(not checked))

        self._valid_to_undefined = QCheckBox("Sin definir", self)
        self._valid_to = QDateEdit(self)
        self._valid_to.setCalendarPopup(True)
        self._valid_to.setDisplayFormat("yyyy-MM-dd")
        self._valid_to.setDate(QDate.currentDate())
        self._valid_to_undefined.toggled.connect(lambda checked: self._valid_to.setEnabled(not checked))

        # Autoridad: convención de domain.documents.entities.Source es
        # "1 = máxima autoridad, None = no priorizada" -- se representa
        # aquí con 0 como valor especial de "sin definir" (mapeado a
        # None en values()) para poder usar un QSpinBox simple, mismo
        # patrón que los campos de "Prioridad" en Diseño conversacional.
        self._source_authority = QSpinBox(self)
        self._source_authority.setRange(0, 100)
        self._source_authority.setSpecialValueText("Sin definir")
        self._source_authority.setToolTip(
            "1 = máxima autoridad frente a otras fuentes en caso de contradicción. 0 = sin definir."
        )

        # Punto 10 de Validacion_observaciones_RAG_STUDIO.md: antes no
        # había ninguna forma de distinguir, dentro del mismo proyecto,
        # una fuente de "contactos" de una de "requisitos de admisión" --
        # el esquema de metadatos era plano y compartido por todas las
        # fuentes por igual. "default" es el mismo valor libre que ya
        # usaba Ingesta para document_type_code (ver ui/ingestion/panel.py);
        # se reutiliza aquí para poder acotar qué campos del esquema
        # (ver ui/metadata/panel.py, "Valores por fuente") aplican a esta
        # fuente en particular.
        self._document_type_code = QLineEdit(self)
        self._document_type_code.setText("default")

        # Idioma: existe en domain.documents.entities.Source desde
        # siempre (default "es"), pero ningún control de esta ventana
        # lo expuso hasta ahora -- ver docstring de la clase.
        self._language = QLineEdit(self)
        self._language.setText("es")
        self._language.setToolTip('Código corto de idioma, por ejemplo "es", "en". "es" si se deja vacío.')

        # Vista previa de imagen (Fase 4 de multimodalidad nativa, RAG
        # 3) -- ver docstring de la clase. Se crea antes de pre-llenar
        # los campos (más abajo) para que el modo edición pueda
        # mostrarla desde el primer instante si la fuente ya es una
        # imagen registrada.
        self._image_preview = QLabel(self)
        self._image_preview.setAlignment(Qt.AlignCenter)
        self._image_preview.setMinimumHeight(120)
        self._image_preview.setWordWrap(True)

        # "Esta fuente sustituye a": solo tiene sentido al registrar
        # (ver docstring de la clase). Con candidates=None o vacío, la
        # opción "-- ninguna --" queda como única alternativa -- mismo
        # patrón que "Campo de metadatos ligado" en Diseño conversacional
        # (ui/conversational/panel.py).
        self._supersedes = None
        if not editing and candidates:
            self._supersedes = QComboBox(self)
            self._supersedes.addItem("-- ninguna --", None)
            for source_id, label in candidates:
                self._supersedes.addItem(label, source_id)
            self._supersedes.setToolTip(
                "Si esta fuente es una versión nueva de un documento ya registrado, elígelo "
                "aquí: la fuente anterior pasará automáticamente a estado \"sustituido\" (si "
                "estaba validada) y el historial documental queda preservado en vez de "
                "reescribirse."
            )

        if editing:
            self._title.setText(existing.title)
            idx = self._source_type.findText(existing.source_type.value)
            if idx >= 0:
                self._source_type.setCurrentIndex(idx)
            self._location.setText(existing.location or "")
            self._owner_area.setText(existing.owner_area or "")
            idx = self._access_level.findText(existing.access_level.value)
            if idx >= 0:
                self._access_level.setCurrentIndex(idx)
            if existing.valid_from is not None:
                self._valid_from_undefined.setChecked(False)
                self._valid_from.setDate(QDate(existing.valid_from.year, existing.valid_from.month, existing.valid_from.day))
            else:
                self._valid_from_undefined.setChecked(True)
            if existing.valid_to is not None:
                self._valid_to_undefined.setChecked(False)
                self._valid_to.setDate(QDate(existing.valid_to.year, existing.valid_to.month, existing.valid_to.day))
            else:
                self._valid_to_undefined.setChecked(True)
            self._source_authority.setValue(existing.source_authority or 0)
            self._document_type_code.setText(existing.document_type_code)
            self._language.setText(existing.language)
        else:
            self._valid_from_undefined.setChecked(True)
            self._valid_to_undefined.setChecked(True)

        location_row = QHBoxLayout()
        location_row.addWidget(self._location)
        location_row.addWidget(self._btn_browse)

        valid_from_row = QHBoxLayout()
        valid_from_row.addWidget(self._valid_from)
        valid_from_row.addWidget(self._valid_from_undefined)

        valid_to_row = QHBoxLayout()
        valid_to_row.addWidget(self._valid_to)
        valid_to_row.addWidget(self._valid_to_undefined)

        form = QFormLayout()
        form.addRow("Título*", self._title)
        form.addRow("Tipo*", self._source_type)
        form.addRow("Ubicación", location_row)
        form.addRow("Área propietaria", self._owner_area)
        form.addRow("Nivel de acceso", self._access_level)
        form.addRow("Vigente desde", valid_from_row)
        form.addRow("Vigente hasta", valid_to_row)
        form.addRow("Autoridad", self._source_authority)
        form.addRow("Tipo de documento", self._document_type_code)
        form.addRow("Idioma", self._language)
        form.addRow("Vista previa", self._image_preview)
        if self._supersedes is not None:
            form.addRow("Esta fuente sustituye a", self._supersedes)

        if location_locked:
            self._source_type.setEnabled(False)
            self._location.setEnabled(False)
            self._btn_browse.setEnabled(False)
            form.addRow(
                "",
                QLabel(
                    "Ubicación y tipo no se pueden cambiar: esta fuente ya tiene texto "
                    "extraído. Si el documento cambió de verdad, registra una fuente nueva "
                    "indicando que sustituye a esta.",
                    self,
                ),
            )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        # Vista previa de imagen: se actualiza al cambiar el tipo o la
        # ubicación (por navegar o escribir a mano) -- y una vez ahora,
        # al terminar de construir el diálogo, para que el modo edición
        # arranque mostrando la miniatura si la fuente ya es una imagen
        # con ubicación precargada.
        self._source_type.currentIndexChanged.connect(lambda _index: self._update_image_preview())
        self._location.textChanged.connect(lambda _text: self._update_image_preview())
        self._update_image_preview()

    def _on_browse(self) -> None:
        # Elegir el archivo con un diálogo real evita el error más
        # común encontrado en validación visual: escribir a mano la
        # carpeta que contiene el archivo en vez de la ruta completa
        # (incluyendo el nombre del archivo) -- QFileDialog siempre
        # devuelve la ruta a un archivo concreto, nunca a un
        # directorio, así que ese error ya no es posible por esta vía.
        #
        # Fase 4 de multimodalidad nativa: filtrado a extensiones de
        # imagen cuando el tipo elegido es Imagen (ver
        # ui.sources.image_source_logic.image_file_dialog_filter) --
        # no es una validación real, solo ayuda a no elegir por error
        # un archivo que claramente no es una imagen.
        file_filter = image_file_dialog_filter(self._source_type.currentText())
        path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo de la fuente", filter=file_filter)
        if not path:
            return
        self._location.setText(path)
        if not self._title.text().strip():
            self._title.setText(Path(path).stem)

    def _update_image_preview(self) -> None:
        """Fase 4 de multimodalidad nativa: refresca la miniatura de
        vista previa según el tipo de fuente y la ubicación actuales --
        ver ui.sources.image_source_logic.image_preview_placeholder_text
        para la parte de la decisión que no necesita Qt."""
        placeholder = image_preview_placeholder_text(self._source_type.currentText(), self._location.text())
        if placeholder is not None:
            self._image_preview.setText(placeholder)
            self._image_preview.setPixmap(QPixmap())
            return
        pixmap = QPixmap(self._location.text().strip())
        if pixmap.isNull():
            self._image_preview.setText("(no se pudo cargar una vista previa de este archivo)")
            self._image_preview.setPixmap(QPixmap())
            return
        self._image_preview.setText("")
        self._image_preview.setPixmap(
            pixmap.scaled(200, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def values(self) -> dict:
        valid_from = None
        if not self._valid_from_undefined.isChecked():
            qd = self._valid_from.date()
            valid_from = date(qd.year(), qd.month(), qd.day())
        valid_to = None
        if not self._valid_to_undefined.isChecked():
            qd = self._valid_to.date()
            valid_to = date(qd.year(), qd.month(), qd.day())
        return {
            "title": self._title.text().strip(),
            "source_type": self._source_type.currentText(),
            "location": self._location.text().strip(),
            "owner_area": self._owner_area.text().strip() or None,
            "access_level": self._access_level.currentText(),
            "valid_from": valid_from,
            "valid_to": valid_to,
            "source_authority": self._source_authority.value() or None,
            "document_type_code": self._document_type_code.text().strip() or "default",
            "language": self._language.text().strip() or "es",
            "supersedes_source_id": self._supersedes.currentData() if self._supersedes is not None else None,
        }


class _SourceLineageDialog(QDialog):
    """Pista C.2b del ADR-003 (docs proyecto/
    RAG_STUDIO_Propuesta_C2_Procedencia_Temporalidad.docx): la cadena
    completa de versiones de una fuente, de la más antigua a la más
    nueva -- antes de esta pista, el detalle de fuente solo mostraba
    un salto hacia atrás ("Sustituye a: ..."). Solo lectura, con un
    botón para exportar la misma cadena como CSV -- el texto lo
    construye application.documents.service.DocumentService.
    export_source_lineage_as_csv, este diálogo solo elige el archivo
    destino y lo escribe."""

    def __init__(self, lineage: list, current_source_id: str, csv_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Linaje de versiones")
        self.resize(520, 360)
        self._csv_text = csv_text

        lines = []
        for position, source in enumerate(lineage, start=1):
            marca = " ← esta fuente" if source.id == current_source_id else ""
            lines.append(
                f"{position}. {source.title} ({source.id}) -- {source.validation_status.value}{marca}"
            )
        text = QLabel("\n".join(lines), self)
        text.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.accepted.connect(self.accept)
        btn_export = QPushButton("Exportar como CSV…", self)
        btn_export.clicked.connect(self._on_export)
        buttons.addButton(btn_export, QDialogButtonBox.ActionRole)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar linaje de versiones", filter="*.csv")
        if not path:
            return
        try:
            Path(path).write_text(self._csv_text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo escribir el archivo: {exc}")
            return
        QMessageBox.information(self, "Exportado", f"Linaje exportado a {path}.")


class SourcesPanel(QWidget):
    """Emite source_selected(source_id) cada vez que cambia la
    selección de la lista de fuentes, para que otros paneles (Ingesta)
    sepan sobre qué fuente operar. Emite cadena vacía si no hay
    selección — mismo patrón que ProjectsPanel.project_selected.

    También emite sources_changed() cada vez que la lista se
    reconstruye (registrar, editar, corregir en bloque, importar
    carpeta, cambiar estado) -- Ronda 4, punto 4b de
    Validacion_observaciones_RAG_STUDIO.md: antes, el combo de
    document_type_code de ui/ingestion/panel.py solo se refrescaba al
    cambiar de proyecto activo (ver IngestionPanel.set_active_project),
    así que un tipo de documento nuevo (o corregido, ver
    bulk_set_document_type_code) capturado aquí no aparecía en Ingesta
    hasta salir y volver a entrar al proyecto."""

    source_selected = Signal(str)
    sources_changed = Signal()

    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None

        layout = QVBoxLayout(self)
        self._project_label = QLabel("Selecciona un proyecto en la pestaña Proyectos.", self)
        layout.addWidget(self._project_label)

        self._source_list = QListWidget(self)
        # Ronda 4, punto 4a de Validacion_observaciones_RAG_STUDIO.md:
        # selección múltiple (Ctrl/Shift-click, mismo gesto estándar de
        # Qt) para poder corregir en bloque el document_type_code de
        # varias fuentes atípicas de un mismo lote importado -- antes,
        # la única selección posible era de una fuente a la vez, y
        # corregir un lote de decenas de fuentes obligaba a editarlas
        # una por una con "Editar fuente".
        self._source_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self._source_list)

        # Detalle de la fuente seleccionada -- antes de esto, no había
        # forma de ver lo que ya se había capturado sin volver a abrir
        # el diálogo de registro (que ni siquiera pre-llenaba nada).
        # Hallazgo real de validación visual: un error de captura
        # (ubicación con la carpeta en vez del archivo) quedaba
        # invisible hasta que fallaba la extracción, más adelante, en
        # otra pestaña.
        self._detail_label = QLabel("Selecciona una fuente para ver su detalle.", self)
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)

        buttons = QHBoxLayout()
        self._btn_register = QPushButton("Registrar fuente")
        self._btn_edit = QPushButton("Editar fuente")
        self._btn_change_status = QPushButton("Cambiar estado de validación")
        # Ronda 5 (hallazgo real de usuario): el estado de validación es
        # informativo/de gobierno documental -- no restringe asignar
        # metadatos, extraer, fragmentar ni indexar una fuente. Solo actúa
        # como filtro OPCIONAL en la pestaña Ingesta ("Solo fuentes
        # vigentes y validadas"); ver Source.is_usable_for_responses.
        self._btn_change_status.setToolTip(
            "El estado de validación no impide usar la fuente en Metadatos ni en Ingesta: solo "
            'se usa como filtro opcional en la búsqueda ("Solo fuentes vigentes y validadas", '
            "pestaña Ingesta). Sustituido, vencido y rechazado no se pueden revertir desde aquí."
        )
        # Punto 2 de Validacion_observaciones_RAG_STUDIO.md: alta masiva
        # desde la carpeta de entrega de RAG CONTENT STUDIO
        # (14_entrega_rag_studio/, con su manifiesto.csv), en vez de
        # registrar archivo por archivo con "Registrar fuente" -- ver
        # application.documents.commands.register_sources_from_folder.
        self._btn_import_folder = QPushButton("Importar carpeta de RAG CONTENT…")
        # Auditoría posterior a la Ronda 77 (hallazgo real de usuario,
        # ver bitácora): tooltip simétrico al de ui/projects/panel.py --
        # este botón sí espera una CARPETA (la carpeta de entrega
        # completa, no un archivo suelto dentro de ella); si en cambio lo
        # que se tiene es un proyecto de RAG STUDIO ya exportado a
        # .agentproj, ese flujo vive en la pestaña Proyectos.
        self._btn_import_folder.setToolTip(
            "Selecciona la carpeta de entrega completa de RAG CONTENT STUDIO "
            "(14_entrega_rag_studio/, la que contiene manifiesto.csv) -- no un archivo suelto "
            "dentro de ella.\n\n"
            "¿Buscas importar un proyecto de RAG STUDIO ya exportado a .agentproj? Ese flujo está "
            "en la pestaña Proyectos, botón \"Importar proyecto (.agentproj)…\"."
        )
        # Ronda 4, punto 4a: corrección en bloque del tipo de documento
        # para la selección múltiple actual -- ver
        # DocumentService.bulk_set_document_type_code.
        self._btn_bulk_document_type = QPushButton("Corregir tipo de documento (selección)…")
        # Pista C.2b del ADR-003: cadena completa de versiones de la
        # fuente seleccionada (supersedes_source_id en ambos
        # sentidos) -- antes de esta pista, el único rastro de
        # versionado visible era el campo "Sustituye a: ..." del
        # detalle, un solo salto hacia atrás.
        self._btn_view_lineage = QPushButton("Ver linaje de versiones…", self)
        buttons.addWidget(self._btn_register)
        buttons.addWidget(self._btn_edit)
        buttons.addWidget(self._btn_change_status)
        buttons.addWidget(self._btn_import_folder)
        buttons.addWidget(self._btn_bulk_document_type)
        buttons.addWidget(self._btn_view_lineage)
        layout.addLayout(buttons)

        self._btn_register.clicked.connect(self._on_register_source)
        self._btn_edit.clicked.connect(self._on_edit_source)
        self._btn_change_status.clicked.connect(self._on_change_status)
        self._btn_import_folder.clicked.connect(self._on_import_from_folder)
        self._btn_bulk_document_type.clicked.connect(self._on_bulk_set_document_type_code)
        self._btn_view_lineage.clicked.connect(self._on_view_lineage)
        self._source_list.currentItemChanged.connect(self._on_selection_changed)

        self._set_enabled(False)
        self._btn_edit.setEnabled(False)
        self._btn_view_lineage.setEnabled(False)

    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._set_enabled(self._project_id is not None)
        if self._project_id:
            self._project_label.setText(f"Proyecto activo: {self._project_id}")
            self._refresh_sources()
        else:
            self._project_label.setText("Selecciona un proyecto en la pestaña Proyectos.")
            self._source_list.clear()
            self._detail_label.setText("Selecciona una fuente para ver su detalle.")
            self._btn_edit.setEnabled(False)
            self._btn_view_lineage.setEnabled(False)
            self.source_selected.emit("")

    def _on_selection_changed(self, current, previous) -> None:
        if current is None:
            self._detail_label.setText("Selecciona una fuente para ver su detalle.")
            self._btn_edit.setEnabled(False)
            self._btn_view_lineage.setEnabled(False)
            self.source_selected.emit("")
            return
        source_id = current.text().rsplit("(", 1)[-1].rstrip(")")
        self._refresh_detail(source_id)
        self._btn_edit.setEnabled(True)
        self._btn_view_lineage.setEnabled(True)
        self.source_selected.emit(source_id)

    def _refresh_detail(self, source_id: str) -> None:
        try:
            source = self._context.document_service.get_source(self._project_id, source_id)
        except Exception:  # noqa: BLE001 - la fuente pudo eliminarse entre listar y seleccionar
            self._detail_label.setText("No se pudo cargar el detalle de esta fuente.")
            return
        vigente_desde = source.valid_from.isoformat() if source.valid_from else "sin definir"
        vigente_hasta = source.valid_to.isoformat() if source.valid_to else "sin definir"
        # Idioma y "sustituye a" se agregaron al detalle por el mismo
        # motivo que ya llevó a agregar vigencia/autoridad aquí (ver
        # comentario original de la clase): un valor que la interfaz ya
        # puede capturar pero que no se mostraba en ningún lado es,
        # en la práctica, invisible para quien usa la herramienta.
        #
        # Se resuelve el id a "título (id)" -- mostrar solo el UUID
        # crudo (como se hacía en un intento anterior de este mismo
        # cambio) obliga a ir a buscar manualmente de qué fuente se
        # trata; no hay comando para eliminar una fuente, así que la
        # referencia siempre debería poder resolverse, pero por si
        # falla (fuente de otro proyecto, error inesperado) se cae de
        # vuelta al id crudo en vez de romper el resto del detalle.
        sustituye_a = "ninguna"
        if source.supersedes_source_id:
            sustituye_a = source.supersedes_source_id
            try:
                superseded = self._context.document_service.get_source(
                    self._project_id, source.supersedes_source_id,
                )
                sustituye_a = f"{superseded.title} ({superseded.id})"
            except Exception:  # noqa: BLE001 - ver comentario arriba
                pass
        self._detail_label.setText(
            f"Título: {source.title}\n"
            f"Tipo: {source.source_type.value}\n"
            f"Ubicación: {source.location or '(sin definir)'}\n"
            f"Área propietaria: {source.owner_area or '(sin definir)'}\n"
            f"Nivel de acceso: {source.access_level.value}\n"
            f"Idioma: {source.language}\n"
            f"Estado de validación: {source.validation_status.value}\n"
            f"Vigente desde: {vigente_desde} — hasta: {vigente_hasta}\n"
            f"Autoridad: {source.source_authority if source.source_authority is not None else 'sin definir'}\n"
            f"Tipo de documento: {source.document_type_code}\n"
            f"Sustituye a: {sustituye_a}"
        )

    def _on_view_lineage(self) -> None:
        current = self._source_list.currentItem()
        if self._project_id is None or current is None:
            return
        source_id = current.text().rsplit("(", 1)[-1].rstrip(")")
        try:
            lineage = self._context.document_service.get_source_lineage(self._project_id, source_id)
            csv_text = self._context.document_service.export_source_lineage_as_csv(self._project_id, source_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        dialog = _SourceLineageDialog(lineage, source_id, csv_text, self)
        dialog.exec()

    def _set_enabled(self, enabled: bool) -> None:
        self._btn_register.setEnabled(enabled)
        self._btn_change_status.setEnabled(enabled)
        self._btn_import_folder.setEnabled(enabled)
        self._btn_bulk_document_type.setEnabled(enabled)
        self._source_list.setEnabled(enabled)
        # _btn_edit se maneja aparte: además de haber proyecto activo,
        # necesita una fuente seleccionada (ver _on_selection_changed).

    def _refresh_sources(self, select_source_id: Optional[str] = None) -> None:
        self._source_list.clear()
        item_to_select = None
        for source in self._context.document_service.list_sources(self._project_id):
            usable = "usable" if source.is_usable_for_responses() else "no usable"
            self._source_list.addItem(
                f"{source.title}  [{source.source_type.value}]  "
                f"[{source.validation_status.value}, {usable}]  ({source.id})"
            )
            aplicar_color_estado_item(
                self._source_list.item(self._source_list.count() - 1),
                source.validation_status.value,
            )
            if select_source_id and source.id == select_source_id:
                item_to_select = self._source_list.item(self._source_list.count() - 1)
        if item_to_select is not None:
            # Dispara _on_selection_changed, que ya refresca el detalle
            # y habilita "Editar fuente" -- así no queda mostrando el
            # detalle desactualizado de antes de guardar.
            self._source_list.setCurrentItem(item_to_select)
        self.sources_changed.emit()

    def _selected_source_id(self) -> Optional[str]:
        item = self._source_list.currentItem()
        if item is None:
            return None
        return item.text().rsplit("(", 1)[-1].rstrip(")")

    def _selected_source_ids(self) -> list[str]:
        """Ronda 4, punto 4a: todos los ids de la selección múltiple
        actual (Ctrl/Shift-click), no solo el `currentItem` -- para la
        corrección en bloque de document_type_code."""
        return [item.text().rsplit("(", 1)[-1].rstrip(")") for item in self._source_list.selectedItems()]

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _on_register_source(self) -> None:
        if self._project_id is None:
            return
        # Candidatos para "Esta fuente sustituye a": las fuentes que ya
        # existen en el proyecto -- ver docstring de _RegisterSourceDialog.
        # Se incluye el estado de validación en la etiqueta (mismo
        # formato que usa la lista principal de fuentes, ver
        # _refresh_sources) para que la persona no elija a ciegas una
        # fuente que ya está "sustituido" o "rechazado" -- elegir una
        # de esas como destino no falla (RegisterSource simplemente no
        # aplica la transición si el estado actual no es "validado"),
        # pero muy probablemente no es la fuente que la persona quería
        # sustituir de verdad.
        candidates = [
            (source.id, f"{source.title} [{source.validation_status.value}] ({source.id})")
            for source in self._context.document_service.list_sources(self._project_id)
        ]
        dialog = _RegisterSourceDialog(self, candidates=candidates)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["title"]:
            QMessageBox.warning(self, "Falta información", "El título es obligatorio.")
            return
        content_hash = self._compute_content_hash(values["location"], values["source_type"])
        try:
            created = self._context.document_service.register_source(
                self._project_id, values["title"], values["source_type"],
                location=values["location"], owner_area=values["owner_area"],
                access_level=values["access_level"], valid_from=values["valid_from"],
                valid_to=values["valid_to"], source_authority=values["source_authority"],
                document_type_code=values["document_type_code"], language=values["language"],
                content_hash=content_hash, supersedes_source_id=values["supersedes_source_id"],
            )
            self._refresh_sources(select_source_id=created.id)
        except Exception as exc:  # noqa: BLE001 - incluye DuplicateSourceError, ya con mensaje claro
            self._report_error(exc)

    @staticmethod
    def _compute_content_hash(location: str, source_type: str) -> Optional[str]:
        """SHA-256 del archivo en `location`, para que RegisterSource
        pueda detectar duplicados reales por contenido (ver
        DuplicateSourceError) -- capacidad que ya existía de punta a
        punta en domain/application, pero que el alta manual desde la
        interfaz nunca activaba porque nadie calculaba este valor aquí
        (a diferencia de la importación desde RAG CONTENT STUDIO, que
        lo toma de la columna hash_contenido del manifiesto).

        Se calcula solo para tipos de fuente que son archivos reales
        (no api/base_de_datos, ver NON_FILE_SOURCE_TYPE_VALUES) y con
        `location` no vacía. Cualquier fallo al leer el archivo (ruta
        no legible en este momento, sin permisos...) nunca debe
        bloquear el registro de la fuente -- mismo criterio que
        RegisterSource._try_copy_original -- así que se ignora en
        silencio y la fuente se registra sin huella de contenido,
        igual que si el usuario no hubiera elegido ningún archivo."""
        if source_type in NON_FILE_SOURCE_TYPE_VALUES or not location.strip():
            return None
        try:
            digest = hashlib.sha256()
            with open(location, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return None

    def _on_edit_source(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None or self._project_id is None:
            return
        try:
            existing = self._context.document_service.get_source(self._project_id, source_id)
            location_locked = self._context.document_service.has_extraction(self._project_id, source_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return

        dialog = _RegisterSourceDialog(self, existing=existing, location_locked=location_locked)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["title"]:
            QMessageBox.warning(self, "Falta información", "El título es obligatorio.")
            return
        try:
            self._context.document_service.update_source_details(
                self._project_id, source_id, values["title"], values["owner_area"],
                values["access_level"], values["location"], values["source_type"],
                valid_from=values["valid_from"], valid_to=values["valid_to"],
                source_authority=values["source_authority"],
                document_type_code=values["document_type_code"],
                language=values["language"],
            )
            self._refresh_sources(select_source_id=source_id)
        except Exception as exc:  # noqa: BLE001 - incluye SourceStructuralFieldsLockedError
            self._report_error(exc)

    def _on_change_status(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None or self._project_id is None:
            return
        target, ok = QInputDialog.getItem(
            self, "Cambiar estado de validación", "Nuevo estado:", VALIDATION_STATUS_OPTIONS, editable=False,
        )
        if not ok:
            return
        # Ronda 5 (hallazgo real de usuario): sustituido/vencido/rechazado
        # no tienen ninguna transición de salida (ver
        # domain.documents.entities.TERMINAL_VALIDATION_STATUSES) -- si se
        # elige uno de estos por equivocación, no hay forma de deshacerlo
        # desde la interfaz. Se advierte ANTES de aplicar el cambio en vez
        # de descubrirlo después, al intentar revertirlo sin éxito.
        if target in TERMINAL_VALIDATION_STATUS_VALUES:
            confirm = QMessageBox.question(
                self, "Confirmar cambio de estado",
                f'El estado "{target}" no se puede revertir desde la interfaz una vez aplicado -- '
                "si te equivocaste, la única corrección posible sería registrar la fuente de nuevo. "
                f'¿Confirmas el cambio a "{target}"?',
            )
            if confirm != QMessageBox.Yes:
                return
        try:
            self._context.document_service.update_validation_status(self._project_id, source_id, target)
            self._refresh_sources()
        except Exception as exc:  # noqa: BLE001 - incluye transiciones no permitidas
            self._report_error(exc)

    def _on_import_from_folder(self) -> None:
        # Se pide la carpeta de entrega (14_entrega_rag_studio/) del
        # proyecto de RAG CONTENT STUDIO, no un archivo -- por eso
        # getExistingDirectory en vez de getOpenFileName, mismo motivo
        # documentado en la observación real: evitar que el usuario
        # tenga que repetir "Registrar fuente" un archivo a la vez.
        if self._project_id is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Elegir carpeta de entrega de RAG CONTENT (14_entrega_rag_studio)",
        )
        if not folder:
            return
        # Ronda 3 (punto 12): el manifiesto de RAG CONTENT no trae columna
        # de tipo de documento -- sin pedirlo aquí, todo el lote quedaba en
        # "default", mezclando otra vez tipos de fuente distintos (el
        # mismo problema que el punto 10 resolvió para el alta manual).
        # Una carpeta de entrega suele corresponder a un solo tipo
        # documental, así que se pide un valor único para todo el lote.
        document_type_code, ok = QInputDialog.getText(
            self, "Tipo de documento del lote",
            "Tipo de documento para todas las fuentes de esta carpeta\n"
            "(p. ej. 'contactos', 'requisitos_admision'; deja 'default' si son de tipos variados):",
            text="default",
        )
        if not ok:
            return
        document_type_code = document_type_code.strip() or "default"
        try:
            result = self._context.document_service.import_sources_from_folder(
                self._project_id, folder, document_type_code=document_type_code,
            )
        except Exception as exc:  # noqa: BLE001 - incluye FileNotFoundError si no hay manifiesto.csv
            self._report_error(exc)
            return

        self._refresh_sources()

        lines = [f"Importadas: {result.imported_count}", f"Omitidas: {result.skipped_count}"]
        # Ronda 92: identidad del lote (multi-lote) -- si es nuevo, una
        # reimportación idéntica o una versión nueva de uno anterior.
        if result.batch_summary:
            lines.append("")
            lines.append(result.batch_summary)
            lines.append(f"Huella del lote: {result.batch_fingerprint}")
        if result.skipped:
            lines.append("")
            lines.append("Detalle de omitidas:")
            for skipped in result.skipped:
                lines.append(f"- {skipped.title}: {skipped.reason}")
        QMessageBox.information(self, "Importación desde RAG CONTENT", "\n".join(lines))

    def _on_bulk_set_document_type_code(self) -> None:
        # Ronda 4, punto 4a: corregir en bloque las fuentes atípicas de
        # un mismo lote importado (p. ej. algunas quedaron con el tipo
        # de documento del lote cuando en realidad son de otro) sin
        # tener que editarlas una por una.
        if self._project_id is None:
            return
        source_ids = self._selected_source_ids()
        if not source_ids:
            QMessageBox.information(
                self, "Selecciona fuentes",
                "Selecciona una o más fuentes en la lista (Ctrl/Shift-click) antes de corregir su tipo de documento.",
            )
            return
        document_type_code, ok = QInputDialog.getText(
            self, "Corregir tipo de documento",
            f"Nuevo tipo de documento para las {len(source_ids)} fuentes seleccionadas:",
            text="default",
        )
        if not ok:
            return
        document_type_code = document_type_code.strip() or "default"
        try:
            result = self._context.document_service.bulk_set_document_type_code(
                self._project_id, source_ids, document_type_code,
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_sources()
        QMessageBox.information(
            self, "Tipo de documento corregido",
            f"Corregidas: {result.updated_count}. Omitidas: {result.skipped_count}.",
        )
