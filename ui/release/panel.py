"""Panel de Liberación (Etapa 7): compuertas de avance, dictamen y
entregables formales sobre los seis contextos anteriores (metadatos,
fragmentación, pipeline, índice, diseño conversacional, calidad).

Regla de capa: solo llama a application (release_service). Nunca
importa domain ni infrastructure directamente (ADR-001, sección 4) --
el vocabulario de estado viene de application.release.options. Los
objetos que devuelve release_service (ReleaseChecklist, ReleaseRecord)
se leen solo por sus atributos, sin importarlos.

Evaluar compuertas y solicitar una liberación son solo lecturas de
repositorios ya existentes (sin llamadas a embeddings/red), así que se
ejecutan de forma síncrona -- eso sigue siendo cierto. "Publicar
instantánea…" y "Exportar paquete de entrega al cliente…" (ver abajo)
YA NO lo son: copian/comprimen todo `projects/<project_id>` (incluidos
los documentos originales y el índice Qdrant), potencialmente cientos
de MB, en el hilo de la interfaz. La auditoría Ronda 10 (hallazgo B13,
ver Validacion_observaciones_RAG_STUDIO.md) señala esto como deuda
pendiente -- moverlas a `jobs`/hilos en segundo plano, como el resto
de la app, queda para una ronda futura; por ahora al menos se muestra
un cursor de espera para que la ventana no parezca congelada sin
ninguna señal.

"Publicar instantánea…" (ADR-002, Fase 1) copia project.db + índice
Qdrant a un directorio de solo lectura versionado, separado de
projects/<project_id> -- primer paso hacia un futuro runtime de
producción que no debe competir con esta misma app por el lock
exclusivo que Qdrant toma sobre su directorio de índice. Deliberadamente
independiente de solicitar una liberación formal.

"Exportar paquete de entrega al cliente…" (Ronda 10, ver
Validacion_observaciones_RAG_STUDIO.md) empaqueta en un solo .zip la
última instantánea publicada, un token de widget nuevo (acotado a
este proyecto), el snippet de embebido y una guía de despliegue + un
informe formal -- para entregarle a quien vaya a operar el runtime de
producción por cuenta del cliente. Requiere que ya se haya publicado
al menos una instantánea (mismo requisito que mostrar la lista de
instantáneas); a diferencia de "Exportar entregables…", no depende de
ninguna liberación mostrada en `_report`."""
from __future__ import annotations

from html import escape as html_escape
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui.theme import aplicar_color_estado_item, estado_html
from ui.errors import describe_error

_STATUS_LABELS = {
    "no_iniciada": "No iniciada",
    "en_preparacion": "En preparación",
    "en_ejecucion": "En ejecución",
    "en_revision": "En revisión",
    "aprobada": "Aprobada",
    "rechazada": "Rechazada",
    "bloqueada": "Bloqueada",
    "sustituida": "Sustituida",
}


