"""Pruebas unitarias de HandleIncomingMessage (ADR-002, Fase 2) --
con un ConversationalService de doble en memoria (solo expone
`.simulate`, mismo criterio de las demás pruebas de application que no
necesitan la pila completa de repositorios). La cobertura de punta a
punta contra Qdrant/SQLite/FastAPI real vive en
tests/integration/test_runtime_api.py; aquí se prueban específicamente
las cuatro ramas de `_response_text_for` (incluyendo abstenerse y
canalizar, que esa prueba de integración no ejercita) y el registro en
la bitácora."""
from __future__ import annotations

from application.conversational.queries.simulate_conversation import SimulationTrace
from application.rag.queries.semantic_search import SemanticSearchResult
from application.runtime.commands.handle_incoming_message import HandleIncomingMessage
from domain.conversational.entities import ChannelingMedium, ChannelingScheme, RuleActionType
from domain.ingestion.entities import Chunk

from .fakes_runtime import FakeChannelingDispatcher, InMemoryConversationLogRepository


class _FakeConversationalService:
    """Devuelve una SimulationTrace fija, sin construir ningún
    repositorio real -- HandleIncomingMessage solo llama a
    `.simulate(project_id, message, provided_variables)`, igual firma
    que ConversationalService.simulate."""

    def __init__(self, trace: SimulationTrace):
        self._trace = trace
        self.calls: list[tuple[str, str, dict]] = []

    def simulate(
        self, project_id, query_text, provided_variables=None, source_id=None, limit=5,
        max_access_level=None,
    ):
        self.calls.append((project_id, query_text, provided_variables or {}))
        return self._trace


def _handle(trace: SimulationTrace):
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    handler = HandleIncomingMessage(service, log_repository)
    handled = handler.execute("p1", 3, trace.query_text, provided_variables=trace.provided_variables)
    return handled, service, log_repository


def test_responder_leaves_response_text_none_and_lists_the_retrieved_sources():
    chunk = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="El horario es de 9 a 17.", token_count=8)
    trace = SimulationTrace(
        query_text="¿cuál es el horario?", matched_intent_name="Consultar horario", confidence=0.8,
        action=RuleActionType.RESPONDER, search_results=[SemanticSearchResult(chunk=chunk, score=0.9)],
    )
    handled, _service, log_repository = _handle(trace)

    assert handled.log_entry.response_text is None  # sin paso de generación de lenguaje natural
    assert handled.log_entry.source_ids == ["s1"]
    assert handled.log_entry.action == "responder"
    assert handled.log_entry.matched_intent == "Consultar horario"
    assert handled.log_entry.confidence == 0.8
    assert log_repository.list_for_project("p1") == [handled.log_entry]


def test_aclarar_uses_the_clarifying_question_as_response_text():
    trace = SimulationTrace(
        query_text="quiero información", matched_intent_name="Consultar admisión", confidence=0.6,
        action=RuleActionType.ACLARAR, missing_variables=["plantel"],
        clarifying_question="¿En qué plantel te interesa?",
    )
    handled, _service, _log = _handle(trace)

    assert handled.log_entry.response_text == "¿En qué plantel te interesa?"
    assert handled.log_entry.source_ids == []


def test_abstenerse_uses_the_abstention_reason_as_response_text():
    trace = SimulationTrace(
        query_text="pregunta rara", action=RuleActionType.ABSTENERSE,
        abstention_reason="Ninguna intención activa coincide con esta consulta.",
    )
    handled, _service, _log = _handle(trace)

    assert handled.log_entry.response_text == "Ninguna intención activa coincide con esta consulta."
    assert handled.log_entry.matched_intent is None


def test_canalizar_uses_the_channeling_scheme_user_message():
    channeling = ChannelingScheme(
        project_id="p1", code="mesa_ayuda", name="Mesa de ayuda",
        user_message="Un asesor te contactará pronto.",
    )
    trace = SimulationTrace(
        query_text="quiero hablar con alguien", action=RuleActionType.CANALIZAR, channeling=channeling,
    )
    handled, _service, _log = _handle(trace)

    assert handled.log_entry.response_text == "Un asesor te contactará pronto."


