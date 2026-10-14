"""Implementación concreta de los 2 repositorios del contexto Calidad
(ADR-001, sección 4)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select

from domain.conversational.entities import RuleActionType
from domain.quality.entities import (
    EvaluationResultItem, EvaluationRun, EvaluationVerdict, TestCase, TestCategory, TestSeverity,
)
from domain.quality.ports import EvaluationRunRepository, TestCaseRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import EvaluationResultItemRecord, EvaluationRunRecord, TestCaseRecord


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyTestCaseRepository(TestCaseRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, test_case: TestCase) -> None:
        with _session_factory_for(self._paths, test_case.project_id)() as session:
            record = session.get(TestCaseRecord, test_case.id)
            if record is None:
                record = TestCaseRecord(id=test_case.id, project_id=test_case.project_id)
                session.add(record)
            record.code = test_case.code
            record.category = test_case.category.value
            record.query_text = test_case.query_text
            record.provided_variables = json.dumps(test_case.provided_variables)
            record.source_id = test_case.source_id
            record.expected_intent = test_case.expected_intent
            record.expected_missing_variable = test_case.expected_missing_variable
            record.expected_action = test_case.expected_action.value if test_case.expected_action else None
            record.forbidden_action = test_case.forbidden_action.value if test_case.forbidden_action else None
            record.expected_channeling = test_case.expected_channeling
            record.expected_source_id = test_case.expected_source_id
            record.severity = test_case.severity.value
            record.active = test_case.active
            record.created_at = test_case.created_at
            record.updated_at = test_case.updated_at
            session.commit()

    def get(self, project_id: str, test_case_id: str) -> Optional[TestCase]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(TestCaseRecord, test_case_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_test_case(record)

    def list_for_project(self, project_id: str) -> list[TestCase]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(TestCaseRecord).where(TestCaseRecord.project_id == project_id).order_by(TestCaseRecord.code)
            ).scalars().all()
            return [_record_to_test_case(record) for record in records]

    def delete(self, project_id: str, test_case_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(TestCaseRecord, test_case_id)
            if record is not None and record.project_id == project_id:
                session.delete(record)
                session.commit()


class SqlAlchemyEvaluationRunRepository(EvaluationRunRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, run: EvaluationRun) -> None:
        # Igual que PipelineRunRepository: se guarda completa cada vez
        # (RunEvaluation llama a save() una sola vez, al terminar la
        # corrida), no hace falta un upsert incremental por item.
        with _session_factory_for(self._paths, run.project_id)() as session:
            session.add(EvaluationRunRecord(
                id=run.id, project_id=run.project_id, scope=run.scope,
                category_filter=run.category_filter.value if run.category_filter else None,
                test_case_id_filter=run.test_case_id_filter,
                started_at=run.started_at, finished_at=run.finished_at,
            ))
            for item in run.items:
                session.add(EvaluationResultItemRecord(
                    id=item.id, run_id=run.id, project_id=run.project_id, test_case_id=item.test_case_id,
                    test_case_code=item.test_case_code, category=item.category.value, verdict=item.verdict.value,
                    actual_intent=item.actual_intent,
                    actual_action=item.actual_action.value if item.actual_action else None,
                    actual_channeling_code=item.actual_channeling_code,
                    mismatches=json.dumps(item.mismatches), regressed=item.regressed, error=item.error,
                    retrieval_check_applicable=item.retrieval_check_applicable,
                    expected_source_rank=item.expected_source_rank,
                ))
            session.commit()

    def get(self, project_id: str, run_id: str) -> Optional[EvaluationRun]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(EvaluationRunRecord, run_id)
            if record is None or record.project_id != project_id:
                return None
            item_records = session.execute(
                select(EvaluationResultItemRecord).where(EvaluationResultItemRecord.run_id == run_id)
            ).scalars().all()
            return _record_to_run(record, item_records)

    def list_for_project(self, project_id: str) -> list[EvaluationRun]:
        with _session_factory_for(self._paths, project_id)() as session:
            run_records = session.execute(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.project_id == project_id)
                .order_by(EvaluationRunRecord.started_at.desc())
            ).scalars().all()
            runs = []
            for run_record in run_records:
                item_records = session.execute(
                    select(EvaluationResultItemRecord).where(EvaluationResultItemRecord.run_id == run_record.id)
                ).scalars().all()
                runs.append(_record_to_run(run_record, item_records))
            return runs

    def get_last_run(self, project_id: str) -> Optional[EvaluationRun]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.project_id == project_id)
                .order_by(EvaluationRunRecord.started_at.desc())
            ).scalars().first()
            if record is None:
                return None
            item_records = session.execute(
                select(EvaluationResultItemRecord).where(EvaluationResultItemRecord.run_id == record.id)
            ).scalars().all()
            return _record_to_run(record, item_records)


def _record_to_test_case(record: TestCaseRecord) -> TestCase:
    return TestCase(
        id=record.id, project_id=record.project_id, code=record.code, category=TestCategory(record.category),
        query_text=record.query_text, provided_variables=json.loads(record.provided_variables),
        source_id=record.source_id, expected_intent=record.expected_intent,
        expected_missing_variable=record.expected_missing_variable,
        expected_action=RuleActionType(record.expected_action) if record.expected_action else None,
        forbidden_action=RuleActionType(record.forbidden_action) if record.forbidden_action else None,
        expected_channeling=record.expected_channeling, expected_source_id=record.expected_source_id,
        severity=TestSeverity(record.severity), active=record.active,
        created_at=record.created_at, updated_at=record.updated_at,
    )


def _record_to_run(record: EvaluationRunRecord, item_records: list[EvaluationResultItemRecord]) -> EvaluationRun:
    return EvaluationRun(
        id=record.id, project_id=record.project_id, scope=record.scope,
        category_filter=TestCategory(record.category_filter) if record.category_filter else None,
        test_case_id_filter=record.test_case_id_filter,
        items=[_record_to_item(item) for item in item_records],
        started_at=record.started_at, finished_at=record.finished_at,
    )


def _record_to_item(record: EvaluationResultItemRecord) -> EvaluationResultItem:
    return EvaluationResultItem(
        id=record.id, test_case_id=record.test_case_id, test_case_code=record.test_case_code,
        category=TestCategory(record.category), verdict=EvaluationVerdict(record.verdict),
        actual_intent=record.actual_intent,
        actual_action=RuleActionType(record.actual_action) if record.actual_action else None,
        actual_channeling_code=record.actual_channeling_code, mismatches=json.loads(record.mismatches),
        regressed=record.regressed, error=record.error,
        retrieval_check_applicable=record.retrieval_check_applicable,
        expected_source_rank=record.expected_source_rank,
    )
