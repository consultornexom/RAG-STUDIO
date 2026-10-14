"""Caso de uso: fragmentar el texto ya extraído de una Source
(INVESTIGACION.odt, A2/A3, Módulo 5).

Resolución de política (RAG STUDIO.odt, sección 21: nada de tipos
documentales fijos en código): se busca primero una FragmentationPolicy
para el document_type_code recibido, luego una "default" del proyecto,
y si no existe ninguna, se usa una política interna con los parámetros
iniciales sugeridos por A2 (350-700 tokens narrativos → 500 de punto
medio, solapamiento 40-100 → 60, fusión bajo 80 tokens).

Reproducibilidad (criterio de aceptación de A3): volver a fragmentar la
misma fuente con la misma política borra los fragmentos anteriores y
genera un conjunto lógico equivalente (misma cantidad, mismo texto,
mismo orden); solo cambian los identificadores, que nunca se prometen
estables entre corridas.
"""
from __future__ import annotations

from typing import Callable, Optional

from domain.ingestion.entities import Chunk, ChunkType, FragmentationPolicy, FragmentationStrategy
from domain.ingestion.exceptions import ExtractionNotFoundError, TokenizerError
from domain.ingestion.ports import (
    ChunkRepository, ExtractionRepository, FragmentationPolicyRepository, TokenCounter,
)
from domain.ingestion.splitting import (
    CountTokensFn, TextSpan, merge_small_spans, resolve_page, split_by_articles, split_by_headings,
    split_by_qa_pairs, split_by_size, split_by_tables, word_count,
)
from domain.metadata.ports import MetadataSchemaRepository, SourceMetadataRepository



