"""Pruebas unitarias de ReleaseService (fachada de application para el
contexto Liberación, Etapa 7) -- evaluación de compuertas, dictamen y
persistencia del historial, sobre los seis contextos previos
construidos con dobles en memoria (mismo patrón que
test_quality_service.py)."""
from datetime import datetime, timezone

from domain.pipeline.entities import PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus
from domain.projects.entities import Project
from domain.quality.entities import EvaluationResultItem, EvaluationRun, EvaluationVerdict, TestCategory
from domain.rag.entities import IndexInfo
from domain.release.entities import ReleaseStatus

from .fakes_conversational import (
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import (
    FakeTextExtractor, InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository,
)
from .fakes_metadata import InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository
from .fakes_pipeline import InMemoryPipelineRunRepository
from .fakes_quality import InMemoryEvaluationRunRepository, InMemoryTestCaseRepository
from .fakes_rag import FakeEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository
from .fakes import InMemoryProjectRepository
from .fakes_release import (
    FakeProjectSnapshotPublisher,
    InMemoryDeploymentPackager,
    InMemoryProjectSnapshotRepository,
    InMemoryReleasePackager,
    InMemoryReleaseRecordRepository,
)
from .fakes_runtime import InMemoryWidgetTokenRepository
from application.conversational.service import ConversationalService
from application.ingestion.service import IngestionService
from application.metadata.service import MetadataService
from application.pipeline.service import PipelineService
from application.quality.service import QualityService
from application.rag.service import RagService
from application.release.service import ReleaseService


class _Stack:
    """Agrupa los seis servicios reales (con dobles en memoria) más
    los repositorios que las pruebas necesitan tocar directamente para
    forzar cada compuerta a pasar o fallar."""

    def __init__(self, release_packager=None, deployment_packager=None):
        self.source_repository = InMemorySourceRepository()
        extraction_repository = InMemoryExtractionRepository()
        self.fragmentation_policy_repository = InMemoryFragmentationPolicyRepository()
        self.chunk_repository = InMemoryChunkRepository()
        self.schema_repository = InMemoryMetadataSchemaRepository()
        catalog_repository = InMemoryCatalogRepository()
        self.source_metadata_repository = InMemorySourceMetadataRepository()

        self.metadata_service = MetadataService(
            self.schema_repository, catalog_repository, self.source_metadata_repository, self.source_repository,
        )
        self.ingestion_service = IngestionService(
            self.source_repository, FakeTextExtractor(), extraction_repository,
            self.fragmentation_policy_repository, self.chunk_repository, self.schema_repository,
            self.source_metadata_repository,
        )
        self.index_info_repository = InMemoryIndexInfoRepository()
        self.rag_service = RagService(
            self.chunk_repository, FakeEmbeddingProvider(), FakeVectorStore(), self.index_info_repository,
        )
        self.pipeline_run_repository = InMemoryPipelineRunRepository()
        self.pipeline_service = PipelineService(
            self.source_repository, self.ingestion_service, self.rag_service, self.pipeline_run_repository,
        )
        self.conversational_service = ConversationalService(
            InMemoryIntentRepository(), InMemoryConversationalVariableRepository(),
            InMemoryGuardrailRuleRepository(), InMemoryChannelingSchemeRepository(),
            self.source_metadata_repository, self.rag_service,
        )
        self.test_case_repository = InMemoryTestCaseRepository()
        self.evaluation_run_repository = InMemoryEvaluationRunRepository()
        self.quality_service = QualityService(
            self.test_case_repository, self.evaluation_run_repository, self.conversational_service,
        )
        self.release_record_repository = InMemoryReleaseRecordRepository()
        # project_repository/snapshot_repository/snapshot_publisher
        # (ADR-002, Fase 1): opcionales, igual patrón que release_packager
        # -- se construyen aquí para que los tests de publish_snapshot no
        # necesiten su propio _Stack.
        self.project_repository = InMemoryProjectRepository()
        self.snapshot_repository = InMemoryProjectSnapshotRepository()
        self.snapshot_publisher = FakeProjectSnapshotPublisher()
        # widget_token_repository/deployment_packager (Ronda 10): mismo
        # patrón opcional -- widget_token_repository se construye siempre
        # (no toca disco, es en memoria) para que las pruebas del paquete
        # de entrega no necesiten su propio _Stack; deployment_packager
        # sigue siendo opcional, igual criterio que release_packager.
        self.widget_token_repository = InMemoryWidgetTokenRepository()
        self.release_service = ReleaseService(
            self.release_record_repository, self.metadata_service, self.ingestion_service, self.pipeline_service,
            self.rag_service, self.conversational_service, self.quality_service,
            release_packager=release_packager,
            project_repository=self.project_repository,
            snapshot_repository=self.snapshot_repository,
            snapshot_publisher=self.snapshot_publisher,
            widget_token_repository=self.widget_token_repository,
            deployment_packager=deployment_packager,
        )

    # ---------- atajos para forzar cada compuerta ----------
    def make_metadata_gate_pass(self, project_id: str) -> None:
        schema = self.metadata_service.create_schema(project_id)
        self.metadata_service.add_field_definition(project_id, schema.id, "titulo", "Título", "texto")

    def make_fragmentation_gate_pass(self, project_id: str) -> None:
        self.ingestion_service.set_fragmentation_policy(project_id, "default")

    def make_pipeline_gate_pass(self, project_id: str) -> None:
        self.pipeline_run_repository.save(PipelineRun(
            project_id=project_id, status=PipelineRunStatus.COMPLETO,
            items=[PipelineRunItem(
                source_id="s1", source_title="fuente 1", status=PipelineItemStatus.EXITOSO,
                started_at=datetime.now(timezone.utc),
            )],
        ))

    def make_index_gate_pass(self, project_id: str) -> None:
        self.index_info_repository.save(IndexInfo(
            project_id=project_id, embedding_provider="fake", embedding_model="fake-hash", dimensions=4,
            points_count=3,
        ))

    def make_conversational_gate_pass(self, project_id: str) -> None:
        self.conversational_service.create_intent(project_id, "consultar_horario", description="consultar horario")
        self.conversational_service.create_guardrail_rule(project_id, "regla base", "aclaracion")


def _make_stack(release_packager=None, deployment_packager=None) -> _Stack:
    return _Stack(release_packager=release_packager, deployment_packager=deployment_packager)


def test_all_gates_fail_on_a_brand_new_project():
    stack = _make_stack()
    checklist = stack.release_service.evaluate_gates("p1")
    assert checklist.all_passed is False
    assert len(checklist.gates) == 7
    # Ronda 53: "Regresión de recuperación" es la única excepción
    # deliberada -- nunca bloquea por falta de datos (menos de dos
    # corridas "completa"), esa responsabilidad ya es de "Calidad".
    other_gates = [g for g in checklist.gates if g.name != "Regresión de recuperación"]
    assert {gate.passed for gate in other_gates} == {False}
    regression_gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert regression_gate.passed is True


def test_metadata_gate_passes_once_schema_has_fields():
    stack = _make_stack()
    stack.make_metadata_gate_pass("p1")
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Metadatos")
    assert gate.passed is True


def test_fragmentation_gate_passes_once_a_policy_exists():
    stack = _make_stack()
    stack.make_fragmentation_gate_pass("p1")
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Fragmentación")
    assert gate.passed is True


def test_pipeline_gate_fails_when_last_run_is_not_usable_as_index_base():
    stack = _make_stack()
    stack.pipeline_run_repository.save(PipelineRun(project_id="p1", status=PipelineRunStatus.EN_CURSO))
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Pipeline reproducible")
    assert gate.passed is False


def test_pipeline_gate_passes_when_last_run_is_usable_as_index_base():
    stack = _make_stack()
    stack.make_pipeline_gate_pass("p1")
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Pipeline reproducible")
    assert gate.passed is True


def test_index_gate_fails_when_index_has_zero_points():
    stack = _make_stack()
    stack.index_info_repository.save(IndexInfo(
        project_id="p1", embedding_provider="fake", embedding_model="fake-hash", dimensions=4, points_count=0,
    ))
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Índice y recuperación")
    assert gate.passed is False


def test_index_gate_passes_when_index_has_points():
    stack = _make_stack()
    stack.make_index_gate_pass("p1")
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Índice y recuperación")
    assert gate.passed is True


def test_conversational_gate_requires_active_intent_and_active_guardrail():
    stack = _make_stack()
    stack.conversational_service.create_intent("p1", "consultar_horario", description="consultar horario")
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Diseño conversacional")
    assert gate.passed is False  # falta guardrail

    stack.conversational_service.create_guardrail_rule("p1", "regla base", "aclaracion")
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Diseño conversacional")
    assert gate.passed is True


def test_quality_gate_fails_without_test_cases_even_with_a_passing_run():
    stack = _make_stack()
    stack.evaluation_run_repository.save(EvaluationRun(project_id="p1", items=[]))
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Calidad")
    assert gate.passed is False


def test_quality_gate_fails_when_last_run_has_blocking_failures():
    stack = _make_stack()
    stack.quality_service.create_test_case("p1", "TEST-001", "respuesta_directa", "consulta")
    stack.evaluation_run_repository.save(EvaluationRun(
        project_id="p1",
        items=[EvaluationResultItem(
            test_case_id="tc1", test_case_code="TEST-001", category=TestCategory.RESPUESTA_DIRECTA,
            verdict=EvaluationVerdict.ROJO,
        )],
    ))
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Calidad")
    assert gate.passed is False


def test_quality_gate_passes_with_test_cases_and_a_clean_run():
    stack = _make_stack()
    stack.quality_service.create_test_case("p1", "TEST-001", "respuesta_directa", "consulta")
    stack.evaluation_run_repository.save(EvaluationRun(
        project_id="p1",
        items=[EvaluationResultItem(
            test_case_id="tc1", test_case_code="TEST-001", category=TestCategory.RESPUESTA_DIRECTA,
            verdict=EvaluationVerdict.VERDE,
        )],
    ))
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Calidad")
    assert gate.passed is True


def test_request_release_is_bloqueada_when_gates_fail_and_persists_it():
    stack = _make_stack()
    record = stack.release_service.request_release("p1")
    assert record.status == ReleaseStatus.BLOQUEADA
    assert record.checklist.all_passed is False
    assert "bloqueada" in record.dictamen.lower()
    assert stack.release_service.list_release_records("p1") == [record]
    assert stack.release_service.get_release_record("p1", record.id).id == record.id


def test_request_release_is_aprobada_when_every_gate_passes():
    stack = _make_stack()
    stack.make_metadata_gate_pass("p1")
    stack.make_fragmentation_gate_pass("p1")
    stack.make_pipeline_gate_pass("p1")
    stack.make_index_gate_pass("p1")
    stack.make_conversational_gate_pass("p1")
    stack.quality_service.create_test_case("p1", "TEST-001", "respuesta_directa", "consulta")
    stack.evaluation_run_repository.save(EvaluationRun(
        project_id="p1",
        items=[EvaluationResultItem(
            test_case_id="tc1", test_case_code="TEST-001", category=TestCategory.RESPUESTA_DIRECTA,
            verdict=EvaluationVerdict.VERDE,
        )],
    ))

    record = stack.release_service.request_release("p1")
    assert record.status == ReleaseStatus.APROBADA
    assert record.checklist.all_passed is True
    assert set(record.deliverables_report.keys()) == {
        "especificacion_metadatos", "diseno_fragmentacion", "pipeline_reproducible", "indice_y_recuperacion",
        "catalogo_reglas", "esquema_canalizacion", "banco_de_pruebas", "matriz_resultados_esperados",
    }
    assert record.deliverables_report["indice_y_recuperacion"]["fragmentos_indexados"] == 3
    # Ronda 3/4 (punto 12): el entregable de especificación de metadatos
    # debe reflejar document_type_code -- None significa campo genérico
    # (aplica a todas las fuentes), no un campo omitido por accidente.
    campo_titulo = next(
        c for c in record.deliverables_report["especificacion_metadatos"]["campos"]
        if c["field_id"] == "titulo"
    )
    assert campo_titulo["document_type_code"] is None


# ---------- "Regresión de recuperación" (Ronda 53, opción B') ----------

def _retrieval_item(rank, code: str = "T1") -> EvaluationResultItem:
    return EvaluationResultItem(
        test_case_id="tc1", test_case_code=code, category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE, retrieval_check_applicable=True, expected_source_rank=rank,
    )


def _save_complete_run(stack, project_id: str, started_at, items) -> None:
    stack.evaluation_run_repository.save(EvaluationRun(
        project_id=project_id, scope="completa", started_at=started_at, items=items,
    ))


def test_regression_gate_passes_with_fewer_than_two_complete_runs():
    stack = _make_stack()
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is True

    _save_complete_run(
        stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc), [_retrieval_item(rank=1)],
    )
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is True  # todavía solo una corrida "completa"


