"""Puertos del contexto Ingesta. Implementados en infrastructure.

TextExtractor no es un repositorio: es un adaptador hacia librerías de
extracción (pypdf, python-docx) que domain no puede importar
directamente (ADR-001, sección 4: domain sin dependencias externas
salvo Pydantic). Por eso vive como puerto aquí y se implementa en
infrastructure/extraction/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.documents.entities import SourceType

from .entities import Chunk, ExtractionRecord, FragmentationPolicy


class TextExtractor(ABC):
    @abstractmethod
    def supports(self, source_type: SourceType) -> bool: ...

    @abstractmethod
    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        """Devuelve (texto, método usado, saltos de página, advertencias).

        source_type se recibe explícitamente (en vez de inferirse del
        archivo) para que el llamador decida con la misma fuente de
        verdad que ya usó para llamar a supports(); el propio
        CompositeTextExtractor lo necesita para elegir el adaptador
        concreto. saltos de página: desplazamientos de carácter donde
        inicia cada página nueva (lista vacía si el formato no tiene
        páginas)."""
        ...

    def extract_structured_blocks(self, location: str, source_type: SourceType) -> dict[str, dict]:
        """Pista B.2 del ADR-003 (ver `docs proyecto/
        RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx`, sección 3.1):
        bloques de contenido estructurado (columnas y filas nativas,
        sin aplanar a Markdown) que este extractor puede ofrecer
        ADEMÁS del texto de extract() -- nunca en vez de él.

        Método CONCRETO, no abstracto (a propósito, decisión de
        implementación distinta a la propuesta original del documento
        de diseño, que planteaba extender la tupla de extract(): eso
        habría tocado los nueve extractores existentes y sus ~30
        pruebas ya escritas solo para agregar un elemento vacío en la
        inmensa mayoría de los casos). Con este método aparte, devuelve
        un diccionario vacío por defecto -- cero cambio de
        comportamiento ni de código para cualquier extractor que no lo
        sobrescriba; solo XlsxExtractor/CsvExtractor lo pueblan de
        verdad. Mismo criterio de "capacidad opcional, aditiva" que
        ocr_engine en PdfTextExtractor."""
        return {}


class OcrEngine(ABC):
    """Adaptador hacia un motor OCR real (Tesseract, vía pytesseract).
    No es un TextExtractor completo: solo sabe convertir una imagen ya
    rasterizada de una sola página en texto -- PdfTextExtractor sigue
    siendo quien decide cuándo hace falta (páginas sin capa de texto)
    y quien arma el resultado final (Módulo 4: OCR para PDF
    escaneado)."""

    @abstractmethod
    def image_to_text(self, image_bytes: bytes) -> str:
        """image_bytes: una imagen ya rasterizada (PNG) de una sola
        página. Devuelve el texto reconocido (puede ser cadena vacía
        si la página no tiene texto legible)."""
        ...


class ExtractionRepository(ABC):
    @abstractmethod
    def save(self, record: ExtractionRecord) -> None: ...

    @abstractmethod
    def get(self, project_id: str, source_id: str) -> Optional[ExtractionRecord]: ...

    @abstractmethod
    def list_history(self, project_id: str, source_id: str) -> list[ExtractionRecord]:
        """Historial de auditoría (ítem 5 de la evaluación de madurez
        post-8-etapas), más reciente primero -- `get()` sigue
        devolviendo solo la extracción vigente (upsert), esto es lo
        que faltaba para poder responder "¿cuándo se extrajo esta
        fuente antes, y con qué resultado?" cada vez que se
        re-extrae. `save()` debe agregar una entrada aquí en cada
        llamada, incluida la primera (a diferencia del historial de
        metadatos, aquí no se filtra por "¿cambió de verdad?": cada
        corrida de extracción es un evento real por sí mismo, con su
        propio método/advertencias, aunque el texto resultante sea
        idéntico al anterior)."""
        ...


class ChunkRepository(ABC):
    @abstractmethod
    def save_many(self, project_id: str, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    def list_for_source(self, project_id: str, source_id: str) -> list[Chunk]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[Chunk]:
        """Todos los fragmentos del proyecto, de todas sus fuentes --
        a diferencia de list_for_source, que solo ve una fuente a la
        vez. Pensado para el comparador de modelos de embeddings (A vs
        B): comparar sobre "todo lo que hay indexado en el proyecto",
        igual que hace SemanticSearch cuando no se filtra por
        source_id."""
        ...

    @abstractmethod
    def get(self, project_id: str, chunk_id: str) -> Optional[Chunk]:
        """Busca un fragmento por id (Etapa 4: SemanticSearch necesita
        recuperar el Chunk completo -- texto, seccion, pagina -- a
        partir del id que devuelve el indice vectorial, que solo
        conoce id + payload, no el contenido)."""
        ...

    @abstractmethod
    def delete_for_source(self, project_id: str, source_id: str) -> None: ...

    @abstractmethod
    def replace_for_source(self, project_id: str, source_id: str, chunks: list[Chunk]) -> None:
        """Reemplaza TODOS los chunks de `source_id` por `chunks`, como
        una sola operación atómica: si guardar los nuevos falla, los
        chunks anteriores deben seguir intactos -- nunca un estado
        intermedio con menos chunks de los que había antes de pedir la
        re-fragmentación.

        Auditoría profunda (ronda posterior a la 76, ver bitácora):
        antes de este método, FragmentSource.execute() llamaba a
        delete_for_source() y luego a save_many() por separado -- dos
        transacciones independientes en la implementación SQL. Si
        save_many() fallaba a mitad de camino (disco lleno, base de
        datos bloqueada por otra sesión concurrente leyendo la misma
        fuente), delete_for_source() ya había confirmado su borrado:
        la fuente terminaba con CERO chunks, peor que antes de pedir
        la re-fragmentación. `chunks=[]` es un caso válido (fuente sin
        contenido usable tras fragmentar) -- deja la fuente sin
        chunks, igual que antes."""
        ...


class FragmentationPolicyRepository(ABC):
    @abstractmethod
    def save_policy(self, policy: FragmentationPolicy) -> None: ...

    @abstractmethod
    def get_policy(self, project_id: str, document_type_code: str) -> Optional[FragmentationPolicy]: ...

    @abstractmethod
    def list_policies(self, project_id: str) -> list[FragmentationPolicy]: ...


class TokenCounter(ABC):
    """Ítem 7 de la evaluación de madurez post-8-etapas: un tokenizador
    real (BPE u otro subword), para reemplazar la aproximación por
    palabras (`domain.ingestion.splitting.word_count`) al decidir
    tamaños de fragmento y al reportar `Chunk.token_count`. Capacidad
    opcional (igual patrón que EmbeddingProvider/OcrEngine): sin ella,
    FragmentSource sigue usando `word_count`, sin ningún cambio de
    comportamiento."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Puede lanzar `domain.ingestion.exceptions.TokenizerError` si
        el tokenizador no está disponible en este momento (paquete no
        instalado, o falta la descarga inicial sin conexión) -- quien
        llama decide si usar `word_count` como respaldo."""
        ...
