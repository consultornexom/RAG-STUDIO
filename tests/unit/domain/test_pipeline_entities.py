"""Pruebas unitarias de las entidades del contexto Pipeline (Etapa 3:
pipeline reproducible)."""
from domain.pipeline.entities import (
    PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus,
)


def _item(status: PipelineItemStatus) -> PipelineRunItem:
    return PipelineRunItem(source_id="s1", source_title="Fuente", status=status)


def test_has_critical_errors_true_when_any_item_failed():
    run = PipelineRun(project_id="p1", items=[_item(PipelineItemStatus.EXITOSO), _item(PipelineItemStatus.FALLIDO)])
    assert run.has_critical_errors is True


def test_has_critical_errors_false_when_no_item_failed():
    run = PipelineRun(project_id="p1", items=[_item(PipelineItemStatus.EXITOSO), _item(PipelineItemStatus.OMITIDO)])
    assert run.has_critical_errors is False


def test_has_critical_errors_false_for_empty_run():
    run = PipelineRun(project_id="p1")
    assert run.has_critical_errors is False


def test_is_usable_as_index_base_only_when_status_is_completo():
    completo = PipelineRun(project_id="p1", status=PipelineRunStatus.COMPLETO)
    con_errores = PipelineRun(project_id="p1", status=PipelineRunStatus.COMPLETO_CON_ERRORES)
    cancelado = PipelineRun(project_id="p1", status=PipelineRunStatus.CANCELADO)
    en_curso = PipelineRun(project_id="p1", status=PipelineRunStatus.EN_CURSO)

    assert completo.is_usable_as_index_base is True
    assert con_errores.is_usable_as_index_base is False
    assert cancelado.is_usable_as_index_base is False
    assert en_curso.is_usable_as_index_base is False