def test_regression_gate_passes_when_neither_run_has_retrieval_applicable_items():
    stack = _make_stack()
    no_retrieval_item = EvaluationResultItem(
        test_case_id="tc1", test_case_code="T1", category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE,
    )
    _save_complete_run(stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc), [no_retrieval_item])
    _save_complete_run(stack, "p1", datetime(2026, 1, 2, tzinfo=timezone.utc), [no_retrieval_item])
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is True
    assert "Menos de dos corridas" not in gate.reason
    assert "no tiene casos con fuente esperada declarada" in gate.reason


def test_regression_gate_reports_no_comparable_previous_run_when_only_the_most_recent_has_metrics():
    # Ronda 84 -- reporte real de usuario: la corrida más reciente sí
    # calculó Recall@3/MRR (4 casos con fuente esperada, todos en el
    # primer lugar), pero la corrida "completa" anterior no tenía
    # ningún caso con fuente esperada declarada. Antes de esta ronda, el
    # mensaje decía incorrectamente que "ninguna de las dos" tenía
    # métricas -- debe distinguir este caso y seguir sin bloquear.
    stack = _make_stack()
    no_retrieval_item = EvaluationResultItem(
        test_case_id="tc1", test_case_code="T1", category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE,
    )
    _save_complete_run(stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc), [no_retrieval_item])
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(4)],
    )
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is True
    assert "Ninguna de las dos" not in gate.reason
    assert "la corrida" in gate.reason.lower() and "anterior" in gate.reason.lower()
    assert "no tiene métricas Recall@3/MRR disponibles" in gate.reason
    assert "todavía no existe una base comparable" in gate.reason


