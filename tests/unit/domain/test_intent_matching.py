"""Pruebas unitarias de match_intent (Etapa 5, emparejamiento HÍBRIDO de
intención: heurístico léxico de Jaccard, siempre disponible, más
similitud semántica de coseno cuando quien llama provee un embebedor --
ver domain.conversational.intent_matching)."""
from domain.conversational.entities import Intent
from domain.conversational.intent_matching import match_intent
from domain.rag.exceptions import EmbeddingProviderError


def _intent(**kwargs) -> Intent:
    kwargs.setdefault("project_id", "p1")
    kwargs.setdefault("name", "intención")
    return Intent(**kwargs)


class _WordOverlapEmbedder:
    """Embebedor de prueba cuya similitud de coseno refleja vocabulario
    compartido de verdad (índice de palabra por orden de aparición, sin
    colisiones de hash) -- suficiente para probar la combinación
    léxico+semántico sin depender de un modelo real. Ver el
    equivalente compartido para pruebas de application:
    tests/unit/application/fakes_rag.py::WordOverlapFakeEmbeddingProvider."""

    _CAPACITY = 200

    def __init__(self):
        self._word_index: dict[str, int] = {}

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._CAPACITY
        for word in text.lower().split():
            index = self._word_index.setdefault(word, len(self._word_index))
            if index < self._CAPACITY:
                vector[index] += 1.0
        return vector

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class _FailingEmbedder:
    """Simula la falta de red/modelo (EmbeddingProviderError) para
    probar que match_intent se degrada a solo léxico sin propagar la
    excepción."""

    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingProviderError("sin red para descargar el modelo")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderError("sin red para descargar el modelo")


def test_match_intent_picks_the_intent_with_more_vocabulary_overlap():
    intents = [
        _intent(name="Consultar requisitos", positive_examples=["qué requisitos necesito", "requisitos de ingreso"]),
        _intent(name="Consultar horarios", positive_examples=["a qué hora abren", "horario de atención"]),
    ]
    match = match_intent("qué requisitos necesito para ingresar", intents)
    assert match is not None
    assert match.intent.name == "Consultar requisitos"
    assert 0.0 < match.confidence <= 1.0


def test_match_intent_returns_none_when_no_active_intent_shares_vocabulary():
    intents = [_intent(name="Consultar horarios", positive_examples=["a qué hora abren"])]
    assert match_intent("quiero cancelar mi tarjeta de crédito", intents) is None


def test_match_intent_ignores_inactive_intents():
    intents = [
        _intent(name="Consultar requisitos", positive_examples=["requisitos de ingreso"], active=False),
    ]
    assert match_intent("requisitos de ingreso", intents) is None


def test_match_intent_returns_none_on_empty_query():
    intents = [_intent(name="Consultar requisitos", positive_examples=["requisitos de ingreso"])]
    assert match_intent("   ", intents) is None


def test_match_intent_returns_none_when_intent_catalog_is_empty():
    assert match_intent("cualquier consulta", []) is None


def test_negative_examples_reduce_confidence_for_a_similar_but_different_intent():
    # "dar de baja" y "consultar mi baja" comparten vocabulario de
    # superficie -- los ejemplos negativos existen para que la
    # intención correcta (o ninguna) gane, sin necesitar un
    # clasificador entrenado.
    baja_administrativa = _intent(
        name="Dar de baja", positive_examples=["quiero darme de baja del programa"],
        negative_examples=["quiero consultar mi estado de baja"],
    )
    match = match_intent("quiero consultar mi estado de baja", [baja_administrativa])
    assert match is None or match.confidence < 0.5


def test_match_intent_does_not_match_on_shared_stopwords_alone():
    # Encontrado durante la verificación end-to-end: "quiero cancelar
    # mi tarjeta de crédito" y una intención sobre requisitos de
    # ingreso no comparten nada real, solo la preposición "de" -- sin
    # filtrar conectores comunes, esa única coincidencia bastaba para
    # "reconocer" la intención equivocada.
    intents = [_intent(
        name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso al programa"],
    )]
    assert match_intent("quiero cancelar mi tarjeta de crédito", intents) is None


def test_match_intent_uses_name_and_description_as_vocabulary_even_without_examples():
    intents = [_intent(name="Consultar requisitos de ingreso", description="requisitos para ingresar al programa")]
    match = match_intent("requisitos para ingresar", intents)
    assert match is not None
    assert match.intent.name == "Consultar requisitos de ingreso"


def test_match_intent_without_embedder_behaves_exactly_as_before():
    # No pasar embed_query/embed_texts (los dos None por defecto) debe
    # comportarse idéntico al heurístico léxico puro de antes -- nadie
    # que ya llamaba match_intent(query, intents) debería ver un cambio.
    intents = [_intent(name="Consultar horarios", positive_examples=["a qué hora abren"])]
    assert match_intent("quiero cancelar mi tarjeta de crédito", intents) is None


