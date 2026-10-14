"""Entidades del contexto Calidad (Etapa 6: "banco de pruebas, centro
de evaluación, regresión, comparación entre corridas, semáforos,
bloqueos automáticos por hallazgos críticos").

RAG STUDIO.odt documenta el banco de pruebas (B4) y sus criterios de
aceptación (B5) sobre el motor conversacional de Etapa 5 -- no sobre
texto generado por un modelo de lenguaje: "la pieza central no es el
modelo generativo ni la base vectorial" sigue aplicando aquí. Por eso
`TestCase` compara contra lo que `SimulationTrace` (Etapa 5) sí produce
(intención, variables, acción, canalización, fuente/fragmento
recuperado) y no contra criterios que exigirían juzgar una respuesta en
lenguaje natural (p. ej. "claridad", "citación", "ausencia de
invenciones" del documento maestro) -- ver README, "Limitaciones
conocidas", para el detalle de qué criterios quedan fuera de alcance
por esta misma razón.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Optional

from pydantic import BaseModel, Field

from domain.conversational.entities import RuleActionType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TestCategory(str, Enum):
    """Las 5 categorías obligatorias más las "imprescindibles" del
    documento maestro (RAG STUDIO.odt, B4)."""

    __test__ = False
    """No es una clase de prueba de pytest -- el nombre "TestCategory"
    viene del vocabulario del propio documento maestro ("casos de
    prueba"); sin este atributo, pytest intenta recolectarla como tal
    en cualquier módulo de pruebas que la importe."""

    RESPUESTA_DIRECTA = "respuesta_directa"
    RESPUESTA_CONDICIONADA = "respuesta_condicionada"
    CONSULTA_AMBIGUA = "consulta_ambigua"
    SIN_INFORMACION = "sin_informacion"
    CON_CANALIZACION = "con_canalizacion"
    CONTRADICCION = "contradiccion"
    FUENTE_VENCIDA = "fuente_vencida"
    FUENTE_NO_VALIDADA = "fuente_no_validada"
    PRIVACIDAD = "privacidad"
    SEGURIDAD = "seguridad"
    CAMBIO_INTENCION = "cambio_intencion"
    CONVERSACION_MULTIVUELTA = "conversacion_multivuelta"
    ERROR_TECNICO = "error_tecnico"
    MANIPULACION_INSTRUCCIONES = "manipulacion_instrucciones"


class TestSeverity(str, Enum):
    __test__ = False

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


class TestCase(BaseModel):
    """Un caso del banco de pruebas (RAG STUDIO.odt, ejemplo real:
    "ID: TEST-ADM-001 / Intención esperada: consultar requisitos /
    Datos proporcionados: programa / Dato faltante: plantel / Acción
    esperada: preguntar plantel / Acción prohibida: responder
    requisitos específicos / Canalización: no / Severidad: alta").

    Cada campo esperado es opcional -- un caso puede verificar solo lo
    que le importa (p. ej. un caso de "sin información" solo necesita
    `expected_action=ABSTENERSE`, sin preocuparse de qué intención se
    detectó)."""

    __test__: ClassVar[bool] = False
    """No es una clase de prueba de pytest -- ver la nota equivalente
    en TestCategory."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    code: str
    """Identificador legible del caso (p. ej. "TEST-ADM-001") -- no es
    el `id` interno, es el que aparece en reportes y comparaciones
    entre corridas."""
    category: TestCategory
    query_text: str
    provided_variables: dict[str, str] = Field(default_factory=dict)
    """"Datos proporcionados" -- variables que ya "sabe" la
    conversación simulada antes de esta consulta."""
    source_id: Optional[str] = None
    """Restringe la simulación a una sola fuente (opcional) -- mismo
    parámetro que ya acepta SimulateConversation."""
    expected_intent: Optional[str] = None
    expected_missing_variable: Optional[str] = None
    """"Dato faltante" -- se espera que esta variable aparezca en
    `SimulationTrace.missing_variables`."""
    expected_action: Optional[RuleActionType] = None
    forbidden_action: Optional[RuleActionType] = None
    """"Acción prohibida" -- si el simulador llega a esta acción, es un
    hallazgo crítico (verdicto ROJO) sin importar la severidad
    declarada del caso."""
    expected_channeling: bool = False
    """"Canalización: sí/no" -- si es True, se espera que la
    simulación termine generando un paquete de canalización real (no
    solo la decisión "canalizar" sin esquema configurado)."""
    expected_source_id: Optional[str] = None
    """"Documento correcto"/"Posición" (criterios de aceptación B5):
    se espera que el primer resultado recuperado venga de esta
    fuente."""
    severity: TestSeverity = TestSeverity.MEDIA
    active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class EvaluationVerdict(str, Enum):
    """Semáforos exactos del documento maestro: "Verde: aprobado.
    Amarillo: requiere revisión. Rojo: bloqueo. Gris: no ejecutado."""

    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"
    GRIS = "gris"


_VERDICT_SEVERITY: dict[EvaluationVerdict, int] = {
    EvaluationVerdict.VERDE: 0,
    EvaluationVerdict.AMARILLO: 1,
    EvaluationVerdict.ROJO: 2,
    EvaluationVerdict.GRIS: 3,
}
"""Para combinar varios hallazgos sobre el mismo caso: gana el
veredicto más severo, nunca el primero por casualidad de orden --
mismo criterio que ACTION_SEVERITY en domain.conversational.entities."""


def most_severe_verdict(verdicts: list[EvaluationVerdict]) -> EvaluationVerdict:
    if not verdicts:
        return EvaluationVerdict.VERDE
    return max(verdicts, key=lambda v: _VERDICT_SEVERITY[v])


def relative_drop(reference: float, current: float) -> float:
    """Caída relativa de `current` respecto de `reference` (Ronda 53,
    opción B/B'): 0.20 significa "cayó un 20% respecto de la
    referencia". Nunca negativo -- una mejora (current > reference) se
    reporta como 0.0, no como una caída negativa, porque el único uso
    de este número es decidir si algo empeoró más allá de un umbral.

    Si `reference` es 0.0 (la corrida de referencia ya tenía Recall@K/
    MRR en cero), no hay una caída relativa que tenga sentido calcular
    -- se devuelve 0.0 en vez de dividir por cero o fabricar un
    porcentaje: esta función no decide si un 0.0 histórico ya era grave,
    solo si HUBO una caída adicional medible desde la referencia."""
    if reference <= 0.0:
        return 0.0
    return max(0.0, (reference - current) / reference)


class EvaluationResultItem(BaseModel):
    """Resultado de correr un TestCase dentro de una EvaluationRun."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    test_case_id: str
    test_case_code: str
    category: TestCategory
    verdict: EvaluationVerdict
    actual_intent: Optional[str] = None
    actual_action: Optional[RuleActionType] = None
    actual_channeling_code: Optional[str] = None
    mismatches: list[str] = Field(default_factory=list)
    """Explicación humana de cada discrepancia encontrada -- lo que se
    muestra en el reporte, no solo el semáforo."""
    regressed: bool = False
    """True si este caso estaba en VERDE en la corrida anterior y dejó
    de estarlo (comparación entre corridas, "regresión")."""
    error: Optional[str] = None
    """Si simular este caso lanzó una excepción (p. ej. sin red para
    el modelo de embeddings), el caso queda en GRIS ("no ejecutado")
    con el error aquí -- no aborta el resto del banco de pruebas
    (mismo criterio de aislamiento de fallas que RunPipeline)."""
    retrieval_check_applicable: bool = False
    """ADR-003, Pista A.1: True cuando el TestCase trae
    expected_source_id -- distingue "no se evaluó recuperación en este
    caso" de "se evaluó y la fuente esperada no apareció" (este segundo
    caso deja expected_source_rank en None). Sin este campo,
    EvaluationRun.recall_at_k no podría saber sobre cuántos casos
    calcular el promedio: no todos los TestCase declaran una fuente
    esperada."""
    expected_source_rank: Optional[int] = None
    """ADR-003, Pista A.1: posición (1 = primer lugar) en la que
    apareció la fuente esperada dentro de trace.search_results, o None
    si nunca apareció entre los resultados que trajo esa simulación
    (acotado por el mismo límite de resultados que ya usa el
    Simulador -- típicamente 5 -- no por el corpus completo; es la
    misma limitación que ya acepta cualquier métrica Recall@K real).
    No cambia el veredicto por sí solo -- el criterio de aprobado/
    rechazado sigue siendo "el primer resultado es el esperado", igual
    que antes de esta ronda; este campo solo agrega la métrica
    cuantitativa que antes no se registraba en ningún lado."""


class EvaluationRun(BaseModel):
    """Una corrida del banco de pruebas. Se conserva el historial
    completo de corridas (igual que PipelineRun) -- el documento
    maestro exige poder comparar corridas pasadas ("regresión",
    "comparación entre corridas"), no solo ver el último resultado."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    scope: str = "completa"
    """"completa" | "categoria" | "individual" -- los tres tipos de
    ejecución de la lista del documento maestro que cubre esta
    iteración (quedan fuera "comparación entre modelos/índices/reglas/
    prompts", ver README limitaciones)."""
    category_filter: Optional[TestCategory] = None
    test_case_id_filter: Optional[str] = None
    items: list[EvaluationResultItem] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    @property
    def overall_verdict(self) -> EvaluationVerdict:
        if not self.items:
            return EvaluationVerdict.GRIS
        return most_severe_verdict([item.verdict for item in self.items])

    @property
    def has_blocking_failures(self) -> bool:
        """Compuerta de Etapa 6 (y de la futura liberación, Etapa 7):
        "bloqueos automáticos por hallazgos críticos" -- cualquier caso
        en ROJO impide considerar esta corrida como aprobada."""
        return any(item.verdict == EvaluationVerdict.ROJO for item in self.items)

    @property
    def regression_count(self) -> int:
        return sum(1 for item in self.items if item.regressed)

    @property
    def retrieval_applicable_items(self) -> list[EvaluationResultItem]:
        """ADR-003, Pista A.1: los casos de esta corrida que sí
        declararon una fuente esperada (`expected_source_id`) -- el
        denominador real de `recall_at_k`, nunca `len(items)` (un banco
        de pruebas mezcla casos que evalúan recuperación con casos que
        solo evalúan acción/intención/canalización)."""
        return [item for item in self.items if item.retrieval_check_applicable]

    def recall_at_k(self, k: int = 3) -> Optional[float]:
        """ADR-003, Pista A.1 -- cuantifica lo que antes solo se sabía
        como aprobado/rechazado: de los casos que declaran una fuente
        esperada, qué fracción la trajo entre los primeros `k`
        resultados de la búsqueda (no solo en el primer lugar, que es
        el único criterio que usa el veredicto AMARILLO/VERDE de cada
        caso). None si esta corrida no tiene ningún caso con fuente
        esperada -- una corrida "completa" de un proyecto que solo usa
        casos de acción/canalización no tiene nada que promediar aquí,
        y devolver 0.0 sería un dato falso, no la ausencia de dato."""
        applicable = self.retrieval_applicable_items
        if not applicable:
            return None
        hits = sum(
            1 for item in applicable
            if item.expected_source_rank is not None and item.expected_source_rank <= k
        )
        return hits / len(applicable)

    def mean_reciprocal_rank(self) -> Optional[float]:
        """Ronda 53 (Propuesta de evaluación continua reforzada,
        opción A confirmada por el consultor): a diferencia de
        recall_at_k, que solo pregunta "¿apareció entre los primeros
        k?", MRR pondera CUÁNTO más arriba apareció -- 1.0 si quedó en
        el primer lugar, 0.5 en el segundo, 1/3 en el tercero, y así
        sucesivamente; 0.0 si nunca apareció. Mismo denominador que
        recall_at_k (retrieval_applicable_items) y mismo criterio de
        ausencia de dato: None si ningún caso de esta corrida declaró
        una fuente esperada, nunca 0.0 fabricado."""
        applicable = self.retrieval_applicable_items
        if not applicable:
            return None
        reciprocal_ranks = [
            (1.0 / item.expected_source_rank) if item.expected_source_rank is not None else 0.0
            for item in applicable
        ]
        return sum(reciprocal_ranks) / len(reciprocal_ranks)


class RetrievalRegressionStatus(str, Enum):
    """Los tres estados reales de comparar Recall@3/MRR entre la
    corrida "completa" más reciente y la inmediatamente anterior (Ronda
    84, hallazgo real de usuario, ver bitácora). Antes de esta ronda, un
    único `if current_recall is None or reference_recall is None`
    colapsaba dos situaciones muy distintas en el mismo mensaje
    ("ninguna corrida tiene fuente esperada"), incluso cuando la corrida
    más reciente sí tenía métricas y solo la de referencia no las
    tenía -- exactamente el reporte real del usuario."""

    SIN_METRICAS_EN_LA_MAS_RECIENTE = "sin_metricas_en_la_mas_reciente"
    """La corrida "completa" más reciente no tiene ningún caso con
    fuente esperada declarada -- no hay Recall@3/MRR que calcular en
    ella, sin importar si la corrida de referencia sí los tiene."""
    SIN_CORRIDA_ANTERIOR_COMPARABLE = "sin_corrida_anterior_comparable"
    """La corrida más reciente sí tiene métricas (current_recall
    poblado), pero la corrida de referencia no -- todavía no existe una
    base comparable, aunque los datos de la más reciente ya se
    calcularon correctamente."""
    COMPARABLE = "comparable"
    """Ambas corridas tienen métricas -- recall_drop/mrr_drop quedan
    poblados con la caída relativa real de cada una."""


class RetrievalRegressionComparison(BaseModel):
    """Resultado de comparar dos corridas "completa" consecutivas por
    Recall@3/MRR -- calculado una sola vez aquí y consumido tanto por la
    compuerta de Liberación
    (application.release.queries.evaluate_release_gates.
    EvaluateReleaseGates._retrieval_regression_gate) como por el panel
    de Calidad (ui/quality/panel.py::_render_regression_comparison), de
    modo que ambos lugares no puedan divergir en qué corridas comparan
    ni en qué mensaje corresponde a cada situación real (Ronda 84,
    criterio de aceptación 5: "el mensaje mostrado en Calidad y el
    mostrado en Liberación deben ser coherentes y utilizar la misma
    lógica de selección de corridas"). Deliberadamente sin threshold ni
    veredicto de bloqueo aquí -- el umbral es una configuración de
    proyecto/instalación que solo conoce la capa de aplicación (ver
    EvaluateReleaseGates._regression_threshold); esta comparación es
    pura y no necesita saberlo para clasificar el estado real."""

    status: RetrievalRegressionStatus
    current_recall: Optional[float] = None
    reference_recall: Optional[float] = None
    current_mrr: Optional[float] = None
    reference_mrr: Optional[float] = None
    recall_drop: Optional[float] = None
    mrr_drop: Optional[float] = None
    """Solo poblados cuando status es COMPARABLE."""

    @property
    def worst_drop(self) -> Optional[float]:
        if self.recall_drop is None or self.mrr_drop is None:
            return None
        return max(self.recall_drop, self.mrr_drop)


def compare_retrieval_regression(
    current: EvaluationRun, reference: EvaluationRun,
) -> RetrievalRegressionComparison:
    """Ver RetrievalRegressionComparison/RetrievalRegressionStatus.
    `current` es la corrida "completa" más reciente; `reference`, la
    inmediatamente anterior -- mismo orden que ya usaban
    _retrieval_regression_gate y _render_regression_comparison antes de
    esta ronda, ahora centralizado en un solo lugar."""
    current_recall = current.recall_at_k(3)
    if current_recall is None:
        return RetrievalRegressionComparison(status=RetrievalRegressionStatus.SIN_METRICAS_EN_LA_MAS_RECIENTE)
    reference_recall = reference.recall_at_k(3)
    if reference_recall is None:
        return RetrievalRegressionComparison(
            status=RetrievalRegressionStatus.SIN_CORRIDA_ANTERIOR_COMPARABLE, current_recall=current_recall,
        )
    current_mrr = current.mean_reciprocal_rank() or 0.0
    reference_mrr = reference.mean_reciprocal_rank() or 0.0
    return RetrievalRegressionComparison(
        status=RetrievalRegressionStatus.COMPARABLE,
        current_recall=current_recall, reference_recall=reference_recall,
        current_mrr=current_mrr, reference_mrr=reference_mrr,
        recall_drop=relative_drop(reference_recall, current_recall),
        mrr_drop=relative_drop(reference_mrr, current_mrr),
    )