def test_regression_gate_fails_when_recall_drops_beyond_the_default_threshold():
    stack = _make_stack()
    # Referencia: 4 casos, los 4 encontraron la fuente esperada en el
    # primer lugar (Recall@3 = 1.0, MRR = 1.0).
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(4)],
    )
    # Corrida actual: 3 de 4 la siguen encontrando, 1 ya no aparece --
    # Recall@3 = 0.75, caída del 25% respecto de 1.0, por encima del
    # umbral por defecto (15%).
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(3)] + [_retrieval_item(rank=None, code="T3")],
    )
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is False
    assert "75%" in gate.reason or "0.75" in gate.reason or "25%" in gate.reason


def test_regression_gate_passes_when_drop_is_within_the_default_threshold():
    stack = _make_stack()
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(20)],
    )
    # 18 de 20 -- Recall@3 = 0.9, caída del 10%, dentro del umbral por
    # defecto (15%).
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(18)]
        + [_retrieval_item(rank=None, code=f"T{i}") for i in range(18, 20)],
    )
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is True


def test_regression_gate_uses_the_project_configured_threshold_instead_of_the_default():
    stack = _make_stack()
    stack.project_repository.save(Project(id="p1", name="Proyecto Uno", quality_regression_threshold=0.5))
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(4)],
    )
    # Misma caída del 25% que en test_regression_gate_fails_...: con el
    # umbral por defecto (15%) bloquearía, pero este proyecto configuró
    # un umbral más permisivo (50%).
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(3)] + [_retrieval_item(rank=None, code="T3")],
    )
    checklist = stack.release_service.evaluate_gates("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is True


def test_regression_gate_falls_back_to_the_default_threshold_without_a_project_repository():
    from application.release.queries.evaluate_release_gates import EvaluateReleaseGates

    stack = _make_stack()
    gates_without_project_repository = EvaluateReleaseGates(
        stack.metadata_service, stack.ingestion_service, stack.pipeline_service, stack.rag_service,
        stack.conversational_service, stack.quality_service,
    )
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 1, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(4)],
    )
    _save_complete_run(
        stack, "p1", datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(3)] + [_retrieval_item(rank=None, code="T3")],
    )
    checklist = gates_without_project_repository.execute("p1")
    gate = next(g for g in checklist.gates if g.name == "Regresión de recuperación")
    assert gate.passed is False  # 25% de caída sigue por encima del 15% por defecto