class FragmentSource:
    def __init__(
        self,
        extraction_repository: ExtractionRepository,
        policy_repository: FragmentationPolicyRepository,
        chunk_repository: ChunkRepository,
        schema_repository: MetadataSchemaRepository,
        source_metadata_repository: SourceMetadataRepository,
        token_counter: Optional[TokenCounter] = None,
    ):
        self._extraction_repository = extraction_repository
        self._policy_repository = policy_repository
        self._chunk_repository = chunk_repository
        self._schema_repository = schema_repository
        self._source_metadata_repository = source_metadata_repository
        # token_counter es una capacidad opcional (ítem 7 de la
        # evaluación de madurez post-8-etapas, mismo patrón que
        # embedding_provider_factory/ocr_engine): sin ella, se sigue
        # usando word_count -- cero cambio de comportamiento.
        self._token_counter = token_counter

    def execute(
        self,
        project_id: str,
        source_id: str,
        schema_id: Optional[str] = None,
        document_type_code: str = "default",
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> Optional[list[Chunk]]:
        """Fragmenta y guarda los Chunk de una fuente.

        `is_cancelled` es cancelación cooperativa (ver
        workers.jobs.JobHandle.is_cancelled). A diferencia de
        ExtractSourceText (una sola llamada atómica al extractor), aquí
        sí hay un bucle real por fragmento -- para una fuente con
        muchas secciones/fragmentos, revisar `is_cancelled` en cada
        vuelta permite abortar de verdad a la mitad, sin esperar a que
        se arme la lista completa. Si se cancela en cualquier punto
        (antes de dividir, durante el armado de fragmentos, o después
        pero antes de guardar), no se toca `delete_for_source` ni
        `save_many`: los fragmentos anteriores de la fuente quedan
        intactos, tal como estaban antes de pedir la re-fragmentación.
        Devuelve `None` en ese caso (ver ExtractSourceText.execute para
        el mismo criterio).
        """
        if is_cancelled():
            return None

        record = self._extraction_repository.get(project_id, source_id)
        if record is None:
            raise ExtractionNotFoundError(source_id)

        count_tokens = self._resolve_count_tokens()
        policy = self._resolve_policy(project_id, document_type_code)
        titled_spans, section_spans = self._split(record.text, policy, count_tokens, record.structured_blocks)
        inherited_metadata = self._resolve_inherited_metadata(project_id, schema_id, source_id)

        chunks: list[Chunk] = []
        section_indices: list[Optional[int]] = []
        section_titles: dict[int, Optional[str]] = {}
        for index, (title, span, chunk_type, section_index, structured_content) in enumerate(titled_spans):
            if is_cancelled():
                return None
            chunks.append(Chunk(
                project_id=project_id, source_id=source_id, chunk_index=index,
                text=span.text.strip(), token_count=count_tokens(span.text),
                section_title=title, chunk_type=chunk_type,
                page_start=resolve_page(span.char_start, record.page_breaks),
                page_end=resolve_page(max(span.char_end - 1, span.char_start), record.page_breaks),
                inherited_metadata=inherited_metadata,
                structured_content=structured_content,
            ))
            section_indices.append(section_index)
            if section_index is not None and section_index not in section_titles:
                section_titles[section_index] = title

        if is_cancelled():
            return None

        for i, chunk in enumerate(chunks):
            chunk.previous_chunk_id = chunks[i - 1].id if i > 0 else None
            chunk.next_chunk_id = chunks[i + 1].id if i < len(chunks) - 1 else None

        # Pista B.1 del ADR-003 (ver docs proyecto/
        # RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 5):
        # solo POR_ENCABEZADO produce jerarquía real por ahora. Un chunk
        # PADRE por sección se crea únicamente cuando esa sección
        # produjo MÁS de un chunk hijo -- si cupo entera en uno solo,
        # un padre sería un duplicado exacto del propio hijo, sin
        # aportar ningún contexto adicional. El padre se añade DESPUÉS
        # de construir la cadena previous/next_chunk_id: nunca forma
        # parte de esa cadena de lectura lineal, solo se recupera por
        # id al expandir contexto (application/rag/queries).
        if section_spans is not None:
            section_child_counts: dict[int, int] = {}
            for section_index in section_indices:
                if section_index is not None:
                    section_child_counts[section_index] = section_child_counts.get(section_index, 0) + 1

            padre_chunks: list[Chunk] = []
            padre_by_section: dict[int, Chunk] = {}
            for section_index, span in enumerate(section_spans):
                if section_child_counts.get(section_index, 0) <= 1:
                    continue
                padre = Chunk(
                    project_id=project_id, source_id=source_id,
                    chunk_index=len(chunks) + len(padre_chunks),
                    text=span.text.strip(), token_count=count_tokens(span.text),
                    section_title=section_titles.get(section_index), chunk_type=ChunkType.PADRE,
                    page_start=resolve_page(span.char_start, record.page_breaks),
                    page_end=resolve_page(max(span.char_end - 1, span.char_start), record.page_breaks),
                    inherited_metadata=inherited_metadata,
                )
                padre_by_section[section_index] = padre
                padre_chunks.append(padre)

            for chunk, section_index in zip(chunks, section_indices, strict=True):
                if section_index is not None and section_index in padre_by_section:
                    chunk.parent_chunk_id = padre_by_section[section_index].id

            chunks.extend(padre_chunks)

        # replace_for_source (auditoría posterior a la Ronda 76, ver
        # bitácora): antes de esta ronda, aquí se llamaba a
        # delete_for_source() y save_many() por separado -- dos
        # transacciones independientes en la implementación SQL. Si
        # save_many() fallaba a mitad de camino (disco lleno, base de
        # datos bloqueada), el borrado ya se había confirmado: la
        # fuente quedaba con CERO chunks, peor que antes de pedir la
        # re-fragmentación. replace_for_source() hace ambas cosas en
        # una sola transacción -- ver domain.ingestion.ports.
        # ChunkRepository.replace_for_source.
        self._chunk_repository.replace_for_source(project_id, source_id, chunks)
        return chunks

    def _resolve_policy(self, project_id: str, document_type_code: str) -> FragmentationPolicy:
        policy = self._policy_repository.get_policy(project_id, document_type_code)
        if policy is not None:
            return policy
        if document_type_code != "default":
            policy = self._policy_repository.get_policy(project_id, "default")
            if policy is not None:
                return policy
        # Sin **dict de por medio (antes _DEFAULT_POLICY_PARAMS): se
        # apoya directamente en los valores por defecto ya declarados
        # en FragmentationPolicy (domain/ingestion/entities.py), que
        # son exactamente estos mismos -- una sola fuente de verdad,
        # y con tipos verificables por mypy.
        return FragmentationPolicy(project_id=project_id, document_type_code="default")

    def _resolve_count_tokens(self) -> CountTokensFn:
        """Ítem 7 de la evaluación de madurez post-8-etapas: resuelve
        una sola vez por corrida si hay un tokenizador real disponible
        -- una llamada de prueba basta para saber si está instalado y
        si ya se pudo descargar su codificación (ver
        infrastructure.tokenization.tiktoken_counter). Si falla, se
        usa `word_count` para el resto de esta corrida, sin abortar la
        fragmentación -- la próxima corrida vuelve a intentarlo (por
        si la conexión a internet aparece más tarde), en vez de
        recordar el fallo para siempre."""
        if self._token_counter is None:
            return word_count
        try:
            self._token_counter.count_tokens("prueba")
        except TokenizerError:
            return word_count
        return self._token_counter.count_tokens

    def _split(
        self, text: str, policy: FragmentationPolicy, count_tokens: CountTokensFn,
        structured_blocks: Optional[dict[str, dict]] = None,
    ) -> tuple[
        list[tuple[Optional[str], TextSpan, ChunkType, Optional[int], Optional[dict]]], Optional[list[TextSpan]],
    ]:
        """Devuelve `(titled_spans, section_spans)`.

        `section_spans` solo es distinto de `None` para POR_ENCABEZADO
        (Pista B.1 del ADR-003, diseño en docs proyecto/
        RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 5):
        es la lista de secciones completas (una por encabezado, sin
        sub-dividir), en el mismo orden que sus índices en
        `titled_spans` (4to elemento de cada tupla, `section_index`).
        `execute()` usa `section_spans` para construir un chunk PADRE
        por sección que sí se sub-dividió en más de un chunk hijo.
        Para el resto de las estrategias, `section_index` es `None`
        en cada tupla y `section_spans` es `None` -- cero cambio de
        comportamiento.

        5to elemento de cada tupla, `structured_content` (Pista B.2 del
        ADR-003): `None` para toda estrategia excepto
        POR_HOJA_ESTRUCTURADA -- el resto de los chunks no tiene
        contenido estructurado propio."""
        if policy.strategy == FragmentationStrategy.DOCUMENTO_COMPLETO:
            stripped = text.strip()
            if not stripped:
                return [], None
            start = text.index(stripped[0])
            span = TextSpan(text=stripped, char_start=start, char_end=start + len(stripped))
            return [(None, span, ChunkType.TEXTO, None, None)], None

        if policy.strategy == FragmentationStrategy.POR_TAMANIO:
            spans = split_by_size(text, policy.target_tokens, policy.overlap_tokens, count_tokens=count_tokens)
            spans = merge_small_spans(spans, policy.min_tokens, count_tokens=count_tokens)
            return [(None, span, ChunkType.TEXTO, None, None) for span in spans], None

        if policy.strategy == FragmentationStrategy.POR_ENCABEZADO:
            sections = split_by_headings(text)
            result: list[tuple[Optional[str], TextSpan, ChunkType, Optional[int], Optional[dict]]] = []
            section_spans: list[TextSpan] = []
            for section_index, (title, span) in enumerate(sections):
                section_spans.append(span)
                if count_tokens(span.text) <= policy.target_tokens:
                    result.append((title, span, ChunkType.TEXTO, section_index, None))
                    continue
                sub_spans = split_by_size(
                    span.text, policy.target_tokens, policy.overlap_tokens, count_tokens=count_tokens,
                )
                sub_spans = merge_small_spans(sub_spans, policy.min_tokens, count_tokens=count_tokens)
                for sub in sub_spans:
                    result.append((title, TextSpan(
                        text=sub.text, char_start=span.char_start + sub.char_start,
                        char_end=span.char_start + sub.char_end,
                    ), ChunkType.TEXTO, section_index, None))
            return result, section_spans

        if policy.strategy == FragmentationStrategy.POR_ARTICULO:
            # Reglamento: un fragmento por artículo completo, sin
            # sub-dividir aunque exceda target_tokens ni fusionar los
            # cortos con el vecino -- el artículo completo es la
            # unidad mínima (INVESTIGACION.odt, A2).
            return [(title, span, ChunkType.TEXTO, None, None) for title, span in split_by_articles(text)], None

        if policy.strategy == FragmentationStrategy.PREGUNTA_RESPUESTA:
            # FAQ: un fragmento por pregunta+respuesta completa, sin
            # solapamiento ni fusión de fragmentos cortos -- una
            # respuesta corta sigue siendo su propia pregunta, no debe
            # mezclarse con la pregunta vecina.
            return [
                (title, span, ChunkType.PREGUNTA_RESPUESTA, None, None)
                for title, span in split_by_qa_pairs(text)
            ], None

        if policy.strategy == FragmentationStrategy.POR_TABLA:
            return [
                (title, span, ChunkType.TABLA if is_table else ChunkType.TEXTO, None, None)
                for title, span, is_table in split_by_tables(text, policy.target_tokens, count_tokens=count_tokens)
            ], None

        if policy.strategy == FragmentationStrategy.POR_HOJA_ESTRUCTURADA:
            return self._split_por_hoja_estructurada(text, structured_blocks or {}), None

        raise NotImplementedError(f"Estrategia de fragmentación no implementada: {policy.strategy}")

    def _split_por_hoja_estructurada(
        self, text: str, structured_blocks: dict[str, dict],
    ) -> list[tuple[Optional[str], TextSpan, ChunkType, Optional[int], Optional[dict]]]:
        """Pista B.2 del ADR-003 (docs proyecto/
        RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx, sección 3.2): un
        chunk ChunkType.ESTRUCTURADO por cada bloque de
        `structured_blocks` -- fuente de verdad de qué chunks existen,
        NUNCA sub-dividido aunque exceda el tamaño estándar (limitación
        conocida, documentada en el diseño). Los encabezados Markdown
        que ya produjo la extracción (`split_by_headings`) se usan solo
        como mejor esfuerzo para ubicar la página de cada bloque -- un
        CSV, por ejemplo, no tiene encabezado alguno, y aun así debe
        producir su único chunk "datos".

        Sin bloques estructurados (fuente no XLSX/CSV, o extractor sin
        esta capacidad), se degrada a DOCUMENTO_COMPLETO -- mismo
        criterio que un `## Título` sin cuerpo bajo POR_ENCABEZADO no
        es un caso especial de esta estrategia."""
        if not structured_blocks:
            stripped = text.strip()
            if not stripped:
                return []
            start = text.index(stripped[0])
            span = TextSpan(text=stripped, char_start=start, char_end=start + len(stripped))
            return [(None, span, ChunkType.TEXTO, None, None)]

        headings = dict(split_by_headings(text))
        result: list[tuple[Optional[str], TextSpan, ChunkType, Optional[int], Optional[dict]]] = []
        for title, block in structured_blocks.items():
            span = headings.get(title)
            if span is None:
                # CSV (clave fija "datos", sin encabezado Markdown) o
                # una hoja cuyo título no coincidió por algún motivo --
                # se usa el texto completo como mejor esfuerzo, en vez
                # de fallar o perder el bloque.
                stripped = text.strip()
                start = text.index(stripped[0]) if stripped else 0
                span = TextSpan(text=stripped, char_start=start, char_end=start + len(stripped))
            result.append((title, span, ChunkType.ESTRUCTURADO, None, block))
        return result

    def _resolve_inherited_metadata(
        self, project_id: str, schema_id: Optional[str], source_id: str,
    ) -> dict[str, str]:
        if schema_id is None:
            return {}
        fields = self._schema_repository.list_fields(project_id, schema_id)
        inherited_field_ids = {f.field_id for f in fields if f.inherited_by_chunks}
        if not inherited_field_ids:
            return {}
        values = self._source_metadata_repository.list_values_for_source(project_id, source_id)
        return {v.field_id: v.value for v in values if v.field_id in inherited_field_ids}
