"""Consulta: búsqueda híbrida -- combina SemanticSearch (vector) y
TextSearch (BM25) con Reciprocal Rank Fusion (RRF), el mismo mecanismo
que resuelve "híbrida" y "reranking" a la vez (Etapa 4, Laboratorio
RAG: "búsqueda semántica/textual/híbrida... y reranking" del documento
maestro).

Por qué RRF y no una combinación lineal de scores: la similitud coseno
de SemanticSearch vive en [0, 1] (o [-1, 1]) mientras que BM25 no tiene
límite superior y depende de la longitud del corpus -- promediar esos
dos números directamente no tiene un significado claro sin normalizar
cada lista por separado, y esa normalización cambia según qué
resultados entraron en el top-K de cada método. RRF evita el problema
por completo: en vez de combinar scores, combina *posiciones* (rank 1,
2, 3...) de cada lista, con una fórmula simple y bien establecida en
recuperación de información (Cormack, Clarke & Buettcher, 2009) que no
necesita normalización ni pesos que ajustar a mano. Es también, en la
práctica, una forma de "reranking": un fragmento que aparece arriba en
ambas búsquedas termina arriba en el resultado combinado, aunque no
fuera el primero en ninguna de las dos por separado.

No se usaba un cross-encoder ni un modelo de lenguaje para reordenar (la
otra forma común de "reranking") a propósito: son dependencias pesadas
(otro modelo a descargar/cargar) que no estaban dentro de las
restricciones del proyecto ("local primero", "sin tareas pesadas en la
interfaz") en esa iteración -- RRF resuelve el mismo requisito (mejorar
el orden combinando señales) sin ese costo.

ADR-003, Pista A.2 ("ganancias rápidas"): un cross-encoder real sigue
siendo OPCIONAL, nunca obligatorio -- pero la evaluación de madurez
posterior a las 8 etapas señaló que un reranker de verdad (que sí mira
el texto de la consulta y del candidato, no solo su posición en dos
listas) puede mejorar el orden más allá de lo que RRF puede lograr por
sí solo, sobre todo cuando ambos métodos coinciden poco. Por eso
`HybridSearch` ahora acepta un `Reranker` (domain.rag.ports) opcional:
quien no lo configure sigue viendo exactamente el mismo comportamiento
de siempre (RRF puro); quien lo configure puede pedirlo explícitamente
con `execute(..., rerank=True)`, y sigue siendo un modelo LOCAL (ver
infrastructure.rerankers.fastembed_cross_encoder), no una API de pago."""
from __future__ import annotations

from collections.abc import Collection
from typing import Optional

from domain.documents.entities import AccessLevel
from domain.rag.exceptions import RerankerError, RerankerUnavailableError
from domain.rag.hierarchy import contextualized_text, hierarchy_rank, ordinal_conflicts
from domain.rag.ports import Reranker

from .semantic_search import SemanticSearch, SemanticSearchResult
from .text_search import TextSearch

_RRF_RANK_CONSTANT = 60
"""Constante estándar de la fórmula RRF (score = suma de 1/(k + rango)
por cada lista donde aparece el resultado). k=60 es el valor con el que
se propuso y validó originalmente el método; no es un parámetro que
este proyecto necesite afinar por corpus."""


