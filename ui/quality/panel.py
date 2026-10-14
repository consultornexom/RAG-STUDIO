"""Panel de Calidad (Etapa 6): banco de pruebas y corridas de
evaluación (semáforos, regresión, bloqueos por hallazgos críticos)
sobre el motor conversacional de Etapa 5.

Regla de capa: solo llama a application (quality_service, jobs). Nunca
importa domain ni infrastructure directamente (ADR-001, sección 4) --
los vocabularios de enums vienen de application.quality.options y
application.conversational.options (acción esperada/prohibida
reutiliza el mismo catálogo que Etapa 5), igual patrón que
FRAGMENTATION_STRATEGY_OPTIONS en Ingesta. Los objetos que devuelve
quality_service (TestCase, EvaluationRun...) se leen solo por sus
atributos, sin importarlos.

Como Ingesta y Diseño conversacional, nace ya dividida en
sub-pestañas: Banco de pruebas y Evaluación.

Ronda 4 (punto 2 de Validacion_observaciones_RAG_STUDIO.md): el banco
de pruebas ahora admite Crear + Editar + Eliminar + Activar/Desactivar
-- antes solo tenía Crear + Activar/Desactivar, y un caso mal
capturado se quedaba acumulado sin poder corregirse ni limpiarse.
Eliminar sigue bloqueado si el caso ya participó en alguna corrida de
evaluación (ver TestCaseInUseError) -- para esos, la vía es
desactivarlo. El código (`code`) no es editable: lo usa la comparación
de regresión entre corridas.

Alcance deliberado que sigue vigente (ver README, "Limitaciones
conocidas"): los tipos de ejecución cubiertos son completa/por
categoría/individual -- "comparación entre modelos/índices/reglas/
prompts" queda para una iteración posterior."""
from __future__ import annotations

from html import escape as html_escape
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from application.conversational.options import RULE_ACTION_OPTIONS
from application.quality.options import (
    DEFAULT_QUALITY_REGRESSION_THRESHOLD, EVALUATION_SCOPE_OPTIONS, TEST_CATEGORY_OPTIONS, TEST_SEVERITY_OPTIONS,
)
from ui.conversational.parsing import parse_provided_variables
from ui.release.gate_status import GateStatusLabel
from ui.theme import estado_html
from ui.errors import describe_error

_TENDENCIA_MAX_CORRIDAS = 10
"""Ronda 53 (opción C): cuántas corridas "completa" recientes se
muestran en el diálogo de tendencia -- no todo el historial, para que
la tabla siga siendo legible de un vistazo."""

_NONE_LABEL = "— sin definir —"


class _EditTestCaseDialog(QDialog):
    """Ronda 4 (punto 2): antes el banco de pruebas no tenía ningún
    "Editar caso" -- solo Crear y Activar/Desactivar. `code` se muestra
    de solo lectura en el título porque no es editable (ver
    UpdateTestCase)."""

    def __init__(self, case, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar caso de prueba ({case.code!r})")

        self._category = QComboBox(self)
        self._category.addItems(TEST_CATEGORY_OPTIONS)
        self._category.setCurrentText(case.category.value)
        self._query = QLineEdit(case.query_text, self)
        self._variables = QLineEdit(
            ", ".join(f"{k}={v}" for k, v in case.provided_variables.items()), self,
        )
        self._source_id = QLineEdit(case.source_id or "", self)
        self._expected_intent = QLineEdit(case.expected_intent or "", self)
        self._expected_missing_variable = QLineEdit(case.expected_missing_variable or "", self)
        self._expected_action = QComboBox(self)
        self._expected_action.addItem(_NONE_LABEL, None)
        for option in RULE_ACTION_OPTIONS:
            self._expected_action.addItem(option, option)
        if case.expected_action is not None:
            self._expected_action.setCurrentText(case.expected_action.value)
        self._forbidden_action = QComboBox(self)
        self._forbidden_action.addItem(_NONE_LABEL, None)
        for option in RULE_ACTION_OPTIONS:
            self._forbidden_action.addItem(option, option)
        if case.forbidden_action is not None:
            self._forbidden_action.setCurrentText(case.forbidden_action.value)
        self._expected_channeling = QCheckBox("Se espera canalización real (con esquema configurado)", self)
        self._expected_channeling.setChecked(case.expected_channeling)
        self._expected_source_id = QLineEdit(case.expected_source_id or "", self)
        self._severity = QComboBox(self)
        self._severity.addItems(TEST_SEVERITY_OPTIONS)
        self._severity.setCurrentText(case.severity.value)

        form = QFormLayout()
        form.addRow("Categoría:", self._category)
        form.addRow("Consulta:", self._query)
        form.addRow("Datos proporcionados:", self._variables)
        form.addRow("Restringir a una fuente:", self._source_id)
        form.addRow("Intención esperada:", self._expected_intent)
        form.addRow("Dato faltante esperado:", self._expected_missing_variable)
        form.addRow("Acción esperada:", self._expected_action)
        form.addRow("Acción prohibida:", self._forbidden_action)
        form.addRow("", self._expected_channeling)
        form.addRow("Fuente esperada (primer resultado):", self._expected_source_id)
        form.addRow("Severidad:", self._severity)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "category": self._category.currentText(),
            "query_text": self._query.text().strip(),
            "provided_variables": parse_provided_variables(self._variables.text()),
            "source_id": self._source_id.text().strip() or None,
            "expected_intent": self._expected_intent.text().strip() or None,
            "expected_missing_variable": self._expected_missing_variable.text().strip() or None,
            "expected_action": self._expected_action.currentData(),
            "forbidden_action": self._forbidden_action.currentData(),
            "expected_channeling": self._expected_channeling.isChecked(),
            "expected_source_id": self._expected_source_id.text().strip() or None,
            "severity": self._severity.currentText(),
        }


