"""Emparejamiento de intención (Etapa 5, "Diseño conversacional").

RAG STUDIO INVESTIGACION.odt es explícito: "La pieza central no es el
modelo generativo ni la base vectorial." -- por eso el emparejamiento
de intención sigue sin depender de un LLM ni de un clasificador
entrenado. Pero un heurístico léxico puro (similitud de Jaccard sobre
tokens) falla justo en lo que un usuario real escribe: paráfrasis,
sinónimos, errores de tecleo -- "quiero darme de baja" y "cómo
suspendo mi inscripción" no comparten ni una palabra, pero significan
lo mismo. Por eso el emparejamiento ahora es HÍBRIDO, exactamente con
el mismo criterio que ya se usó para búsqueda textual+semántica en
Etapa 4 (BM25 + embeddings, combinados): la similitud léxica de
Jaccard sigue calculándose siempre (barata, sin red, funciona sin
ninguna dependencia externa) y, si quien llama puede ofrecer una forma
de generar embeddings (reutilizando el mismo `EmbeddingProvider` que ya
tiene `RagService` para Etapa 4 -- no se agrega un segundo modelo ni
una dependencia nueva), también se calcula una similitud semántica de
coseno contra los ejemplos de cada intención. El score final por
intención es el máximo de ambas señales, así que el resultado nunca
empeora frente al heurístico léxico anterior, solo puede mejorar
cuando el proveedor de embeddings está disponible.

Si el proveedor de embeddings no está disponible (no se pasó, o falla
por falta de red/modelo -- `EmbeddingProviderError`), el emparejamiento
se degrada en silencio a solo léxico: el Diseño conversacional sigue
siendo usable sin conexión, la dependencia de red solo entra en juego
cuando de verdad hace falta buscar en el índice (acción RESPONDER).
"""
from __future__ import annotations

from math import sqrt
from typing import Callable, Optional

from domain.rag.exceptions import EmbeddingProviderError
from domain.rag.text_search import tokenize

from .entities import Intent

EmbedQueryFn = Callable[[str], list[float]]
EmbedTextsFn = Callable[[list[str]], list[list[float]]]

# Conectores/preposiciones muy comunes del español -- sin filtrarlos,
# dos textos sin ninguna relación real todavía pueden compartir "de",
# "la", "el"... y producir un score de Jaccard pequeño pero positivo,
# lo que haría que match_intent "reconozca" una intención por una sola
# palabra de función compartida (se detectó exactamente este caso
# durante la verificación end-to-end: "quiero cancelar mi tarjeta de
# crédito" empataba con una intención sobre requisitos de ingreso solo
# por compartir "de"). Mismo criterio ya usado en
# ui.ingestion.search_highlighting._SPANISH_STOPWORDS, pero aquí afecta
# el resultado real (no solo qué se resalta), así que vive en domain.
_STOPWORDS = {
    "de", "la", "el", "en", "y", "o", "a", "que", "del", "los", "las", "un", "una", "unos", "unas",
    "es", "son", "para", "por", "con", "sin", "su", "sus", "al", "lo", "se", "no", "sí", "e", "u",
    "mi", "tu", "me", "te", "le", "les", "qué", "cómo", "cuál", "cuáles", "quien", "quién",
}


def _meaningful_tokens(text: str) -> set[str]:
    return {token for token in tokenize(text) if token not in _STOPWORDS}


class IntentScore:
    """Puntuación de UNA intención para una consulta (Ronda 90): se expone
    para que el Simulador pueda explicar por qué ganó una intención y no
    otra. `margin` = positivo - negativo (lo que decide), `positive` /
    `negative` = similitud con el ejemplo positivo / negativo más
    parecido, `channel` = "semantico" o "lexico" (el que dio el margen)."""

    def __init__(self, intent: Intent, margin: float, positive: float, negative: float, channel: str):
        self.intent = intent
        self.margin = margin
        self.positive = positive
        self.negative = negative
        self.channel = channel


class IntentMatch:
    """Resultado de emparejar una consulta contra el catálogo de
    intenciones activas de un proyecto."""

    def __init__(self, intent: Intent, confidence: float, scores: Optional[list[IntentScore]] = None):
        self.intent = intent
        self.confidence = confidence
        self.scores: list[IntentScore] = scores or []
        """Todas las intenciones activas, de mayor a menor margen."""

    def __repr__(self) -> str:  # pragma: no cover - solo para depurar en consola
        return f"IntentMatch(intent={self.intent.name!r}, confidence={self.confidence:.3f})"


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / len(a | b)