class HybridSearch:
    def __init__(
        self, semantic_search: SemanticSearch, text_search: TextSearch,
        reranker: Optional[Reranker] = None,
    ):
        # reranker es una capacidad OPCIONAL (mismo patrón que
        # source_repository en SemanticSearch/TextSearch, o
        # embedding_provider_factory en RagService): sin él,
        # execute(rerank=True) lanza RerankerUnavailableError en vez de
        # ignorar el pedido en silencio -- quien no lo configure no ve
        # ningún cambio de comportamiento respecto a antes de esta ronda.
        self._semantic = semantic_search
        self._text = text_search
        self._reranker = reranker

    @property
    def has_reranker(self) -> bool:
        return self._reranker is not None

    @property
    def reranker_model_name(self) -> Optional[str]:
        """Ronda 102 (C4): modelo de reranking configurado (None si no hay)."""
        return self._reranker.model_name if self._reranker is not None else None

    @property
    def reranker_loaded(self) -> bool:
        """Ronda 105b (P1): hay reranker y su modelo está cargado."""
        return self._reranker is not None and self._reranker.is_loaded

    def ensure_reranker_ready(self) -> None:
        """Ronda 105b (P1): carga y verifica el modelo; RerankerUnavailableError
        si no hay reranker, RerankerError si no carga."""
        if self._reranker is None:
            raise RerankerUnavailableError()
        self._reranker.ensure_ready()

    def execute(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        candidate_limit: int = 40, rerank: bool = False, expand_to_parent: bool = False,
        max_access_level: Optional[AccessLevel] = None,
        source_ids: Optional[Collection[str]] = None,
        use_hierarchy: bool = True,
    ) -> list[SemanticSearchResult]:
        """use_hierarchy (Ronda 100): con False se omite la señal jerárquica
        (ruta de encabezados y ordinales) en esta búsqueda y en la textual
        -- para comparar antes/después o descartarla en un proyecto
        concreto; por defecto participa.

        candidate_limit: cuántos resultados se piden a cada método
        antes de fusionar -- debe ser mayor o igual a `limit` para que
        RRF tenga material real que combinar (fusionar solo el top-5
        de cada lista deja poco margen para que un resultado "segundo
        en ambas" le gane a uno "primero en una sola"). Con
        rerank=True, `candidate_limit` también acota cuántos candidatos
        ya fusionados por RRF se le pasan al Reranker real -- el mismo
        criterio: dejarle material de sobra para reordenar, no solo los
        `limit` finales.

        Auditoría Ronda 21: el default subió de 20 a 40 como precaución
        explícita del consultor -- con 20, el Reranker solo alcanzaba a
        ver los candidatos que RRF ya había puesto en su propio top-20
        (el fetch a cada método usa este mismo número), así que un
        fragmento realmente relevante que RRF hubiera enterrado más
        abajo (plausible en un corpus real con muchos fragmentos
        parecidos, no en los corpus sintéticos de 2-5 fragmentos de las
        pruebas) nunca llegaba a tener la oportunidad de ser rescatado
        por el reranking. 40 no es un valor validado contra un corpus
        real todavía -- es un margen de seguridad mientras se consigue
        uno; puede requerir ajuste (por latencia o por calidad) una vez
        que haya datos reales con los que medir.

        rerank=True exige haber configurado un Reranker al construir
        este HybridSearch (ver RerankerUnavailableError) -- no hay
        "modo degradado" silencioso a RRF puro, para que quien lo pida
        sepa de inmediato si de verdad se está aplicando.

        expand_to_parent (Pista B.1 del ADR-003) se reenvía sin cambios
        a SemanticSearch y TextSearch -- se pide sobre TODOS los
        candidatos (hasta candidate_limit de cada lista), no solo sobre
        los `limit` finales, porque en este punto todavía no se sabe
        cuáles sobrevivirán a la fusión RRF (o al reranking); el
        `parent_chunk` de cada candidato se conserva al armar el
        resultado final, tanto con RRF puro como con reranking.

        max_access_level (Pista B.3 del ADR-003, docs proyecto/
        RAG_STUDIO_Propuesta_B3_Control_Acceso.docx): se reenvía sin
        cambios a SemanticSearch y TextSearch, igual criterio que
        only_usable_sources -- se filtra antes de fusionar, no después,
        para que RRF/el reranker nunca lleguen a ver un candidato que
        de todos modos se descartaría."""
        if rerank and self._reranker is None:
            raise RerankerUnavailableError()

        semantic_results = self._semantic.execute(
            project_id, query_text, limit=candidate_limit, source_id=source_id,
            only_usable_sources=only_usable_sources, expand_to_parent=expand_to_parent,
            max_access_level=max_access_level, source_ids=source_ids,
        )
        text_results = self._text.execute(
            project_id, query_text, limit=candidate_limit, source_id=source_id,
            only_usable_sources=only_usable_sources, expand_to_parent=expand_to_parent,
            max_access_level=max_access_level, source_ids=source_ids, use_hierarchy=use_hierarchy,
        )

        fused_scores: dict[str, float] = {}
        result_by_id: dict[str, SemanticSearchResult] = {}
        for ranked_list in (semantic_results, text_results):
            for rank, result in enumerate(ranked_list, start=1):
                fused_scores[result.chunk.id] = (
                    fused_scores.get(result.chunk.id, 0.0) + 1.0 / (_RRF_RANK_CONSTANT + rank)
                )
                # Si el mismo chunk aparece en ambas listas, cualquiera
                # de las dos sirve para recuperar chunk/parent_chunk --
                # expand_to_parent no depende del método de búsqueda,
                # así que ambas ramas habrían resuelto el mismo padre.
                result_by_id[result.chunk.id] = result

        # Ronda 100: tercera lista RRF, jerárquica -- los MISMOS candidatos
        # (nunca agrega fragmentos nuevos ni pasa por encima de filtros),
        # ordenados por cuántos términos de la consulta aparecen en su ruta
        # de encabezados (chunk.section_path), con ordinales normalizados.
        # Solo participan candidatos con alguna coincidencia: sin rutas
        # guardadas (fragmentos anteriores a la Ronda 100 u otras
        # estrategias) la lista queda vacía y el resultado es el de siempre.
        hierarchy_terms: dict[str, list[str]] = {}
        hierarchy_weight: dict[str, int] = {}
        conflicts: dict[str, list[str]] = {}
        if use_hierarchy:
            jerarquia = hierarchy_rank(
                query_text, [(chunk_id, result_by_id[chunk_id].chunk.section_path) for chunk_id in result_by_id],
            )
            for rank, (chunk_id, terminos) in enumerate(jerarquia, start=1):
                fused_scores[chunk_id] += 1.0 / (_RRF_RANK_CONSTANT + rank)
                hierarchy_terms[chunk_id] = terminos
                hierarchy_weight[chunk_id] = sum(2 if "_" in t else 1 for t in terminos)
            # Ronda 101 (validación real de NEXOM): un fragmento cuya ruta
            # dice "6.º semestre" cuando la consulta pide explícitamente el
            # quinto contradice la consulta. Ver _final_key.
            for chunk_id in result_by_id:
                conflicto = ordinal_conflicts(query_text, result_by_id[chunk_id].chunk.section_path)
                if conflicto:
                    conflicts[chunk_id] = conflicto

        def _final_key(chunk_id: str, score: float) -> tuple:
            """Ronda 101: orden final. 1) primero los candidatos SIN conflicto
            de ordinal explícito; 2) el score (RRF o reranker+jerarquía); 3) a
            igual score, el de mayor coincidencia jerárquica. Sin ordinales en
            la consulta o sin rutas, 1) y 3) no distinguen nada y el orden es
            el de siempre."""
            return (0 if chunk_id in conflicts else 1, score, hierarchy_weight.get(chunk_id, 0))

        ordered = sorted(fused_scores.items(), key=lambda pair: _final_key(*pair), reverse=True)

        if not rerank:
            return [
                SemanticSearchResult(
                    chunk=result_by_id[chunk_id].chunk, score=score,
                    parent_chunk=result_by_id[chunk_id].parent_chunk,
                    hierarchy_terms=hierarchy_terms.get(chunk_id, []),
                    hierarchy_conflicts=conflicts.get(chunk_id, []),
                )
                for chunk_id, score in ordered[:limit]
            ]

        # ADR-003, Pista A.2: se le pasa al Reranker el lote ya
        # fusionado por RRF (hasta candidate_limit candidatos, no solo
        # los `limit` finales) -- igual que RRF necesita material real
        # de las dos listas para poder mejorar el orden, el Reranker
        # necesita más de `limit` candidatos para poder promover uno
        # que RRF dejó fuera del primer lugar.
        candidates = ordered[:candidate_limit]
        candidate_chunks = [result_by_id[chunk_id].chunk for chunk_id, _ in candidates]
        # Ronda 100: con la señal jerárquica activa, el reranker recibe la
        # ruta de encabezados antes del texto ("Bachillerato — Plantel X >
        # Área … > 5.º semestre\n<texto>"). Solo es la entrada del reranker
        # en esta consulta: no cambia chunk.text ni el vector indexado.
        textos_rerank = [
            contextualized_text(chunk.text, chunk.section_path) if use_hierarchy else chunk.text
            for chunk in candidate_chunks
        ]
        rerank_scores = self._reranker.score(query_text, textos_rerank)
        # Auditoría Ronda 21: el contrato de Reranker.score exige un puntaje
        # por candidato en el mismo orden, pero nada impide que un adaptador
        # mal implementado devuelva más o menos -- sin esta verificación,
        # zip(..., strict=True) lanzaría un ValueError crudo en vez de un
        # error de dominio reconocible por quien llama (mismo criterio que
        # EmbeddingProviderError: cualquier falla de un modelo/proveedor real
        # debe llegar como una excepción propia del contexto RAG, no como un
        # error genérico de Python).
        if len(rerank_scores) != len(candidate_chunks):
            raise RerankerError(
                f"El reranker {self._reranker.model_name!r} devolvió {len(rerank_scores)} puntaje(s) "
                f"para {len(candidate_chunks)} candidato(s) -- deben coincidir uno a uno."
            )
        reranked = sorted(
            zip(candidate_chunks, rerank_scores, strict=True), key=lambda pair: pair[1], reverse=True,
        )
        if use_hierarchy and hierarchy_terms:
            # Ronda 100: el orden del reranker se fusiona (RRF) con la lista
            # jerárquica de estos mismos candidatos, para que la señal de la
            # ruta no se pierda al reordenar; el score devuelto sigue siendo el
            # del reranker. Medido en evaluacion_recuperacion.py: sin esta
            # fusión el reranker (modelo en inglés) deshacía la mejora.
            posicion = {chunk.id: i for i, (chunk, _) in enumerate(reranked, start=1)}
            jerarquica = {
                chunk_id: i for i, (chunk_id, _) in enumerate(
                    hierarchy_rank(query_text, [(c.id, c.section_path) for c in candidate_chunks]), start=1,
                )
            }
            fusion = {
                chunk_id: 1.0 / (_RRF_RANK_CONSTANT + pos)
                + (1.0 / (_RRF_RANK_CONSTANT + jerarquica[chunk_id]) if chunk_id in jerarquica else 0.0)
                for chunk_id, pos in posicion.items()
            }
            # Ronda 101 (validación real de NEXOM): antes la fusión dejaba
            # EMPATES -- reranker 1.º + jerarquía 2.º contra reranker 2.º +
            # jerarquía 1.º suman lo mismo -- y el desempate quedaba en el
            # orden del reranker, que en el caso real ponía "6.º semestre"
            # sobre el "5.º" pedido. Ahora el orden final usa _final_key:
            # conflicto de ordinal, fusión y, a igual fusión, coincidencia
            # jerárquica.
            reranked = sorted(reranked, key=lambda pair: _final_key(pair[0].id, fusion[pair[0].id]), reverse=True)
        elif use_hierarchy and conflicts:
            reranked = sorted(reranked, key=lambda pair: _final_key(pair[0].id, pair[1]), reverse=True)
        return [
            SemanticSearchResult(
                chunk=chunk, score=score, parent_chunk=result_by_id[chunk.id].parent_chunk,
                hierarchy_terms=hierarchy_terms.get(chunk.id, []),
                hierarchy_conflicts=conflicts.get(chunk.id, []),
            )
            for chunk, score in reranked[:limit]
        ]