class ReleasePanel(QWidget):
    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None
        self._history_cache: list = []
        self._selected_record = None
        """La última ReleaseRecord mostrada en `_report` (recién
        solicitada o abierta del historial) -- lo que "Exportar
        entregables" empaqueta (ítem 6 de la evaluación de madurez
        post-8-etapas). Se guarda el objeto tal cual (se lee solo por
        atributos, igual criterio que el resto del panel)."""

        layout = QVBoxLayout(self)

        form = QGroupBox("Compuertas de liberación", self)
        form_layout = QVBoxLayout(form)
        action_row = QHBoxLayout()
        self._btn_evaluate = QPushButton("Evaluar compuertas", form)
        self._btn_evaluate.clicked.connect(self._on_evaluate_gates)
        self._btn_request = QPushButton("Solicitar liberación", form)
        self._btn_request.clicked.connect(self._on_request_release)
        action_row.addWidget(self._btn_evaluate)
        action_row.addWidget(self._btn_request)
        form_layout.addLayout(action_row)
        # Paquete exportable de entregables (ítem 6 de la evaluación de
        # madurez post-8-etapas): antes, los 8 entregables formales
        # solo existían como JSON en línea dentro del registro de
        # liberación -- sin archivos reales que compartir fuera de la
        # app. Actúa sobre la liberación que se esté mostrando en
        # `_report` (recién solicitada, o abierta desde el historial).
        self._btn_export_package = QPushButton("Exportar entregables…", form)
        self._btn_export_package.clicked.connect(self._on_export_package)
        # Auditoría posterior a la Ronda 77 (hallazgo real de usuario en
        # otra confusión de "Importar…"): estos tres botones comparten
        # vocabulario ("entregables"/"entrega") pero cada uno depende de
        # una precondición distinta y produce un archivo distinto -- se
        # agregan tooltips para no repetir el mismo tipo de confusión.
        self._btn_export_package.setToolTip(
            "Exporta el registro de ESTA liberación (la mostrada abajo, recién solicitada o abierta "
            "del historial con doble clic): el dictamen, el diseño conversacional y los resultados de "
            "evaluación en un .zip. No incluye el índice de búsqueda ni un runtime desplegable."
        )
        form_layout.addWidget(self._btn_export_package)
        # Publicar instantánea (ADR-002, Fase 1): copia de solo lectura de
        # project.db + índice Qdrant a un directorio versionado, separado
        # de projects/<project_id> -- para un futuro runtime de producción
        # que no debe competir con esta misma app por el lock exclusivo de
        # Qdrant. Deliberadamente independiente de "Solicitar liberación":
        # no requiere haber evaluado ni aprobado ninguna compuerta (mismo
        # criterio que Exportar proyecto/Generar respaldo en Proyectos).
        # Si hay una liberación mostrada en `_report`, su id se guarda
        # como referencia opcional de trazabilidad.
        self._btn_publish_snapshot = QPushButton("Publicar instantánea…", form)
        self._btn_publish_snapshot.clicked.connect(self._on_publish_snapshot)
        self._btn_publish_snapshot.setToolTip(
            "Copia de solo lectura de la base de datos y el índice de búsqueda del proyecto a una "
            "carpeta versionada -- no exporta ningún archivo ni pide dónde guardarlo. No requiere "
            "ninguna liberación aprobada. Es el paso previo obligatorio para \"Exportar paquete de "
            "entrega al cliente…\": sin al menos una instantánea publicada, ese botón fallará con un "
            "error explicando esto mismo."
        )
        form_layout.addWidget(self._btn_publish_snapshot)
        # Paquete de entrega al cliente (Ronda 10): distinto de "Exportar
        # entregables…" -- no depende de ninguna liberación mostrada en
        # _report, solo de que exista una instantánea publicada.
        self._btn_export_deployment = QPushButton("Exportar paquete de entrega al cliente…", form)
        self._btn_export_deployment.clicked.connect(self._on_export_deployment_package)
        self._btn_export_deployment.setToolTip(
            "Exporta un .zip listo para desplegar: la instantánea publicada más reciente, un token "
            "de widget nuevo, el snippet de embebido, la guía de despliegue y el informe formal. "
            "Requiere haber publicado al menos una instantánea con \"Publicar instantánea…\" -- no "
            "depende de ninguna liberación del historial."
        )
        form_layout.addWidget(self._btn_export_deployment)
        layout.addWidget(form)

        self._report = QTextBrowser(self)
        self._report.setReadOnly(True)
        layout.addWidget(self._report)

        history_label = QLabel("Historial de liberaciones (más reciente primero):", self)
        layout.addWidget(history_label)
        self._history_list = QListWidget(self)
        self._history_list.itemDoubleClicked.connect(self._on_open_history_record)
        layout.addWidget(self._history_list)

        snapshots_label = QLabel("Instantáneas publicadas (más reciente primero):", self)
        layout.addWidget(snapshots_label)
        self._snapshots_list = QListWidget(self)
        layout.addWidget(self._snapshots_list)

        self._apply_button_states()

    # ---------- wiring de proyecto activo ----------
    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._report.setHtml("")
        self._selected_record = None
        self._refresh_history()
        self._refresh_snapshots()
        self._apply_button_states()

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _apply_button_states(self) -> None:
        ready = self._project_id is not None
        self._btn_evaluate.setEnabled(ready)
        self._btn_request.setEnabled(ready)
        self._history_list.setEnabled(ready)
        self._btn_export_package.setEnabled(ready and self._selected_record is not None)
        self._btn_publish_snapshot.setEnabled(ready)
        self._btn_export_deployment.setEnabled(ready)

    # ================= Compuertas =================
    def _on_evaluate_gates(self) -> None:
        if not self._project_id:
            return
        try:
            checklist = self._context.release_service.evaluate_gates(self._project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._render_checklist(checklist)

    def _render_checklist(self, checklist) -> None:
        parts = [
            f"<p><b>{'Todas las compuertas se cumplen.' if checklist.all_passed else 'Hay compuertas sin cumplir.'}</b></p>"
        ]
        for gate in checklist.gates:
            marca = estado_html("✔", "exitoso") if gate.passed else estado_html("✘", "fallido")
            parts.append(f"<p>[{marca}] <b>{html_escape(gate.name)}</b> — {html_escape(gate.reason)}</p>")
        self._report.setHtml("".join(parts))

    # ================= Solicitud de liberación =================
    def _on_request_release(self) -> None:
        if not self._project_id:
            return
        try:
            record = self._context.release_service.request_release(self._project_id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._selected_record = record
        self._render_record(record)
        self._refresh_history()
        self._apply_button_states()

    def _render_record(self, record) -> None:
        estado = _STATUS_LABELS.get(record.status.value, record.status.value)
        # estado_html ya escapa `texto` internamente (ver ui/theme.py) --
        # no hace falta escaparlo aquí también.
        estado_text = estado_html(estado, record.status.value)
        parts = [
            f"<p><b>Liberación {record.id}</b> — estado: <b>{estado_text}</b></p>",
            f"<p>{html_escape(record.dictamen)}</p>",
            "<p><b>Compuertas evaluadas:</b></p>",
        ]
        for gate in record.checklist.gates:
            marca = estado_html("✔", "exitoso") if gate.passed else estado_html("✘", "fallido")
            parts.append(f"<p>[{marca}] <b>{html_escape(gate.name)}</b> — {html_escape(gate.reason)}</p>")
        if record.evidence:
            parts.append("<p><b>Evidencia (versiones congeladas):</b></p>")
            for key, value in record.evidence.items():
                parts.append(f"<p style='margin-left:20px;'>{html_escape(key)}: {html_escape(str(value))}</p>")
        self._report.setHtml("".join(parts))

    # ================= Historial =================
    def _refresh_history(self) -> None:
        self._history_list.clear()
        self._history_cache = []
        if not self._project_id:
            return
        self._history_cache = self._context.release_service.list_release_records(self._project_id)
        for record in self._history_cache:
            estado = _STATUS_LABELS.get(record.status.value, record.status.value)
            self._history_list.addItem(f"{record.created_at:%Y-%m-%d %H:%M} — {estado}")
            aplicar_color_estado_item(
                self._history_list.item(self._history_list.count() - 1), record.status.value,
            )

    def _on_open_history_record(self, _item) -> None:
        row = self._history_list.currentRow()
        if row < 0 or row >= len(self._history_cache):
            return
        self._selected_record = self._history_cache[row]
        self._render_record(self._selected_record)
        self._apply_button_states()

    # ================= Paquete exportable de entregables =================
    def _on_export_package(self) -> None:
        if self._project_id is None or self._selected_record is None:
            QMessageBox.warning(
                self, "Falta información",
                "Solicita una liberación o abre una del historial primero (doble clic).",
            )
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar entregables", filter="*.zip")
        if not path:
            return
        try:
            result_path = self._context.release_service.export_deliverables_package(
                self._project_id, self._selected_record.id, path,
            )
        except Exception as exc:  # noqa: BLE001 - incluye release_packager no configurado
            self._report_error(exc)
            return
        QMessageBox.information(self, "Exportado", f"Paquete de entregables exportado a {result_path}.")

    # ================= Instantáneas publicadas (ADR-002, Fase 1) =================
    def _on_publish_snapshot(self) -> None:
        if self._project_id is None:
            return
        source_release_id = self._selected_record.id if self._selected_record is not None else None
        # Cursor de espera (auditoría Ronda 10, hallazgo B13): esta
        # operación copia todo projects/<project_id> (documentos
        # originales + índice Qdrant) de forma síncrona en el hilo de
        # la interfaz -- con un proyecto grande puede tardar y, sin
        # ninguna señal, la ventana parece congelada. Mover esto a un
        # hilo en segundo plano (como el resto de la app) queda para
        # una ronda futura; esto es la mitigación mínima mientras tanto.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            snapshot = self._context.release_service.publish_snapshot(self._project_id, source_release_id)
        except Exception as exc:  # noqa: BLE001 - incluye dependencias de instantáneas no configuradas
            self._report_error(exc)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_snapshots()
        QMessageBox.information(
            self, "Instantánea publicada",
            f"Versión {snapshot.version} publicada en:\n{snapshot.snapshot_dir}",
        )

    def _refresh_snapshots(self) -> None:
        self._snapshots_list.clear()
        if not self._project_id:
            return
        snapshots = self._context.release_service.list_snapshots(self._project_id)
        for snapshot in snapshots:
            etiqueta = f"{snapshot.created_at:%Y-%m-%d %H:%M} — v{snapshot.version} — {snapshot.snapshot_dir}"
            self._snapshots_list.addItem(etiqueta)

    # ================= Paquete de entrega al cliente (Ronda 10) =================
    def _on_export_deployment_package(self) -> None:
        if self._project_id is None:
            return
        # Ronda 92: nombre sugerido con la versión que se va a entregar,
        # para que quien despliega sepa qué versión debe servir el runtime.
        snapshots = self._context.release_service.list_snapshots(self._project_id)
        version = max((s.version for s in snapshots), default=None)
        sugerido = f"entrega_cliente_{self._project_id}_v{version}.zip" if version else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar paquete de entrega al cliente", sugerido, filter="*.zip",
        )
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        # Cursor de espera (auditoría Ronda 10, hallazgo B13): comprime
        # la instantánea completa -- misma justificación que en
        # _on_publish_snapshot.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result_path = self._context.release_service.export_deployment_package(self._project_id, path)
        except Exception as exc:  # noqa: BLE001 - incluye "no hay instantánea publicada"
            self._report_error(exc)
            return
        finally:
            QApplication.restoreOverrideCursor()
        QMessageBox.information(
            self, "Paquete exportado",
            f"Paquete de entrega al cliente exportado a:\n{result_path}\n\n"
            "Incluye la instantánea publicada"
            + (f" (versión {version})" if version else "")
            + ", un token de widget nuevo, el snippet de embebido, la guía de despliegue "
            "y el informe formal de la entrega.\n\nAl desplegar: RAGSTUDIO_SNAPSHOT_DIR debe apuntar a la "
            "carpeta 'instantanea' del paquete extraído (ver GUIA_DESPLIEGUE.md).",
        )
