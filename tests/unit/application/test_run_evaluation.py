"""Pruebas unitarias de RunEvaluation (Etapa 6: banco de pruebas,
semáforos, regresión, bloqueos) -- reutiliza ConversationalService
(Etapa 5) con dobles de prueba en memoria, sin red ni Qdrant real."""
from domain.conversational.entities import GuardrailRule, Intent, RuleActionType, RuleType
from domain.documents.entities import Source, SourceType
from domain.ingestion.entities import Chunk
from domain.quality.entities import EvaluationVerdict, TestCategory, TestSeverity
from domain.rag.entities import VectorPoint

from .fakes_conversational import (
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryChunkRepository
from .fakes_metadata import InMemorySourceMetadataRepository
from .fakes_plugins import InMemoryPluginRepository
from .fakes_quality import InMemoryEvaluationRunRepository, InMemoryTestCaseRepository
from .fakes_rag import FakeEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository
from application.conversational.service import ConversationalService
from application.quality.commands.run_evaluation import RunEvaluation
from application.rag.service import RagService


def _index_chunk(chunk_repo, embedder, store, project_id, chunk: Chunk) -> None:
    chunk_repo.save_many(project_id, [chunk])
    [vector] = embedder.embed_texts([chunk.text])
    store.ensure_collection(project_id, embedder.dimensions)
    store.upsert(project_id, [VectorPoint(id=chunk.id, vector=vector, payload={"source_id": chunk.source_id})])


class Fixture:
    def __init__(self):
        self.sources = InMemorySourceRepository()
        self.chunks = InMemoryChunkRepository()
        self.embedder = FakeEmbeddingProvider()
        self.store = FakeVectorStore()
        self.rag = RagService(
            self.chunks, self.embedder, self.store, InMemoryIndexInfoRepository(), source_repository=self.sources,
        )
        self.intents = InMemoryIntentRepository()
        self.variables = InMemoryConversationalVariableRepository()
        self.guardrails = InMemoryGuardrailRuleRepository()
        self.channeling = InMemoryChannelingSchemeRepository()
        self.source_metadata = InMemorySourceMetadataRepository()
        self.conversational = ConversationalService(
            self.intents, self.variables, self.guardrails, self.channeling, self.source_metadata, self.rag,
        )
        self.test_cases = InMemoryTestCaseRepository()
        self.runs = InMemoryEvaluationRunRepository()
        self.run_evaluation = RunEvaluation(self.test_cases, self.runs, self.conversational)

    def add_validated_source_with_chunk(self, source_id: str, text: str) -> Source:
        source = Source(id=source_id, project_id="p1", title=f"Fuente {source_id}", source_type=SourceType.TXT, validation_status="validado")
        self.sources.save(source)
        chunk = Chunk(project_id="p1", source_id=source_id, chunk_index=0, text=text, token_count=len(text.split()))
        _index_chunk(self.chunks, self.embedder, self.store, "p1", chunk)
        return source


def test_run_evaluation_marks_verde_when_everything_matches_expectations():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-001", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")

    assert len(run.items) == 1
    assert run.items[0].verdict == EvaluationVerdict.VERDE
    assert run.overall_verdict == EvaluationVerdict.VERDE
    assert run.has_blocking_failures is False


def test_run_evaluation_marks_rojo_when_forbidden_action_happens():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "informacion general del programa")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["informacion general del programa"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-002", category=TestCategory.RESPUESTA_CONDICIONADA,
        query_text="informacion general del programa", forbidden_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")

    assert run.items[0].verdict == EvaluationVerdict.ROJO
    assert any("prohibida" in m for m in run.items[0].mismatches)
    assert run.has_blocking_failures is True


def test_run_evaluation_action_mismatch_severity_controls_rojo_vs_amarillo():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar horarios", positive_examples=["a qué hora abren"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-ALTA", category=TestCategory.SIN_INFORMACION,
        query_text="quiero cancelar mi tarjeta de crédito", expected_action=RuleActionType.RESPONDER,
        severity=TestSeverity.ALTA,
    ))
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-BAJA", category=TestCategory.SIN_INFORMACION,
        query_text="quiero cancelar mi tarjeta de crédito", expected_action=RuleActionType.RESPONDER,
        severity=TestSeverity.BAJA,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    by_code = {item.test_case_code: item for item in run.items}
    assert by_code["TEST-ALTA"].verdict == EvaluationVerdict.ROJO
    assert by_code["TEST-BAJA"].verdict == EvaluationVerdict.AMARILLO


