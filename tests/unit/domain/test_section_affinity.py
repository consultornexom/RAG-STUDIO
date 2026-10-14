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
