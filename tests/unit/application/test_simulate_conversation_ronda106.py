"""Ronda 106 (autorizada por NEXOM): procedimiento de recuperación por
proyecto en SimulateConversation -- r106 (V + Y + R) o r105b."""
import pytest

from domain.conversational.entities import Intent, RuleActionType
from domain.conversational.retrieval_procedure import UnknownRetrievalProcedureError
from domain.conversational.section_affinity import combine_with_retrieval

from application.conversational.queries.simulate_conversation import SimulateConversation
from application.rag.service import RagService

from .fakes_conversational import InMemoryChannelingSchemeRepository, InMemoryGuardrailRuleRepository
from .fakes_rag import InMemoryIndexInfoRepository
from .test_simulate_conversation_ronda102 import _agrega
from .test_simulate_conversation_variables import P, Fx, _escenario

CONSULTA = "¿Qué necesito para ingresar a Gestión Profesional de Proyectos?"


def _simulador(fx: Fx, procedimiento) -> None:
    rag = RagService(fx.chunks, fx.embedder, fx.store, InMemoryIndexInfoRepository(), source_repository=fx.sources)
    fx.simulate = SimulateConversation(
        fx.intents, fx.variables, InMemoryGuardrailRuleRepository(), InMemoryChannelingSchemeRepository(),
        fx.metadata, rag, source_repository=fx.sources, schema_repository=fx.schemas, catalog_repository=fx.catalogs,
        retrieval_procedure=(lambda _pid: procedimiento),
    )


def _escenario_puente() -> Fx:
    """Patrón sintético de la Ronda 102 en miniatura: un plan con una
    sección «Requisitos de ingreso» que solo remite a requisitos_ingreso.md
    (título exacto de la intención) y el documento referido."""
    fx = _escenario()
    fx.intents.save(Intent(
        project_id=P, name="Consultar requisitos de ingreso", description="Requisitos de ingreso al programa.",
        positive_examples=["¿Qué necesito para ingresar a Gestión Profesional de Proyectos?"],
        required_variables=["programa_academico"],
    ))
    fx.fuente("plan_gpp.md", "gestion_profesional_de_proyectos", [])
    fx.fuente("requisitos_ingreso.md", "gestion_profesional_de_proyectos", [])
    _agrega(fx, "plan_gpp.md", 0, "Los requisitos de ingreso están en requisitos_ingreso.md. necesito ingresar",
            section_title="Requisitos de ingreso")
    _agrega(fx, "requisitos_ingreso.md", 0,
            "---\nnivel: x\n---\n# Documentos\nActa de nacimiento, CURP, certificado y fotografías para ingresar")
    _agrega(fx, "requisitos_ingreso.md", 1, "---\nnivel: x\n---\n")
    return fx


@pytest.mark.parametrize("guardado, esperado", [(None, "r105b"), ("r105b", "r105b"), ("r106", "r106"),
                                                 (" R106 ", "r106")])
def test_procedimiento_efectivo_segun_el_ajuste(guardado, esperado):
    fx = _escenario_puente()
    _simulador(fx, guardado)
    trace = fx.simulate.execute(P, CONSULTA)
    assert trace.retrieval_pipeline == esperado


def test_sin_lector_el_procedimiento_es_r105b():
    fx = _escenario()
    assert fx.simulate.execute(P, "cual es el objetivo del programa Gestión Profesional de Proyectos") \
        .retrieval_pipeline == "r105b"


def test_procedimiento_desconocido_falla_de_forma_explicita():
    fx = _escenario_puente()
    _simulador(fx, "r999")
    with pytest.raises(UnknownRetrievalProcedureError, match="r999"):
        fx.simulate.execute(P, CONSULTA)


def test_r106_pone_el_documento_referido_delante_del_puente():
    fx = _escenario_puente()
    _simulador(fx, "r106")
    trace = fx.simulate.execute(P, CONSULTA)
    assert trace.action == RuleActionType.RESPONDER and trace.applied_metadata_filters
    fuentes = [r.chunk.source_id for r in trace.search_results]
    puente = next(i for i, r in enumerate(trace.search_results) if r.chunk.source_id == "plan_gpp.md")
    destino = fuentes.index("requisitos_ingreso.md")
    assert destino < puente
    vista = trace.result_ordering[destino]
    assert vista.referenced_from and vista.referenced_from_sources == ["plan_gpp.md"]
    # Y: el fragmento solo-YAML no tiene título de afinidad.
    for r, o in zip(trace.search_results, trace.result_ordering, strict=True):
        if r.chunk.text.strip().endswith("---") and r.chunk.chunk_index == 1:
            assert o.affinity_title == "" and o.affinity == 0


