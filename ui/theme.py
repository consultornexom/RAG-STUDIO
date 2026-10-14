"""Paleta de colores y hoja de estilos (QSS) de la interfaz.

Agregado 2026-07-29, a pedido explícito del consultor, tras revisar qué
hizo RAG CONTENT STUDIO (herramienta hermana del mismo autor) en su
propia iteración de colores y confirmar que aplica igual aquí: agregar
un esquema de color no afecta el rendimiento (RAG STUDIO no tenía hasta
ahora ningún `setStyleSheet()`/`QPalette` propio, solo el tema por
defecto del sistema operativo, y no hay ningún bucle de repintado
continuo que un color pudiera encarecer -- el único `QTimer` real de la
app, `_poll_timer` en `ui/ingestion/panel.py` y
`ui/conversational/panel.py`, ya existía desde antes para sondear
trabajos en segundo plano, y su intervalo no cambia con esto).

Paleta original (2026-07-29): misma paleta de azules que ya usa RAG
CONTENT STUDIO (`ui/theme.py` de ese proyecto), a propósito -- en ese
momento no había ninguna paleta propia de RAG STUDIO que respetar (su
manual de usuario usaba los estilos de encabezado por defecto de
Word/LibreOffice, no colores personalizados).

Actualización 2026-08-24, a pedido explícito del consultor ("analiza
los colores del logo y en base a ello, cambia los colores actuales de
la UI por una combinación muy profesional de tonos"): RAG STUDIO ya
tiene su propio logo (`ui/LOGO.png`, usado desde antes en la pantalla
de bienvenida de `ui/app.py`), así que dejó de tener sentido heredar la
paleta de la herramienta hermana -- ahora tiene su propia identidad
visual, derivada de ese logo. Los colores no se eligieron a ojo: se
extrajeron programáticamente del archivo real (`ui/LOGO.png`, 2816x1536)
con un clustering de color (k-means, k=8, sobre los píxeles "vívidos"
-- saturación > 40 -- para no dejar que el fondo gris del logo domine
el resultado). Los ocho grupos resultantes, ordenados por peso:
azul acero medio (~19%), azul-cian apagado (~18%), azul marino
estructural (~15%), azul marino profundo (~14%), violeta profundo
(~10%), cian brillante (~9%), violeta claro/lavanda (~8%) y celeste
muy claro (~6%). De ahí salen las tres familias de marca de abajo:
`AZUL_OSCURO`/`AZUL_MEDIO`/`AZUL_OSCURO_HOVER` (los azules marino y
acero -- base de la interfaz, botones y selección, el mismo rol que
cumplía la paleta anterior), `VIOLETA_ACENTO`/`VIOLETA_ACENTO_CLARO`
(del violeta del rayo/estrella y de la palabra "STUDIO" del logo --
un acento nuevo, reservado a propósito para foco de teclado en campos
de entrada y un detalle en la pestaña activa, nunca para botones
normales, para que siga leyéndose como acento y no compita con el azul
como color "de acción") y `CIAN_PROCESO`/`CIAN_PROCESO_FONDO` (del
brillo cian de los bordes de los cubos -- reemplaza al antiguo
`AZUL_PROCESO` para la categoría semántica "en proceso"/"ejecutando":
mismo significado exacto de antes, siguiendo siendo un tono de la
familia azul/fría, pero con el tono específico del logo en vez de un
azul de Material Design genérico). Los tres colores semánticos que sí
tienen un significado normado fuera de esta app -- verde/éxito,
ámbar/atención, rojo/bloqueo, documentados en el capítulo 3.4 del
Manual de Usuario como parte del lenguaje de semáforos -- se dejaron
sin cambiar a propósito: no vienen del logo, son una convención de
semáforo universal (verde=aprobado, ámbar=revisión, rojo=bloqueo) y
cambiarlos por gusto estético rompería esa asociación aprendida sin
ninguna ganancia real de marca.

A diferencia de RAG CONTENT STUDIO (que usa QTableWidget con una
columna "Estado" propia), RAG STUDIO muestra su estado siempre como
parte del texto de una fila de QListWidget (por ejemplo,
"Proyecto X  [en_construccion]  (id)") o como una palabra dentro de un
reporte HTML en QTextBrowser (por ejemplo, "veredicto general: Rojo
(bloqueo)"). Por eso este módulo ofrece dos formas de aplicar color en
vez de una:

1. `aplicar_color_estado_item(item, valor_estado)` -- colorea el texto
   e ícono de fondo de un `QListWidgetItem` completo (para listas como
   Proyectos y Fuentes, donde toda la fila representa una sola entidad
   y su estado).
2. `estado_html(texto, valor_estado)` -- envuelve un fragmento de texto
   en un `<span>` con color en línea, para insertarlo dentro de un
   reporte HTML ya existente (pipeline, evaluación, liberación). El
   texto original SIEMPRE se conserva -- el color refuerza, nunca
   reemplaza (accesibilidad básica para variaciones de percepción del
   color), igual que en RAG CONTENT STUDIO.

Los valores de estado que reconoce vienen de los siete enums reales de
esta aplicación (confirmados leyendo las entidades, no adivinados):
`ProjectStatus` (`domain/projects/entities.py`), `SourceValidationStatus`
(`domain/documents/entities.py`), `JobStatus` (`workers/jobs.py`),
`PipelineRunStatus`/`PipelineItemStatus` (`domain/pipeline/entities.py`),
`ReleaseStatus` (`domain/release/entities.py`) y `EvaluationVerdict`
(`domain/quality/entities.py`) -- el mismo inventario documentado en el
capítulo 16 del manual de usuario. Los valores que no aparecen en
ningún conjunto de abajo (por ejemplo "inicial", "borrador",
"pendiente" en su sentido neutro de "en cola") se dejan sin color
especial a propósito, para que las filas que sí necesitan destacar
(éxito, atención, bloqueo) resalten por contraste en vez de competir
con una pantalla donde todo tiene color."""
from __future__ import annotations