# ---------- paquete exportable de entregables (ítem 6 de la
# evaluación de madurez post-8-etapas) ----------

def test_export_deliverables_package_delegates_to_the_configured_packager():
    packager = InMemoryReleasePackager()
    stack = _make_stack(release_packager=packager)
    record = stack.release_service.request_release("p1")

    result_path = stack.release_service.export_deliverables_package("p1", record.id, "/tmp/salida.zip")

    assert result_path == "/tmp/salida.zip"
    assert len(packager.calls) == 1
    exported_record, destination = packager.calls[0]
    assert exported_record.id == record.id
    assert destination == "/tmp/salida.zip"


def test_export_deliverables_package_raises_without_a_configured_packager():
    stack = _make_stack()  # sin release_packager -- capacidad opcional sin configurar
    record = stack.release_service.request_release("p1")

    try:
        stack.release_service.export_deliverables_package("p1", record.id, "/tmp/salida.zip")
        raise AssertionError("debía fallar sin un release_packager configurado")
    except RuntimeError:
        pass


def test_export_deliverables_package_raises_for_unknown_record():
    from domain.release.exceptions import ReleaseRecordNotFoundError

    packager = InMemoryReleasePackager()
    stack = _make_stack(release_packager=packager)
    try:
        stack.release_service.export_deliverables_package("p1", "no-existe", "/tmp/salida.zip")
        raise AssertionError("debía fallar para un record_id inexistente")
    except ReleaseRecordNotFoundError:
        pass
    assert packager.calls == []


