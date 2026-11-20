"""Ronda 106 (autorizada por NEXOM), componente R: los 15 casos borde de la
Ronda 104b (docs proyecto/Ronda104_Fragmentos_Puente/casos_borde_referencias.py)
como pruebas unitarias, más el ajuste de títulos de la Ronda 105 y la
detección solo-YAML del componente Y."""
from dataclasses import dataclass, field

import pytest

from domain.conversational.reference_resolution import (
    MAX_DESTINOS, MAX_POR_FUENTE, content_words, enforce_destinations_first, is_yaml_only, resolve_references,
    source_names,
)


@dataclass
class C:
    id: str
    source_id: str
    text: str
    section_title: str | None = None
    section_path: list = field(default_factory=list)


@dataclass
class R:
    chunk: C


YAML = "---\nunidad_id: x\nnivel: bachillerato\n---\n"
PUENTE = "## Información compartida\n\nPara evitar duplicación, consultar requisitos_ingreso.md — requisitos de ingreso."
CONTENIDO = "## Contenido\n\n- Acta de nacimiento original.\n- Certificado de secundaria.\n- CURP."
FUENTES = {"plan": "plan_a.md", "req": "requisitos_ingreso.md", "areas": "areas_formacion.md"}


def ids(lista):
    return [r.chunk.id for r in lista]


def test_valores_autorizados():
    assert MAX_POR_FUENTE == 2 and MAX_DESTINOS == 5


# 1. Caso base (3 casos).
def _caso_base():
    cands = [R(C("p1", "plan", PUENTE)), R(C("x", "plan", "## Info\n\nTexto general del plan con varias palabras.")),
             R(C("r1", "req", CONTENIDO))]
    return resolve_references(cands, FUENTES)


def test_01_destino_insertado_antes_del_puente():
    res = _caso_base()
    assert ids(res.candidates)[:2] == ["r1", "p1"] and res.links == {"r1": ["p1"]}


def test_02_restriccion_final_destino_delante_aunque_la_afinidad_lo_ponga_detras():
    assert enforce_destinations_first(["p1", "x", "r1"], _caso_base().links) == ["r1", "p1", "x"]


def test_03_restriccion_si_el_puente_no_esta_no_se_mueve_nada():
    assert enforce_destinations_first(["x", "r1"], _caso_base().links) == ["x", "r1"]


# 2. Referencia inexistente.
def test_04_referencia_a_un_archivo_que_no_es_fuente_sin_cambios():
    cands = [R(C("p1", "plan", "Consultar no_existe.md para más detalles.")), R(C("r1", "req", CONTENIDO))]
    res = resolve_references(cands, FUENTES)
    assert ids(res.candidates) == ["p1", "r1"] and not res.links


# 3. Referencia ambigua.
def test_05_referencia_ambigua_no_se_resuelve_y_queda_en_la_traza():
    dobles = {**FUENTES, "req2": "requisitos_ingreso.md"}
    cands = [R(C("p1", "plan", PUENTE)), R(C("r1", "req", CONTENIDO)), R(C("r2", "req2", CONTENIDO))]
    res = resolve_references(cands, dobles)
    assert not res.links and res.ambiguous == ["requisitos_ingreso", "requisitos_ingreso.md"]


# 4. Referencias circulares (2 casos).
CIRC = {"a": "unidad_a.md", "b": "unidad_b.md"}


def test_06_circular_entre_puentes_sin_bucles():
    cands = [R(C("a1", "a", "Ver unidad_b.md.")), R(C("b1", "b", "Ver unidad_a.md."))]
    res = resolve_references(cands, CIRC)
    assert not res.links and ids(res.candidates) == ["a1", "b1"]


def test_07_circular_con_contenido_un_solo_nivel():
    cands = [R(C("a1", "a", "Ver unidad_b.md.")), R(C("b1", "b", "Ver unidad_a.md.")),
             R(C("a2", "a", "## Contenido A\n\nTexto propio de la unidad A con suficientes palabras.")),
             R(C("b2", "b", "## Contenido B\n\nTexto propio de la unidad B con suficientes palabras."))]
    res = resolve_references(cands, CIRC)
    assert res.links == {"b2": ["a1"], "a2": ["b1"]} and ids(res.candidates) == ["b2", "a1", "a2", "b1"]


# 5. Fuente referida no permitida (2 casos).
def test_08_fuente_referida_fuera_de_los_filtros_no_se_incorpora():
    cands = [R(C("p1", "plan", PUENTE)), R(C("x", "plan", "Otro texto del plan con palabras suficientes."))]
    assert not resolve_references(cands, {"plan": "plan_a.md"}).links


def test_09_fuente_referida_permitida_pero_sin_candidatos_no_se_incorpora():
    """Equivalente del «modo búsqueda sin resultados» del prototipo: en modo
    pool (el implementado), un destino solo puede venir del conjunto de la
    búsqueda filtrada; si la fuente no tiene candidatos, no se trae nada."""
    cands = [R(C("p1", "plan", PUENTE)), R(C("x", "plan", "Otro texto del plan con palabras suficientes."))]
    res = resolve_references(cands, FUENTES)
    assert not res.links and ids(res.candidates) == ["p1", "x"]