def _net_score(positive: float, negative: float) -> float:
    """Puntuación con la que se ELIGE la intención (Ronda 91).

    Hasta la Ronda 90 era "positivo menos negativo". Con el proyecto real
    del usuario (AGENTE UDL, 695 consultas de 35 programas, incluidas
    paráfrasis que no están entre los ejemplos) eso acertaba 570 y ahora
    595: los ejemplos negativos de una intención son, a propósito, frases
    con la misma estructura ("¿Qué materias lleva...?" como negativo de
    perfil de egreso), así que restarlos SIEMPRE castigaba a la intención
    correcta aunque la consulta se pareciera mucho más a uno de sus
    positivos. Ahora el negativo solo resta cuando la consulta se parece
    MÁS a él que al mejor positivo, y resta esa diferencia: el negativo
    conserva su función (impedir que la intención gane con frases que no
    le corresponden) sin hundir a la que sí corresponde.

    Nota: en la Ronda 89 esta misma fórmula se probó y se descartó, pero
    aquella medición estaba distorsionada por el enmascarado asimétrico
    (solo la consulta perdía los nombres de programa) que se corrigió en
    la Ronda 90."""
    return max(0.0, min(1.0, positive - max(0.0, negative - positive)))


def _lexical_scores(query_tokens: set[str], intent: Intent) -> tuple[float, float, float]:
    """(margen, similitud positiva, similitud negativa) -- ver match_intent
    sobre por qué se usan por separado (Ronda 89)."""
    positive_text = " ".join([intent.name, intent.description, *intent.positive_examples])
    positive_score = _jaccard(query_tokens, _meaningful_tokens(positive_text))
    negative_score = _jaccard(query_tokens, _meaningful_tokens(" ".join(intent.negative_examples)))
    return _net_score(positive_score, negative_score), positive_score, negative_score


def _lexical_score(query_tokens: set[str], intent: Intent) -> float:
    return _lexical_scores(query_tokens, intent)[0]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _positive_reference_texts(intent: Intent) -> list[str]:
    # Mismo criterio que _lexical_score: si la intención no tiene
    # ejemplos positivos todavía, nombre+descripción siguen dando algo
    # de vocabulario contra qué comparar semánticamente.
    texts = list(intent.positive_examples)
    combined = " ".join([intent.name, intent.description]).strip()
    if combined:
        texts.append(combined)
    return texts


def _semantic_scores(
    query_text: str, intents: list[Intent], embed_query: EmbedQueryFn, embed_texts: EmbedTextsFn,
) -> dict[str, tuple[float, float, float]]:
    """Similitud de coseno contra los ejemplos de cada intención, con la
    misma fórmula "positivo menos negativo" que `_lexical_score`. Se
    embeben en un solo lote todos los textos de referencia de todas las
    intenciones (vía `embed_texts`, el lado "documento" del proveedor)
    para no hacer una llamada al modelo por cada ejemplo; la consulta se
    embebe una sola vez con `embed_query` (el lado correcto para
    comparar contra referencias ya embebidas, igual que en la búsqueda
    semántica de Etapa 4). Devuelve el score por `Intent.id`, no por
    intención completa, para poder usarse como diccionario de consulta.
    """
    reference_texts: list[str] = []
    spans: dict[str, tuple[int, int, int, int]] = {}  # intent.id -> (pos_start, pos_end, neg_start, neg_end)
    for intent in intents:
        positive_texts = _positive_reference_texts(intent)
        pos_start = len(reference_texts)
        reference_texts.extend(positive_texts)
        pos_end = len(reference_texts)

        neg_start = len(reference_texts)
        reference_texts.extend(intent.negative_examples)
        neg_end = len(reference_texts)

        spans[intent.id] = (pos_start, pos_end, neg_start, neg_end)

    if not reference_texts:
        return {}

    query_vector = embed_query(query_text)
    reference_vectors = embed_texts(reference_texts)

    scores: dict[str, tuple[float, float, float]] = {}
    for intent in intents:
        pos_start, pos_end, neg_start, neg_end = spans[intent.id]
        positive_score = max(
            (_cosine_similarity(query_vector, v) for v in reference_vectors[pos_start:pos_end]),
            default=0.0,
        )
        negative_score = max(
            (_cosine_similarity(query_vector, v) for v in reference_vectors[neg_start:neg_end]),
            default=0.0,
        )
        scores[intent.id] = (_net_score(positive_score, negative_score), positive_score, negative_score)
    return scores