from html import escape as _html_escape
from typing import Optional

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QListWidgetItem

# -- Colores de marca (extraídos de ui/LOGO.png, ver docstring) --------
AZUL_OSCURO = "#152A4E"
AZUL_MEDIO = "#2C5A87"
AZUL_OSCURO_HOVER = "#0E1C33"

# -- Acento violeta (del rayo/estrella y "STUDIO" del logo) -------------
# Reservado a propósito para foco de teclado y un detalle de la pestaña
# activa -- nunca para botones normales (ver docstring del módulo).
VIOLETA_ACENTO = "#6C4FBD"
VIOLETA_ACENTO_CLARO = "#EDE7FB"

# -- Neutrales (tono frío, consistente con el azul marino de marca) -----
GRIS_FONDO_VENTANA = "#F3F5F9"
GRIS_FONDO_TARJETA = "#FFFFFF"
GRIS_BORDE = "#D6DCE6"
GRIS_TEXTO = "#20262F"
BLANCO = "#FFFFFF"

# -- Colores semánticos de estado (texto + fondo suave) -----------------
# Verde/ámbar/rojo son la convención universal de semáforo (manual,
# capítulo 3.4) y se dejan sin cambiar a propósito -- no vienen del
# logo. "En proceso" sí se retiñó con el cian del logo (ver docstring):
# mismo significado semántico de siempre, mismo tono frío/azulado,
# ahora con el matiz específico de marca en vez de un azul genérico.
VERDE_EXITO = "#2E7D32"
VERDE_EXITO_FONDO = "#E8F5E9"
AMBAR_ATENCION = "#B45309"
AMBAR_ATENCION_FONDO = "#FEF3E2"
CIAN_PROCESO = "#2E8FB0"
CIAN_PROCESO_FONDO = "#E4F3F7"
ROJO_BLOQUEO = "#C62828"
ROJO_BLOQUEO_FONDO = "#FDECEA"

# Alias retrocompatible: código o pruebas que todavía se refieran al
# nombre anterior ("azul de proceso") siguen funcionando -- incluso
# aunque hoy ningún archivo del repo lo haga (verificado antes de este
# cambio), es una constante pública de un módulo sin guion bajo inicial,
# así que no cuesta nada dejar el alias por compatibilidad hacia
# adelante.
AZUL_PROCESO = CIAN_PROCESO
AZUL_PROCESO_FONDO = CIAN_PROCESO_FONDO

# -- Categorías semánticas de estado -------------------------------------
# Un mismo valor de texto (por ejemplo "cancelado") puede pertenecer a
# más de uno de los siete enums reales; se mantiene el mismo color en
# todos los casos para que sea predecible, igual que hace RAG CONTENT
# STUDIO al fusionar sus cinco enums en un solo mapa.
_EXITO = {
    "completado", "validado", "aprobado", "liberado", "aprobada",
    "exitoso", "completo", "verde",
}
_ATENCION = {
    "pendiente", "pausado", "borrador", "completo_con_errores", "amarillo",
}
_EN_PROCESO = {
    "preparando", "ejecutando", "en_revision", "en_configuracion",
    "en_construccion", "en_pruebas", "en_preparacion", "en_ejecucion",
    "en_curso",
}
_BLOQUEO = {
    "fallido", "rechazado", "vencido", "rechazada", "bloqueada", "rojo",
}
# El resto -- inicial, sustituido, archivado, cancelado, omitido,
# no_iniciada, sustituida, gris -- son pasos neutros, terminales sin
# alerta, o decisiones deliberadas (cancelar algo no es un fallo): se
# dejan sin color especial, ver docstring del módulo.


def color_para_estado(valor_estado: str) -> Optional[tuple[str, str]]:
    """Devuelve (color_de_texto, color_de_fondo) en hexadecimal para
    `valor_estado`, o None si no amerita un color especial (ver arriba)."""
    if valor_estado in _EXITO:
        return VERDE_EXITO, VERDE_EXITO_FONDO
    if valor_estado in _ATENCION:
        return AMBAR_ATENCION, AMBAR_ATENCION_FONDO
    if valor_estado in _EN_PROCESO:
        return CIAN_PROCESO, CIAN_PROCESO_FONDO
    if valor_estado in _BLOQUEO:
        return ROJO_BLOQUEO, ROJO_BLOQUEO_FONDO
    return None