# 6. Destinos sin contenido.
def test_10_destino_solo_yaml_o_solo_encabezado_se_salta():
    cands = [R(C("p1", "plan", PUENTE)), R(C("ry", "req", YAML)), R(C("rh", "req", "# Requisitos de ingreso")),
             R(C("r1", "req", CONTENIDO))]
    res = resolve_references(cands, FUENTES)
    assert list(res.links) == ["r1"] and ids(res.candidates)[0] == "r1"


# 7. Fragmento largo.
def test_11_fragmento_largo_que_cita_otra_fuente_no_es_puente():
    largo = "## Plan\n\n" + " ".join(["palabra"] * 90) + " ver requisitos_ingreso.md"
    cands = [R(C("l1", "plan", largo)), R(C("r1", "req", CONTENIDO))]
    assert not resolve_references(cands, FUENTES).links


# 8. Varios fragmentos por fuente (2 casos).
def _varios():
    return [R(C("p1", "plan", PUENTE)), R(C("rp", "req", "## Procedencia\n\nDocumento derivado de los dos folletos.")),
            R(C("r1", "req", CONTENIDO))]


def test_12_varios_fragmentos_uno_por_fuente():
    assert list(resolve_references(_varios(), FUENTES, max_per_source=1).links) == ["rp"]


def test_13_varios_fragmentos_dos_por_fuente_predeterminado():
    res = resolve_references(_varios(), FUENTES)
    assert set(res.links) == {"rp", "r1"} and ids(res.candidates)[:3] == ["rp", "r1", "p1"]


# 9. Mención propia o dentro de otro nombre.
def test_14_mencion_de_la_propia_fuente_o_dentro_de_otro_nombre_no_es_referencia():
    cands = [R(C("r0", "req", "Este archivo requisitos_ingreso.md resume.")),
             R(C("p1", "plan", "Ver mis_requisitos_ingreso.md2 no aplica."))]
    assert not resolve_references(cands, FUENTES).links


# 10. Tope de destinos.
def test_15_tope_de_destinos_por_consulta():
    muchos = {f"s{i}": f"unidad_{i}.md" for i in range(7)}
    muchos["plan"] = "plan_a.md"
    texto = "Ver " + ", ".join(f"unidad_{i}.md" for i in range(7))
    cands = [R(C("p1", "plan", texto))] + [
        R(C(f"c{i}", f"s{i}", f"## U{i}\n\nContenido propio número {i} extenso.")) for i in range(7)
    ]
    assert len(resolve_references(cands, muchos).links) == MAX_DESTINOS


# Ajuste de la Ronda 105 y otros detalles del diseño.
@pytest.mark.parametrize("titulo, esperado", [
    ("requisitos_ingreso.md", ["requisitos_ingreso.md", "requisitos_ingreso"]),
    ("Información general", []),
    ("Plan de estudios.pdf", ["plan de estudios.pdf"]),
    ("guia-aspirante", ["guia-aspirante"]),
    ("", []),
])
def test_titulo_sin_extension_ni_forma_de_identificador_no_cuenta(titulo, esperado):
    assert source_names(titulo) == esperado


def test_titulo_comun_sin_extension_no_genera_referencias():
    fuentes = {"plan": "plan_a.md", "info": "Información general"}
    cands = [R(C("p1", "plan", "Ver Información general para más datos.")),
             R(C("i1", "info", "## Datos\n\nTexto con contenido propio suficiente."))]
    assert not resolve_references(cands, fuentes).links


def test_mencion_dentro_del_yaml_no_cuenta():
    cands = [R(C("p1", "plan", "---\nver: requisitos_ingreso.md\n---\n## Algo\n\nTexto.")), R(C("r1", "req", CONTENIDO))]
    assert not resolve_references(cands, FUENTES).links


def test_un_destino_no_se_duplica_si_lo_traen_dos_puentes():
    cands = [R(C("p1", "plan", PUENTE)), R(C("p2", "areas", PUENTE)), R(C("r1", "req", CONTENIDO))]
    res = resolve_references(cands, FUENTES)
    assert ids(res.candidates) == ["r1", "p1", "p2"] and res.links == {"r1": ["p1", "p2"]}


def test_solo_yaml_y_palabras_de_contenido():
    assert is_yaml_only(YAML) and is_yaml_only("") and not is_yaml_only(YAML + "# Título")
    assert content_words(YAML + "# Título\n\nUno dos tres") == 3


def test_patron_sintetico_ronda102_v_sola_reabre_la_regresion_y_r_la_evita():
    """Ronda 105f: requisitos_ingreso.md 1.º de la búsqueda (afinidad 0.86) y
    dos secciones «Requisitos de ingreso» de los planes que solo remiten a él
    (búsqueda 2.º y 3.º, afinidad 1.00). Con V sola los puentes pasan delante;
    con V + R el documento queda primero."""
    from domain.conversational.section_affinity import combine_by_value

    puente = "## Requisitos de ingreso\n\nLos requisitos están en requisitos_ingreso.md."
    cands = [R(C("r1", "req", CONTENIDO)), R(C("p1", "plan", puente)), R(C("p2", "areas", puente))]
    afinidad = {"r1": 0.86, "p1": 1.0, "p2": 1.0}
    solo_v = [cands[i].chunk.id for i in combine_by_value([afinidad[c.chunk.id] for c in cands])]
    assert solo_v.index("r1") == 2
    res = resolve_references(cands, FUENTES)
    orden = [res.candidates[i].chunk.id for i in combine_by_value([afinidad[c.chunk.id] for c in res.candidates])]
    assert enforce_destinations_first(orden, res.links)[0] == "r1"