def match_intent(
    query_text: str,
    intents: list[Intent],
    embed_query: Optional[EmbedQueryFn] = None,
    embed_texts: Optional[EmbedTextsFn] = None,
    text_transform: Optional[Callable[[str], str]] = None,
) -> Optional[IntentMatch]:
    """Empareja `query_text` contra las intenciones ACTIVAS de
    `intents` y devuelve la de mayor score, o None si ninguna intención
    activa obtiene un score positivo -- ese caso se trata como "no se
    reconoce ninguna intención", y quien llama (ver SimulateConversation)
    debe abstenerse en vez de inventar una intención.

    Score por intención = el MÁXIMO entre la similitud léxica de Jaccard
    (siempre se calcula, no depende de nada externo) y, si se proveen
    `embed_query`/`embed_texts`, la similitud semántica de coseno contra
    los mismos ejemplos (ver `_semantic_scores`). Tomar el máximo -- no
    un promedio -- significa que este emparejamiento híbrido nunca
    encuentra MENOS que el heurístico léxico por sí solo, solo puede
    encontrar coincidencias adicionales que la superposición de palabras
    se perdería (paráfrasis, sinónimos).

    text_transform (Ronda 90): transformación que se aplica POR IGUAL a la
    consulta y a todos los textos de referencia (nombre, descripción,
    ejemplos positivos y negativos). SimulateConversation la usa para
    quitar las menciones de valores de catálogo (nombres de programas).
    En la Ronda 89 solo se quitaban de la consulta: una pregunta idéntica
    a un ejemplo positivo ("¿Cuál es el perfil de egreso de la
    licenciatura en Derecho?") dejaba de coincidir con su propio ejemplo
    y ganaba otra intención.

    Desempate por prioridad (Ronda 90): si dos intenciones obtienen el
    mismo margen, gana la de mayor `priority`, como siempre documentó el
    Manual del Usuario (antes el código no usaba la prioridad).

    Si `embed_query`/`embed_texts` fallan (típicamente
    `EmbeddingProviderError` por falta de red/modelo) se degrada en
    silencio a solo léxico, para que Diseño conversacional siga siendo
    usable sin conexión -- la dependencia de red real solo entra cuando
    de verdad hay que buscar en el índice.
    """
    if text_transform is not None:
        query_text = text_transform(query_text)
    query_tokens = _meaningful_tokens(query_text)
    if not query_tokens:
        return None

    active_intents = [intent for intent in intents if intent.active]
    if not active_intents:
        return None
    if text_transform is not None:
        active_intents = [
            intent.model_copy(update={
                "name": text_transform(intent.name),
                "description": text_transform(intent.description),
                "positive_examples": [text_transform(t) for t in intent.positive_examples],
                "negative_examples": [text_transform(t) for t in intent.negative_examples],
            })
            for intent in active_intents
        ]
        originals = {intent.id: intent for intent in intents}
    else:
        originals = {intent.id: intent for intent in active_intents}

    semantic_scores: dict[str, tuple[float, float, float]] = {}
    if embed_query is not None and embed_texts is not None:
        try:
            semantic_scores = _semantic_scores(query_text, active_intents, embed_query, embed_texts)
        except EmbeddingProviderError:
            semantic_scores = {}

    # Ronda 89 (2026-10-04, hallazgo real de usuario en AGENTE UDL): se
    # separa QUÉ intención gana de CON QUÉ confianza se reporta.
    # - Para elegir se sigue usando el margen "positivo menos negativo":
    #   medido con la consulta real del proyecto, es lo que mejor separa
    #   intenciones parecidas (los ejemplos negativos existen para eso).
    # - Como confianza se reporta la similitud con el mejor ejemplo
    #   positivo de la intención ganadora (0 a 1). Antes se reportaba el
    #   margen: una consulta idéntica a un ejemplo positivo aparecía con
    #   0.573, y una correcta pero con negativos parecidos con ~0.03, de
    #   modo que una regla "confianza < 0.10 -> abstenerse" descartaba
    #   preguntas bien reconocidas.
    puntajes: list[IntentScore] = []
    for intent in active_intents:
        lexical = _lexical_scores(query_tokens, intent)
        semantic = semantic_scores.get(intent.id, (0.0, 0.0, 0.0))
        margin, positive, negative = semantic if semantic[0] > lexical[0] else lexical
        canal = "semantico" if semantic[0] > lexical[0] else "lexico"
        puntajes.append(IntentScore(originals[intent.id], margin, positive, negative, canal))
    # Mayor margen primero; a igual margen, mayor prioridad.
    puntajes.sort(key=lambda p: (p.margin, p.intent.priority), reverse=True)
    if not puntajes or puntajes[0].margin <= 0.0:
        return None
    ganador = puntajes[0]
    return IntentMatch(
        intent=ganador.intent, confidence=max(0.0, min(1.0, ganador.positive)), scores=puntajes,
    )
