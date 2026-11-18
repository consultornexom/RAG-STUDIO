"""Ronda 102 (hallazgo real de NEXOM, LOTE01_Bachillerato): C1 (afinidad
combinada con la búsqueda), C2 (título de fragmentos sin sección) y C4
(ajuste "Reranking en el agente" visible en el trazado)."""
import pytest

from domain.conversational.entities import Intent, RuleActionType
from domain.ingestion.entities import Chunk
from domain.rag.entities import VectorPoint

from application.conversational.queries.simulate_conversation import SimulateConversation
from application.rag.service import RagService

from .fakes_conversational import InMemoryChannelingSchemeRepository, InMemoryGuardrailRuleRepository
from .fakes_rag import FakeReranker, InMemoryIndexInfoRepository
from .test_simulate_conversation_variables import P, Fx, _escenario


def _con_simulador(fx: Fx, *, reranker=None, ajuste=None) -> list:
    """Reemplaza el simulador del escenario por uno con reranker/ajuste;
    devuelve la lista donde se anotan los `rerank=` recibidos."""
    rag = RagService(fx.chunks, fx.embedder, fx.store, InMemoryIndexInfoRepository(), source_repository=fx.sources,
                     reranker=reranker)
    recibidos: list = []
    original = rag.search_hybrid

    def espia(*args, **kwargs):
        recibidos.append(kwargs.get("rerank"))
        return original(*args, **kwargs)

    rag.search_hybrid = espia  # type: ignore[method-assign]
    fx.simulate = SimulateConversation(
        fx.intents, fx.variables, InMemoryGuardrailRuleRepository(), InMemoryChannelingSchemeRepository(),
        fx.metadata, rag, source_repository=fx.sources, schema_repository=fx.schemas, catalog_repository=fx.catalogs,
        agent_reranking=(lambda _pid: ajuste),
    )
    return recibidos


CONSULTA = "cual es el objetivo del programa Gestión Profesional de Proyectos"


@pytest.mark.parametrize("ajuste, con_modelo, aplicado, etiqueta", [
    # Ronda 105b (P1, alternativa B estricta): Automático = sin reranking
    # aunque haya modelo (antes lo aplicaba en el Simulador).
    (None, True, False, "automatico"),
    (None, False, False, "automatico"),
    (True, True, True, "activado"),
    (False, True, False, "desactivado"),
])
def test_reranking_del_agente_segun_ajuste_del_proyecto(ajuste, con_modelo, aplicado, etiqueta):
    fx = _escenario()
    recibidos = _con_simulador(fx, reranker=FakeReranker("modelo-x") if con_modelo else None, ajuste=ajuste)
    trace = fx.simulate.execute(P, CONSULTA)
    assert trace.action == RuleActionType.RESPONDER
    assert recibidos == [aplicado]
    assert trace.reranking_setting == etiqueta
    assert trace.reranking_applied is aplicado
    assert trace.reranking_model == ("modelo-x" if aplicado else None)
    assert trace.reranking_note is None
    assert trace.runtime_effective_reranking == ("con_reranking" if aplicado else "sin_reranking")
    assert trace.reranking_model_status == ("cargado" if aplicado else "no_requerido")


def test_reranking_activado_sin_modelo_falla_de_forma_explicita():
    """Ronda 105b (P1, B estricta): antes se respondía sin reranking con un
    aviso; ahora la consulta falla con un error explícito."""
    from domain.rag.exceptions import RerankingRequiredUnavailableError

    fx = _escenario()
    recibidos = _con_simulador(fx, reranker=None, ajuste=True)
    with pytest.raises(RerankingRequiredUnavailableError, match="Activado"):
        fx.simulate.execute(P, CONSULTA)
    assert recibidos == []


def test_reranking_activado_con_modelo_que_no_carga_falla_de_forma_explicita():
    from domain.rag.exceptions import RerankerError, RerankingRequiredUnavailableError

    class NoCarga(FakeReranker):
        def ensure_ready(self):
            raise RerankerError("sin red para descargar el modelo")

        @property
        def is_loaded(self):
            return False

    fx = _escenario()
    _con_simulador(fx, reranker=NoCarga("modelo-x"), ajuste=True)
    with pytest.raises(RerankingRequiredUnavailableError, match="no se pudo cargar"):
        fx.simulate.execute(P, CONSULTA)


def test_sin_ajuste_configurado_el_comportamiento_es_el_de_antes():
    """Sin agent_reranking (construcción anterior a la Ronda 102):
    automático, igual que antes."""
    fx = _escenario()
    trace = fx.simulate.execute(P, CONSULTA)
    assert trace.reranking_setting == "automatico" and trace.reranking_applied is False


def _agrega(fx: Fx, source_id: str, indice: int, texto: str, section_title=None) -> None:
    chunk = Chunk(project_id=P, source_id=source_id, chunk_index=indice, text=texto, token_count=len(texto.split()),
                  section_title=section_title)
    fx.chunks.save_many(P, [chunk])
    [vector] = fx.embedder.embed_texts([texto])
    fx.store.upsert(P, [VectorPoint(id=chunk.id, vector=vector, payload={"source_id": source_id})])


def test_trazado_separa_puesto_en_la_busqueda_y_afinidad():
    fx = _escenario()
    fx.intents.save(Intent(
        project_id=P, name="Consultar requisitos de ingreso", description="Requisitos de ingreso al programa.",
        positive_examples=["¿Qué necesito para ingresar a Gestión Profesional de Proyectos?"],
        required_variables=["programa_academico"],
    ))
    fx.fuente("s-req", "gestion_profesional_de_proyectos", [])
    # Documento completo con encabezado YAML: sin section_title; antes su
    # "título" era "---" (afinidad cero).
    _agrega(fx, "s-req", 0, "---\nnivel: x\n---\n# Requisitos de ingreso\nCURP y acta. necesito ingresar requisitos")
    trace = fx.simulate.execute(P, "¿Qué necesito para ingresar a Gestión Profesional de Proyectos?")
    assert trace.matched_intent_name == "Consultar requisitos de ingreso"
    assert len(trace.result_ordering) == len(trace.search_results) > 0
    primero = trace.result_ordering[0]
    assert primero.affinity_title == "Requisitos de ingreso" and primero.affinity > 0
    assert all(o.retrieval_rank >= 1 for o in trace.result_ordering)


def test_fragmento_sin_titulo_ni_encabezado_usa_el_titulo_de_la_fuente():
    fx = _escenario()
    fx.intents.save(Intent(
        project_id=P, name="Consultar requisitos de ingreso", description="Requisitos de ingreso al programa.",
        positive_examples=["¿Qué necesito para ingresar a Gestión Profesional de Proyectos?"],
        required_variables=["programa_academico"],
    ))
    fx.fuente("requisitos_ingreso.md", "gestion_profesional_de_proyectos", [])
    _agrega(fx, "requisitos_ingreso.md", 0, "CURP, acta de nacimiento; necesito ingresar")
    trace = fx.simulate.execute(P, "¿Qué necesito para ingresar a Gestión Profesional de Proyectos?")
    titulos = {o.affinity_title for o in trace.result_ordering}
    assert "requisitos_ingreso" in titulos