def test_run_evaluation_marks_amarillo_when_expected_intent_differs():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "informacion sobre horarios de atencion")
    fx.intents.save(Intent(project_id="p1", name="Consultar horarios", positive_examples=["horarios de atencion"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-003", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="horarios de atencion", expected_intent="Otra intención distinta",
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.AMARILLO


def test_run_evaluation_marks_amarillo_when_expected_missing_variable_absent():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "informacion general")
    fx.intents.save(Intent(project_id="p1", name="Consultar información", positive_examples=["informacion general"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-004", category=TestCategory.RESPUESTA_CONDICIONADA,
        query_text="informacion general", expected_missing_variable="programa",
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.AMARILLO
    assert any("dato faltante" in m for m in run.items[0].mismatches)


def test_run_evaluation_marks_amarillo_when_channeling_expected_but_not_generated():
    fx = Fixture()
    fx.intents.save(Intent(
        project_id="p1", name="Dar de baja", positive_examples=["quiero darme de baja"],
        fallback_channeling_code="no-existe",
    ))
    fx.guardrails.save(GuardrailRule(
        project_id="p1", name="Siempre canaliza", rule_type=RuleType.CANALIZACION,
        conditions=[], action=RuleActionType.CANALIZAR,
    ))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-005", category=TestCategory.CON_CANALIZACION,
        query_text="quiero darme de baja", expected_channeling=True,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.AMARILLO
    assert any("canalización" in m for m in run.items[0].mismatches)


def test_run_evaluation_marks_amarillo_when_expected_source_differs():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s-correcta", "requisitos generales del programa correcto")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos generales del programa"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-006", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos generales del programa", expected_source_id="s-otra-fuente",
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.AMARILLO
    # ADR-003, Pista A.1: la fuente esperada nunca aparece entre los
    # resultados (no existe en el índice) -- retrieval_check_applicable
    # debe quedar en True (sí se declaró una fuente esperada) pero el
    # rango en None (nunca se encontró, no es lo mismo que "no aplica").
    assert run.items[0].retrieval_check_applicable is True
    assert run.items[0].expected_source_rank is None
    assert run.recall_at_k(3) == 0.0


# ---------- ADR-003, Pista A.1: rango de la fuente esperada ----------

def _fake_trace_with_search_results(source_ids_in_order: list[str]):
    """Construye un SimulationTrace mínimo con resultados de búsqueda
    en el orden dado -- permite controlar exactamente en qué posición
    aparece cada fuente, sin depender del ruido determinista de
    FakeEmbeddingProvider (que no refleja similitud semántica real)."""
    from application.conversational.queries.simulate_conversation import SimulationTrace
    from application.rag.queries.semantic_search import SemanticSearchResult
    from domain.conversational.entities import RuleActionType
    from domain.ingestion.entities import Chunk

    results = [
        SemanticSearchResult(
            chunk=Chunk(project_id="p1", source_id=source_id, chunk_index=0, text="x", token_count=1),
            score=1.0,
        )
        for source_id in source_ids_in_order
    ]
    return SimulationTrace(query_text="consulta", action=RuleActionType.RESPONDER, search_results=results)


def test_run_evaluation_records_the_rank_where_the_expected_source_was_found_beyond_first_place():
    fx = Fixture()
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-RANK", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="consulta", expected_source_id="s-tercera",
    ))
    fx.conversational.simulate = lambda *args, **kwargs: _fake_trace_with_search_results(
        ["s-primera", "s-segunda", "s-tercera", "s-cuarta"]
    )

    run = fx.run_evaluation.execute("p1", scope="completa")

    assert run.items[0].retrieval_check_applicable is True
    assert run.items[0].expected_source_rank == 3
    # El veredicto AMARILLO existente no cambia (sigue exigiendo el
    # PRIMER lugar) -- este campo solo agrega la métrica cuantitativa.
    assert run.items[0].verdict == EvaluationVerdict.AMARILLO
    assert run.recall_at_k(3) == 1.0  # dentro de los primeros 3
    assert run.recall_at_k(2) == 0.0  # fuera de los primeros 2


def test_run_evaluation_leaves_rank_none_when_expected_source_never_appears_in_results():
    fx = Fixture()
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-NORANK", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="consulta", expected_source_id="s-inexistente",
    ))
    fx.conversational.simulate = lambda *args, **kwargs: _fake_trace_with_search_results(["s-otra"])

    run = fx.run_evaluation.execute("p1", scope="completa")

    assert run.items[0].retrieval_check_applicable is True
    assert run.items[0].expected_source_rank is None
    assert run.recall_at_k(5) == 0.0


def test_run_evaluation_marks_gris_and_isolates_fault_when_simulation_raises():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar algo", positive_examples=["consulta buena"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(project_id="p1", code="TEST-BUENO", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta buena"))
    fx.test_cases.save(TestCase(project_id="p1", code="TEST-MALO", category=TestCategory.ERROR_TECNICO, query_text="consulta que falla"))

    original_simulate = fx.conversational.simulate

    def _flaky(project_id, query_text, **kwargs):
        if query_text == "consulta que falla":
            raise RuntimeError("sin red para el modelo de embeddings")
        return original_simulate(project_id, query_text, **kwargs)

    fx.conversational.simulate = _flaky

    run = fx.run_evaluation.execute("p1", scope="completa")
    by_code = {item.test_case_code: item for item in run.items}
    assert by_code["TEST-MALO"].verdict == EvaluationVerdict.GRIS
    assert "sin red" in by_code["TEST-MALO"].error
    # el caso bueno no se ve afectado por la falla del otro (aislamiento)
    assert by_code["TEST-BUENO"].verdict != EvaluationVerdict.GRIS


