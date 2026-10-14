"""Funciones puras de búsqueda textual (Etapa 4, Laboratorio RAG:
"búsqueda semántica/textual/híbrida" del documento maestro).

Sin dependencias externas (ADR-001, sección 4: domain sin dependencias
salvo Pydantic) -- BM25 es un algoritmo de estadística de texto simple,
no necesita una librería de búsqueda completa (Elasticsearch/Whoosh)
para un corpus del tamaño típico de un proyecto de RAG STUDIO (cientos
o miles de fragmentos, no millones). Si algún día un proyecto real
crece lo suficiente para que este barrido en memoria sea lento, migrar
a SQLite FTS5 (ya se usa SQLite para todo lo demás) es un cambio
aislado a `application.rag.queries.text_search.TextSearch`, sin tocar
el resto del motor.
"""
from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

_BM25_K1 = 1.5
_BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    """Palabras en minúsculas, sin puntuación -- suficiente para
    contar frecuencias de término; no es un tokenizador de un modelo de
    embeddings (mismo criterio de aproximación deliberada que
    domain.ingestion.splitting.word_count)."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def bm25_scores(
    query_text: str, documents: list[str], k1: float = _BM25_K1, b: float = _BM25_B,
) -> list[float]:
    """Puntúa cada documento en `documents` contra `query_text` con
    BM25 (Robertson/Sparck Jones), la fórmula estándar de búsqueda
    textual por palabra clave: pondera cada término de la consulta por
    qué tan raro es en el corpus (idf) y qué tan seguido aparece en
    cada documento (tf), con normalización por longitud de documento
    para no favorecer documentos largos solo por ser largos.

    Devuelve una lista de scores en el mismo orden que `documents`
    (no ordenada) -- quien llama decide cómo ordenar/recortar (ver
    application.rag.queries.text_search.TextSearch). Un documento sin
    ningún término de la consulta obtiene 0.0, nunca un score negativo:
    a diferencia de la fórmula de idf clásica (que puede dar negativo
    para términos presentes en más de la mitad del corpus), aquí se
    usa la variante "+1" que mantiene el idf siempre positivo -- un
    término muy común sigue aportando algo, en vez de penalizar."""
    query_terms = tokenize(query_text)
    if not query_terms or not documents:
        return [0.0] * len(documents)

    doc_tokens = [tokenize(doc) for doc in documents]
    doc_lengths = [len(tokens) for tokens in doc_tokens]
    non_empty_lengths = [length for length in doc_lengths if length > 0]
    avg_length = sum(non_empty_lengths) / len(non_empty_lengths) if non_empty_lengths else 0.0

    n_docs = len(documents)
    unique_query_terms = set(query_terms)
    document_frequency = {
        term: sum(1 for tokens in doc_tokens if term in tokens) for term in unique_query_terms
    }
    idf = {
        term: math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1)
        for term, freq in document_frequency.items()
    }

    scores: list[float] = []
    for tokens, length in zip(doc_tokens, doc_lengths, strict=True):
        if length == 0:
            scores.append(0.0)
            continue
        term_counts: dict[str, int] = {}
        for token in tokens:
            term_counts[token] = term_counts.get(token, 0) + 1
        score = 0.0
        length_norm = (1 - b + b * length / avg_length) if avg_length else 1.0
        for term in query_terms:
            term_frequency = term_counts.get(term, 0)
            if term_frequency == 0:
                continue
            numerator = idf[term] * term_frequency * (k1 + 1)
            denominator = term_frequency + k1 * length_norm
            score += numerator / denominator
        scores.append(score)
    return scores