# ---------- instantáneas publicadas de proyecto (ADR-002, Fase 1) ----------

def test_publish_snapshot_delegates_to_the_configured_publisher():
    stack = _make_stack()
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))

    snapshot = stack.release_service.publish_snapshot("p1")

    assert snapshot.project_id == "p1"
    assert snapshot.version == 1
    assert snapshot.snapshot_dir == "/fake/snapshots/p1/v1"
    assert stack.snapshot_publisher.calls == [("p1", 1)]
    assert stack.release_service.list_snapshots("p1") == [snapshot]


def test_publish_snapshot_increments_version_on_each_call():
    stack = _make_stack()
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))

    first = stack.release_service.publish_snapshot("p1")
    second = stack.release_service.publish_snapshot("p1")

    assert (first.version, second.version) == (1, 2)
    assert [s.version for s in stack.release_service.list_snapshots("p1")] == [2, 1]


def test_publish_snapshot_keeps_the_optional_source_release_id():
    stack = _make_stack()
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    record = stack.release_service.request_release("p1")

    snapshot = stack.release_service.publish_snapshot("p1", source_release_id=record.id)

    assert snapshot.source_release_id == record.id


def test_publish_snapshot_raises_for_unknown_project():
    from domain.projects.exceptions import ProjectNotFoundError

    stack = _make_stack()
    try:
        stack.release_service.publish_snapshot("no-existe")
        raise AssertionError("debía fallar para un proyecto inexistente")
    except ProjectNotFoundError:
        pass
    assert stack.snapshot_publisher.calls == []


def test_publish_snapshot_raises_without_configured_snapshot_dependencies():
    # Mismo criterio que export_deliverables_package sin release_packager:
    # las tres dependencias de instantáneas son opcionales a nivel de
    # ReleaseService -- construir el servicio sin ellas no debe fallar,
    # solo la llamada a publish_snapshot.
    stack = _make_stack()
    stack.release_service = ReleaseService(
        stack.release_record_repository, stack.metadata_service, stack.ingestion_service,
        stack.pipeline_service, stack.rag_service, stack.conversational_service, stack.quality_service,
    )
    try:
        stack.release_service.publish_snapshot("p1")
        raise AssertionError("debía fallar sin project_repository/snapshot_repository/snapshot_publisher")
    except RuntimeError:
        pass
    assert stack.release_service.list_snapshots("p1") == []


def test_list_snapshots_is_isolated_per_project():
    stack = _make_stack()
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    stack.project_repository.save(Project(id="p2", name="Proyecto 2"))

    stack.release_service.publish_snapshot("p1")
    stack.release_service.publish_snapshot("p2")

    assert [s.project_id for s in stack.release_service.list_snapshots("p1")] == ["p1"]
    assert [s.project_id for s in stack.release_service.list_snapshots("p2")] == ["p2"]


def test_release_records_are_isolated_per_project():
    stack = _make_stack()
    stack.release_service.request_release("p1")
    assert stack.release_service.list_release_records("p2") == []


# ---------- paquete de entrega al cliente (Ronda 10) ----------

