
from domain.ingestion.splitting import (
    TextSpan, merge_small_spans, resolve_page, split_by_articles, split_by_headings, split_by_qa_pairs,
    split_by_size, split_by_tables, word_count,
)


def test_word_count_counts_whitespace_separated_tokens():
    assert word_count("uno dos tres") == 3
    assert word_count("") == 0


def test_split_by_size_respects_char_offsets():
    text = " ".join(f"w{i}" for i in range(30))
    spans = split_by_size(text, target_tokens=10, overlap_tokens=2)
    for span in spans:
        assert text[span.char_start:span.char_end] == span.text
    # el primer y último fragmento deben cubrir el inicio y el final del texto
    assert spans[0].char_start == 0
    assert spans[-1].char_end == len(text)


def test_split_by_size_produces_overlap():
    text = " ".join(f"w{i}" for i in range(20))
    spans = split_by_size(text, target_tokens=10, overlap_tokens=3)
    assert len(spans) >= 2
    # las palabras del final del primer fragmento deben reaparecer al inicio del segundo
    first_words = spans[0].text.split()
    second_words = spans[1].text.split()
    assert first_words[-3:] == second_words[:3]


def test_split_by_size_empty_text_returns_no_spans():
    assert split_by_size("   ", target_tokens=100, overlap_tokens=10) == []


# ---------- count_tokens inyectable (ítem 7 de la evaluación de
# madurez post-8-etapas): un tokenizador real puede sustituir la
# aproximación por palabras sin cambiar la API pública ni el
# comportamiento por defecto (ver tests arriba, todos siguen pasando
# sin pasar count_tokens). ----------

def _tokens_per_word(n: int):
    """Fake determinista: cada palabra vale `n` "tokens" -- permite
    verificar que split_by_size/merge_small_spans/split_by_tables usan
    de verdad el count_tokens inyectado, no siempre word_count."""
    return lambda text: len(text.split()) * n


def test_split_by_size_uses_injected_token_budget_not_word_count():
    text = " ".join(f"w{i}" for i in range(40))
    # Con 2 tokens por palabra y target_tokens=20, cada ventana debe
    # tener 10 palabras (20 tokens reales), no 20 palabras.
    spans = split_by_size(text, target_tokens=20, overlap_tokens=0, count_tokens=_tokens_per_word(2))
    assert len(spans[0].text.split()) == 10


def test_split_by_size_default_count_tokens_is_word_count():
    text = " ".join(f"w{i}" for i in range(30))
    with_default = split_by_size(text, target_tokens=10, overlap_tokens=2)
    with_explicit_word_count = split_by_size(text, target_tokens=10, overlap_tokens=2, count_tokens=word_count)
    assert with_default == with_explicit_word_count


def test_merge_small_spans_uses_injected_count_tokens():
    # "uno dos" cuenta como 4 "tokens" con el fake (2 palabras * 2) --
    # por debajo de min_tokens=5, así que se fusiona; con word_count
    # (2 tokens) también se fusionaría, así que se sube min_tokens para
    # que la diferencia sea observable: con tokens_per_word=1 (o sea
    # word_count) "grande" (20 palabras) NO se fusiona con min_tokens=15,
    # pero con tokens_per_word igual a 1 sigue sin fusionar -- se prueba
    # el caso opuesto: un fragmento de 10 palabras que con word_count
    # (10 tokens) fusionaría bajo min_tokens=15, pero con
    # tokens_per_word=2 (20 tokens) ya no debe fusionarse.
    spans = [
        TextSpan(" ".join(f"w{i}" for i in range(10)), 0, 50),
        TextSpan(" ".join(f"x{i}" for i in range(10)), 51, 100),
    ]
    merged_with_word_count = merge_small_spans(spans, min_tokens=15)
    assert len(merged_with_word_count) == 1  # 10 tokens < 15: se fusiona

    merged_with_real_tokens = merge_small_spans(spans, min_tokens=15, count_tokens=_tokens_per_word(2))
    assert len(merged_with_real_tokens) == 2  # 20 tokens >= 15: no se fusiona