def aplicar_color_estado_item(item: QListWidgetItem, valor_estado: str) -> None:
    """Colorea `item` (una fila de QListWidget ya creada) según
    `color_para_estado()`. No hace nada si el estado no tiene un color
    especial asignado -- la fila conserva el estilo por defecto de la
    lista."""
    colores = color_para_estado(valor_estado)
    if colores is None:
        return
    color_texto, color_fondo = colores
    item.setForeground(QBrush(QColor(color_texto)))
    item.setBackground(QBrush(QColor(color_fondo)))


def estado_html(texto: str, valor_estado: str) -> str:
    """Envuelve `texto` en un <span> con color en línea según
    `color_para_estado()`, para insertar dentro de un reporte HTML ya
    existente (QTextBrowser). Si el estado no tiene color especial,
    devuelve `texto` escapado tal cual, sin ningún span.

    `texto` siempre se escapa (html.escape) antes de insertarse: la
    mayoría de quienes llaman a esta función pasan etiquetas fijas del
    código (por ejemplo "Completo, con errores"), pero algunos también
    pasan datos que en teoría podrían contener texto arbitrario (por
    ejemplo el nombre de un caso de prueba). Antes de esta corrección
    (auditoría de madurez ronda 5) el escape quedaba a criterio de cada
    llamador -- inconsistente entre paneles (ver ui/release/panel.py,
    que sí lo hacía por su cuenta, contra ui/quality/panel.py e
    ui/ingestion/panel.py, que no) -- ahora se garantiza aquí una sola
    vez, en el propio punto donde se arma el <span>."""
    texto_seguro = _html_escape(texto)
    colores = color_para_estado(valor_estado)
    if colores is None:
        return texto_seguro
    color_texto, _ = colores
    return f'<span style="color:{color_texto}; font-weight:bold;">{texto_seguro}</span>'


HOJA_DE_ESTILOS = f"""
QMainWindow, QDialog {{
    background-color: {GRIS_FONDO_VENTANA};
}}

QWidget {{
    color: {GRIS_TEXTO};
}}

/* -- Pestañas (las 8 pestañas principales y sus sub-pestañas) -- */
QTabWidget::pane {{
    border: 1px solid {GRIS_BORDE};
    border-radius: 4px;
    background-color: {GRIS_FONDO_TARJETA};
}}

QTabBar::tab {{
    background-color: {GRIS_FONDO_VENTANA};
    border: 1px solid {GRIS_BORDE};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 12px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {AZUL_MEDIO};
    color: {BLANCO};
    border-top: 3px solid {VIOLETA_ACENTO};
    padding-top: 3px;
}}

QTabBar::tab:hover:!selected {{
    background-color: #E9EDF6;
}}

/* -- Listas (Proyectos, Fuentes, Intenciones, Complementos, etc.) -- */
QListWidget {{
    background-color: {BLANCO};
    border: 1px solid {GRIS_BORDE};
    border-radius: 4px;
    outline: 0;
    alternate-background-color: #F7F9FC;
}}

QListWidget::item {{
    padding: 5px 8px;
}}

QListWidget::item:selected {{
    background-color: {AZUL_MEDIO};
    color: {BLANCO};
}}

QListWidget::item:hover:!selected {{
    background-color: #E9EDF6;
}}

/* -- Botones -- */
QPushButton {{
    background-color: {AZUL_MEDIO};
    color: {BLANCO};
    border: none;
    border-radius: 4px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    background-color: {AZUL_OSCURO};
}}

QPushButton:pressed {{
    background-color: {AZUL_OSCURO_HOVER};
}}

QPushButton:disabled {{
    background-color: #A9B4C4;
    color: #EEF1F5;
}}

/* -- Reportes (Pipeline, Evaluación, Liberación, Búsqueda RAG...) -- */
QTextBrowser {{
    background-color: {BLANCO};
    border: 1px solid {GRIS_BORDE};
    border-radius: 4px;
}}

/* -- Tarjetas / agrupadores de formularios -- */
QGroupBox {{
    background-color: {GRIS_FONDO_TARJETA};
    border: 1px solid {GRIS_BORDE};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    color: {AZUL_OSCURO};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

/* -- Campos de entrada -- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit {{
    background-color: {BLANCO};
    border: 1px solid {GRIS_BORDE};
    border-radius: 4px;
    padding: 3px 5px;
    selection-background-color: {AZUL_MEDIO};
    selection-color: {BLANCO};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {VIOLETA_ACENTO};
}}

/* -- Barras de progreso (trabajos en segundo plano) -- */
QProgressBar {{
    border: 1px solid {GRIS_BORDE};
    border-radius: 4px;
    text-align: center;
    background-color: {BLANCO};
}}

QProgressBar::chunk {{
    background-color: {CIAN_PROCESO};
    border-radius: 3px;
}}

/* -- Splitters -- */
QSplitter::handle {{
    background-color: {GRIS_BORDE};
}}
"""