def test_r105b_conserva_el_orden_anterior_exacto():
    """r105b = sin ajuste = construcción anterior a la Ronda 106."""
    textos = {}
    for procedimiento in ("r105b", None):
        fx = _escenario_puente()
        _simulador(fx, procedimiento)
        trace = fx.simulate.execute(P, CONSULTA)
        assert all(not o.referenced_from for o in trace.result_ordering)
        textos[procedimiento] = [r.chunk.text for r in trace.search_results]
    fx = _escenario_puente()  # sin lector de procedimiento
    textos["sin_lector"] = [r.chunk.text for r in fx.simulate.execute(P, CONSULTA).search_results]
    assert textos["r105b"] == textos[None] == textos["sin_lector"]


def test_decision_identica_en_ambos_procedimientos():
    """V, Y y R actúan solo en el orden: intención, confianza, variables,
    filtros, reglas y acción son los mismos."""
    trazas = {}
    for procedimiento in ("r105b", "r106"):
        fx = _escenario_puente()
        _simulador(fx, procedimiento)
        trazas[procedimiento] = fx.simulate.execute(P, CONSULTA)
    a, b = trazas["r105b"], trazas["r106"]
    campos = ("matched_intent_name", "confidence", "detected_variables", "missing_variables",
              "applied_metadata_filters", "fired_rules", "action", "retrieval_query", "excluded_by_metadata_filter")
    assert {c: getattr(a, c) for c in campos} == {c: getattr(b, c) for c in campos}
    assert {r.chunk.id for r in a.search_results} | {r.chunk.id for r in b.search_results}


def test_sin_filtros_r106_entrega_lo_mismo_que_r105b():
    resultados = {}
    for procedimiento in ("r105b", "r106"):
        fx = _escenario()
        fx.intents.save(Intent(project_id=P, name="Consultar objetivo", description="Objetivo del programa.",
                               positive_examples=["¿Cuál es el objetivo?"]))
        _simulador(fx, procedimiento)
        trace = fx.simulate.execute(P, "¿Cuál es el objetivo?")
        assert not trace.applied_metadata_filters
        resultados[procedimiento] = [r.chunk.text for r in trace.search_results]
    assert resultados["r105b"] == resultados["r106"]


def test_combine_with_retrieval_sigue_siendo_el_de_r105b():
    assert combine_with_retrieval([0.18, 0.57]) == [0, 1]


@pytest.mark.parametrize("procedimiento", ["r105b", "r106"])
def test_ronda91_perfil_del_egresado_sigue_primero(procedimiento):
    """Prueba histórica de afinidad de la Ronda 91 con ambos procedimientos."""
    fx = _escenario()
    fx.intents.save(Intent(
        project_id=P, name="Consultar perfil de egreso", description="Consulta el perfil de egreso.",
        positive_examples=["¿Qué conocimientos obtiene quien termina Gestión Profesional de Proyectos?"],
        required_variables=["programa_academico"],
    ))
    for i, (titulo, texto) in enumerate([
        ("Casos que requieren handoff", "conocimientos obtiene quien termina canalizar"),
        ("Perfil del egresado", "Al terminar domina la gestión de proyectos"),
    ]):
        _agrega(fx, "s-gpp", 10 + i, texto, section_title=titulo)
    _simulador(fx, procedimiento)
    trace = fx.simulate.execute(
        P, "¿Qué conocimientos obtiene quien termina la licenciatura en Gestión Profesional de Proyectos?", limit=3,
    )
    assert trace.matched_intent_name == "Consultar perfil de egreso"
    assert trace.section_ordering is True and trace.retrieval_pipeline == procedimiento
    assert trace.search_results[0].chunk.section_title == "Perfil del egresado"
