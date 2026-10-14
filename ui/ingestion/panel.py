"""Panel de Ingesta: Laboratorio de extracción (Módulo 4) + Diseñador
de fragmentación (Módulo 5) + indexación y búsqueda semántica (Etapa
4 — núcleo RAG), sobre la fuente activa.

Regla de capa: solo llama a application (ingestion_service,
metadata_service, rag_service, document_service, jobs). Nunca importa
domain ni infrastructure directamente, y nunca ejecuta trabajo pesado
en el hilo de la interfaz — extracción, fragmentación, indexación y
búsqueda se delegan a application.jobs, igual que "Simular tarea
larga" en ProjectsPanel.
"""
from __future__ import annotations

import logging
from html import escape as html_escape
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application.ingestion.options import FRAGMENTATION_STRATEGY_OPTIONS

from ui.release.gate_status import GateStatusLabel
from ui.theme import estado_html

from .index_logic import index_method_for_source_type
from .search_highlighting import extract_highlight_terms, highlight_terms
from ui.errors import describe_error

logger = logging.getLogger(__name__)


class IngestionPanel(QWidget):
    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None
        self._source_id: Optional[str] = None
        self._ready = False
        self._active_job = None
        self._active_job_kind: Optional[str] = None
        # "extraccion" | "fragmentacion" | "indexacion" | "busqueda" | "comparacion" | "pipeline" | "estructurada"
        self._pending_search_results = None
        self._pending_search_query = ""
        self._pending_search_mode = "Semántica"
        # Auditoría Ronda 21: si se marcó "Reranking real" pero el modo no
        # era Híbrida, la búsqueda lo ignora (ver _on_search) -- sin este
        # aviso, quien probara esa combinación no tenía ninguna señal de
        # que el resultado mostrado NO llevaba reranking, a pesar de haber
        # marcado la casilla.
        self._pending_search_rerank_ignored = False
        self._pending_compare_result = None
        self._pending_compare_query = ""
        self._compare_available = False
        self._pending_pipeline_run = None
        self._pending_structured_result = None
        self._project_ready = False

        layout = QVBoxLayout(self)
        self._status_label = QLabel("Selecciona un proyecto y una fuente en las pestañas anteriores.", self)
        layout.addWidget(self._status_label)

        # Avisos tempranos (no bloqueantes) de las compuertas de
        # Liberación que dependen de esta pestaña -- ver
        # ui/release/gate_status.py. Son 3 (no 1, a diferencia de las
        # demás pestañas) porque Ingesta concentra Fragmentación,
        # Pipeline reproducible e Índice y recuperación.
        self._gate_status_labels = {
            name: GateStatusLabel(name, self)
            for name in ("Fragmentación", "Pipeline reproducible", "Índice y recuperación")
        }
        for gate_label in self._gate_status_labels.values():
            layout.addWidget(gate_label)

        progress_row = QHBoxLayout()
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        progress_row.addWidget(self._progress)
        self._btn_cancel = QPushButton("Cancelar", self)
        progress_row.addWidget(self._btn_cancel)
        layout.addLayout(progress_row)

        # Sub-pestañas por etapa (una por proceso: Pipeline, Extracción,
        # Fragmentación, Búsqueda RAG, Comparador) -- antes todo vivía
        # apilado en una sola columna vertical, lo que dejaba muy poco
        # espacio para ver el resultado de cada proceso (había que
        # scrollear una pestaña larguísima). El estado/progreso/cancelar
        # de arriba se queda fijo y visible sin importar la sub-pestaña
        # activa, porque un trabajo en segundo plano puede venir de
        # cualquiera de ellas.
        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        # --- Pipeline reproducible (Etapa 3): corrida por lote sobre
        # TODAS las fuentes del proyecto, a diferencia del resto de esta
        # pestaña (que actúa sobre una sola fuente activa) -- por eso se
        # habilita con solo tener un proyecto seleccionado, sin
        # necesitar una fuente activa (ver _project_ready). ---
        pipeline_group = QGroupBox("Pipeline del proyecto (todas las fuentes)", self)
        pipeline_layout = QVBoxLayout(pipeline_group)
        pipeline_row = QHBoxLayout()
        # Ronda 3 (punto 13): antes esto era un QLineEdit de texto libre,
        # totalmente desconectado del document_type_code que ya se
        # captura al registrar/editar una fuente (ui/sources/panel.py) --
        # dos cuadros de texto libre para el mismo concepto, sin ninguna
        # validación cruzada. Un usuario podía escribir "contactos" en
        # Fuentes y "Contactos" aquí, dejando una política de
        # fragmentación que nunca se aplica a esas fuentes, sin ningún
        # aviso. Se reemplaza por un combo editable, poblado con los
        # document_type_code que ya existen entre las fuentes del
        # proyecto (ver _refresh_document_type_options) -- sigue
        # permitiendo escribir un valor nuevo si de verdad se necesita.
        self._pipeline_document_type_code = QComboBox(pipeline_group)
        self._pipeline_document_type_code.setEditable(True)
        self._pipeline_document_type_code.addItem("default")
        self._btn_run_pipeline = QPushButton("Ejecutar pipeline completo", pipeline_group)
        pipeline_row.addWidget(QLabel("document_type_code:", pipeline_group))
        pipeline_row.addWidget(self._pipeline_document_type_code)
        pipeline_row.addWidget(self._btn_run_pipeline)
        pipeline_layout.addLayout(pipeline_row)
        self._pipeline_report = QTextBrowser(pipeline_group)
        self._pipeline_report.setReadOnly(True)
        pipeline_layout.addWidget(self._pipeline_report)
        self._tabs.addTab(pipeline_group, "Pipeline")

        # --- Laboratorio de extracción (Módulo 4) ---
        extraction_group = QGroupBox("Extracción", self)
        extraction_layout = QVBoxLayout(extraction_group)
        extraction_buttons = QHBoxLayout()
        self._btn_extract = QPushButton("Extraer texto")
        extraction_buttons.addWidget(self._btn_extract)
        # Historial de extracciones (ítem 5 de la evaluación de madurez
        # post-8-etapas): antes, re-extraer sustituía en silencio el
        # resultado anterior sin dejar ningún rastro de intentos
        # previos -- ver domain.ingestion.ports.ExtractionRepository.list_history.
        self._btn_view_extraction_history = QPushButton("Ver historial de extracciones")
        extraction_buttons.addWidget(self._btn_view_extraction_history)
        extraction_layout.addLayout(extraction_buttons)
        self._extraction_info = QLabel("Sin extracción todavía.", extraction_group)
        extraction_layout.addWidget(self._extraction_info)
        self._extraction_preview = QTextEdit(extraction_group)
        self._extraction_preview.setReadOnly(True)
        extraction_layout.addWidget(self._extraction_preview)
        self._tabs.addTab(extraction_group, "Extracción")

        # --- Diseñador de fragmentación (Módulo 5) ---
        fragmentation_group = QGroupBox("Fragmentación", self)
        fragmentation_layout = QVBoxLayout(fragmentation_group)

        policy_row = QHBoxLayout()
        # Mismo motivo que self._pipeline_document_type_code arriba.
        self._document_type_code = QComboBox(fragmentation_group)
        self._document_type_code.setEditable(True)
        self._document_type_code.addItem("default")
        self._strategy = QComboBox(fragmentation_group)
        self._strategy.addItems(FRAGMENTATION_STRATEGY_OPTIONS)
        self._target_tokens = QSpinBox(fragmentation_group)
        self._target_tokens.setRange(1, 100_000)
        self._target_tokens.setValue(500)
        self._overlap_tokens = QSpinBox(fragmentation_group)
        self._overlap_tokens.setRange(0, 100_000)
        self._overlap_tokens.setValue(60)
        self._min_tokens = QSpinBox(fragmentation_group)
        self._min_tokens.setRange(0, 100_000)
        self._min_tokens.setValue(80)
        for label, widget in (
            ("document_type_code:", self._document_type_code), ("Estrategia:", self._strategy),
            ("Tokens objetivo:", self._target_tokens), ("Solapamiento:", self._overlap_tokens),
            ("Mínimo (fusionar bajo):", self._min_tokens),
        ):
            policy_row.addWidget(QLabel(label, fragmentation_group))
            policy_row.addWidget(widget)
        fragmentation_layout.addLayout(policy_row)

        buttons_row = QHBoxLayout()
        self._btn_save_policy = QPushButton("Guardar política")
        self._btn_fragment = QPushButton("Fragmentar")
        buttons_row.addWidget(self._btn_save_policy)
        buttons_row.addWidget(self._btn_fragment)
        fragmentation_layout.addLayout(buttons_row)

        self._chunk_list = QListWidget(fragmentation_group)
        fragmentation_layout.addWidget(self._chunk_list)
        self._tabs.addTab(fragmentation_group, "Fragmentación")

        # --- Indexación y búsqueda semántica (Etapa 4 — núcleo RAG) ---
        rag_group = QGroupBox("RAG: indexación y búsqueda semántica", self)
        rag_layout = QVBoxLayout(rag_group)

        self._btn_index = QPushButton("Indexar esta fuente", rag_group)
        rag_layout.addWidget(self._btn_index)
        self._index_info_label = QLabel("Índice del proyecto: sin datos todavía.", rag_group)
        rag_layout.addWidget(self._index_info_label)

        search_row = QHBoxLayout()
        self._search_query = QLineEdit(rag_group)
        # Modo de búsqueda (Etapa 4, Laboratorio RAG): Semántica (por
        # vector, necesita haber indexado antes), Textual (BM25 por
        # palabra clave, no necesita índice) e Híbrida (fusión de
        # ambas por Reciprocal Rank Fusion -- ver
        # application/rag/queries/hybrid_search.py sobre por qué RRF
        # también cumple el rol de "reranking"). ADR-003, Pista A.2:
        # en modo Híbrida, la casilla "Reranking real" de más abajo
        # permite pedir además un reordenamiento con un cross-encoder
        # local sobre los candidatos ya fusionados por RRF.
        self._search_mode = QComboBox(rag_group)
        self._search_mode.addItems(["Semántica", "Textual", "Híbrida"])
        self._search_scope_source_only = QCheckBox("Solo esta fuente", rag_group)
        # Control de documentos excluidos (Módulo 4 -- Laboratorio RAG):
        # sin marcar, la búsqueda sigue viendo todo lo indexado (incluye
        # borradores, útil mientras se prueba); marcado, excluye
        # resultados de fuentes rechazadas, vencidas o no validadas
        # (documento maestro, "supuestos prohibidos").
        self._search_only_usable = QCheckBox("Solo fuentes vigentes y validadas", rag_group)
        # ADR-003, Pista A.2 ("ganancias rápidas"): reranking real
        # (cross-encoder local) sobre los candidatos ya fusionados por
        # RRF -- solo aplica al modo Híbrida (ver _on_search). Se
        # habilita/inhabilita según RagService.has_reranker (ver
        # _apply_button_states): sin un Reranker configurado, marcarla
        # produciría RerankerUnavailableError en vez de silenciarla sin
        # explicación.
        self._search_rerank = QCheckBox("Reranking real (cross-encoder, solo Híbrida)", rag_group)
        # Pista B.1 del ADR-003 (docs proyecto/
        # RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 6):
        # a diferencia de "Reranking real", esta casilla no depende de
        # ninguna capacidad opcional configurada al arrancar la app --
        # siempre está disponible (con proyecto+fuente activos), y
        # simplemente no tiene efecto visible si ningún resultado
        # proviene de una sección con chunk padre (POR_ENCABEZADO con
        # secciones sub-divididas en más de un fragmento).
        self._search_expand_to_parent = QCheckBox(
            "Expandir a sección completa (chunk padre)", rag_group
        )
        self._btn_search = QPushButton("Buscar", rag_group)
        search_row.addWidget(QLabel("Consulta:", rag_group))
        search_row.addWidget(self._search_query)
        search_row.addWidget(QLabel("Modo:", rag_group))
        search_row.addWidget(self._search_mode)
        search_row.addWidget(self._search_scope_source_only)
        search_row.addWidget(self._search_only_usable)
        search_row.addWidget(self._search_rerank)
        search_row.addWidget(self._search_expand_to_parent)
        search_row.addWidget(self._btn_search)
        rag_layout.addLayout(search_row)

        # QTextBrowser (no QListWidget) porque el comparador de
        # resultados necesita rich text para resaltar en cada
        # fragmento las palabras de la consulta que coincidieron --
        # QListWidget solo soporta texto plano.
        self._search_results = QTextBrowser(rag_group)
        self._search_results.setReadOnly(True)
        self._search_results.setOpenExternalLinks(False)
        rag_layout.addWidget(self._search_results)
        self._tabs.addTab(rag_group, "Búsqueda RAG")

        # --- Datos estructurados (Pista B.2b del ADR-003) ---
        # Filtros y agregaciones deterministas sobre chunks
        # ChunkType.ESTRUCTURADO -- hojas XLSX/CSV fragmentadas con
        # FragmentationStrategy.POR_HOJA_ESTRUCTURADA (ver
        # docs proyecto/RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx,
        # sección 3.3). Sin LLM, sin SQL libre: un DSL cerrado (ver
        # domain.rag.structured_query), pensado aquí solo para PROBAR
        # la capacidad desde el escritorio -- exponerla al agente
        # externo por HTTP (B.2c) queda fuera de esta ronda.
        structured_group = QGroupBox("Datos estructurados (filtros y agregaciones)", self)
        structured_layout = QVBoxLayout(structured_group)

        structured_layout.addWidget(QLabel(
            "Filtros -- uno por línea, \"columna operador valor\" (operadores: == != > >= < <= contains). "
            "Vacío = sin filtros.",
            structured_group,
        ))
        self._structured_filters = QTextEdit(structured_group)
        self._structured_filters.setPlaceholderText("plantel == Mérida\nmatricula > 50")
        self._structured_filters.setMaximumHeight(70)
        structured_layout.addWidget(self._structured_filters)

        structured_agg_row = QHBoxLayout()
        self._structured_agg_function = QComboBox(structured_group)
        self._structured_agg_function.addItems(["(sin agregación)", "count", "sum", "avg", "min", "max"])
        self._structured_agg_column = QLineEdit(structured_group)
        self._structured_agg_column.setPlaceholderText("columna a agregar (no aplica a 'count')")
        self._structured_group_by = QLineEdit(structured_group)
        self._structured_group_by.setPlaceholderText("agrupar por (opcional)")
        self._structured_scope_source_only = QCheckBox("Solo esta fuente", structured_group)
        self._btn_structured_query = QPushButton("Consultar datos estructurados", structured_group)
        structured_agg_row.addWidget(QLabel("Agregación:", structured_group))
        structured_agg_row.addWidget(self._structured_agg_function)
        structured_agg_row.addWidget(self._structured_agg_column)
        structured_agg_row.addWidget(self._structured_group_by)
        structured_agg_row.addWidget(self._structured_scope_source_only)
        structured_agg_row.addWidget(self._btn_structured_query)
        structured_layout.addLayout(structured_agg_row)

        self._structured_results = QTextBrowser(structured_group)
        self._structured_results.setReadOnly(True)
        self._structured_results.setOpenExternalLinks(False)
        structured_layout.addWidget(self._structured_results)
        self._tabs.addTab(structured_group, "Datos estructurados")

        # --- Comparador de modelos de embeddings (A vs B) ---
        # Corre la MISMA consulta con dos perfiles distintos y muestra
        # los resultados de cada uno lado a lado -- sin persistir un
        # segundo índice paralelo (ver
        # application/rag/queries/compare_embedding_profiles.py sobre
        # por qué se calcula en memoria). Reutiliza el resaltado de
        # coincidencias del comparador de resultados de búsqueda.
        compare_group = QGroupBox("Comparador de modelos de embeddings (A vs B)", self)
        compare_layout = QVBoxLayout(compare_group)

        compare_profiles_row = QHBoxLayout()
        self._compare_profile_a = QComboBox(compare_group)
        self._compare_profile_b = QComboBox(compare_group)
        compare_profiles_row.addWidget(QLabel("Modelo A:", compare_group))
        compare_profiles_row.addWidget(self._compare_profile_a)
        compare_profiles_row.addWidget(QLabel("Modelo B:", compare_group))
        compare_profiles_row.addWidget(self._compare_profile_b)
        compare_layout.addLayout(compare_profiles_row)

        compare_query_row = QHBoxLayout()
        self._compare_query = QLineEdit(compare_group)
        self._compare_scope_source_only = QCheckBox("Solo esta fuente", compare_group)
        self._btn_compare = QPushButton("Comparar modelos", compare_group)
        compare_query_row.addWidget(QLabel("Consulta:", compare_group))
        compare_query_row.addWidget(self._compare_query)
        compare_query_row.addWidget(self._compare_scope_source_only)
        compare_query_row.addWidget(self._btn_compare)
        compare_layout.addLayout(compare_query_row)

        self._compare_results = QTextBrowser(compare_group)
        self._compare_results.setReadOnly(True)
        self._compare_results.setOpenExternalLinks(False)
        compare_layout.addWidget(self._compare_results)
        self._tabs.addTab(compare_group, "Comparador de modelos")

        self._btn_run_pipeline.clicked.connect(self._on_run_pipeline)
        self._btn_extract.clicked.connect(self._on_extract)
        self._btn_view_extraction_history.clicked.connect(self._on_view_extraction_history)
        self._btn_save_policy.clicked.connect(self._on_save_policy)
        self._btn_fragment.clicked.connect(self._on_fragment)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_index.clicked.connect(self._on_index)
        self._btn_search.clicked.connect(self._on_search)
        self._btn_structured_query.clicked.connect(self._on_structured_query)
        self._btn_compare.clicked.connect(self._on_compare)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._poll_active_job)

        self._populate_compare_profiles()
        self._apply_button_states()

    # ---------- wiring de proyecto/fuente activos ----------
    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._source_id = None
        self._reset_views()
        self._refresh_document_type_options()
        # El reporte del pipeline es por proyecto (igual que el índice),
        # no por fuente: se limpia aquí (al cambiar de proyecto), no en
        # _reset_views (que también se llama al solo cambiar de fuente
        # dentro del mismo proyecto -- ahí el reporte sigue siendo
        # válido).
        self._pipeline_report.setHtml("")
        self._update_enabled_state()
        if self._project_id:
            # El índice es por proyecto (no por fuente): se refresca en
            # cuanto hay un proyecto activo, sin esperar a elegir fuente.
            self._refresh_index_info()
        else:
            self._index_info_label.setText("Índice del proyecto: sin datos todavía.")
        if self._project_id:
            self._refresh_gate_status()
        else:
            for gate_label in self._gate_status_labels.values():
                gate_label.clear_status()

    def set_active_source(self, source_id: str) -> None:
        self._source_id = source_id or None
        self._reset_views()
        self._update_enabled_state()
        if self._project_id and self._source_id:
            self._refresh_extraction_preview()
            self._refresh_chunk_list()

    def refresh_document_type_options(self) -> None:
        """Punto público equivalente a _refresh_document_type_options,
        para que otros paneles puedan pedir el refresco sin tocar un
        método privado (Ronda 4, punto 4b de
        Validacion_observaciones_RAG_STUDIO.md). Se conecta a
        SourcesPanel.sources_changed en ui/projects/main_window.py:
        antes, los combos de document_type_code de este panel solo se
        refrescaban al cambiar de proyecto activo, así que un tipo de
        documento nuevo (o corregido en bloque, ver
        DocumentService.bulk_set_document_type_code) capturado en
        Fuentes no aparecía aquí hasta salir y volver a entrar al
        proyecto."""
        self._refresh_document_type_options()

    def _refresh_document_type_options(self) -> None:
        """Ronda 3 (punto 13 de Validacion_observaciones_RAG_STUDIO.md):
        antes _pipeline_document_type_code y _document_type_code eran
        dos QLineEdit de texto libre, sin relación con el
        document_type_code que ya se captura al registrar/editar una
        fuente en ui/sources/panel.py -- un typo aquí dejaba una
        política de fragmentación que nunca se aplicaba a esas fuentes,
        sin ningún aviso. Se pueblan los combos con los valores que ya
        existen entre las fuentes del proyecto activo; siguen siendo
        editables por si se necesita un valor todavía no usado por
        ninguna fuente (p. ej. definir la política antes de importar)."""
        codes = ["default"]
        if self._project_id:
            try:
                sources = self._context.document_service.list_sources(self._project_id)
            except Exception:  # noqa: BLE001 - no debe tumbar el cambio de proyecto
                sources = []
            for source in sources:
                if source.document_type_code not in codes:
                    codes.append(source.document_type_code)
        for combo in (self._pipeline_document_type_code, self._document_type_code):
            previous = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(codes)
            if previous and previous not in codes:
                combo.addItem(previous)
            combo.setCurrentText(previous or "default")
            combo.blockSignals(False)

    def _populate_compare_profiles(self) -> None:
        """Llena los selectores de modelo con los perfiles configurados
        en RagService (ver app/bootstrap.py). Si hay menos de 2
        perfiles disponibles, el comparador no tiene sentido (no hay
        nada que comparar) y se deshabilita con una nota explicativa,
        en vez de dejar botones activos que siempre fallarían."""
        profiles = self._context.rag_service.available_embedding_profiles()
        self._compare_available = len(profiles) >= 2
        self._compare_profile_a.clear()
        self._compare_profile_b.clear()
        self._compare_profile_a.addItems(profiles)
        self._compare_profile_b.addItems(profiles)
        if len(profiles) >= 2:
            self._compare_profile_b.setCurrentIndex(1)
        else:
            self._compare_results.setHtml(
                "<p>El comparador de modelos no está disponible en esta instalación "
                "(hacen falta al menos 2 perfiles de embeddings configurados).</p>"
            )

    def _reset_views(self) -> None:
        self._extraction_info.setText("Sin extracción todavía.")
        self._extraction_preview.setPlainText("")
        self._chunk_list.clear()
        self._search_results.setHtml("")
        if self._compare_available:
            self._compare_results.setHtml("")

    def _update_enabled_state(self) -> None:
        self._ready = self._project_id is not None and self._source_id is not None
        self._project_ready = self._project_id is not None
        self._apply_button_states()
        if self._ready:
            self._status_label.setText(f"Proyecto: {self._project_id}  |  Fuente: {self._source_id}")
        else:
            self._status_label.setText("Selecciona un proyecto y una fuente en las pestañas anteriores.")

    def _apply_button_states(self) -> None:
        """Los controles de acción se habilitan solo si hay
        proyecto+fuente activos Y no hay un trabajo en curso;
        "Cancelar" es lo opuesto: solo tiene sentido mientras hay un
        trabajo activo. El pipeline reproducible es la excepción: actúa
        sobre todo el proyecto, así que solo exige un proyecto activo
        (self._project_ready), sin necesitar una fuente seleccionada."""
        busy = self._active_job is not None
        can_act = self._ready and not busy
        pipeline_can_act = self._project_ready and not busy
        for widget in (self._pipeline_document_type_code, self._btn_run_pipeline, self._pipeline_report):
            widget.setEnabled(pipeline_can_act)
        for widget in (
            self._btn_extract, self._btn_save_policy, self._btn_fragment, self._document_type_code,
            self._strategy, self._target_tokens, self._overlap_tokens, self._min_tokens, self._chunk_list,
            self._btn_index, self._btn_search, self._search_query, self._search_mode,
            self._search_scope_source_only, self._search_only_usable, self._search_results,
            self._search_expand_to_parent,
            self._structured_filters, self._structured_agg_function, self._structured_agg_column,
            self._structured_group_by, self._structured_scope_source_only, self._btn_structured_query,
            self._structured_results,
        ):
            widget.setEnabled(can_act)
        # Reranking real (ADR-003, Pista A.2): además de proyecto+fuente
        # activos, exige que RagService se haya construido con un
        # Reranker configurado (ver app/bootstrap.py) -- sin eso,
        # marcarla produciría RerankerUnavailableError al buscar.
        self._search_rerank.setEnabled(can_act and self._context.rag_service.has_reranker)
        # El comparador además exige que haya al menos 2 perfiles
        # configurados (self._compare_available, ver
        # _populate_compare_profiles) -- si no, se queda deshabilitado
        # aunque haya proyecto+fuente activos.
        compare_can_act = can_act and self._compare_available
        for widget in (
            self._compare_profile_a, self._compare_profile_b, self._compare_query,
            self._compare_scope_source_only, self._btn_compare, self._compare_results,
        ):
            widget.setEnabled(compare_can_act)
        self._btn_cancel.setEnabled(busy)

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _submit_job(self, fn, *, key: Optional[str] = None) -> bool:
        """Envía `fn` a segundo plano y guarda el handle en
        `self._active_job`. Devuelve `False` sin tocar el estado del
        panel si `key` ya tiene un trabajo en curso (ítem 3 de la
        segunda evaluación de madurez post-8-etapas, ver bitácora) --
        en la práctica no debería pasar nunca desde esta misma
        instancia del panel (ya se autolimita con `_active_job is not
        None` antes de llamar aquí), pero el runner lo garantiza de
        verdad para cualquier otro llamador (otra ventana, un script)
        que trabaje sobre el mismo proyecto/fuente."""
        try:
            self._active_job = self._context.jobs.submit_task(fn, key=key)
        except Exception as exc:  # noqa: BLE001 - incluye JobAlreadyRunningError
            self._active_job_kind = None
            self._report_error(exc)
            return False
        return True

    def _refresh_gate_status(self) -> None:
        for gate_label in self._gate_status_labels.values():
            gate_label.refresh(self._context.release_service, self._project_id)

    # ---------- pipeline reproducible (Etapa 3) ----------
    def _on_run_pipeline(self) -> None:
        if self._active_job is not None or self._project_id is None:
            return
        project_id = self._project_id
        document_type_code = self._pipeline_document_type_code.currentText().strip() or "default"
        schema_id = self._active_schema_id(project_id)

        self._status_label.setText("Ejecutando el pipeline completo en segundo plano…")
        self._active_job_kind = "pipeline"
        self._pending_pipeline_run = None

        def _run(handle) -> None:
            self._pending_pipeline_run = self._context.pipeline_service.run(
                project_id, document_type_code=document_type_code, schema_id=schema_id,
                is_cancelled=handle.is_cancelled,
            )

        if not self._submit_job(_run, key=f"pipeline:{project_id}"):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _refresh_pipeline_report(self) -> None:
        run = self._pending_pipeline_run
        self._pending_pipeline_run = None
        if run is None:
            return

        status_labels = {
            "completo": "Completo",
            "completo_con_errores": "Completo, con errores",
            "cancelado": "Cancelado",
            "en_curso": "En curso",
        }
        run_status_text = estado_html(
            status_labels.get(run.status.value, run.status.value), run.status.value,
        )
        parts = [f"<p><b>Corrida {run.id}</b> — estado: {run_status_text}"
                 f" — {len(run.items)} fuente(s) procesada(s).</p>"]
        for item in run.items:
            status_note = estado_html({
                "exitoso": "✔ exitoso",
                "fallido": "✘ fallido",
                "omitido": "— omitido (sin cambios)",
                "cancelado": "⏸ cancelado",
            }.get(item.status.value, item.status.value), item.status.value)
            detail = f"{status_note} — {html_escape(item.source_title)}"
            if item.chunks_indexed:
                detail += f" ({item.chunks_indexed} fragmento(s) indexado(s))"
            if item.warnings:
                detail += f" — {len(item.warnings)} advertencia(s)"
            if item.error:
                detail += f" — <b>{html_escape(item.error)}</b>"
            parts.append(f"<p>{detail}</p>")
        self._pipeline_report.setHtml("".join(parts))
        self._refresh_gate_status()

    # ---------- extracción ----------
    def _refresh_extraction_preview(self) -> None:
        record = self._context.ingestion_service.get_extraction_record(self._project_id, self._source_id)
        if record is None:
            self._extraction_info.setText("Sin extracción todavía.")
            self._extraction_preview.setPlainText("")
            return
        warning_note = f" — {len(record.warnings)} advertencia(s)" if record.warnings else ""
        self._extraction_info.setText(
            f"{record.char_count} caracteres extraídos (método: {record.extraction_method}){warning_note}."
        )
        self._extraction_preview.setPlainText(record.text)

    def _on_extract(self) -> None:
        if self._active_job is not None or self._project_id is None or self._source_id is None:
            return
        project_id, source_id = self._project_id, self._source_id
        self._status_label.setText("Extrayendo texto en segundo plano…")
        self._active_job_kind = "extraccion"
        if not self._submit_job(
            lambda handle: self._context.ingestion_service.extract_source_text(
                project_id, source_id, is_cancelled=handle.is_cancelled,
            ),
            key=f"ingesta:{project_id}:{source_id}",
        ):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _on_view_extraction_history(self) -> None:
        if self._project_id is None or self._source_id is None:
            QMessageBox.warning(self, "Falta información", "Elige un proyecto y una fuente primero.")
            return
        history = self._context.ingestion_service.list_extraction_history(self._project_id, self._source_id)
        if not history:
            QMessageBox.information(
                self, "Historial de extracciones", "Esta fuente todavía no se ha extraído nunca.",
            )
            return
        lines = []
        for record in history:
            method = record.extraction_method or "(sin especificar)"
            warning_note = f", {len(record.warnings)} advertencia(s)" if record.warnings else ""
            lines.append(
                f"{record.extracted_at:%Y-%m-%d %H:%M} — método: {method}, "
                f"{record.char_count} caracteres{warning_note}"
            )
        QMessageBox.information(self, "Historial de extracciones", "\n".join(lines))

    # ---------- fragmentación ----------
    def _refresh_chunk_list(self) -> None:
        self._chunk_list.clear()
        chunks = self._context.ingestion_service.list_chunks(self._project_id, self._source_id)
        for chunk in chunks:
            section = f", sección: {chunk.section_title}" if chunk.section_title else ""
            pages = (
                f", páginas {chunk.page_start}-{chunk.page_end}"
                if chunk.page_start is not None else ""
            )
            # El tipo solo se muestra cuando no es el genérico "texto"
            # (Módulo 5: artículo/pregunta+respuesta/tabla), para no
            # llenar de ruido la lista en las estrategias de siempre.
            tipo = f", tipo: {chunk.chunk_type.value}" if chunk.chunk_type.value != "texto" else ""
            self._chunk_list.addItem(
                f"[{chunk.chunk_index}] {chunk.token_count} tokens{section}{pages}{tipo}"
            )

    def _on_save_policy(self) -> None:
        if self._project_id is None:
            return
        code = self._document_type_code.currentText().strip() or "default"
        try:
            self._context.ingestion_service.set_fragmentation_policy(
                self._project_id, code, strategy=self._strategy.currentText(),
                target_tokens=self._target_tokens.value(), overlap_tokens=self._overlap_tokens.value(),
                min_tokens=self._min_tokens.value(),
            )
            self._refresh_gate_status()
            QMessageBox.information(self, "Política guardada", f"Política para {code!r} guardada.")
        except Exception as exc:  # noqa: BLE001 - incluye parámetros incoherentes
            self._report_error(exc)

    def _on_fragment(self) -> None:
        if self._active_job is not None or self._project_id is None or self._source_id is None:
            return
        project_id, source_id = self._project_id, self._source_id
        document_type_code = self._document_type_code.currentText().strip() or "default"
        schema_id = self._active_schema_id(project_id)

        self._status_label.setText("Fragmentando en segundo plano…")
        self._active_job_kind = "fragmentacion"
        if not self._submit_job(
            lambda handle: self._context.ingestion_service.fragment_source(
                project_id, source_id, schema_id=schema_id, document_type_code=document_type_code,
                is_cancelled=handle.is_cancelled,
            ),
            key=f"ingesta:{project_id}:{source_id}",
        ):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _active_schema_id(self, project_id: str) -> Optional[str]:
        # Atrapa cualquier excepción a propósito: este método solo se usa
        # para decidir si mostrar un aviso opcional (esquema de metadatos
        # sin asignar), nunca para bloquear la ingesta -- un proyecto sin
        # esquema todavía es un caso normal (auditoría de madurez ronda 5:
        # antes este silencio no tenía comentario ni registro, indistinguible
        # de un fallo real de base de datos).
        try:
            schema, _fields = self._context.metadata_service.get_schema(project_id)
            return schema.id
        except Exception:
            logger.debug(
                "No se pudo obtener el esquema de metadatos activo del proyecto %s "
                "(se trata como 'sin esquema asignado').", project_id, exc_info=True,
            )
            return None

    # ---------- indexación y búsqueda semántica (RAG) ----------
    def _refresh_index_info(self) -> None:
        info = self._context.rag_service.get_index_info(self._project_id)
        if info is None:
            self._index_info_label.setText("Índice del proyecto: sin datos todavía.")
            return
        self._index_info_label.setText(
            f"Índice del proyecto — modelo: {info.embedding_model} ({info.dimensions}d), "
            f"{info.points_count} fragmento(s) indexado(s)."
        )
        self._refresh_gate_status()

    def _on_index(self) -> None:
        if self._active_job is not None or self._project_id is None or self._source_id is None:
            return
        project_id, source_id = self._project_id, self._source_id
        # Fase 4 de multimodalidad nativa (RAG 3): una fuente
        # SourceType.IMAGEN_NATIVA se indexa con
        # RagService.index_image_source, no con index_source (el de
        # texto) -- este último no produciría ningún error visible,
        # simplemente indexaría 0 fragmentos en silencio, porque una
        # imagen nativa nunca pasa por FragmentSource (ver Ronda 65,
        # punto 221). La decisión de qué método usar vive en
        # ui.ingestion.index_logic (sin Qt, con pruebas propias).
        try:
            source_type = self._context.document_service.get_source(project_id, source_id).source_type.value
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        method_name = index_method_for_source_type(source_type)

        self._status_label.setText("Indexando en segundo plano…")
        self._active_job_kind = "indexacion"
        if not self._submit_job(
            lambda handle: getattr(self._context.rag_service, method_name)(project_id, source_id),
            key=f"ingesta:{project_id}:{source_id}",
        ):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _on_search(self) -> None:
        if self._active_job is not None or self._project_id is None:
            return
        query_text = self._search_query.text().strip()
        if not query_text:
            # Ronda 8, punto 27 (hallazgo real de usuario, vídeo 2): antes
            # esto retornaba en silencio -- sin ningún job, sin ningún
            # aviso -- y quien probara "Consulta:" vacío no tenía forma de
            # saber si el botón no hacía nada o si la búsqueda seguía en
            # curso. Mismo criterio que "Elige dos modelos distintos" en
            # el Comparador de modelos, unas líneas más abajo.
            QMessageBox.information(self, "Falta la consulta", "Escribe una consulta antes de buscar.")
            return
        project_id = self._project_id
        source_filter = self._source_id if self._search_scope_source_only.isChecked() else None
        only_usable = self._search_only_usable.isChecked()
        mode = self._search_mode.currentText()
        # Reranking real solo tiene sentido en modo Híbrida (se aplica
        # DESPUÉS de la fusión RRF, ver HybridSearch.execute) -- en los
        # otros modos se ignora en vez de deshabilitar la casilla según
        # el modo elegido, para no complicar el cableado de señales con
        # un caso más de "combo cambió". Auditoría Ronda 21: que se
        # ignore no significa que deba ser invisible -- se registra para
        # avisar en el resultado (ver _refresh_search_results), porque
        # antes de este aviso no había ninguna señal de que la casilla
        # marcada no tuvo efecto en esa búsqueda en particular.
        rerank_requested = self._search_rerank.isChecked()
        rerank = rerank_requested and mode == "Híbrida"
        self._pending_search_rerank_ignored = rerank_requested and not rerank
        expand_to_parent = self._search_expand_to_parent.isChecked()

        # La búsqueda también se envía a segundo plano: embeber la
        # consulta puede requerir descargar el modelo la primera vez
        # (sin red, tardaría o fallaría) — igual que extraer/fragmentar,
        # nunca debe bloquear el hilo de la interfaz. La búsqueda
        # textual no necesita el modelo de embeddings, pero se manda
        # igual en segundo plano para no bifurcar el flujo de la UI
        # según el modo elegido.
        self._status_label.setText("Buscando en segundo plano…")
        self._active_job_kind = "busqueda"
        self._pending_search_results = None
        # Se guardan aparte del campo/combo de texto: si el usuario los
        # cambia mientras la búsqueda todavía corre en segundo plano, el
        # resaltado y el aviso de relevancia deben seguir usando la
        # consulta y el modo que de verdad se buscaron.
        self._pending_search_query = query_text
        self._pending_search_mode = mode

        def _run(handle) -> None:
            if mode == "Textual":
                self._pending_search_results = self._context.rag_service.search_text(
                    project_id, query_text, limit=10, source_id=source_filter,
                    only_usable_sources=only_usable, expand_to_parent=expand_to_parent,
                )
            elif mode == "Híbrida":
                self._pending_search_results = self._context.rag_service.search_hybrid(
                    project_id, query_text, limit=10, source_id=source_filter,
                    only_usable_sources=only_usable, rerank=rerank, expand_to_parent=expand_to_parent,
                )
            else:
                self._pending_search_results = self._context.rag_service.search(
                    project_id, query_text, limit=10, source_id=source_filter,
                    only_usable_sources=only_usable, expand_to_parent=expand_to_parent,
                )

        # Auditoría profunda (ronda posterior a la 76, ver bitácora):
        # mismo criterio que _on_structured_query/_on_compare -- usar
        # _submit_job() en vez de llamar a jobs.submit_task()
        # directamente, para que una excepción real al enviar el
        # trabajo no se propague sin capturar.
        if not self._submit_job(_run):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _refresh_search_results(self) -> None:
        results = self._pending_search_results or []
        query_text = self._pending_search_query
        mode = self._pending_search_mode
        rerank_ignored = self._pending_search_rerank_ignored
        self._pending_search_results = None
        self._pending_search_query = ""
        self._pending_search_mode = "Semántica"
        self._pending_search_rerank_ignored = False

        # Auditoría Ronda 21: este aviso va ANTES del caso "sin
        # resultados" (y no se pierde en él) -- de lo contrario, marcar
        # "Reranking real" en un modo que no es Híbrida y no obtener
        # resultados dejaría a quien prueba sin ninguna pista de que la
        # casilla nunca llegó a aplicarse, ni siquiera intentándolo.
        ignored_note = (
            "<p><i>Nota: se marcó \"Reranking real\", pero esta búsqueda no fue en modo Híbrida -- "
            "esa casilla solo tiene efecto en modo Híbrida, así que se ignoró.</i></p>"
            if rerank_ignored else ""
        )

        if not results:
            self._search_results.setHtml(f"{ignored_note}<p>Sin resultados.</p>")
            return

        # Comparador de resultados: resaltar en cada fragmento las
        # palabras de la consulta que coincidieron, para que se
        # entienda mejor por qué un resultado quedó arriba de otro
        # (más allá de solo mirar el score).
        terms = extract_highlight_terms(query_text)
        parts: list[str] = [ignored_note] if ignored_note else []
        # El umbral de "relevancia baja" (DEFAULT_MIN_RELEVANT_SCORE)
        # está calibrado para similitud coseno -- BM25 (Textual) y el
        # score de fusión RRF (Híbrida) viven en escalas distintas, sin
        # significado comparable contra ese umbral, así que el aviso
        # solo aplica al modo Semántica.
        if mode == "Semántica" and self._context.rag_service.has_low_relevance(results):
            best = max(result.score for result in results)
            parts.append(
                f"<p><b>Aviso:</b> relevancia baja (mejor score {best:.3f}). Es posible que "
                "el proyecto no tenga contenido relacionado con esta consulta -- revisa los "
                "resultados con cuidado antes de confiar en ellos.</p>"
            )
        elif mode != "Semántica":
            parts.append(f"<p><i>Modo: {mode}. El score no es una similitud coseno -- "
                          "solo sirve para ordenar estos resultados entre sí.</i></p>")
        for result in results:
            source_title = self._source_title(result.chunk.project_id, result.chunk.source_id)
            section = f" — sección: {result.chunk.section_title}" if result.chunk.section_title else ""
            preview = result.chunk.text[:140].replace("\n", " ")
            header = html_escape(f"{source_title}{section}")
            highlighted_preview = highlight_terms(html_escape(preview), terms)
            parts.append(f"<p>[{result.score:.3f}] {header} — {highlighted_preview}…</p>")
            # Pista B.1 del ADR-003: "adjuntar", no "reemplazar" -- el
            # extracto puntual de arriba sigue siendo el que de verdad
            # coincidió con la consulta; esto es contexto adicional,
            # sangrado para distinguirlo visualmente del resultado en
            # sí, igual que el aviso de relevancia baja no se confunde
            # con un resultado.
            if result.parent_chunk is not None:
                parent_preview = result.parent_chunk.text[:400].replace("\n", " ")
                parts.append(
                    "<p style='margin-left: 24px;'><i>Contexto de la sección completa: "
                    f"{html_escape(parent_preview)}…</i></p>"
                )
        self._search_results.setHtml("".join(parts))

    def _on_structured_query(self) -> None:
        # Pista B.2b del ADR-003: mismo patrón que _on_search -- se
        # manda a segundo plano porque, aunque hoy no requiere ningún
        # modelo, sigue siendo trabajo sobre potencialmente todos los
        # chunks del proyecto, y este panel nunca bloquea el hilo de
        # interfaz para ninguna operación de RAG (ver docstring del
        # módulo).
        if self._active_job is not None or self._project_id is None:
            return
        project_id = self._project_id
        filters_text = self._structured_filters.toPlainText()
        aggregation_function = self._structured_agg_function.currentText()
        if aggregation_function == "(sin agregación)":
            aggregation_function = ""
        aggregation_column = self._structured_agg_column.text().strip()
        group_by = self._structured_group_by.text().strip()
        source_filter = self._source_id if self._structured_scope_source_only.isChecked() else None

        self._status_label.setText("Consultando datos estructurados en segundo plano…")
        self._active_job_kind = "estructurada"
        self._pending_structured_result = None

        def _run(handle) -> None:
            # ValueError (filtro/agregación mal escritos) se deja
            # propagar a propósito: el runner de jobs lo captura como
            # fallo y _poll_active_job ya muestra `error` tal cual en
            # un QMessageBox -- el mensaje de
            # RagService.query_structured_from_text ya es claro por sí
            # mismo (columna/operador/función inválidos), sin necesidad
            # de traducirlo de nuevo aquí.
            self._pending_structured_result = self._context.rag_service.query_structured_from_text(
                project_id, filters_text=filters_text,
                aggregation_function=aggregation_function, aggregation_column=aggregation_column,
                group_by=group_by, source_id=source_filter,
            )

        # Auditoría profunda (ronda posterior a la 76, ver bitácora):
        # antes se llamaba a jobs.submit_task() directamente aquí, sin
        # el try/except que sí envuelve a _submit_job() (usado por
        # Indexar/Extraer/Fragmentar/Pipeline en este mismo panel) --
        # una excepción real al enviar el trabajo (no solo
        # JobAlreadyRunningError) se habría propagado sin capturar,
        # dejando _status_label diciendo "en segundo plano" con
        # _active_job nunca asignado.
        if not self._submit_job(_run):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _refresh_structured_query_results(self) -> None:
        result = self._pending_structured_result
        self._pending_structured_result = None
        if result is None:
            self._structured_results.setHtml("<p>Sin resultados.</p>")
            return

        parts: list[str] = []
        if result.aggregation is not None:
            parts.append("<p><b>Agregación:</b></p><ul>")
            if not result.aggregation:
                parts.append(
                    "<li><i>(sin grupos -- ninguna fila cumplió los filtros o tenía la columna de "
                    "agrupación)</i></li>"
                )
            for bucket in result.aggregation:
                group_label = html_escape(bucket.group_value) if bucket.group_value is not None else "(total)"
                value_label = "sin datos numéricos" if bucket.value is None else f"{bucket.value:g}"
                parts.append(f"<li>{group_label}: {value_label}</li>")
            parts.append("</ul>")

        if not result.rows:
            parts.append(
                "<p>Sin filas que cumplan los filtros -- o el proyecto (o esta fuente) no tiene chunks "
                "ChunkType.ESTRUCTURADO todavía (hojas XLSX/CSV fragmentadas con la estrategia "
                "\"Por hoja estructurada\", ver pestaña Fragmentación).</p>"
            )
        else:
            parts.append(f"<p><b>Filas ({len(result.rows)}):</b></p>")
            # Recorte a 200 filas: esta vista es para probar la consulta,
            # no para exportar datos -- una hoja real puede tener miles
            # de filas, y renderizar todas en un QTextBrowser sería lento
            # sin aportar nada que el propio filtro no ya haya resuelto.
            for row in result.rows[:200]:
                section = f" — {html_escape(row.section_title)}" if row.section_title else ""
                values = ", ".join(f"{html_escape(str(k))}={html_escape(str(v))}" for k, v in row.values.items())
                parts.append(f"<p>{section}: {values}</p>")
            if len(result.rows) > 200:
                parts.append(f"<p><i>… y {len(result.rows) - 200} filas más (no mostradas).</i></p>")
        self._structured_results.setHtml("".join(parts))

    def _source_title(self, project_id: str, source_id: str) -> str:
        # Atrapa cualquier excepción a propósito: esto solo formatea un
        # encabezado legible en los resultados de búsqueda -- si la fuente
        # ya no existe o falla su lectura, mostrar el id crudo como
        # respaldo es preferible a que la búsqueda entera falle (auditoría
        # de madurez ronda 5: se agrega registro para poder distinguir
        # este caso de un fallo real de base de datos).
        try:
            return self._context.document_service.get_source(project_id, source_id).title
        except Exception:
            logger.debug(
                "No se pudo obtener el título de la fuente %s del proyecto %s "
                "(se usa el id como respaldo en el resultado de búsqueda).",
                source_id, project_id, exc_info=True,
            )
            return source_id

    def _on_compare(self) -> None:
        if self._active_job is not None or self._project_id is None or not self._compare_available:
            return
        query_text = self._compare_query.text().strip()
        if not query_text:
            # Ronda 8, punto 27 (hallazgo real de usuario, vídeo 2): con
            # "Consulta:" vacío, este método retornaba en silencio -- no
            # se crea ningún job de comparación, así que "La comparación
            # de modelos terminó" NUNCA puede provenir de este clic en
            # particular (ese mensaje solo lo dispara un job de tipo
            # "comparacion" que sí llegó a completarse, ver
            # _poll_active_job). Sin este aviso, quien probara la
            # consulta vacía no tenía ninguna señal de que el botón no
            # hizo nada -- lo más probable es que el mensaje "terminó"
            # que vio el usuario correspondiera a una comparación
            # anterior (con texto) que seguía resolviéndose en segundo
            # plano. Mismo criterio que "Elige dos modelos distintos",
            # unas líneas más abajo.
            QMessageBox.information(self, "Falta la consulta", "Escribe una consulta antes de comparar.")
            return
        profile_a = self._compare_profile_a.currentText()
        profile_b = self._compare_profile_b.currentText()
        if profile_a == profile_b:
            QMessageBox.warning(
                self, "Elige dos modelos distintos", "Selecciona dos perfiles diferentes para comparar."
            )
            return
        project_id = self._project_id
        source_filter = self._source_id if self._compare_scope_source_only.isChecked() else None

        # Igual que buscar/indexar: puede requerir descargar un modelo
        # la primera vez, así que se envía a segundo plano para no
        # bloquear la interfaz.
        self._status_label.setText("Comparando modelos en segundo plano…")
        self._active_job_kind = "comparacion"
        self._pending_compare_result = None
        self._pending_compare_query = query_text

        def _run(handle) -> None:
            self._pending_compare_result = self._context.rag_service.compare_profiles(
                project_id, query_text, profile_a, profile_b, source_id=source_filter, limit=5,
            )

        # Auditoría profunda (ronda posterior a la 76, ver bitácora):
        # mismo criterio que _on_structured_query -- usar _submit_job()
        # en vez de llamar a jobs.submit_task() directamente, para que
        # una excepción real al enviar el trabajo no se propague sin
        # capturar.
        if not self._submit_job(_run):
            return
        self._progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _refresh_compare_results(self) -> None:
        comparison = self._pending_compare_result
        query_text = self._pending_compare_query
        self._pending_compare_result = None
        self._pending_compare_query = ""

        if comparison is None:
            self._compare_results.setHtml("<p>No se pudo completar la comparación.</p>")
            return

        result_a, result_b = comparison
        terms = extract_highlight_terms(query_text)
        html = self._render_comparison_side("Modelo A", result_a, terms) + self._render_comparison_side(
            "Modelo B", result_b, terms
        )
        self._compare_results.setHtml(html)

    def _render_comparison_side(self, label: str, result, terms: list) -> str:
        header = html_escape(f"{label} ({result.profile}): {result.model_name} ({result.dimensions}d)")
        parts = [f"<h4>{header}</h4>"]
        if not result.results:
            parts.append("<p>Sin resultados.</p>")
            return "".join(parts)
        for scored in result.results:
            source_title = self._source_title(scored.chunk.project_id, scored.chunk.source_id)
            section = f" — sección: {scored.chunk.section_title}" if scored.chunk.section_title else ""
            preview = scored.chunk.text[:140].replace("\n", " ")
            chunk_header = html_escape(f"{source_title}{section}")
            highlighted_preview = highlight_terms(html_escape(preview), terms)
            parts.append(f"<p>[{scored.score:.3f}] {chunk_header} — {highlighted_preview}…</p>")
        return "".join(parts)

    # ---------- cancelación ----------
    def _on_cancel(self) -> None:
        if self._active_job is None:
            return
        # Cancelación cooperativa (workers.jobs.ThreadJobRunner).
        # extract_source_text y fragment_source ahora sí revisan
        # JobHandle.is_cancelled() (extracción: antes/después de la
        # llamada al extractor, que en sí sigue siendo atómica;
        # fragmentación: también en cada vuelta del bucle por
        # fragmento, un punto de control real) y, si detectan la
        # cancelación, no persisten nada -- los datos anteriores de la
        # fuente quedan intactos. Indexación y búsqueda semántica
        # todavía no revisan el indicador (son llamadas únicas a
        # embed_texts/upsert, sin un bucle propio donde insertar un
        # punto de control barato) y siguen corriendo hasta terminar.
        self._active_job.cancel()
        self._status_label.setText("Cancelación solicitada…")

    # ---------- sondeo del trabajo en segundo plano ----------
    def _poll_active_job(self) -> None:
        if self._active_job is None:
            return
        self._progress.setValue(int(self._active_job.progress * 100))
        if self._active_job.status.value not in ("completado", "fallido", "cancelado"):
            return

        self._poll_timer.stop()
        status = self._active_job.status.value
        kind = self._active_job_kind
        error = self._active_job.error
        self._active_job = None
        self._active_job_kind = None
        self._update_enabled_state()

        if status == "fallido":
            self._status_label.setText("El trabajo falló.")
            QMessageBox.critical(self, "Error", error or "Error desconocido.")
            return

        if status == "cancelado":
            if kind in ("extraccion", "fragmentacion"):
                # Ver _on_cancel: estos dos sí revisan is_cancelled()
                # antes de guardar, así que lo más probable es que no
                # se haya persistido nada nuevo -- se refresca igual
                # para mostrar el estado real (que puede ser el mismo
                # de antes de pedir la operación).
                self._status_label.setText(
                    "Cancelado: no se guardaron datos nuevos (los anteriores, si había, siguen intactos)."
                )
            elif kind in ("comparacion", "estructurada"):
                # Ni el comparador de modelos ni la consulta
                # estructurada persisten nada (ver
                # compare_embedding_profiles.py / structured_query.py:
                # todo se calcula en memoria), así que "sus datos se
                # guardaron" no aplica aquí -- simplemente ya había
                # terminado de calcular.
                self._status_label.setText(
                    "Cancelación registrada, pero el cálculo ya había terminado."
                )
            elif kind == "pipeline":
                # A diferencia de extraccion/fragmentacion (nada nuevo
                # persistido) o indexacion/busqueda (ya había terminado):
                # el pipeline SÍ revisa is_cancelled() entre fuentes, así
                # que se detiene a medio camino de verdad -- pero las
                # fuentes que ya se alcanzaron a procesar sí quedan
                # guardadas (ver el reporte para cuáles).
                self._status_label.setText(
                    "Pipeline cancelado: se detuvo antes de procesar todas las fuentes. Las que ya se "
                    "procesaron quedaron guardadas -- revisa el reporte."
                )
            else:
                # indexación/búsqueda: todavía no revisan is_cancelled()
                # a mitad de camino (ver _on_cancel), así que el trabajo
                # ya había terminado y sus datos SÍ quedan guardados.
                self._status_label.setText(
                    "Cancelación registrada, pero el trabajo ya había terminado: sus datos se guardaron igual."
                )
        else:
            self._status_label.setText("Listo.")

        if kind == "extraccion":
            self._refresh_extraction_preview()
        elif kind == "fragmentacion":
            self._refresh_chunk_list()
        elif kind == "indexacion":
            self._refresh_index_info()
            # Fase 4 de multimodalidad nativa: para una fuente
            # IMAGEN_NATIVA, el único Chunk tipo IMAGEN se crea recién
            # aquí, dentro de IndexImageSource -- no en "Fragmentar"
            # (ver Ronda 65, punto 221; Ronda 66, punto 224). Sin este
            # refresco, la pestaña Fragmentación seguiría mostrando la
            # lista vacía de antes de indexar hasta que la persona
            # cambiara de fuente y volviera. Para una fuente de texto
            # esto no cambia nada (index_source no modifica los
            # Chunk ya fragmentados), así que es seguro para ambos casos.
            self._refresh_chunk_list()
        elif kind == "busqueda":
            self._refresh_search_results()
        elif kind == "comparacion":
            self._refresh_compare_results()
        elif kind == "estructurada":
            self._refresh_structured_query_results()
        elif kind == "pipeline":
            self._refresh_pipeline_report()
            self._refresh_index_info()

        # Aviso emergente al terminar con éxito (a pedido del consultor,
        # validación de madurez sobre notificaciones): antes, un trabajo
        # exitoso solo cambiaba este status_label a "Listo.", visible
        # solo si el usuario seguía parado en esta pestaña -- si se había
        # ido a otra (por ejemplo, mientras corría "Ejecutar pipeline
        # completo"), no se enteraba de que ya había terminado. Los
        # errores ya usaban QMessageBox (visible sin importar la pestaña
        # activa); ahora el éxito también, para el mismo tipo de trabajos
        # -- excepto "busqueda"/"estructurada", que se dejan sin aviso a
        # propósito: ahí el usuario normalmente ya está mirando la
        # pantalla esperando el resultado, así que un emergente sería
        # una molestia, no una ayuda.
        if status == "completado" and kind not in ("busqueda", "estructurada"):
            mensaje_listo = {
                "extraccion": "La extracción de texto terminó.",
                "fragmentacion": "La fragmentación terminó.",
                "indexacion": "La indexación terminó.",
                "comparacion": "La comparación de modelos terminó.",
                "pipeline": "El pipeline completo terminó de correr. Revisa el reporte para ver el "
                            "detalle por fuente.",
            }.get(kind, "El trabajo terminó.")
            QMessageBox.information(self, "Listo", mensaje_listo)