def test_split_by_headings_groups_by_markdown_heading():
    text = "# Uno\ncontenido uno\n\n## Uno.uno\ncontenido dos\n\n# Dos\ncontenido tres\n"
    sections = split_by_headings(text)
    titles = [t for t, _ in sections]
    assert titles == ["Uno", "Uno.uno", "Dos"]
    for _, span in sections:
        assert text[span.char_start:span.char_end] == span.text


def test_split_by_headings_without_headings_returns_single_untitled_section():
    text = "solo texto narrativo sin encabezados"
    sections = split_by_headings(text)
    assert len(sections) == 1
    assert sections[0][0] is None
    assert sections[0][1].text == text


def test_split_by_headings_preserves_preamble_before_first_heading():
    text = "preámbulo sin título\n\n# Primer título\ncontenido\n"
    sections = split_by_headings(text)
    assert sections[0][0] is None
    assert "preámbulo" in sections[0][1].text
    assert sections[1][0] == "Primer título"


def test_merge_small_spans_combines_below_threshold():
    # "uno dos" (2 palabras) se une al fragmento grande; el resultado
    # sigue siendo grande, pero "fin" (1 palabra) queda de nuevo por
    # debajo del umbral y también termina uniéndose: todo colapsa en 1.
    spans = [
        TextSpan("uno dos", 0, 7),
        TextSpan(" ".join(f"w{i}" for i in range(20)), 8, 100),
        TextSpan("fin", 101, 104),
    ]
    merged = merge_small_spans(spans, min_tokens=5)
    assert len(merged) == 1
    assert word_count(merged[0].text) == 23
    assert "uno" in merged[0].text and "fin" in merged[0].text


def test_merge_small_spans_keeps_two_large_neighbors_separate():
    spans = [
        TextSpan("pequeño", 0, 7),
        TextSpan(" ".join(f"a{i}" for i in range(20)), 8, 100),
        TextSpan(" ".join(f"b{i}" for i in range(20)), 101, 200),
    ]
    merged = merge_small_spans(spans, min_tokens=5)
    assert len(merged) == 2
    assert word_count(merged[0].text) >= 5
    assert word_count(merged[1].text) >= 5


def test_merge_small_spans_leaves_large_spans_untouched():
    spans = [TextSpan(" ".join(f"w{i}" for i in range(20)), 0, 100)]
    merged = merge_small_spans(spans, min_tokens=5)
    assert merged == spans


def test_resolve_page_returns_none_without_page_breaks():
    assert resolve_page(50, []) is None


def test_resolve_page_maps_offset_to_correct_page():
    page_breaks = [100, 250, 400]
    assert resolve_page(0, page_breaks) == 1
    assert resolve_page(99, page_breaks) == 1
    assert resolve_page(100, page_breaks) == 2
    assert resolve_page(300, page_breaks) == 3
    assert resolve_page(500, page_breaks) == 4


# ---------- split_by_articles (Módulo 5: reglamento -- "artículo
# completo, incluso si excede el tamaño estándar") ----------

def test_split_by_articles_groups_by_article_heading_and_keeps_offsets():
    text = (
        "Artículo 1.- Este reglamento aplica a todo el alumnado.\n"
        "Excepto quienes tengan beca vigente.\n\n"
        "Artículo 2.- La inscripción debe realizarse en tiempo y forma.\n"
    )
    sections = split_by_articles(text)
    titles = [t for t, _ in sections]
    assert titles == ["Artículo 1", "Artículo 2"]
    assert "Excepto quienes tengan beca vigente" in sections[0][1].text
    for _, span in sections:
        assert text[span.char_start:span.char_end] == span.text


def test_split_by_articles_preserves_preamble_without_title():
    text = "Disposiciones generales antes del primer artículo.\n\nArtículo 1.- Contenido.\n"
    sections = split_by_articles(text)
    assert sections[0][0] is None
    assert "Disposiciones generales" in sections[0][1].text
    assert sections[1][0] == "Artículo 1"


def test_split_by_articles_without_articles_returns_single_untitled_section():
    text = "solo texto narrativo sin ningún artículo detectable"
    sections = split_by_articles(text)
    assert len(sections) == 1
    assert sections[0][0] is None
    assert sections[0][1].text == text


