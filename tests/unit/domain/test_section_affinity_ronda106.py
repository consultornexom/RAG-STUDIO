"""Ronda 106 (autorizada por NEXOM): componentes V (afinidad ponderada por
valor) e Y (fragmentos solo-YAML sin afinidad)."""
from domain.conversational.section_affinity import affinity_title, combine_by_value, combine_with_retrieval

YAML = "---\nunidad_id: bach-tl\nnivel: bachillerato\n---\n"


def test_v_resuelve_el_empate_de_udl_bach_003():
    """Ronda 105f: «Información general» (búsqueda #1, afinidad 0.18) y
    requisitos (búsqueda #2, afinidad 0.57). Por puesto empatan (1/61 + 1/62)
    y gana la búsqueda; por valor gana la afinidad alta."""
    afinidades = [0.18, 0.57]
    assert combine_with_retrieval(afinidades) == [0, 1]
    assert combine_by_value(afinidades) == [1, 0]


def test_v_afinidad_cero_no_suma_y_se_conserva_el_orden_de_la_busqueda():
    assert combine_by_value([0.0, 0.0, 0.0]) == [0, 1, 2]
    assert combine_by_value([0.0, 0.3, 0.0]) == [1, 0, 2]


def test_v_una_afinidad_alta_equivale_al_primer_puesto_de_la_busqueda():
    # 1/(61+19) + 1.0/61 > 1/61 + 0: el puesto 20 con afinidad 1 supera al 1.º sin afinidad.
    afinidades = [0.0] * 19 + [1.0]
    assert combine_by_value(afinidades)[0] == 19


def test_v_la_diferencia_de_afinidad_pesa_segun_su_magnitud():
    # 0.05 de diferencia no compensa 10 puestos de búsqueda; 0.5 sí.
    assert combine_by_value([0.40] + [0.0] * 9 + [0.45])[0] == 0
    assert combine_by_value([0.10] + [0.0] * 9 + [0.60])[0] == 10


def test_v_empate_exacto_lo_decide_la_busqueda():
    assert combine_by_value([0.5, 0.5]) == [0, 1]


def test_y_fragmento_solo_yaml_sin_titulo():
    assert affinity_title(None, YAML, "bachillerato_torres_landa.md", exclude_yaml_only=True) == ""
    # Sin Y (r105b): título de la fuente, como en la Ronda 102 (C2).
    assert affinity_title(None, YAML, "bachillerato_torres_landa.md") == "bachillerato_torres_landa"


def test_y_no_afecta_a_fragmentos_con_contenido_ni_con_titulo_de_seccion():
    con_texto = YAML + "Texto del plan sin encabezado."
    assert affinity_title(None, con_texto, "plan.md", exclude_yaml_only=True) == "plan"
    assert affinity_title(None, YAML + "# Requisitos de ingreso\nCURP", "r.md", exclude_yaml_only=True) == \
        "Requisitos de ingreso"
    assert affinity_title("Información general", YAML, "plan.md", exclude_yaml_only=True) == "Información general"