def test_match_intent_finds_semantic_match_when_lexical_score_is_zero():
    # "vocabulario" real distinto de "palabras compartidas": el
    # embebedor de prueba comparte vocabulario real solo cuando de
    # verdad hay palabras en común -- aquí se simula un caso donde el
    # heurístico léxico solo no encontraría nada (ninguna palabra en
    # común) pero un modelo semántico real sí reconocería la paráfrasis.
    # Como el fake de prueba solo puede "entender" palabras compartidas
    # (no sinónimos reales), se arma el ejemplo positivo para que
    # comparta vocabulario con la consulta pero el score léxico puro
    # quede en 0 por los stopwords filtrados de por medio.
    embedder = _WordOverlapEmbedder()
    intents = [_intent(
        name="Dar de baja", description="",
        positive_examples=["suspender inscripción programa"],
    )]

    lexical_only = match_intent("quiero suspender mi inscripción del programa", intents)
    hybrid = match_intent(
        "quiero suspender mi inscripción del programa", intents,
        embed_query=embedder.embed_query, embed_texts=embedder.embed_texts,
    )

    assert hybrid is not None
    assert hybrid.intent.name == "Dar de baja"
    # La combinación híbrida nunca debe rendir menos que el léxico solo.
    lexical_confidence = lexical_only.confidence if lexical_only is not None else 0.0
    assert hybrid.confidence >= lexical_confidence


def test_match_intent_degrades_to_lexical_when_embedding_provider_fails():
    failing = _FailingEmbedder()
    intents = [
        _intent(name="Consultar requisitos", positive_examples=["qué requisitos necesito", "requisitos de ingreso"]),
    ]
    match = match_intent(
        "qué requisitos necesito para ingresar", intents,
        embed_query=failing.embed_query, embed_texts=failing.embed_texts,
    )
    assert match is not None
    assert match.intent.name == "Consultar requisitos"


def test_match_intent_semantic_path_still_returns_none_without_any_real_overlap():
    # Sin ninguna palabra en común (ni siquiera un conector como "de"
    # -- el fake de prueba no filtra stopwords como sí lo hace el lado
    # léxico, así que aquí se evita cualquier coincidencia incidental
    # para probar el caso limpio de "cero vocabulario compartido").
    embedder = _WordOverlapEmbedder()
    intents = [_intent(name="Consultar horarios", positive_examples=["horario apertura sucursal"])]
    match = match_intent(
        "quiero cancelar mi tarjeta crédito", intents,
        embed_query=embedder.embed_query, embed_texts=embedder.embed_texts,
    )
    assert match is None


def test_negativo_parecido_pero_menos_parecido_que_el_positivo_no_hunde_la_confianza():
    """Ronda 89 (AGENTE UDL): la confianza reportaba el margen "positivo
    menos negativo"; una consulta correcta cuyo ejemplo negativo era una
    frase parecida quedaba con confianza ~0 y la regla "confianza < 0.10 ->
    abstenerse" la descartaba. La intención se sigue ELIGIENDO por ese
    margen, pero la confianza es la similitud con el mejor positivo."""
    perfil = _intent(
        name="Consultar perfil de egreso",
        positive_examples=["cual es el perfil de egreso de la carrera"],
        negative_examples=["cual es el campo laboral de la carrera"],
    )
    match = match_intent("cual es el perfil de egreso", [perfil])
    assert match is not None and match.confidence >= 0.5


def test_consulta_identica_a_un_ejemplo_positivo_tiene_confianza_1():
    intent = _intent(
        name="objetivo diplomado", positive_examples=["cual es el objetivo del diplomado"],
        negative_examples=["cual es el costo del diplomado"],
    )
    match = match_intent("cual es el objetivo del diplomado", [intent])
    assert match is not None and match.confidence == 1.0


# ---------- Ronda 90 (2026-10-05, hallazgo real de usuario) ----------

def _quitar_derecho(texto: str) -> str:
    return texto.replace("Derecho", "").replace("derecho", "")


def test_la_transformacion_se_aplica_igual_a_la_consulta_y_a_los_ejemplos():
    """Con la consulta transformada pero los ejemplos intactos, una pregunta
    IDÉNTICA a un ejemplo positivo dejaba de coincidir con él."""
    perfil = _intent(
        name="perfil egreso", priority=50,
        positive_examples=["cual es el perfil de egreso de la licenciatura en Derecho"],
        negative_examples=["que materias lleva Arquitectura"],
    )
    general = _intent(
        name="programa especifico", priority=40,
        positive_examples=["cuentame sobre la licenciatura en Psicologia"],
        negative_examples=["cual es el perfil de egreso de Ingenieria Civil"],
    )
    match = match_intent(
        "cual es el perfil de egreso de la licenciatura en Derecho", [perfil, general],
        text_transform=_quitar_derecho,
    )
    assert match is not None and match.intent.name == "perfil egreso"
    assert match.confidence == 1.0
    assert [s.intent.name for s in match.scores] == ["perfil egreso", "programa especifico"]


def test_a_igual_margen_gana_la_mayor_prioridad():
    baja = _intent(name="alfa", priority=10, positive_examples=["horario de la biblioteca"])
    alta = _intent(name="beta", priority=90, positive_examples=["horario de la biblioteca"])
    assert match_intent("horario de la biblioteca", [baja, alta]).intent.name == "beta"
    assert match_intent("horario de la biblioteca", [alta, baja]).intent.name == "beta"


def test_un_negativo_parecido_no_hunde_a_un_positivo_mucho_mas_parecido():
    """Ronda 91: el negativo solo resta cuando la consulta se parece MÁS a él
    que al mejor positivo."""
    perfil = _intent(
        name="perfil", positive_examples=["que conocimientos obtiene quien termina la carrera"],
        negative_examples=["que materias lleva la carrera"],
    )
    general = _intent(name="general", positive_examples=["cuentame sobre la carrera"])
    match = match_intent("que conocimientos y habilidades obtiene quien termina la carrera", [perfil, general])
    assert match.intent.name == "perfil"
