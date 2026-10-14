"""Ventana principal: ensambla las pestañas de Proyectos, Fuentes,
Metadatos, Ingesta, Diseño conversacional, Calidad, Liberación,
Monitoreo y Complementos (Etapas 1-8 del documento maestro, más el
lazo de mejora continua de ADR-002, Fase 5).

Regla de capa (ADR-001, sección 4): esta ventana y sus paneles solo
llaman a application (project_service, document_service,
metadata_service, ingestion_service, conversational_service,
quality_service, release_service, monitoring_service, plugin_service,
jobs). Nunca importan domain ni infrastructure directamente, y nunca
ejecutan trabajo pesado en el hilo de la interfaz.

El proyecto activo se propaga con la señal
ProjectsPanel.project_selected -> SourcesPanel/MetadataPanel/
IngestionPanel/ConversationalPanel/QualityPanel/ReleasePanel/
MonitoringPanel.set_active_project. La fuente activa se propaga con
SourcesPanel.source_selected -> IngestionPanel.set_active_source, así
que Ingesta siempre opera sobre la fuente elegida en la pestaña
Fuentes dentro del proyecto elegido en la pestaña Proyectos. Diseño
conversacional, Calidad, Liberación y Monitoreo operan a nivel de
proyecto completo (como el pipeline reproducible en Ingesta), no de
una fuente en particular -- Monitoreo lee `runtime.db` (bitácora real
de `interfaces/api/`, ADR-002 Fase 2) filtrado por ese mismo
project_id. Complementos es la única pestaña que no depende de ningún
proyecto activo: el registro de complementos es global a la
instalación (`application.db`), no por proyecto -- por eso no está
conectada a `project_selected`.

SourcesPanel.sources_changed -> IngestionPanel.refresh_document_type_options
(Ronda 4, punto 4b): antes, los combos de document_type_code de Ingesta
solo se refrescaban al cambiar de proyecto activo -- un tipo de
documento nuevo (o corregido en bloque) capturado en Fuentes no
aparecía en Ingesta hasta salir y volver a entrar al proyecto.

SourcesPanel.sources_changed -> MetadataPanel.refresh_value_source_selector
(Ronda 5, hallazgo real de usuario en video): mismo síntoma que el
anterior pero en "Metadatos > Valores por fuente" -- el selector de
fuentes solo se refrescaba al llamar set_active_project, así que
importar o registrar fuentes nuevas en la misma sesión dejaba el
selector vacío/desactualizado hasta reiniciar la aplicación.

MetadataPanel.schema_changed -> ConversationalPanel.refresh_metadata_fields
(Ronda 79, hallazgo real de usuario): mismo síntoma otra vez, ahora en
Diseño conversacional > Variables, selector "Campo de metadatos
ligado" -- crear el esquema o agregarle campos después de seleccionar
el proyecto activo dejaba ese selector mostrando solo "— ninguno —"
hasta salir y volver a entrar al proyecto.

El título de la ventana se mantiene simple ("RAG STUDIO") a propósito:
enumerar cada etapa completada ahí dejó de ser práctico en cuanto se
cerró el ciclo completo de las 8 etapas del documento maestro; ese
detalle vive en el README (bitácora) y en las pestañas mismas, no en la
barra de título.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from ui.conversational.panel import ConversationalPanel
from ui.ingestion.panel import IngestionPanel
from ui.metadata.panel import MetadataPanel
from ui.monitoring.panel import MonitoringPanel
from ui.plugins.panel import PluginsPanel
from ui.quality.panel import QualityPanel
from ui.release.panel import ReleasePanel
from ui.sources.panel import SourcesPanel

from .panel import ProjectsPanel
from ui.errors import describe_error


class MainWindow(QMainWindow):
    def __init__(self, app_context):
        super().__init__()
        self._context = app_context

        self.setWindowTitle("RAG STUDIO")
        self.resize(900, 600)

        self._projects_panel = ProjectsPanel(app_context, self)
        self._sources_panel = SourcesPanel(app_context, self)
        self._metadata_panel = MetadataPanel(app_context, self)
        self._ingestion_panel = IngestionPanel(app_context, self)
        self._conversational_panel = ConversationalPanel(app_context, self)
        self._quality_panel = QualityPanel(app_context, self)
        self._release_panel = ReleasePanel(app_context, self)
        self._monitoring_panel = MonitoringPanel(app_context, self)
        self._plugins_panel = PluginsPanel(app_context, self)

        tabs = QTabWidget(self)
        tabs.addTab(self._projects_panel, "Proyectos")
        tabs.addTab(self._sources_panel, "Fuentes")
        tabs.addTab(self._metadata_panel, "Metadatos")
        tabs.addTab(self._ingestion_panel, "Ingesta")
        tabs.addTab(self._conversational_panel, "Diseño conversacional")
        tabs.addTab(self._quality_panel, "Calidad")
        tabs.addTab(self._release_panel, "Liberación")
        tabs.addTab(self._monitoring_panel, "Monitoreo")
        tabs.addTab(self._plugins_panel, "Complementos")
        self.setCentralWidget(tabs)

        self._projects_panel.project_selected.connect(self._sources_panel.set_active_project)
        self._projects_panel.project_selected.connect(self._metadata_panel.set_active_project)
        self._projects_panel.project_selected.connect(self._ingestion_panel.set_active_project)
        self._projects_panel.project_selected.connect(self._conversational_panel.set_active_project)
        self._projects_panel.project_selected.connect(self._quality_panel.set_active_project)
        self._projects_panel.project_selected.connect(self._release_panel.set_active_project)
        self._projects_panel.project_selected.connect(self._monitoring_panel.set_active_project)
        self._sources_panel.source_selected.connect(self._ingestion_panel.set_active_source)
        self._sources_panel.sources_changed.connect(self._ingestion_panel.refresh_document_type_options)
        self._sources_panel.sources_changed.connect(self._metadata_panel.refresh_value_source_selector)
        self._metadata_panel.schema_changed.connect(self._conversational_panel.refresh_metadata_fields)

        # Menú "Ayuda" -> "Exportar diagnóstico" (ítem 5 de la segunda
        # evaluación de madurez post-8-etapas, ver bitácora en README):
        # no depende de ningún proyecto activo, igual que Complementos,
        # así que vive en la barra de menú en vez de en una pestaña.
        help_menu = self.menuBar().addMenu("Ayuda")
        export_diagnostics_action = help_menu.addAction("Exportar diagnóstico…")
        export_diagnostics_action.triggered.connect(self._on_export_diagnostics)

    def closeEvent(self, event) -> None:  # noqa: N802 - nombre exigido por Qt
        # Auditoría profunda (ronda posterior a la 76, hallazgo O): antes
        # cerrar la ventana mientras un ThreadJobRunner.submit(...) seguía
        # corriendo (una ingesta, una reindexación, una simulación) lo
        # abandonaba en silencio -- los hilos de trabajo son
        # `daemon=True`, así que el proceso termina de inmediato sin
        # esperar a que el trabajo acabe ni avisar que quedó a medias.
        # Esto no cancela ni espera el trabajo (ThreadJobRunner no ofrece
        # una espera bloqueante de la UI para eso, y bloquear el cierre
        # indefinidamente sería peor); solo le da al usuario la
        # oportunidad de cancelar el cierre y esperar a que termine por su
        # cuenta, en vez de que la app desaparezca sin ningún aviso.
        if self._context.jobs.any_running():
            confirm = QMessageBox.question(
                self,
                "Trabajo en curso",
                "Todavía hay al menos un trabajo en segundo plano en curso (por ejemplo, una "
                "ingesta, una reindexación o una simulación). Si cierras ahora, ese trabajo se "
                "interrumpe sin completarse.\n\n¿Cerrar la aplicación de todas formas?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()

    def _on_export_diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar diagnóstico", filter="*.zip")
        if not path:
            return
        try:
            result_path = self._context.diagnostics.export_diagnostics_package(path)
        except Exception as exc:  # noqa: BLE001 - cualquier fallo al escribir el .zip
            QMessageBox.critical(self, "Error", describe_error(exc))
            return
        QMessageBox.information(
            self, "Diagnóstico exportado",
            f"Se exportó un paquete de diagnóstico (registros + información del entorno) a:\n{result_path}\n\n"
            "Puedes adjuntarlo a un correo o ticket de soporte.",
        )