def test_split_by_articles_recognizes_abbreviated_and_case_insensitive_forms():
    text = "art. 3 primer inciso.\n\nARTÍCULO 4 segundo inciso.\n"
    sections = split_by_articles(text)
    assert len(sections) == 2
    assert sections[0][0] == "art. 3"
    assert sections[1][0] == "ARTÍCULO 4"


# ---------- split_by_qa_pairs (Módulo 5: preguntas frecuentes -- "un
# fragmento por pregunta completa, sin solapamiento") ----------

def test_split_by_qa_pairs_groups_question_with_its_answer():
    text = (
        "P: ¿Cuál es la duración de la maestría?\n"
        "R: La maestría dura 4 cuatrimestres.\n\n"
        "P: ¿Hay examen de admisión?\n"
        "R: Sí, uno de conocimientos generales.\n"
    )
    sections = split_by_qa_pairs(text)
    titles = [t for t, _ in sections]
    assert titles == ["P: ¿Cuál es la duración de la maestría?", "P: ¿Hay examen de admisión?"]
    assert "La maestría dura 4 cuatrimestres" in sections[0][1].text
    assert "Sí, uno de conocimientos generales" in sections[1][1].text


def test_split_by_qa_pairs_recognizes_pregunta_prefix_case_insensitive():
    text = "Pregunta: ¿Qué documentos se requieren?\nRespuesta: Acta de nacimiento y CURP.\n"
    sections = split_by_qa_pairs(text)
    assert len(sections) == 1
    assert sections[0][0] == "Pregunta: ¿Qué documentos se requieren?"


def test_split_by_qa_pairs_without_markers_returns_single_untitled_section():
    text = "un documento sin ningún marcador de pregunta reconocible"
    sections = split_by_qa_pairs(text)
    assert len(sections) == 1
    assert sections[0][0] is None


# ---------- split_by_tables (Módulo 5: tabla -- "repetir encabezados
# en cada fragmento") ----------

def test_split_by_tables_separates_text_and_table_blocks():
    text = (
        "Texto antes de la tabla.\n\n"
        "| Programa | Plantel |\n"
        "| --- | --- |\n"
        "| Ing. Biomédica | Mérida |\n"
        "| Ing. Industrial | Progreso |\n\n"
        "Texto después de la tabla.\n"
    )
    result = split_by_tables(text, target_tokens=500)
    is_table_flags = [is_table for _, _, is_table in result]
    assert is_table_flags == [False, True, False]

    _, before_span, _ = result[0]
    assert "antes" in before_span.text

    title, table_span, _ = result[1]
    assert title == "Tabla"
    assert "Programa" in table_span.text and "Plantel" in table_span.text
    assert "Ing. Biomédica" in table_span.text

    _, after_span, _ = result[2]
    assert "después" in after_span.text


def test_split_by_tables_repeats_header_in_every_row_group_when_table_is_large():
    header = "| Col |\n| --- |\n"
    rows = "\n".join(f"| fila {i} con varias palabras de relleno aquí mismo |" for i in range(20))
    text = header + rows
    result = split_by_tables(text, target_tokens=15)
    assert len(result) > 1
    for title, span, is_table in result:
        assert is_table is True
        assert title == "Tabla"
        assert "Col" in span.text
        assert "---" in span.text


def test_split_by_tables_without_any_table_falls_back_to_split_by_size():
    text = "puro texto narrativo sin ninguna tabla que reconocer aquí mismo"
    result = split_by_tables(text, target_tokens=100)
    assert len(result) == 1
    title, span, is_table = result[0]
    assert title is None
    assert is_table is False
    assert span.text == text


def test_split_by_tables_empty_text_returns_no_spans():
    assert split_by_tables("   ", target_tokens=100) == []


def test_split_by_tables_uses_injected_count_tokens_for_row_grouping():
    header = "| Col |\n| --- |\n"
    rows = "\n".join(f"| fila {i} |" for i in range(10))
    text = header + rows

    with_word_count = split_by_tables(text, target_tokens=8)
    with_real_tokens = split_by_tables(text, target_tokens=8, count_tokens=_tokens_per_word(3))

    # Con 3 tokens por palabra, el mismo target_tokens agota el
    # presupuesto con menos filas por grupo -- más grupos en total.
    assert len(with_real_tokens) > len(with_word_count)
