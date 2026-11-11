"""Ronda 91: afinidad intención -> título de sección."""
from domain.conversational.entities import Intent
from domain.conversational.section_affinity import SectionAffinity, raices


def _i(name, description="", positivos=()):
    return Intent(project_id="p1", name=name, description=description, positive_examples=list(positivos))


PERFIL = _i("Consultar perfil de egreso", "Consulta el perfil de egreso de un programa académico.",
            ["¿Qué conocimientos obtiene quien termina Ingeniería Civil?"])
PLAN = _i("Consultar plan de estudios", "Consulta las materias o áreas formativas del plan de estudios.",
          ["¿Qué materias lleva Arquitectura?"])
CAMPO = _i("Consultar campo de trabajo", "Sectores en los que puede desempeñarse un egresado.",
           ["¿Dónde puede trabajar un egresado de Psicología?"])
TODAS = [PERFIL, PLAN, CAMPO]


def test_raices_sin_acentos_y_con_la_misma_raiz():
    assert raices("Perfil del egresado") == raices("perfil de egreso")
    assert "estud" in raices("Plan de estudios")


def test_la_seccion_del_perfil_gana_para_la_intencion_de_perfil():
    a = SectionAffinity(PERFIL, TODAS, "¿Qué conocimientos obtiene quien termina ?")
    titulos = ["Casos que requieren handoff", "Perfil del aspirante", "Perfil del egresado", "Uso permitido por el agente"]
    assert max(titulos, key=a.score) == "Perfil del egresado"
    assert a.score("Casos que requieren handoff") == 0.0
    assert a.score("Uso permitido por el agente") == 0.0


def test_cada_intencion_prefiere_su_seccion():
    titulos = ["Perfil del egresado", "Areas formativas / plan de estudios", "Campo de trabajo"]
    assert max(titulos, key=SectionAffinity(PLAN, TODAS, "¿Qué materias lleva ?").score) == titulos[1]
    assert max(titulos, key=SectionAffinity(CAMPO, TODAS, "¿Dónde puede trabajar ?").score) == titulos[2]


def test_titulo_vacio_tiene_afinidad_cero():
    assert SectionAffinity(PERFIL, TODAS, "x").score(None) == 0.0


# ---------- Ronda 102: C2 (título sin sección) y C1 (combinación con la búsqueda) ----------

from domain.conversational.section_affinity import (  # noqa: E402
    affinity_title, combine_with_retrieval, first_markdown_heading,
)

YAML = "---\nunidad_id: x\n# comentario yaml\nnivel_academico: bachillerato\n---\n\n"


def test_primer_encabezado_salta_el_encabezado_yaml():
    assert first_markdown_heading(YAML + "# Requisitos de ingreso — Bachillerato UDL\n\n## Contenido\n") == \
        "Requisitos de ingreso — Bachillerato UDL"
    assert first_markdown_heading("Texto sin título.\n\n### Sección ###\n") == "Sección"
    assert first_markdown_heading(YAML + "Solo texto.") is None
    assert first_markdown_heading("#hashtag sin espacio") is None
    assert first_markdown_heading(None) is None
    # "---" sin cierre no es YAML: se busca el encabezado en todo el texto.
    assert first_markdown_heading("---\n# Título\n") == "Título"


def test_titulo_para_afinidad_seccion_encabezado_o_fuente():
    assert affinity_title("Plan de estudios", YAML + "# Otro", "doc.md") == "Plan de estudios"
    assert affinity_title(None, YAML + "# Requisitos de ingreso\n", "requisitos_ingreso.md") == "Requisitos de ingreso"
    assert affinity_title(None, YAML + "sin encabezado", "requisitos_ingreso.md") == "requisitos_ingreso"
    assert affinity_title(None, "texto", None) == ""
    # Antes era la primera línea: "---" (afinidad cero).
    a = SectionAffinity(_i("consultar_requisitos", "Requisitos de ingreso", ["¿Qué necesito para ingresar?"]),
                        [PERFIL, PLAN], "requisitos para ingresar")
    assert a.score("---") == 0.0
    assert a.score(affinity_title(None, YAML + "# Requisitos de ingreso — Bachillerato UDL", "r.md")) >= 0.5


def test_la_afinidad_no_entierra_el_mejor_resultado_de_la_busqueda():
    """Caso NEXOM (diagnóstico Ronda 102): la búsqueda pone primero el
    documento de requisitos (afinidad 0.86); dos secciones que solo remiten
    a él tienen afinidad 1.00. Antes quedaba 3.º."""
    assert combine_with_retrieval([0.86, 1.0, 1.0, 0.0, 0.0])[:3] == [0, 1, 2]
    # Con un título menos descriptivo (0.50) sigue adelante del tercero.
    assert combine_with_retrieval([0.5, 1.0, 1.0, 0.0, 0.0])[:2] == [0, 1]


def test_la_afinidad_sigue_subiendo_la_seccion_pedida_ronda_91():
    """Ronda 91: "Perfil del egresado" 4.º en la búsqueda, detrás de
    secciones de control editorial sin afinidad."""
    assert combine_with_retrieval([0.0, 0.0, 0.0, 1.0, 0.0])[0] == 3


def test_sin_afinidad_o_a_igual_afinidad_se_conserva_el_orden_de_la_busqueda():
    assert combine_with_retrieval([0.0] * 5) == [0, 1, 2, 3, 4]
    assert combine_with_retrieval([0.5, 0.5, 0.5]) == [0, 1, 2]
    assert combine_with_retrieval([]) == []
    # Un peor puesto de afinidad se compensa con un mejor puesto en la búsqueda.
    assert combine_with_retrieval([0.6, 0.9, 0.3])[0] in (0, 1)
    assert combine_with_retrieval([0.6, 0.9, 0.3]) == [0, 1, 2]
