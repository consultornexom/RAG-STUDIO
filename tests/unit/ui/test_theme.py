"""Pruebas unitarias de la lógica pura de ui/theme.py: mapeo de estado
a color (`color_para_estado`) y armado de <span> coloreado
(`estado_html`). No construyen ningún widget real -- solo importan el
módulo, que sí depende de PySide6.QtGui/QtWidgets a nivel de import
(para QBrush/QColor/QListWidgetItem, usados por
`aplicar_color_estado_item`, no cubierta aquí). Se omite automáticamente
si el entorno no tiene las bibliotecas nativas de Qt disponibles --
mismo criterio que tests/smoke/test_ui_construction.py (agregada en la
auditoría de madurez ronda 5: antes ui/theme.py no tenía ninguna
prueba, pese a que esta parte de su lógica es trivialmente probable sin
pantalla)."""
import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}); se omite la prueba de ui/theme.py.",
                allow_module_level=True)

from ui.theme import color_para_estado, estado_html

# Los siete enums reales de la aplicación (ver docstring de ui/theme.py
# y capítulo 16 del manual de usuario) -- un valor representativo de
# cada categoría semántica, para no depender de importar los propios
# enums de domain/workers aquí (esta prueba es deliberadamente sobre la
# lógica de color, no sobre los enums en sí).
_CASOS_EXITO = ["completado", "validado", "aprobado", "liberado", "aprobada", "exitoso", "verde"]
_CASOS_ATENCION = ["pendiente", "pausado", "borrador", "amarillo"]
_CASOS_EN_PROCESO = ["ejecutando", "en_revision", "en_construccion", "en_curso"]
_CASOS_BLOQUEO = ["fallido", "rechazado", "vencido", "bloqueada", "rojo"]
_CASOS_NEUTROS = ["inicial", "sustituido", "archivado", "cancelado", "gris", "no_iniciada"]


@pytest.mark.parametrize("valor_estado", _CASOS_EXITO)
def test_color_para_estado_exito(valor_estado):
    color_texto, color_fondo = color_para_estado(valor_estado)
    assert color_texto == "#2E7D32"
    assert color_fondo == "#E8F5E9"


@pytest.mark.parametrize("valor_estado", _CASOS_ATENCION)
def test_color_para_estado_atencion(valor_estado):
    color_texto, color_fondo = color_para_estado(valor_estado)
    assert color_texto == "#B45309"
    assert color_fondo == "#FEF3E2"


@pytest.mark.parametrize("valor_estado", _CASOS_EN_PROCESO)
def test_color_para_estado_en_proceso(valor_estado):
    # Auditoría de UI 2026-08-24: el tono de "en proceso" pasó de un azul
    # genérico (#1565C0) al cian extraído del logo de RAG STUDIO
    # (ver ui/theme.py, CIAN_PROCESO) -- mismo significado semántico,
    # mismo matiz frío/azulado, ahora coherente con la marca.
    color_texto, color_fondo = color_para_estado(valor_estado)
    assert color_texto == "#2E8FB0"
    assert color_fondo == "#E4F3F7"


@pytest.mark.parametrize("valor_estado", _CASOS_BLOQUEO)
def test_color_para_estado_bloqueo(valor_estado):
    color_texto, color_fondo = color_para_estado(valor_estado)
    assert color_texto == "#C62828"
    assert color_fondo == "#FDECEA"


@pytest.mark.parametrize("valor_estado", _CASOS_NEUTROS)
def test_color_para_estado_neutro_no_tiene_color_especial(valor_estado):
    assert color_para_estado(valor_estado) is None


def test_color_para_estado_valor_desconocido_no_tiene_color_especial():
    assert color_para_estado("valor_que_no_existe_en_ningun_enum") is None


def test_estado_html_envuelve_en_span_con_color_cuando_aplica():
    resultado = estado_html("Completo", "completado")
    assert resultado == '<span style="color:#2E7D32; font-weight:bold;">Completo</span>'


def test_estado_html_no_agrega_span_si_estado_es_neutro():
    resultado = estado_html("Archivado", "archivado")
    assert resultado == "Archivado"


def test_estado_html_escapa_caracteres_especiales_con_color():
    # Defensa en profundidad (auditoría de madurez ronda 5): aunque hoy
    # todos los llamadores reales pasan etiquetas fijas sin caracteres
    # especiales, estado_html no debe confiar en eso -- un "&"/"<"/">"
    # sin escapar rompería el HTML del reporte (QTextBrowser).
    resultado = estado_html("<script>alert(1)</script> & cía", "fallido")
    assert resultado == (
        '<span style="color:#C62828; font-weight:bold;">'
        "&lt;script&gt;alert(1)&lt;/script&gt; &amp; cía</span>"
    )


def test_estado_html_escapa_caracteres_especiales_sin_color():
    resultado = estado_html("<b>x</b> & y", "archivado")
    assert resultado == "&lt;b&gt;x&lt;/b&gt; &amp; y"