def test_run_evaluation_scope_completa_skips_inactive_cases():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar algo", positive_examples=["consulta"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(project_id="p1", code="ACTIVO", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta", active=True))
    fx.test_cases.save(TestCase(project_id="p1", code="INACTIVO", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta", active=False))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert [item.test_case_code for item in run.items] == ["ACTIVO"]


def test_run_evaluation_scope_categoria_filters_by_category():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar algo", positive_examples=["consulta"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(project_id="p1", code="A", category=TestCategory.SEGURIDAD, query_text="consulta"))
    fx.test_cases.save(TestCase(project_id="p1", code="B", category=TestCategory.PRIVACIDAD, query_text="consulta"))

    run = fx.run_evaluation.execute("p1", scope="categoria", category_filter=TestCategory.SEGURIDAD)
    assert [item.test_case_code for item in run.items] == ["A"]


def test_run_evaluation_scope_individual_runs_even_if_inactive():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar algo", positive_examples=["consulta"]))
    from domain.quality.entities import TestCase
    case = TestCase(project_id="p1", code="INACTIVO", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta", active=False)
    fx.test_cases.save(case)

    run = fx.run_evaluation.execute("p1", scope="individual", test_case_id_filter=case.id)
    assert [item.test_case_code for item in run.items] == ["INACTIVO"]


def test_run_evaluation_unknown_scope_raises_value_error():
    fx = Fixture()
    try:
        fx.run_evaluation.execute("p1", scope="lo-que-sea")
        raise AssertionError("debía lanzar ValueError")
    except ValueError:
        pass


def test_run_evaluation_detects_regression_against_previous_run():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    intent = Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"])
    fx.intents.save(intent)
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-REG", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    first = fx.run_evaluation.execute("p1", scope="completa")
    assert first.items[0].verdict == EvaluationVerdict.VERDE
    assert first.items[0].regressed is False

    # Se desactiva la intención -> la segunda corrida ya no puede
    # responder (se abstiene), lo que debe marcarse como regresión
    # respecto a la corrida anterior en VERDE.
    fx.intents.save(intent.model_copy(update={"active": False}))

    second = fx.run_evaluation.execute("p1", scope="completa")
    assert second.items[0].verdict != EvaluationVerdict.VERDE
    assert second.items[0].regressed is True


def test_run_evaluation_stops_early_when_cancelled_between_cases():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar algo", positive_examples=["consulta"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(project_id="p1", code="UNO", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta"))
    fx.test_cases.save(TestCase(project_id="p1", code="DOS", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta"))

    calls = {"n": 0}

    def is_cancelled():
        return calls["n"] >= 1

    original_run_one = fx.run_evaluation._run_one

    def _wrapped(*args, **kwargs):
        result = original_run_one(*args, **kwargs)
        calls["n"] += 1
        return result

    fx.run_evaluation._run_one = _wrapped

    run = fx.run_evaluation.execute("p1", scope="completa", is_cancelled=is_cancelled)
    assert len(run.items) == 1


def test_run_evaluation_saves_the_run_via_the_repository():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar algo", positive_examples=["consulta"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(project_id="p1", code="UNO", category=TestCategory.RESPUESTA_DIRECTA, query_text="consulta"))

    run = fx.run_evaluation.execute("p1", scope="completa")

    saved = fx.runs.get("p1", run.id)
    assert saved is not None
    assert len(saved.items) == len(run.items)


# ---------- Complementos EVALUADOR (Etapa 8) conectados a una corrida real ----------

def _with_plugin_repository(fx: Fixture) -> InMemoryPluginRepository:
    """Reconstruye fx.run_evaluation con un PluginRepository -- el
    Fixture base no lo pasa (para que las pruebas de arriba, sin
    complementos, sigan viendo el comportamiento de siempre)."""
    plugins = InMemoryPluginRepository()
    fx.run_evaluation = RunEvaluation(fx.test_cases, fx.runs, fx.conversational, plugin_repository=plugins)
    return plugins


def _register_evaluator(plugins: InMemoryPluginRepository, code: str, entry_point: str, enabled: bool = True) -> None:
    from domain.plugins.entities import Plugin, PluginKind
    plugins.save(Plugin(kind=PluginKind.EVALUADOR, code=code, name=code, entry_point=entry_point, enabled=enabled))


def test_run_evaluation_without_plugin_repository_behaves_exactly_as_before():
    # Ninguna prueba de arriba pasa plugin_repository -- este caso lo
    # deja explícito: sin él, RunEvaluation ni siquiera intenta mirar
    # complementos.
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-SIN-PLUGINS", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.VERDE


def test_run_evaluation_downgrades_to_amarillo_when_a_custom_evaluator_rejects():
    fx = Fixture()
    plugins = _with_plugin_repository(fx)
    _register_evaluator(
        plugins, "siempre-rechaza", "tests.unit.application.fakes_quality:AlwaysRejectCustomEvaluator",
    )
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-EVAL", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")

    assert run.items[0].verdict == EvaluationVerdict.AMARILLO
    assert any("siempre-rechaza" in m for m in run.items[0].mismatches)


def test_run_evaluation_ignores_a_disabled_custom_evaluator():
    fx = Fixture()
    plugins = _with_plugin_repository(fx)
    _register_evaluator(
        plugins, "desactivado", "tests.unit.application.fakes_quality:AlwaysRejectCustomEvaluator",
        enabled=False,
    )
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-DESACTIVADO", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.VERDE


def test_run_evaluation_ignores_a_custom_evaluator_with_a_broken_entry_point():
    fx = Fixture()
    plugins = _with_plugin_repository(fx)
    _register_evaluator(plugins, "roto", "no.such.module:Whatever")
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-ROTO", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    # Un complemento con entry_point roto no debe tumbar la corrida --
    # simplemente se descarta al armar la lista de evaluadores.
    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.VERDE


def test_run_evaluation_reports_amarillo_when_a_custom_evaluator_raises_at_runtime():
    fx = Fixture()
    plugins = _with_plugin_repository(fx)
    _register_evaluator(plugins, "se-cae", "tests.unit.application.fakes_quality:BrokenCustomEvaluator")
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-SE-CAE", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")

    assert run.items[0].verdict == EvaluationVerdict.AMARILLO
    assert any("se-cae" in m and "falló" in m for m in run.items[0].mismatches)


def test_run_evaluation_stays_verde_when_an_active_custom_evaluator_approves():
    fx = Fixture()
    plugins = _with_plugin_repository(fx)
    _register_evaluator(plugins, "siempre-aprueba", "tests.unit.application.fakes_quality:AlwaysApproveCustomEvaluator")
    fx.add_validated_source_with_chunk("s1", "requisitos de ingreso completos")
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos de ingreso"]))
    from domain.quality.entities import TestCase
    fx.test_cases.save(TestCase(
        project_id="p1", code="TEST-APRUEBA", category=TestCategory.RESPUESTA_DIRECTA,
        query_text="requisitos de ingreso", expected_action=RuleActionType.RESPONDER,
    ))

    run = fx.run_evaluation.execute("p1", scope="completa")
    assert run.items[0].verdict == EvaluationVerdict.VERDE