def test_canalizar_without_a_resolved_channeling_scheme_leaves_response_text_none():
    trace = SimulationTrace(query_text="quiero hablar con alguien", action=RuleActionType.CANALIZAR, channeling=None)
    handled, _service, _log = _handle(trace)

    assert handled.log_entry.response_text is None


def test_canalizar_dispatches_to_the_channeling_dispatcher_when_configured():
    channeling = ChannelingScheme(
        project_id="p1", code="mesa_ayuda", name="Mesa de ayuda", medium=ChannelingMedium.MESA_AYUDA,
        target_area="Soporte", reason="Consulta compleja", user_message="Un asesor te contactará pronto.",
    )
    trace = SimulationTrace(
        query_text="quiero hablar con alguien", matched_intent_name="Escalar", action=RuleActionType.CANALIZAR,
        channeling=channeling,
    )
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    dispatcher = FakeChannelingDispatcher()
    handler = HandleIncomingMessage(service, log_repository, channeling_dispatcher=dispatcher)

    handled = handler.execute("p1", 3, "quiero hablar con alguien")

    assert len(dispatcher.calls) == 1
    payload = dispatcher.calls[0]
    assert payload.project_id == "p1"
    assert payload.log_id == handled.log_entry.id
    assert payload.code == "mesa_ayuda"
    assert payload.medium == "mesa_ayuda"
    assert payload.target_area == "Soporte"
    assert payload.matched_intent == "Escalar"


def test_canalizar_without_a_dispatcher_configured_does_not_fail():
    channeling = ChannelingScheme(project_id="p1", code="mesa_ayuda", name="Mesa de ayuda")
    trace = SimulationTrace(query_text="hola", action=RuleActionType.CANALIZAR, channeling=channeling)
    handled, _service, _log = _handle(trace)  # sin channeling_dispatcher -- mismo comportamiento que la Fase 2.

    assert handled.log_entry.action == "canalizar"


def test_a_dispatch_failure_does_not_propagate_and_the_conversation_is_still_logged():
    channeling = ChannelingScheme(project_id="p1", code="mesa_ayuda", name="Mesa de ayuda", user_message="Ok.")
    trace = SimulationTrace(query_text="hola", action=RuleActionType.CANALIZAR, channeling=channeling)
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    dispatcher = FakeChannelingDispatcher(fail_with=RuntimeError("el webhook está caído"))
    handler = HandleIncomingMessage(service, log_repository, channeling_dispatcher=dispatcher)

    handled = handler.execute("p1", 1, "hola")  # no debe levantar la excepción del dispatcher.

    assert handled.log_entry.response_text == "Ok."
    assert log_repository.list_for_project("p1") == [handled.log_entry]


def test_responder_never_calls_the_channeling_dispatcher():
    chunk = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="texto", token_count=1)
    trace = SimulationTrace(
        query_text="hola", action=RuleActionType.RESPONDER, search_results=[SemanticSearchResult(chunk=chunk, score=0.9)],
    )
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    dispatcher = FakeChannelingDispatcher()
    handler = HandleIncomingMessage(service, log_repository, channeling_dispatcher=dispatcher)

    handler.execute("p1", 1, "hola")

    assert dispatcher.calls == []


def test_execute_generates_a_new_conversation_id_when_none_is_given():
    trace = SimulationTrace(query_text="hola", action=RuleActionType.ABSTENERSE)
    handled, _service, _log = _handle(trace)

    assert handled.log_entry.conversation_id  # no vacío
    assert isinstance(handled.log_entry.conversation_id, str)


def test_execute_generates_different_conversation_ids_for_independent_calls():
    service = _FakeConversationalService(SimulationTrace(query_text="hola", action=RuleActionType.ABSTENERSE))
    log_repository = InMemoryConversationLogRepository()
    handler = HandleIncomingMessage(service, log_repository)

    first = handler.execute("p1", 1, "hola")
    second = handler.execute("p1", 1, "hola de nuevo")

    assert first.log_entry.conversation_id != second.log_entry.conversation_id


def test_execute_preserves_the_conversation_id_given_by_the_caller():
    service = _FakeConversationalService(SimulationTrace(query_text="hola", action=RuleActionType.ABSTENERSE))
    log_repository = InMemoryConversationLogRepository()
    handler = HandleIncomingMessage(service, log_repository)

    handled = handler.execute("p1", 1, "hola", conversation_id="conv-fija-123")

    assert handled.log_entry.conversation_id == "conv-fija-123"