def test_export_deployment_package_delegates_to_the_configured_packager():
    packager = InMemoryDeploymentPackager()
    stack = _make_stack(deployment_packager=packager)
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    stack.release_service.publish_snapshot("p1")

    result_path = stack.release_service.export_deployment_package("p1", "/tmp/entrega.zip")

    assert result_path == "/tmp/entrega.zip"
    assert len(packager.calls) == 1
    package, destination = packager.calls[0]
    assert destination == "/tmp/entrega.zip"
    assert package.project_id == "p1"
    assert package.project_name == "Proyecto 1"
    assert package.snapshot_version == 1
    assert package.snapshot_dir == "/fake/snapshots/p1/v1"
    assert "Proyecto 1" in package.informe
    assert package.widget_token in package.widget_snippet
    # La guía documenta el ID del token (para poder revocarlo sin
    # ambigüedad, ver hallazgo B7 de la Ronda 10) -- no el valor
    # completo, que solo vive en widget-embed.html.
    assert package.widget_token_id in package.guia_despliegue
    assert package.widget_token not in package.guia_despliegue


def test_export_deployment_package_issues_a_fresh_widget_token_scoped_to_the_project():
    packager = InMemoryDeploymentPackager()
    stack = _make_stack(deployment_packager=packager)
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    stack.release_service.publish_snapshot("p1")

    stack.release_service.export_deployment_package("p1", "/tmp/entrega.zip")

    tokens = stack.widget_token_repository.list_for_project("p1")
    assert len(tokens) == 1
    assert tokens[0].is_active is True
    package, _ = packager.calls[0]
    assert tokens[0].token == package.widget_token
    assert tokens[0].id == package.widget_token_id


def test_export_deployment_package_revokes_the_just_issued_token_if_the_packager_fails():
    # Ronda 10, hallazgo B5: un fallo del empaquetador (aquí, forzado)
    # no debe dejar un token de widget activo sin que nadie lo sepa.
    class _FailingPackager(InMemoryDeploymentPackager):
        def export(self, package, destination_path):
            raise OSError("disco lleno (forzado por la prueba)")

    stack = _make_stack(deployment_packager=_FailingPackager())
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    stack.release_service.publish_snapshot("p1")

    try:
        stack.release_service.export_deployment_package("p1", "/tmp/entrega.zip")
        raise AssertionError("debía propagar el error del empaquetador")
    except OSError:
        pass

    tokens = stack.widget_token_repository.list_for_project("p1")
    assert len(tokens) == 1
    assert tokens[0].is_active is False  # revocado, no huérfano


def test_export_deployment_package_raises_without_a_published_snapshot():
    from domain.release.exceptions import NoPublishedSnapshotError

    packager = InMemoryDeploymentPackager()
    stack = _make_stack(deployment_packager=packager)
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))

    try:
        stack.release_service.export_deployment_package("p1", "/tmp/entrega.zip")
        raise AssertionError("debía fallar sin ninguna instantánea publicada")
    except NoPublishedSnapshotError:
        pass
    assert packager.calls == []
    assert stack.widget_token_repository.list_for_project("p1") == []


def test_export_deployment_package_raises_for_unknown_project():
    from domain.projects.exceptions import ProjectNotFoundError

    packager = InMemoryDeploymentPackager()
    stack = _make_stack(deployment_packager=packager)

    try:
        stack.release_service.export_deployment_package("no-existe", "/tmp/entrega.zip")
        raise AssertionError("debía fallar para un proyecto inexistente")
    except ProjectNotFoundError:
        pass
    assert packager.calls == []


def test_export_deployment_package_raises_without_a_configured_packager():
    stack = _make_stack()  # sin deployment_packager -- capacidad opcional sin configurar
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    stack.release_service.publish_snapshot("p1")

    try:
        stack.release_service.export_deployment_package("p1", "/tmp/entrega.zip")
        raise AssertionError("debía fallar sin un deployment_packager configurado")
    except RuntimeError:
        pass


def test_export_deployment_package_uses_the_latest_published_snapshot():
    packager = InMemoryDeploymentPackager()
    stack = _make_stack(deployment_packager=packager)
    stack.project_repository.save(Project(id="p1", name="Proyecto 1"))
    stack.release_service.publish_snapshot("p1")
    stack.release_service.publish_snapshot("p1")

    stack.release_service.export_deployment_package("p1", "/tmp/entrega.zip")

    package, _ = packager.calls[0]
    assert package.snapshot_version == 2
