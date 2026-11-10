"""Ronda 99 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
ventana de solo lectura con el detalle de un fragmento guardado.

Todo se muestra como TEXTO PLANO (QPlainTextEdit de solo lectura): el
contenido de un fragmento nunca se interpreta como HTML ni como
instrucciones, se conservan los saltos de línea y caracteres especiales, y
se puede seleccionar y copiar. La ventana solo LEE (IngestionService.
get_chunk_detail): no modifica el fragmento ni dispara re-indexación.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

_ESTADO_CONTEXTO = {
    "derivado": "derivado del texto extraído de la fuente",
    "sin_encabezados": "el texto extraído no tiene encabezados Markdown",
    "sin_extraccion": "la fuente no tiene texto extraído guardado",
    "no_localizado": "el texto del fragmento no se encontró tal cual en el texto extraído "
                     "(la fuente pudo volver a extraerse después de fragmentar)",
    "no_aplica": "el fragmento no proviene de un encabezado (estrategia sin secciones)",
}


def _ref(ref) -> str:
    if ref is None:
        return "—"
    if not ref.found:
        return f"{ref.id} (ya no existe en esta fuente)"
    titulo = f" «{ref.section_title}»" if ref.section_title else ""
    return f"[{ref.chunk_index}]{titulo} — {ref.id}"


def format_chunk_detail(detail) -> dict[str, str]:
    """Secciones de texto plano de la ventana: 'texto', 'propiedades',
    'metadatos' y 'contexto'. Función pura para poder probarla sin Qt."""
    c = detail.chunk
    paginas = (
        f"{c.page_start}–{c.page_end}" if c.page_start is not None and c.page_end not in (None, c.page_start)
        else (str(c.page_start) if c.page_start is not None else "—")
    )
    fuente = detail.source_title
    if detail.source_position is not None:
        fuente = f"{detail.source_position} de {detail.source_count} — {detail.source_title}"
    propiedades = "\n".join([
        f"Identificador del fragmento: {c.id}",
        f"Fuente: {fuente}",
        f"Identificador de la fuente: {detail.source_id}",
        f"Tipo documental de la fuente: {detail.source_document_type_code or '—'}",
        f"Índice del fragmento: {c.chunk_index}",
        f"Tipo de fragmento: {getattr(c.chunk_type, 'value', c.chunk_type)}",
        f"Tokens: {c.token_count}",
        f"Título de sección: {c.section_title or '—'}",
        f"Páginas: {paginas}",
        f"Fragmento padre: {_ref(detail.parent)}",
        f"Fragmento anterior: {_ref(detail.previous)}",
        f"Fragmento siguiente: {_ref(detail.next)}",
        f"Caracteres: {len(c.text)}",
        f"Indexación: {'sí' if detail.indexable else 'no'} — {detail.indexable_reason}",
        f"Versión de pipeline: {c.pipeline_version}",
        f"Creado: {c.created_at:%Y-%m-%d %H:%M:%S}",
    ])
    if detail.inherited_metadata:
        lineas = []
        for m in detail.inherited_metadata:
            nombre = f"{m.display_name} ({m.field_id})" if m.display_name else m.field_id
            if m.multiple:
                lineas.append(f"{nombre} — {len(m.values)} valor(es):")
                lineas.extend(f"    • {v}" for v in m.values)
                lineas.append(f"    representación original: {m.raw_value}")
            else:
                lineas.append(f"{nombre}: {m.raw_value}")
        metadatos = "\n".join(lineas)
    else:
        metadatos = "Este fragmento no hereda metadatos (ningún campo del esquema tiene \"Heredar a fragmentos\" con valor en la fuente)."
    estado = _ESTADO_CONTEXTO.get(detail.heading_context_status, detail.heading_context_status)
    stored = getattr(detail, "stored_section_path", []) or []
    contexto = ["1) RUTA RECONSTRUIDA PARA DIAGNÓSTICO (derivada del texto extraído; no se guarda)", f"Estado: {estado}."]
    if detail.heading_path:
        for nivel, titulo in zip(detail.heading_path_levels, detail.heading_path, strict=True):
            contexto.append(f"{'  ' * (nivel - 1)}{'#' * nivel} {titulo}")
        if detail.heading_context_missing:
            contexto.append("El TEXTO del fragmento no contiene estos encabezados superiores:")
            contexto.extend(f"    • {t}" for t in detail.heading_context_missing)
        else:
            contexto.append("El texto del fragmento contiene todos los encabezados de su ruta.")
    # Ronda 100: ruta almacenada en el fragmento y su uso real en la búsqueda.
    contexto += ["", "2) RUTA ALMACENADA EN EL FRAGMENTO (Chunk.section_path)"]
    if stored:
        for nivel, titulo in zip(detail.stored_section_levels, stored, strict=True):
            contexto.append(f"{'  ' * (nivel - 1)}{'#' * nivel} {titulo}")
        if detail.stored_matches_derived is True:
            contexto.append("Coincide con la ruta reconstruida.")
        elif detail.stored_matches_derived is False:
            contexto.append("NO coincide con la ruta reconstruida: la fuente pudo volver a extraerse después de "
                            "fragmentar; conviene volver a fragmentarla.")
    else:
        contexto.append("Sin ruta almacenada: el fragmento se generó antes de la Ronda 100 o con una estrategia sin "
                        "encabezados. Vuelva a fragmentar la fuente (o ejecute el pipeline) para guardarla.")
    contexto += ["", "3) INFORMACIÓN JERÁRQUICA QUE USA LA BÚSQUEDA"]
    if detail.retrieval_hierarchy_active:
        contexto.append("Señal jerárquica de la búsqueda híbrida: ACTIVA (el fragmento se indexa y tiene ruta).")
    else:
        contexto.append("Señal jerárquica de la búsqueda híbrida: inactiva"
                        + (" (el fragmento no se indexa)." if stored else " (sin ruta almacenada)."))
    contexto.append("Encabezados superiores que la búsqueda textual agrega al texto: "
                    + (", ".join(detail.retrieval_extra_terms) or "ninguno"))
    contexto.append("Ordinales normalizados: " + (", ".join(detail.retrieval_ordinal_terms) or "ninguno"))
    contexto.append("La búsqueda semántica usa solo el texto del fragmento (la ruta no se agrega al vector).")
    contexto += ["", "Texto exacto que puntúa la búsqueda textual (BM25):", detail.retrieval_lexical_document]
    return {"texto": c.text, "propiedades": propiedades, "metadatos": metadatos, "contexto": "\n".join(contexto)}


def _plain(parent: QWidget, monospace: bool = False) -> QPlainTextEdit:
    caja = QPlainTextEdit(parent)
    caja.setReadOnly(True)
    caja.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    if monospace:
        caja.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    return caja


class ChunkDetailDialog(QDialog):
    """`load(chunk_id)` vuelve a consultar el detalle; los botones Anterior,
    Siguiente y Padre navegan entre fragmentos de la misma fuente."""

    def __init__(self, get_detail: Callable[[str], object], chunk_id: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Detalle del fragmento (solo lectura)")
        self.resize(900, 700)
        self._get_detail = get_detail
        self._detail = None
        layout = QVBoxLayout(self)
        self._encabezado = QLabel(self)
        self._encabezado.setTextFormat(Qt.TextFormat.PlainText)
        self._encabezado.setWordWrap(True)
        layout.addWidget(self._encabezado)
        self._tabs = QTabWidget(self)
        self._texto = _plain(self, monospace=True)
        self._propiedades = _plain(self)
        self._metadatos = _plain(self)
        self._contexto = _plain(self)
        self._tabs.addTab(self._texto, "Texto del fragmento")
        self._tabs.addTab(self._propiedades, "Propiedades")
        self._tabs.addTab(self._metadatos, "Metadatos heredados")
        self._tabs.addTab(self._contexto, "Contexto jerárquico")
        layout.addWidget(self._tabs)
        botones = QHBoxLayout()
        self._btn_anterior = QPushButton("◀ Anterior", self)
        self._btn_siguiente = QPushButton("Siguiente ▶", self)
        self._btn_padre = QPushButton("Ir al padre", self)
        self._btn_copiar = QPushButton("Copiar texto", self)
        self._btn_cerrar = QPushButton("Cerrar", self)
        for b in (self._btn_anterior, self._btn_siguiente, self._btn_padre, self._btn_copiar):
            botones.addWidget(b)
        botones.addStretch(1)
        botones.addWidget(self._btn_cerrar)
        layout.addLayout(botones)
        self._btn_anterior.clicked.connect(lambda: self._ir(self._detail.previous))
        self._btn_siguiente.clicked.connect(lambda: self._ir(self._detail.next))
        self._btn_padre.clicked.connect(lambda: self._ir(self._detail.parent))
        self._btn_copiar.clicked.connect(self.copy_text)
        self._btn_cerrar.clicked.connect(self.accept)
        self.load(chunk_id)

    def load(self, chunk_id: str) -> bool:
        detail = self._get_detail(chunk_id)
        if detail is None:
            self._encabezado.setText("El fragmento ya no existe (la fuente pudo volver a fragmentarse).")
            for caja in (self._texto, self._propiedades, self._metadatos, self._contexto):
                caja.setPlainText("")
            for b in (self._btn_anterior, self._btn_siguiente, self._btn_padre, self._btn_copiar):
                b.setEnabled(False)
            return False
        self._detail = detail
        secciones = format_chunk_detail(detail)
        c = detail.chunk
        self._encabezado.setText(
            f"{detail.source_title} — fragmento [{c.chunk_index}]"
            + (f" «{c.section_title}»" if c.section_title else "")
            + f" — {getattr(c.chunk_type, 'value', c.chunk_type)}, {c.token_count} tokens"
        )
        self._texto.setPlainText(secciones["texto"])
        self._propiedades.setPlainText(secciones["propiedades"])
        self._metadatos.setPlainText(secciones["metadatos"])
        self._contexto.setPlainText(secciones["contexto"])
        self._btn_anterior.setEnabled(bool(detail.previous and detail.previous.found))
        self._btn_siguiente.setEnabled(bool(detail.next and detail.next.found))
        self._btn_padre.setEnabled(bool(detail.parent and detail.parent.found))
        self._btn_copiar.setEnabled(True)
        return True

    def _ir(self, ref) -> None:
        if ref is not None and ref.found:
            self.load(ref.id)

    def copy_text(self) -> None:
        if self._detail is not None:
            QGuiApplication.clipboard().setText(self._detail.chunk.text)
