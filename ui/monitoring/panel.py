"""Panel de Monitoreo (ADR-002, Fase 5 -- "lazo de mejora continua"):
lee la bitácora de conversaciones reales que escribe `interfaces/api/`
(Fase 2) en `runtime.db`, filtrable por acción, y permite promover
cualquiera de ellas a un caso de prueba del banco de calidad (Etapa 6)
sin salir de RAG STUDIO.

Pista C.1 del ADR-003 (docs proyecto/RAG_STUDIO_Propuesta_C1_Observabilidad.docx):
también muestra un resumen agregado de observabilidad básica (turnos
totales, latencia promedio, conteo por acción, tasa de abstención)
sobre una ventana configurable ("todo el histórico" / últimos 7-30-90
días) -- calculado por `RuntimeMonitoringService.get_metrics_summary`,
sin traer filas completas a esta capa.

Regla de capa: solo llama a application (monitoring_service). Nunca
importa domain ni infrastructure directamente (ADR-001, sección 4) --
el vocabulario de acción viene de application.conversational.options
(mismo catálogo que ya usa Calidad para "acción esperada"/"acción
prohibida"), y las categorías/severidades de application.quality.options.

A diferencia de Ingesta/Diseño conversacional/Calidad, esta pestaña no
necesita hilos en segundo plano: leer `runtime.db` es una lectura de
SQLite local, sin llamadas a embeddings ni red (mismo criterio que
Liberación). Si el proceso `interfaces/api/` nunca corrió contra esta
instalación, `runtime.db` simplemente no tiene filas todavía -- no es
un error, se muestra como lista vacía."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application.conversational.options import RULE_ACTION_OPTIONS
from application.quality.options import TEST_CATEGORY_OPTIONS, TEST_SEVERITY_OPTIONS
from application.runtime.options import FAILED_ACTION_OPTION
from ui.errors import describe_error

# Pista C.4a del ADR-003 (docs proyecto/
# RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx): canal
# operador -- solo RELEVANTE/IRRELEVANTE son juicios que un humano
# puede emitir revisando esta pestaña. CITADO_EN_RESPUESTA (señal de
# comportamiento del agente externo, no un juicio) queda fuera de este
# combo a propósito -- solo el canal HTTP puede reportarla (ver
# docstring de domain.runtime.entities.FeedbackSignal).
_FEEDBACK_SIGNAL_OPTIONS = [("Relevante", "relevante"), ("Irrelevante", "irrelevante")]

_TODAS_LABEL = "— todas —"

# Pista C.1 del ADR-003 (docs proyecto/RAG_STUDIO_Propuesta_C1_Observabilidad.docx):
# ventana configurable del resumen de métricas -- (etiqueta, días);
# días=None significa "todo el histórico del proyecto", no una fecha
# real (mismo criterio que ConversationMetricsSummary.since).
_WINDOW_OPTIONS: list[tuple[str, Optional[int]]] = [
    ("Todo el histórico", None),
    ("Últimos 7 días", 7),
    ("Últimos 30 días", 30),
    ("Últimos 90 días", 90),
]


class _PromoteToTestCaseDialog(QDialog):
    """Solo pide lo que la conversación real no puede rellenar por sí
    sola (código, categoría, severidad) -- consulta, intención
    esperada, acción esperada y fuente se copian de la conversación
    tal cual (ver RuntimeMonitoringService.promote_to_test_case)."""

    def __init__(self, entry, suggested_code: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Promover a caso de prueba")

        self._code = QLineEdit(suggested_code, self)
        self._category = QComboBox(self)
        self._category.addItems(TEST_CATEGORY_OPTIONS)
        if entry.action == "canalizar":
            self._category.setCurrentText("con_canalizacion")
        elif entry.action == "abstenerse":
            self._category.setCurrentText("sin_informacion")
        elif entry.action == FAILED_ACTION_OPTION and "error_tecnico" in TEST_CATEGORY_OPTIONS:
            self._category.setCurrentText("error_tecnico")
        self._severity = QComboBox(self)
        self._severity.addItems(TEST_SEVERITY_OPTIONS)
        self._severity.setCurrentText("media")

        form = QFormLayout()
        form.addRow("Código:", self._code)
        form.addRow("Categoría:", self._category)
        form.addRow("Severidad:", self._severity)
        form.addRow("Consulta (de la conversación):", QLabel(entry.message, self))
        form.addRow("Acción registrada:", QLabel(entry.action, self))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "code": self._code.text().strip(),
            "category": self._category.currentText(),
            "severity": self._severity.currentText(),
        }


class _MarkRetrievalFeedbackDialog(QDialog):
    """Pista C.4a del ADR-003 -- canal operador: marcar, para una
    fuente concreta ya mostrada en este turno real, si fue relevante o
    irrelevante. Más fino que "Promover a caso de prueba" (que juzga
    la conversación completa): no crea ningún TestCase, solo una señal
    de relevancia (`RetrievalFeedbackEntry`, origin=OPERADOR)."""

    def __init__(self, source_ids: list[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Marcar relevancia de una fuente")

        self._source = QComboBox(self)
        for source_id in source_ids:
            self._source.addItem(source_id, source_id)
        self._signal = QComboBox(self)
        for label, value in _FEEDBACK_SIGNAL_OPTIONS:
            self._signal.addItem(label, value)
        self._notes = QLineEdit(self)
        self._notes.setPlaceholderText("Opcional -- por qué se marcó así")

        form = QFormLayout()
        form.addRow("Fuente mostrada en este turno:", self._source)
        form.addRow("Señal:", self._signal)
        form.addRow("Notas:", self._notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "source_id": self._source.currentData(),
            "signal": self._signal.currentData(),
            "notes": self._notes.text().strip() or None,
        }


class _ConversationThreadDialog(QDialog):
    """Ronda 20: reconstruye una conversación completa (todos los
    turnos que comparten `conversation_id`, del más antiguo al más
    reciente) -- antes de esta ronda, `RuntimeMonitoringService.
    list_conversation_thread` (Ronda 19) existía en la capa de
    aplicación pero ningún botón de esta pestaña lo invocaba: el
    prefijo "conv:xxxxxxxx" de cada fila dejaba notar a simple vista
    qué filas compartían conversación, pero reconstruirla completa
    seguía exigiendo salir de RAG STUDIO. Este diálogo es solo lectura,
    sin acciones adicionales."""

    def __init__(self, entries: list, conversation_id: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Conversación completa — conv:{conversation_id[:8]}")
        self.resize(560, 420)

        text = QTextEdit(self)
        text.setReadOnly(True)
        lines = []
        for index, entry in enumerate(entries, start=1):
            lines.append(f"— Turno {index} — {entry.created_at:%Y-%m-%d %H:%M} — acción: {entry.action} —")
            lines.append(f"Usuario: {entry.message}")
            if entry.response_text:
                lines.append(f"Motor: {entry.response_text}")
            if entry.matched_intent:
                lines.append(f"(intención reconocida: {entry.matched_intent})")
            # Ronda 93: diagnóstico completo de un turno fallido.
            if entry.action == FAILED_ACTION_OPTION:
                lines.append(f"Categoría de error: {entry.error_category or 'unclassified'}")
                lines.append(f"Etapa: {entry.error_stage or 'desconocida'}  —  Código: {entry.error_code or '—'}")
                lines.append(f"Resumen: {entry.error_summary or '(sin resumen)'}")
                if entry.error_detail:
                    lines.append("Detalle técnico:")
                    lines.append(entry.error_detail)
            if getattr(entry, "trace_id", None):
                lines.append(f"Trace ID: {entry.trace_id}")
            lines.append("")
        text.setPlainText("\n".join(lines).strip())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(buttons)


class MonitoringPanel(QWidget):
    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None
        self._entries_cache: list = []

        layout = QVBoxLayout(self)

        metrics_box = QGroupBox("Observabilidad básica — resumen de la ventana seleccionada", self)
        metrics_layout = QVBoxLayout(metrics_box)
        metrics_row = QHBoxLayout()
        metrics_row.addWidget(QLabel("Ventana:", metrics_box))
        self._window_filter = QComboBox(metrics_box)
        for label, _days in _WINDOW_OPTIONS:
            self._window_filter.addItem(label)
        self._window_filter.currentIndexChanged.connect(self._refresh_metrics)
        metrics_row.addWidget(self._window_filter)
        metrics_row.addStretch(1)
        # Ronda 56: botón para ver, sin SQL manual, si ya se cumplen los
        # criterios de reapertura de la Ronda 45 (alertas proactivas /
        # aprendizaje del retrieval Opción 3) -- ver
        # RuntimeMonitoringService.evaluate_reopening_criteria().
        self._btn_reopening_criteria = QPushButton("Criterios de reapertura (Ronda 45)…", metrics_box)
        self._btn_reopening_criteria.clicked.connect(self._on_view_reopening_criteria)
        metrics_row.addWidget(self._btn_reopening_criteria)
        metrics_layout.addLayout(metrics_row)
        self._metrics_label = QLabel("(selecciona un proyecto para ver el resumen)", metrics_box)
        self._metrics_label.setWordWrap(True)
        metrics_layout.addWidget(self._metrics_label)
        layout.addWidget(metrics_box)

        form = QGroupBox("Conversaciones reales (runtime de producción)", self)
        form_layout = QVBoxLayout(form)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtrar por acción:", form))
        self._action_filter = QComboBox(form)
        self._action_filter.addItem(_TODAS_LABEL, None)
        for option in [*RULE_ACTION_OPTIONS, FAILED_ACTION_OPTION]:
            self._action_filter.addItem(option, option)
        self._action_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._action_filter)
        self._btn_refresh = QPushButton("Actualizar", form)
        self._btn_refresh.clicked.connect(self._refresh_conversations)
        filter_row.addWidget(self._btn_refresh)
        filter_row.addStretch(1)
        form_layout.addLayout(filter_row)

        self._conversation_list = QListWidget(form)
        self._conversation_list.itemSelectionChanged.connect(self._apply_button_states)
        form_layout.addWidget(self._conversation_list)

        row_actions = QHBoxLayout()
        self._btn_promote = QPushButton("Promover a caso de prueba…", form)
        self._btn_promote.clicked.connect(self._on_promote)
        row_actions.addWidget(self._btn_promote)
        self._btn_mark_feedback = QPushButton("Marcar relevancia de fuentes…", form)
        self._btn_mark_feedback.clicked.connect(self._on_mark_feedback)
        row_actions.addWidget(self._btn_mark_feedback)
        self._btn_view_thread = QPushButton("Ver conversación completa…", form)
        self._btn_view_thread.clicked.connect(self._on_view_thread)
        row_actions.addWidget(self._btn_view_thread)
        row_actions.addStretch(1)
        form_layout.addLayout(row_actions)

        layout.addWidget(form)
        self._apply_button_states()

    # ---------- wiring de proyecto activo ----------
    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._refresh_conversations()

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _apply_button_states(self) -> None:
        ready = self._project_id is not None
        self._window_filter.setEnabled(ready)
        self._btn_reopening_criteria.setEnabled(ready)
        self._action_filter.setEnabled(ready)
        self._btn_refresh.setEnabled(ready)
        self._conversation_list.setEnabled(ready)
        self._btn_promote.setEnabled(ready and self._conversation_list.currentRow() >= 0)
        self._btn_view_thread.setEnabled(ready and self._conversation_list.currentRow() >= 0)
        row = self._conversation_list.currentRow()
        has_sources = (
            ready and 0 <= row < len(self._entries_cache) and bool(self._entries_cache[row].source_ids)
        )
        self._btn_mark_feedback.setEnabled(has_sources)

    # ================= Observabilidad básica (Pista C.1) =================
    def _refresh_metrics(self) -> None:
        if not self._project_id:
            self._metrics_label.setText("(selecciona un proyecto para ver el resumen)")
            return
        _label, days = _WINDOW_OPTIONS[self._window_filter.currentIndex()]
        since = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None
        try:
            summary = self._context.monitoring_service.get_metrics_summary(self._project_id, since=since)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        if summary.total_turns == 0:
            self._metrics_label.setText("(sin conversaciones registradas en esta ventana)")
            return
        if summary.avg_latency_ms is not None:
            latencia = f"{summary.avg_latency_ms:.0f} ms"
        else:
            latencia = "sin datos"
        # Percentiles (Ronda 44, Pista C.5 del ADR-003): p95/p99 se
        # muestran junto al promedio -- "sin datos" con el mismo
        # criterio que avg_latency_ms (nunca 0 ms como valor falso).
        if summary.p95_latency_ms is not None:
            p95 = f"{summary.p95_latency_ms:.0f} ms"
        else:
            p95 = "sin datos"
        if summary.p99_latency_ms is not None:
            p99 = f"{summary.p99_latency_ms:.0f} ms"
        else:
            p99 = "sin datos"
        if summary.abstention_rate is not None:
            abstencion = f"{summary.abstention_rate:.0%}"
        else:
            abstencion = "sin datos"
        conteo_por_accion = ", ".join(
            f"{accion}: {conteo}" for accion, conteo in sorted(summary.turns_by_action.items())
        )
        texto = (
            f"Turnos totales: {summary.total_turns}  —  "
            f"Latencia promedio: {latencia} (p95: {p95}, p99: {p99})  —  "
            f"Tasa de abstención: {abstencion}\n"
            f"Por acción: {conteo_por_accion}"
        )
        if summary.failed_turns:
            texto += (
                f"\nTurnos fallidos (error técnico): {summary.failed_turns} "
                f"({(summary.failure_rate or 0):.0%}) -- filtra por acción 'fallo' para ver la causa"
            )
        texto += f"\n{self._feedback_summary_line(since)}"
        self._metrics_label.setText(texto)

    def _feedback_summary_line(self, since: Optional[datetime]) -> str:
        # Pista C.4a del ADR-003 -- vista agregada de las señales de
        # relevancia ya capturadas (canal operador + canal del agente
        # externo), junto al resto de observabilidad básica. Si este
        # RuntimeMonitoringService se construyó sin feedback_repository
        # (p. ej. en algún contexto de pruebas que no lo necesite), se
        # omite la línea en silencio en vez de romper el resto del
        # resumen.
        try:
            feedback_summary = self._context.monitoring_service.get_retrieval_feedback_summary(
                self._project_id, since=since,
            )
        except RuntimeError:
            return ""
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return ""
        if feedback_summary.total_entries == 0:
            return "Señales de relevancia: (ninguna registrada en esta ventana)"
        por_senal = ", ".join(
            f"{senal}: {conteo}" for senal, conteo in sorted(feedback_summary.counts_by_signal.items())
        )
        por_origen = ", ".join(
            f"{origen}: {conteo}" for origen, conteo in sorted(feedback_summary.counts_by_origin.items())
        )
        return (
            f"Señales de relevancia: {feedback_summary.total_entries} total "
            f"({por_senal}) — origen: {por_origen}"
        )

    # ================= Ronda 56: criterios de reapertura (Ronda 45) =================
    def _on_view_reopening_criteria(self) -> None:
        """Muestra, sin necesitar una consulta SQL manual sobre el
        project.db/runtime.db real (lo que hasta la Ronda 56 exigía
        cada ronda de consultoría, ver Rondas 43/45/50), si ya se
        cumplen los criterios de reapertura de la Ronda 45 para los dos
        pendientes de RAG 5 diferidos por falta de evidencia de uso
        real: alertas proactivas de observabilidad, y el ajuste
        automático del retrieval (aprendizaje, Opción 3). Cumplirlos no
        obliga a construir nada -- solo señala que ya vale la pena
        volver a preguntar (ver domain.runtime.entities.
        ReopeningCriteriaStatus)."""
        if not self._project_id:
            return
        try:
            status = self._context.monitoring_service.evaluate_reopening_criteria(self._project_id)
        except RuntimeError as exc:
            QMessageBox.information(self, "Criterios de reapertura", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return

        def _marca(cumplida: bool) -> str:
            return "✓ cumplida" if cumplida else "✗ no cumplida"

        texto = (
            "Alertas proactivas de observabilidad (Ronda 45):\n"
            f"  • Proyecto liberado: {_marca(status.proyecto_liberado)}\n"
            f"  • Token de widget activo: {_marca(status.token_widget_activo)}\n"
            f"  • Turnos en los últimos 30 días: {status.turnos_ultimos_30_dias} "
            f"(se requieren 50)\n"
            f"  → {'LISTO PARA RECONSIDERAR' if status.alertas_proactivas_reunidas else 'todavía no'}\n"
            "\n"
            "Aprendizaje del retrieval, Opción 3 (Ronda 45):\n"
            f"  • Entradas de retroalimentación totales: {status.entradas_feedback_totales} "
            "(se requieren 100)\n"
            f"  • Fuentes distintas: {status.fuentes_distintas_en_feedback} (se requieren 10)\n"
            f"  • Días desde la primera entrada: "
            f"{status.dias_desde_la_primera_entrada if status.dias_desde_la_primera_entrada is not None else 'sin datos'} "
            "(se requieren 30)\n"
            f"  → {'LISTO PARA RECONSIDERAR' if status.aprendizaje_opcion3_reunidas else 'todavía no'}\n"
            "\n"
            "Cumplir estos criterios no obliga a construir nada -- solo indica que ya "
            "hay evidencia real suficiente para volver a preguntar."
        )
        QMessageBox.information(self, "Criterios de reapertura (Ronda 45)", texto)

    # ================= Conversaciones =================
    def _on_filter_changed(self) -> None:
        self._refresh_conversations()

    def _refresh_conversations(self) -> None:
        self._conversation_list.clear()
        self._entries_cache = []
        self._refresh_metrics()
        if not self._project_id:
            self._apply_button_states()
            return
        action = self._action_filter.currentData()
        try:
            self._entries_cache = self._context.monitoring_service.list_conversations(
                self._project_id, action=action,
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            self._apply_button_states()
            return
        if not self._entries_cache:
            self._conversation_list.addItem("(sin conversaciones registradas todavía)")
            self._conversation_list.setEnabled(False)
        else:
            self._conversation_list.setEnabled(True)
            for entry in self._entries_cache:
                intent = entry.matched_intent or "(sin intención)"
                # conv:{...} (Ronda 19): primeros 8 caracteres de
                # conversation_id -- suficiente para notar a simple
                # vista qué filas pertenecen a la misma conversación
                # (varios turnos consecutivos comparten el mismo
                # prefijo) sin alargar demasiado cada línea de la lista.
                accion = entry.action
                if entry.action == FAILED_ACTION_OPTION:
                    # Ronda 93: la causa del fallo, visible en la propia fila.
                    accion = f"fallo [{entry.error_category or 'unclassified'} · {entry.error_stage or 'desconocida'}]"
                self._conversation_list.addItem(
                    f"{entry.created_at:%Y-%m-%d %H:%M} — conv:{entry.conversation_id[:8]} — "
                    f"{accion} — {intent} — {entry.message}"
                )
        self._apply_button_states()

    # ================= Ver conversación completa (Ronda 20) =================
    def _on_view_thread(self) -> None:
        row = self._conversation_list.currentRow()
        if self._project_id is None or row < 0 or row >= len(self._entries_cache):
            return
        entry = self._entries_cache[row]
        try:
            thread = self._context.monitoring_service.list_conversation_thread(
                self._project_id, entry.conversation_id,
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        dialog = _ConversationThreadDialog(thread, entry.conversation_id, self)
        dialog.exec()

    # ================= Promoción a caso de prueba =================
    def _on_promote(self) -> None:
        row = self._conversation_list.currentRow()
        if self._project_id is None or row < 0 or row >= len(self._entries_cache):
            return
        entry = self._entries_cache[row]
        suggested_code = f"MON-{entry.id[:8]}"
        dialog = _PromoteToTestCaseDialog(entry, suggested_code, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["code"]:
            QMessageBox.warning(self, "Falta código", "El caso de prueba necesita un código.")
            return
        try:
            test_case = self._context.monitoring_service.promote_to_test_case(
                self._project_id, entry.id, values["code"], values["category"], severity=values["severity"],
            )
        except Exception as exc:  # noqa: BLE001 - incluye código duplicado
            self._report_error(exc)
            return
        QMessageBox.information(
            self, "Caso de prueba creado",
            f"Se creó el caso {test_case.code!r} en el banco de pruebas (pestaña Calidad).",
        )

    # ================= Señal de relevancia -- canal operador (Pista C.4a) =================
    def _on_mark_feedback(self) -> None:
        row = self._conversation_list.currentRow()
        if self._project_id is None or row < 0 or row >= len(self._entries_cache):
            return
        entry = self._entries_cache[row]
        if not entry.source_ids:
            QMessageBox.information(
                self, "Sin fuentes", "Este turno no muestra ninguna fuente recuperada -- nada que marcar.",
            )
            return
        dialog = _MarkRetrievalFeedbackDialog(entry.source_ids, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self._context.monitoring_service.record_retrieval_feedback(
                self._project_id, entry.id, values["source_id"], values["signal"], notes=values["notes"],
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_metrics()
        QMessageBox.information(self, "Señal registrada", "Se guardó la señal de relevancia.")
