"""Corrida del banco de pruebas (Etapa 6, "Calidad": banco de pruebas,
evaluación, regresión, semáforos, bloqueos por hallazgos críticos).

`RunEvaluation` reutiliza `ConversationalService.simulate` (Etapa 5)
tal cual -- cada TestCase es, en el fondo, una llamada al simulador con
una consulta y unas variables ya "proporcionadas", comparando el
`SimulationTrace` resultante contra lo que el caso espera. No
reimplementa nada del motor conversacional.

Desde la evaluación de madurez posterior a las 8 etapas: además de los
criterios integrados, `RunEvaluation` ahora también invoca los
complementos de tipo EVALUADOR registrados y activos en Etapa 8
(`domain.plugins`) -- cerraba una brecha real entre "mecanismo
construido" (registrar y validar un `CustomEvaluator`) y "mecanismo
conectado" (que de verdad participe en una corrida). Es capacidad
opcional, igual que `embedding_provider_factory` en `RagService`: quien
construye `RunEvaluation` sin `plugin_repository` (la mayoría de las
pruebas existentes) no ve ningún cambio de comportamiento.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from application.conversational.service import ConversationalService
from domain.plugins.entities import PluginKind
from domain.plugins.loader import load_and_validate
from domain.plugins.ports import CustomEvaluator, PluginRepository
from domain.quality.entities import (
    EvaluationResultItem, EvaluationRun, EvaluationVerdict, TestCase, TestCategory, TestSeverity,
    most_severe_verdict,
)
from domain.quality.ports import EvaluationRunRepository, TestCaseRepository
from domain.runtime.failures import FailureStage

from application.runtime.failure_diagnosis import (
    diagnose_exception,
    format_evaluation_error,
    format_traceback,
)

logger = logging.getLogger(__name__)


class RunEvaluation:
    def __init__(
        self, test_case_repository: TestCaseRepository, evaluation_run_repository: EvaluationRunRepository,
        conversational_service: ConversationalService, plugin_repository: Optional[PluginRepository] = None,
    ):
        self._test_cases = test_case_repository
        self._runs = evaluation_run_repository
        self._conversational = conversational_service
        self._plugins = plugin_repository

    def execute(
        self, project_id: str, scope: str = "completa",
        category_filter: Optional[TestCategory] = None, test_case_id_filter: Optional[str] = None,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> EvaluationRun:
        selected = self._select_test_cases(project_id, scope, category_filter, test_case_id_filter)

        # La comparación de regresión usa la corrida anterior COMPLETA
        # del proyecto (cualquier alcance) -- si un caso estaba en
        # VERDE ahí y deja de estarlo ahora, es una regresión real, sin
        # importar si la corrida anterior fue "completa" o "por
        # categoría".
        last_run = self._runs.get_last_run(project_id)
        previous_verdict_by_code = {item.test_case_code: item.verdict for item in last_run.items} if last_run else {}

        # Se cargan una sola vez por corrida (no por caso de prueba):
        # los complementos EVALUADOR activos son globales a la
        # instalación, no cambian a mitad de una corrida.
        custom_evaluators = self._load_custom_evaluators()

        run = EvaluationRun(
            project_id=project_id, scope=scope, category_filter=category_filter,
            test_case_id_filter=test_case_id_filter,
        )
        for test_case in selected:
            if is_cancelled():
                break
            run.items.append(self._run_one(project_id, test_case, previous_verdict_by_code, custom_evaluators))

        run.finished_at = datetime.now(timezone.utc)
        self._runs.save(run)
        return run

    def _select_test_cases(
        self, project_id: str, scope: str, category_filter: Optional[TestCategory],
        test_case_id_filter: Optional[str],
    ) -> list[TestCase]:
        all_cases = self._test_cases.list_for_project(project_id)
        if scope == "completa":
            return [case for case in all_cases if case.active]
        if scope == "categoria":
            return [case for case in all_cases if case.active and case.category == category_filter]
        if scope == "individual":
            # Una corrida individual se pide explícitamente sobre un
            # caso concreto -- se ejecuta aunque esté desactivado, a
            # diferencia de "completa"/"categoria" (que solo recorren
            # el banco vigente).
            return [case for case in all_cases if case.id == test_case_id_filter]
        raise ValueError(f"Alcance de evaluación desconocido: {scope!r}")

    def _load_custom_evaluators(self) -> list[tuple[str, CustomEvaluator]]:
        """Instancias listas para usarse de cada complemento EVALUADOR
        activo -- se resuelven una sola vez por corrida (ver `execute`).
        Un complemento roto (entry_point inválido, no implementa el
        contrato, falla al instanciar) se omite para esta corrida sin
        abortar el resto: la validación explícita ya vive en Complementos
        ("Validar seleccionado"), `RunEvaluation` no es quien debe
        re-diagnosticar la salud de un complemento."""
        if self._plugins is None:
            return []
        evaluators: list[tuple[str, CustomEvaluator]] = []
        for plugin in self._plugins.list_by_kind(PluginKind.EVALUADOR):
            if not plugin.enabled:
                continue
            try:
                evaluator_class = load_and_validate(plugin)
                evaluators.append((plugin.code, evaluator_class()))
            # Swallow deliberado (ver docstring del método): no oculta un problema de seguridad, bandit avisa igual.
            except Exception:  # noqa: BLE001  # nosec B112
                continue
        return evaluators

    def _run_one(
        self, project_id: str, test_case: TestCase, previous_verdict_by_code: dict[str, EvaluationVerdict],
        custom_evaluators: list[tuple[str, CustomEvaluator]],
    ) -> EvaluationResultItem:
        try:
            trace = self._conversational.simulate(
                project_id, test_case.query_text, provided_variables=test_case.provided_variables,
                source_id=test_case.source_id,
            )
        except Exception as exc:  # noqa: BLE001 - aislamiento de fallas, mismo criterio que RunPipeline
            # Ronda 93 (auditoría del hallazgo "caso failed sin categoría"):
            # antes se guardaba solo str(exc) -- vacío para excepciones sin
            # mensaje (KeyError(), AssertionError()...), y la pestaña Calidad
            # mostraba el caso gris SIN ninguna causa; además no quedaba
            # rastro en el registro. Ahora se clasifica con el mismo
            # diagnóstico que el runtime y se deja la traza en el log.
            diagnosis = diagnose_exception(exc, FailureStage.MOTOR_CONVERSACIONAL)
            logger.error(
                "Caso %s no evaluable -- categoria=%s etapa=%s codigo=%s\n%s",
                test_case.code, diagnosis.category.value, diagnosis.stage.value, diagnosis.code,
                format_traceback(exc),
            )
            return EvaluationResultItem(
                test_case_id=test_case.id, test_case_code=test_case.code, category=test_case.category,
                verdict=EvaluationVerdict.GRIS, error=format_evaluation_error(diagnosis),
            )

        mismatches: list[str] = []
        verdicts: list[EvaluationVerdict] = []

        if test_case.forbidden_action is not None and trace.action == test_case.forbidden_action:
            mismatches.append(f"Se ejecutó la acción prohibida: {trace.action.value}")
            verdicts.append(EvaluationVerdict.ROJO)

        if test_case.expected_action is not None and trace.action != test_case.expected_action:
            mismatches.append(f"Acción esperada: {test_case.expected_action.value} -- se obtuvo: {trace.action.value}")
            severe = test_case.severity in (TestSeverity.ALTA, TestSeverity.CRITICA)
            verdicts.append(EvaluationVerdict.ROJO if severe else EvaluationVerdict.AMARILLO)

        if test_case.expected_intent is not None and trace.matched_intent_name != test_case.expected_intent:
            mismatches.append(
                f"Intención esperada: {test_case.expected_intent!r} -- se obtuvo: {trace.matched_intent_name!r}"
            )
            verdicts.append(EvaluationVerdict.AMARILLO)

        if (
            test_case.expected_missing_variable is not None
            and test_case.expected_missing_variable not in trace.missing_variables
        ):
            mismatches.append(f"Se esperaba el dato faltante {test_case.expected_missing_variable!r}, no apareció")
            verdicts.append(EvaluationVerdict.AMARILLO)

        if test_case.expected_channeling and trace.channeling is None:
            # Ronda 87: decir POR QUÉ no hubo paquete, para que quien
            # prueba sepa qué corregir (intención, regla o esquema).
            if trace.channeling_note:
                detalle = f" ({trace.channeling_note})"
            elif not trace.matched_intent_name:
                detalle = " (ninguna intención coincidió con la consulta)"
            elif trace.action.value != "canalizar":
                detalle = (
                    f" (la decisión fue {trace.action.value!r}: ninguna regla de guardrail activa con "
                    "acción 'canalizar' cumplió sus condiciones)"
                )
            else:
                detalle = ""
            mismatches.append("Se esperaba un paquete de canalización, pero no se generó ninguno" + detalle)
            verdicts.append(EvaluationVerdict.AMARILLO)

        retrieval_check_applicable = False
        expected_source_rank: Optional[int] = None
        if test_case.expected_source_id is not None:
            # ADR-003, Pista A.1: además del criterio de aprobado/
            # rechazado ya existente (el PRIMER resultado debe ser la
            # fuente esperada), se registra en qué posición apareció
            # esa fuente entre TODOS los resultados de esta simulación
            # -- sin esto, EvaluationRun.recall_at_k no tendría ningún
            # dato del que partir, y antes de esta ronda esa posición
            # se descartaba en cuanto se sabía que no era la primera.
            retrieval_check_applicable = True
            top_source = trace.search_results[0].chunk.source_id if trace.search_results else None
            if top_source != test_case.expected_source_id:
                mismatches.append(
                    f"Se esperaba el primer resultado de la fuente {test_case.expected_source_id!r}, "
                    f"se obtuvo {top_source!r}"
                )
                verdicts.append(EvaluationVerdict.AMARILLO)
            for rank, result in enumerate(trace.search_results, start=1):
                if result.chunk.source_id == test_case.expected_source_id:
                    expected_source_rank = rank
                    break

        # Complementos EVALUADOR (Etapa 8): criterios adicionales más
        # allá de lo que compara el propio RunEvaluation por defecto.
        # Un evaluador personalizado que rechaza el caso cuenta como
        # AMARILLO ("requiere revisión") -- el contrato no expone una
        # noción de severidad propia, así que se trata igual que el
        # resto de discrepancias "blandas" (p. ej. intención esperada
        # distinta), reservando ROJO para lo que ya bloquea hoy
        # (acción prohibida, acción esperada con severidad alta/crítica).
        # Si el propio evaluador lanza una excepción al ejecutarse, se
        # reporta como discrepancia en vez de tumbar el resto del caso
        # (mismo criterio de aislamiento de fallas que el resto de
        # RunEvaluation).
        for code, evaluator in custom_evaluators:
            try:
                approved, reason = evaluator.evaluate(trace, test_case)
            except Exception as exc:  # noqa: BLE001 - un evaluador roto no debe tumbar el caso
                mismatches.append(f"El evaluador personalizado {code!r} falló al ejecutarse: {exc}")
                verdicts.append(EvaluationVerdict.AMARILLO)
                continue
            if not approved:
                mismatches.append(f"Evaluador personalizado {code!r}: {reason}")
                verdicts.append(EvaluationVerdict.AMARILLO)

        verdict = most_severe_verdict(verdicts) if verdicts else EvaluationVerdict.VERDE
        regressed = previous_verdict_by_code.get(test_case.code) == EvaluationVerdict.VERDE and verdict != EvaluationVerdict.VERDE

        return EvaluationResultItem(
            test_case_id=test_case.id, test_case_code=test_case.code, category=test_case.category, verdict=verdict,
            actual_intent=trace.matched_intent_name, actual_action=trace.action,
            actual_channeling_code=(trace.channeling.code if trace.channeling else None),
            mismatches=mismatches, regressed=regressed,
            retrieval_check_applicable=retrieval_check_applicable, expected_source_rank=expected_source_rank,
        )