class _TrendDialog(QDialog):
    """Ronda 53 (Propuesta de evaluación continua reforzada, opción C
    confirmada por el consultor): tendencia de Recall@3/MRR sobre las
    últimas corridas "completa" -- una comparación corrida-contra-
    corrida-anterior (ver bloque de comparación en _render_run) puede
    no notar una caída lenta y gradual repartida en varias rondas de
    evaluación; esta tabla existe para que un humano sí la note, aunque
    ninguna compuerta la haya bloqueado. Sin gráfico (no hay precedente
    de gráficos en ningún panel de este proyecto) -- una tabla de texto
    simple, igual que el resto de listas de este panel."""

    def __init__(self, complete_runs: list, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Tendencia de Recall@3 / MRR (corridas \"completa\")")
        self.setMinimumWidth(520)

        browser = QTextBrowser(self)
        recent = complete_runs[:_TENDENCIA_MAX_CORRIDAS]
        if not recent:
            browser.setHtml("<p>No hay ninguna corrida de alcance \"completa\" todavía.</p>")
        else:
            rows = [
                "<tr><th align='left'>Fecha</th><th align='left'>Recall@3</th>"
                "<th align='left'>MRR</th><th align='left'>Veredicto general</th></tr>"
            ]
            for run in recent:
                recall_3 = run.recall_at_k(3)
                mrr = run.mean_reciprocal_rank()
                recall_cell = f"{recall_3:.0%}" if recall_3 is not None else "—"
                mrr_cell = f"{mrr:.2f}" if mrr is not None else "—"
                rows.append(
                    "<tr>"
                    f"<td>{run.started_at:%Y-%m-%d %H:%M}</td>"
                    f"<td>{recall_cell}</td>"
                    f"<td>{mrr_cell}</td>"
                    f"<td>{html_escape(run.overall_verdict.value)}</td>"
                    "</tr>"
                )
            table = "<table cellspacing='6'>" + "".join(rows) + "</table>"
            note = ""
            if len(complete_runs) > _TENDENCIA_MAX_CORRIDAS:
                note = (
                    f"<p><i>Mostrando las {_TENDENCIA_MAX_CORRIDAS} corridas \"completa\" más "
                    f"recientes de {len(complete_runs)} en total.</i></p>"
                )
            browser.setHtml(f"<p>Más reciente primero.</p>{table}{note}")
        browser.setReadOnly(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(browser)
        layout.addWidget(buttons)


class QualityPanel(QWidget):
    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None

        self._test_cases_cache: list = []
        self._active_job = None
        self._pending_run = None

        layout = QVBoxLayout(self)

        # Aviso temprano (no bloqueante) de la compuerta de Liberación
        # "Calidad" -- ver ui/release/gate_status.py.
        self._gate_status_label = GateStatusLabel("Calidad", self)
        layout.addWidget(self._gate_status_label)
        # Ronda 53 (opción B'): la nueva compuerta "Regresión de
        # recuperación" es independiente de "Calidad" (bloqueos por
        # caso individual) -- mismo patrón de aviso temprano.
        self._regression_gate_status_label = GateStatusLabel("Regresión de recuperación", self)
        layout.addWidget(self._regression_gate_status_label)

        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_test_cases_tab(), "Banco de pruebas")
        self._tabs.addTab(self._build_evaluation_tab(), "Evaluación")

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._poll_active_job)

        self._apply_button_states()

    # ---------- wiring de proyecto activo ----------
    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._eval_report.setHtml("")
        self._refresh_test_cases()
        self._refresh_run_history()
        self._refresh_regression_threshold()
        self._apply_button_states()
        if self._project_id:
            self._gate_status_label.refresh(self._context.release_service, self._project_id)
            self._regression_gate_status_label.refresh(self._context.release_service, self._project_id)
        else:
            self._gate_status_label.clear_status()
            self._regression_gate_status_label.clear_status()

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _apply_button_states(self) -> None:
        ready = self._project_id is not None
        busy = self._active_job is not None
        for widget in (
            self._btn_create_test_case, self._btn_toggle_test_case, self._btn_edit_test_case,
            self._btn_delete_test_case, self._test_case_list,
            self._tc_code, self._tc_category, self._tc_query, self._tc_variables, self._tc_source_id,
            self._tc_expected_intent, self._tc_expected_missing_variable, self._tc_expected_action,
            self._tc_forbidden_action, self._tc_expected_channeling, self._tc_expected_source_id,
            self._tc_severity,
        ):
            widget.setEnabled(ready)
        for widget in (self._eval_scope, self._eval_category, self._eval_test_case, self._run_history_list):
            widget.setEnabled(ready and not busy)
        self._btn_run_evaluation.setEnabled(ready and not busy)
        self._eval_cancel.setEnabled(busy)
        for widget in (self._regression_threshold, self._btn_save_regression_threshold, self._btn_view_trend):
            widget.setEnabled(ready)

    # ================= Banco de pruebas =================
    def _build_test_cases_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        form = QGroupBox("Nuevo caso de prueba", tab)
        form_layout = QVBoxLayout(form)

        self._tc_code = QLineEdit(form)
        self._tc_code.setPlaceholderText("Código (p. ej. TEST-ADM-001)")
        self._tc_category = QComboBox(form)
        self._tc_category.addItems(TEST_CATEGORY_OPTIONS)
        row1 = QHBoxLayout()
        row1.addWidget(self._tc_code)
        row1.addWidget(QLabel("Categoría:", form))
        row1.addWidget(self._tc_category)
        form_layout.addLayout(row1)

        self._tc_query = QLineEdit(form)
        self._tc_query.setPlaceholderText("Consulta")
        form_layout.addWidget(self._tc_query)

        self._tc_variables = QLineEdit(form)
        self._tc_variables.setPlaceholderText("Datos proporcionados (opcional): codigo=valor, codigo2=valor2")
        self._tc_source_id = QLineEdit(form)
        self._tc_source_id.setPlaceholderText("Restringir a una fuente (opcional, ID)")
        row2 = QHBoxLayout()
        row2.addWidget(self._tc_variables)
        row2.addWidget(self._tc_source_id)
        form_layout.addLayout(row2)

        self._tc_expected_intent = QLineEdit(form)
        self._tc_expected_intent.setPlaceholderText("Intención esperada (opcional)")
        self._tc_expected_missing_variable = QLineEdit(form)
        self._tc_expected_missing_variable.setPlaceholderText("Dato faltante esperado (opcional)")
        row3 = QHBoxLayout()
        row3.addWidget(self._tc_expected_intent)
        row3.addWidget(self._tc_expected_missing_variable)
        form_layout.addLayout(row3)

        self._tc_expected_action = QComboBox(form)
        self._tc_expected_action.addItem(_NONE_LABEL, None)
        for option in RULE_ACTION_OPTIONS:
            self._tc_expected_action.addItem(option, option)
        self._tc_forbidden_action = QComboBox(form)
        self._tc_forbidden_action.addItem(_NONE_LABEL, None)
        for option in RULE_ACTION_OPTIONS:
            self._tc_forbidden_action.addItem(option, option)
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Acción esperada:", form))
        row4.addWidget(self._tc_expected_action)
        row4.addWidget(QLabel("Acción prohibida:", form))
        row4.addWidget(self._tc_forbidden_action)
        form_layout.addLayout(row4)

        self._tc_expected_channeling = QCheckBox("Se espera canalización real (con esquema configurado)", form)
        self._tc_expected_source_id = QLineEdit(form)
        self._tc_expected_source_id.setPlaceholderText("Fuente esperada en el primer resultado (opcional, ID)")
        self._tc_severity = QComboBox(form)
        self._tc_severity.addItems(TEST_SEVERITY_OPTIONS)
        row5 = QHBoxLayout()
        row5.addWidget(self._tc_expected_channeling)
        row5.addWidget(self._tc_expected_source_id)
        row5.addWidget(QLabel("Severidad:", form))
        row5.addWidget(self._tc_severity)
        form_layout.addLayout(row5)

        self._btn_create_test_case = QPushButton("Crear caso de prueba", form)
        self._btn_create_test_case.clicked.connect(self._on_create_test_case)
        form_layout.addWidget(self._btn_create_test_case)
        layout.addWidget(form)

        list_row = QHBoxLayout()
        self._btn_toggle_test_case = QPushButton("Activar/Desactivar seleccionado", tab)
        self._btn_toggle_test_case.clicked.connect(self._on_toggle_test_case)
        list_row.addWidget(self._btn_toggle_test_case)
        self._btn_edit_test_case = QPushButton("Editar…", tab)
        self._btn_edit_test_case.clicked.connect(self._on_edit_test_case)
        list_row.addWidget(self._btn_edit_test_case)
        self._btn_delete_test_case = QPushButton("Eliminar", tab)
        self._btn_delete_test_case.clicked.connect(self._on_delete_test_case)
        list_row.addWidget(self._btn_delete_test_case)
        layout.addLayout(list_row)
        self._test_case_list = QListWidget(tab)
        layout.addWidget(self._test_case_list)
        return tab

    def _refresh_test_cases(self) -> None:
        self._test_case_list.clear()
        self._test_cases_cache = []
        if self._project_id:
            self._test_cases_cache = self._context.quality_service.list_test_cases(self._project_id)
            for case in self._test_cases_cache:
                estado = "activo" if case.active else "inactivo"
                self._test_case_list.addItem(
                    f"[{estado}] {case.code} — categoría: {case.category.value} — severidad: {case.severity.value}"
                )
        self._populate_individual_test_case_combo()

    def _on_create_test_case(self) -> None:
        if not self._project_id:
            return
        code = self._tc_code.text().strip()
        query_text = self._tc_query.text().strip()
        if not code or not query_text:
            QMessageBox.warning(self, "Faltan datos", "El caso necesita código y consulta.")
            return
        try:
            self._context.quality_service.create_test_case(
                self._project_id, code, self._tc_category.currentText(), query_text,
                provided_variables=parse_provided_variables(self._tc_variables.text()),
                source_id=self._tc_source_id.text().strip() or None,
                expected_intent=self._tc_expected_intent.text().strip() or None,
                expected_missing_variable=self._tc_expected_missing_variable.text().strip() or None,
                expected_action=self._tc_expected_action.currentData(),
                forbidden_action=self._tc_forbidden_action.currentData(),
                expected_channeling=self._tc_expected_channeling.isChecked(),
                expected_source_id=self._tc_expected_source_id.text().strip() or None,
                severity=self._tc_severity.currentText(),
            )
        except Exception as exc:  # noqa: BLE001 - incluye código duplicado
            self._report_error(exc)
            return
        for field in (
            self._tc_code, self._tc_query, self._tc_variables, self._tc_source_id, self._tc_expected_intent,
            self._tc_expected_missing_variable, self._tc_expected_source_id,
        ):
            field.clear()
        self._tc_expected_action.setCurrentIndex(0)
        self._tc_forbidden_action.setCurrentIndex(0)
        self._tc_expected_channeling.setChecked(False)
        self._tc_severity.setCurrentIndex(0)
        self._refresh_test_cases()
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_toggle_test_case(self) -> None:
        row = self._test_case_list.currentRow()
        if row < 0 or row >= len(self._test_cases_cache) or not self._project_id:
            return
        case = self._test_cases_cache[row]
        try:
            self._context.quality_service.set_test_case_active(self._project_id, case.id, not case.active)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_test_cases()

    def _on_edit_test_case(self) -> None:
        row = self._test_case_list.currentRow()
        if row < 0 or row >= len(self._test_cases_cache) or not self._project_id:
            return
        case = self._test_cases_cache[row]
        dialog = _EditTestCaseDialog(case, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["query_text"]:
            QMessageBox.warning(self, "Falta información", "El caso necesita una consulta.")
            return
        try:
            self._context.quality_service.update_test_case(self._project_id, case.id, **values)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_test_cases()

    def _on_delete_test_case(self) -> None:
        # Ronda 4 (punto 2): bloqueado si el caso ya participó en
        # alguna corrida de evaluación (TestCaseInUseError) -- para
        # esos, la vía es desactivarlo, no eliminarlo.
        row = self._test_case_list.currentRow()
        if row < 0 or row >= len(self._test_cases_cache) or not self._project_id:
            return
        case = self._test_cases_cache[row]
        confirm = QMessageBox.question(self, "Eliminar caso de prueba", f"¿Eliminar el caso {case.code!r}?")
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.quality_service.delete_test_case(self._project_id, case.id)
        except Exception as exc:  # noqa: BLE001 - incluye TestCaseInUseError
            self._report_error(exc)
            return
        self._refresh_test_cases()

    # ================= Evaluación =================
    def _build_evaluation_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        form = QGroupBox("Ejecutar evaluación", tab)
        form_layout = QVBoxLayout(form)

        self._eval_scope = QComboBox(form)
        self._eval_scope.addItems(EVALUATION_SCOPE_OPTIONS)
        self._eval_scope.currentTextChanged.connect(self._on_scope_changed)
        self._eval_category = QComboBox(form)
        self._eval_category.addItems(TEST_CATEGORY_OPTIONS)
        self._eval_test_case = QComboBox(form)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Alcance:", form))
        row1.addWidget(self._eval_scope)
        row1.addWidget(QLabel("Categoría:", form))
        row1.addWidget(self._eval_category)
        row1.addWidget(QLabel("Caso individual:", form))
        row1.addWidget(self._eval_test_case)
        form_layout.addLayout(row1)

        action_row = QHBoxLayout()
        self._btn_run_evaluation = QPushButton("Ejecutar evaluación", form)
        self._btn_run_evaluation.clicked.connect(self._on_run_evaluation)
        self._eval_cancel = QPushButton("Cancelar", form)
        self._eval_cancel.clicked.connect(self._on_cancel_evaluation)
        action_row.addWidget(self._btn_run_evaluation)
        action_row.addWidget(self._eval_cancel)
        form_layout.addLayout(action_row)

        self._eval_progress = QProgressBar(form)
        self._eval_progress.setRange(0, 100)
        form_layout.addWidget(self._eval_progress)
        self._eval_status = QLabel("", form)
        form_layout.addWidget(self._eval_status)
        layout.addWidget(form)

        # Ronda 53 (Propuesta de evaluación continua reforzada, opción
        # B' confirmada por el consultor): umbral de la compuerta de
        # liberación "Regresión de recuperación" -- solo compara
        # corridas de alcance "completa" entre sí (ver
        # ListCompleteEvaluationRuns/_retrieval_regression_gate).
        regression_group = QGroupBox("Compuerta \"Regresión de recuperación\"", tab)
        regression_layout = QHBoxLayout(regression_group)
        regression_layout.addWidget(QLabel("Umbral de caída admitida (Recall@3/MRR):", regression_group))
        self._regression_threshold = QDoubleSpinBox(regression_group)
        self._regression_threshold.setRange(0.0, 100.0)
        self._regression_threshold.setDecimals(0)
        self._regression_threshold.setSuffix("%")
        self._regression_threshold.setSingleStep(1.0)
        regression_layout.addWidget(self._regression_threshold)
        self._btn_save_regression_threshold = QPushButton("Guardar umbral", regression_group)
        self._btn_save_regression_threshold.clicked.connect(self._on_save_regression_threshold)
        regression_layout.addWidget(self._btn_save_regression_threshold)
        self._btn_view_trend = QPushButton("Ver tendencia de Recall@3 / MRR…", regression_group)
        self._btn_view_trend.clicked.connect(self._on_view_trend)
        regression_layout.addWidget(self._btn_view_trend)
        layout.addWidget(regression_group)

        self._eval_report = QTextBrowser(tab)
        self._eval_report.setReadOnly(True)
        layout.addWidget(self._eval_report)

        history_label = QLabel("Historial de corridas (más reciente primero):", tab)
        layout.addWidget(history_label)
        self._run_history_list = QListWidget(tab)
        self._run_history_list.itemDoubleClicked.connect(self._on_open_history_run)
        self._run_history_cache: list = []
        layout.addWidget(self._run_history_list)

        self._on_scope_changed(self._eval_scope.currentText())
        return tab

    def _on_scope_changed(self, scope: str) -> None:
        self._eval_category.setEnabled(scope == "categoria" and self._project_id is not None)
        self._eval_test_case.setEnabled(scope == "individual" and self._project_id is not None)

    def _populate_individual_test_case_combo(self) -> None:
        self._eval_test_case.clear()
        for case in self._test_cases_cache:
            self._eval_test_case.addItem(f"{case.code} ({case.category.value})", case.id)
        self._on_scope_changed(self._eval_scope.currentText())

    # ---------- Ronda 53: umbral de la compuerta "Regresión de
    # recuperación" y tendencia de Recall@3/MRR (opciones B'/C) ----------
    def _refresh_regression_threshold(self) -> None:
        if not self._project_id:
            self._regression_threshold.setValue(DEFAULT_QUALITY_REGRESSION_THRESHOLD * 100)
            return
        try:
            project = self._context.project_service.get_project(self._project_id)
        except Exception:  # noqa: BLE001 - lectura de solo apoyo visual, nunca debe tumbar la pestaña
            self._regression_threshold.setValue(DEFAULT_QUALITY_REGRESSION_THRESHOLD * 100)
            return
        threshold = project.quality_regression_threshold
        if threshold is None:
            threshold = DEFAULT_QUALITY_REGRESSION_THRESHOLD
        self._regression_threshold.setValue(threshold * 100)

    def _on_save_regression_threshold(self) -> None:
        if not self._project_id:
            return
        threshold = self._regression_threshold.value() / 100.0
        try:
            self._context.project_service.update_quality_regression_threshold(self._project_id, threshold)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._regression_gate_status_label.refresh(self._context.release_service, self._project_id)
        QMessageBox.information(self, "Listo", "Umbral guardado.")

    def _on_view_trend(self) -> None:
        if not self._project_id:
            return
        try:
            complete_runs = self._context.quality_service.list_complete_evaluation_runs(self._project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        dialog = _TrendDialog(complete_runs, self)
        dialog.exec()

    def _on_run_evaluation(self) -> None:
        if self._active_job is not None or not self._project_id:
            return
        project_id = self._project_id
        scope = self._eval_scope.currentText()
        category_filter = self._eval_category.currentText() if scope == "categoria" else None
        test_case_id_filter = self._eval_test_case.currentData() if scope == "individual" else None
        if scope == "individual" and not test_case_id_filter:
            QMessageBox.warning(self, "Falta el caso", "Elige un caso de prueba para una corrida individual.")
            return

        self._eval_status.setText("Ejecutando la evaluación en segundo plano…")
        self._pending_run = None

        def _run(handle) -> None:
            self._pending_run = self._context.quality_service.run_evaluation(
                project_id, scope=scope, category_filter=category_filter, test_case_id_filter=test_case_id_filter,
                is_cancelled=handle.is_cancelled,
            )

        try:
            self._active_job = self._context.jobs.submit_task(_run, key=f"evaluacion:{project_id}")
        except Exception as exc:  # noqa: BLE001 - incluye JobAlreadyRunningError
            self._report_error(exc)
            return
        self._eval_progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _on_cancel_evaluation(self) -> None:
        if self._active_job is None:
            return
        self._active_job.cancel()
        self._eval_status.setText("Cancelación solicitada…")

    def _poll_active_job(self) -> None:
        if self._active_job is None:
            return
        self._eval_progress.setValue(int(self._active_job.progress * 100))
        if self._active_job.status.value not in ("completado", "fallido", "cancelado"):
            return

        self._poll_timer.stop()
        status = self._active_job.status.value
        error = self._active_job.error
        self._active_job = None
        self._apply_button_states()

        if status == "fallido":
            self._eval_status.setText("La evaluación falló.")
            QMessageBox.critical(self, "Error", error or "Error desconocido.")
            return
        if status == "cancelado":
            self._eval_status.setText(
                "Evaluación cancelada: se detuvo antes de correr todos los casos -- revisa el reporte."
            )
        else:
            self._eval_status.setText("Listo.")
        self._refresh_evaluation_report()
        self._refresh_run_history()
        self._gate_status_label.refresh(self._context.release_service, self._project_id)
        self._regression_gate_status_label.refresh(self._context.release_service, self._project_id)

        # Aviso emergente al terminar con éxito (ver mismo cambio en
        # ui/ingestion/panel.py y ui/conversational/panel.py): antes,
        # solo cambiaba _eval_status, invisible si el usuario ya no
        # estaba parado en esta pestaña.
        if status == "completado":
            QMessageBox.information(self, "Listo", "La evaluación terminó. Revisa el reporte y los semáforos.")

    def _refresh_evaluation_report(self) -> None:
        run = self._pending_run
        self._pending_run = None
        if run is None:
            return
        self._render_run(run)

    def _render_run(self, run) -> None:
        verdict_labels = {"verde": "Verde (aprobado)", "amarillo": "Amarillo (requiere revisión)",
                           "rojo": "Rojo (bloqueo)", "gris": "Gris (no ejecutado)"}
        overall_verdict_text = estado_html(
            verdict_labels.get(run.overall_verdict.value, run.overall_verdict.value),
            run.overall_verdict.value,
        )
        parts = [
            f"<p><b>Corrida {run.id}</b> — alcance: {html_escape(run.scope)} "
            f"— {len(run.items)} caso(s) — <b>veredicto general: "
            f"{overall_verdict_text}</b>"
            f"{' — BLOQUEA LIBERACIÓN' if run.has_blocking_failures else ''}"
            f"{f' — {run.regression_count} regresión(es)' if run.regression_count else ''}</p>"
        ]
        # ADR-003, Pista A.1: métrica cuantitativa de recuperación --
        # solo se muestra si al menos un caso de esta corrida declaró
        # una fuente esperada (recall_at_k devuelve None si no hay
        # ninguno, p. ej. una corrida de solo casos de canalización).
        recall_3 = run.recall_at_k(3)
        if recall_3 is not None:
            applicable_count = len(run.retrieval_applicable_items)
            # Ronda 53 (opción A confirmada por el consultor): MRR junto
            # a Recall@3 -- mismo denominador, mismo criterio de
            # ausencia de dato (ver EvaluationRun.mean_reciprocal_rank).
            mrr = run.mean_reciprocal_rank()
            mrr_text = f" — MRR: <b>{mrr:.2f}</b>" if mrr is not None else ""
            parts.append(
                f"<p>Calidad de recuperación — Recall@3: <b>{recall_3:.0%}</b>{mrr_text} "
                f"(sobre {applicable_count} caso(s) con fuente esperada declarada)</p>"
            )
        if run.scope == "completa":
            parts.append(self._render_regression_comparison(run))
        for item in run.items:
            verdict_note = estado_html(
                verdict_labels.get(item.verdict.value, item.verdict.value), item.verdict.value,
            )
            detail = f"[{verdict_note}] {html_escape(item.test_case_code)} ({html_escape(item.category.value)})"
            if item.regressed:
                detail += " — <b>regresión</b>"
            if item.actual_intent:
                detail += f" — intención: {html_escape(item.actual_intent)}"
            if item.actual_action:
                detail += f" — acción: {html_escape(item.actual_action.value)}"
            if item.error:
                # Ronda 93: el error trae categoría/etapa/código y detalle técnico en varias líneas.
                primera, _, resto = item.error.partition("\n")
                detail += f" — <b>error:</b> {html_escape(primera)}"
                if resto:
                    detail += (
                        "<br><span style='font-family:monospace;font-size:small;'>"
                        + html_escape(resto).replace("\n", "<br>") + "</span>"
                    )
            elif item.verdict.value == "gris":
                # Corridas guardadas antes de la Ronda 93 con una excepción sin mensaje.
                detail += (
                    " — <b>error:</b> sin causa registrada (corrida anterior a la clasificación de "
                    "errores; vuelve a evaluar para obtener categoría y etapa)"
                )
            parts.append(f"<p>{detail}</p>")
            for mismatch in item.mismatches:
                parts.append(f"<p style='margin-left:20px;'>— {html_escape(mismatch)}</p>")
        self._eval_report.setHtml("".join(parts))

    def _render_regression_comparison(self, run) -> str:
        """Ronda 53 (opción B confirmada por el consultor): compara
        Recall@3/MRR de esta corrida "completa" contra la corrida
        "completa" inmediatamente anterior -- mismo par que evalúa
        _retrieval_regression_gate, para que lo que ve el consultor
        aquí explique exactamente por qué esa compuerta pasó o
        bloqueó (o viceversa: por qué todavía no puede evaluarse).

        Ronda 84 (hallazgo real de usuario, ver bitácora): la
        clasificación de las tres situaciones reales (sin métricas
        todavía / solo esta corrida las tiene / ambas comparables) se
        delega a QualityService.compare_retrieval_regression -- mismo
        criterio de capa común que usa _retrieval_regression_gate, para
        que este mensaje nunca pueda divergir del de Liberación (antes
        de esta ronda, un `if ... or ...` local aquí mostraba "esta
        corrida o la de referencia" incluso cuando esta corrida sí tenía
        métricas y solo la de referencia no las tenía)."""
        if not self._project_id:
            return ""
        complete_runs = self._context.quality_service.list_complete_evaluation_runs(self._project_id)
        older = [r for r in complete_runs if r.id != run.id and r.started_at < run.started_at]
        if not older:
            return "<p><i>Sin otra corrida \"completa\" anterior con la que comparar todavía.</i></p>"
        reference = older[0]
        comparison = self._context.quality_service.compare_retrieval_regression(run, reference)

        if comparison.status.value == "sin_metricas_en_la_mas_reciente":
            return (
                "<p><i>Esta corrida no tiene casos con fuente esperada declarada -- no hay "
                "Recall@3/MRR que comparar.</i></p>"
            )
        if comparison.status.value == "sin_corrida_anterior_comparable":
            return (
                "<p><i>Esta corrida contiene casos con fuente esperada, pero la corrida \"completa\" "
                f"de referencia ({reference.started_at:%Y-%m-%d %H:%M}) no tiene métricas Recall@3/MRR "
                "disponibles; todavía no existe una base comparable para evaluar regresión.</i></p>"
            )
        return (
            "<p><b>Comparación con la corrida \"completa\" anterior</b> "
            f"({reference.started_at:%Y-%m-%d %H:%M}): "
            f"Recall@3 {comparison.reference_recall:.0%} → {comparison.current_recall:.0%} "
            f"(caída: {comparison.recall_drop:.0%}), "
            f"MRR {comparison.reference_mrr:.2f} → {comparison.current_mrr:.2f} "
            f"(caída: {comparison.mrr_drop:.0%})</p>"
        )

    def _refresh_run_history(self) -> None:
        self._run_history_list.clear()
        self._run_history_cache = []
        if not self._project_id:
            return
        self._run_history_cache = self._context.quality_service.list_evaluation_runs(self._project_id)
        for run in self._run_history_cache:
            recall_3 = run.recall_at_k(3)
            recall_suffix = f" — Recall@3: {recall_3:.0%}" if recall_3 is not None else ""
            self._run_history_list.addItem(
                f"{run.started_at:%Y-%m-%d %H:%M} — {run.scope} — {len(run.items)} caso(s) "
                f"— veredicto: {run.overall_verdict.value}{recall_suffix}"
            )

    def _on_open_history_run(self, _item) -> None:
        row = self._run_history_list.currentRow()
        if row < 0 or row >= len(self._run_history_cache):
            return
        self._render_run(self._run_history_cache[row])