def test_execute_with_the_same_conversation_id_groups_turns_in_the_repository():
    service = _FakeConversationalService(SimulationTrace(query_text="hola", action=RuleActionType.ABSTENERSE))
    log_repository = InMemoryConversationLogRepository()
    handler = HandleIncomingMessage(service, log_repository)

    first = handler.execute("p1", 1, "hola", conversation_id="conv-1")
    second = handler.execute("p1", 1, "otra vez", conversation_id="conv-1")

    thread = log_repository.list_for_conversation("p1", "conv-1")
    assert [entry.id for entry in thread] == [first.log_entry.id, second.log_entry.id]


def test_auto_dispatch_channeling_false_does_not_dispatch_inside_execute():
    # Auditoría Ronda 46, hallazgo #146, corregido en la Ronda 51:
    # interfaces/api/app.py llama a execute() con
    # auto_dispatch_channeling=False para poder soltar loaded.lock
    # ANTES de entregar el evento de canalización (que puede tardar
    # varios segundos en reintentos/espera si el webhook está caído).
    channeling = ChannelingScheme(project_id="p1", code="mesa_ayuda", name="Mesa de ayuda", user_message="Ok.")
    trace = SimulationTrace(query_text="hola", action=RuleActionType.CANALIZAR, channeling=channeling)
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    dispatcher = FakeChannelingDispatcher()
    handler = HandleIncomingMessage(service, log_repository, channeling_dispatcher=dispatcher)

    handled = handler.execute("p1", 1, "hola", auto_dispatch_channeling=False)

    assert dispatcher.calls == []  # todavía no se despachó nada
    assert handled.log_entry.response_text == "Ok."  # el resto de execute() sí corrió normal


def test_dispatch_channeling_can_be_called_separately_after_execute():
    # Continuación del caso anterior: quien llama con
    # auto_dispatch_channeling=False es responsable de invocar
    # dispatch_channeling() por su cuenta -- típicamente después de
    # soltar el lock que protege a execute().
    channeling = ChannelingScheme(
        project_id="p1", code="mesa_ayuda", name="Mesa de ayuda", target_area="Soporte", user_message="Ok.",
    )
    trace = SimulationTrace(
        query_text="hola", matched_intent_name="Escalar", action=RuleActionType.CANALIZAR, channeling=channeling,
    )
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    dispatcher = FakeChannelingDispatcher()
    handler = HandleIncomingMessage(service, log_repository, channeling_dispatcher=dispatcher)

    handled = handler.execute("p1", 1, "hola", auto_dispatch_channeling=False)
    handler.dispatch_channeling("p1", handled.log_entry, handled.trace)

    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0].code == "mesa_ayuda"


def test_dispatch_channeling_called_directly_is_a_no_op_for_a_non_canalizar_trace():
    # Los tres guardas de dispatch_channeling() deben poder llamarse
    # sin condición previa (así lo hace interfaces/api/app.py) -- una
    # acción que no fue "canalizar" no debe intentar nada.
    trace = SimulationTrace(query_text="hola", action=RuleActionType.ABSTENERSE, abstention_reason="No aplica.")
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    dispatcher = FakeChannelingDispatcher()
    handler = HandleIncomingMessage(service, log_repository, channeling_dispatcher=dispatcher)

    handled = handler.execute("p1", 1, "hola", auto_dispatch_channeling=False)
    handler.dispatch_channeling("p1", handled.log_entry, handled.trace)  # no debe fallar ni despachar

    assert dispatcher.calls == []


def test_execute_passes_through_project_id_snapshot_version_and_provided_variables():
    trace = SimulationTrace(
        query_text="hola", provided_variables={"plantel": "Campus Norte"}, action=RuleActionType.ABSTENERSE,
    )
    service = _FakeConversationalService(trace)
    log_repository = InMemoryConversationLogRepository()
    handler = HandleIncomingMessage(service, log_repository)

    handled = handler.execute("p1", 7, "hola", provided_variables={"plantel": "Campus Norte"})

    assert service.calls == [("p1", "hola", {"plantel": "Campus Norte"})]
    assert handled.log_entry.project_id == "p1"
    assert handled.log_entry.snapshot_version == 7
    assert handled.log_entry.latency_ms is not None and handled.log_entry.latency_ms >= 0
