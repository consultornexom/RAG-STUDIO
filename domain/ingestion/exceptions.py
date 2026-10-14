"""Excepciones del contexto Ingesta. Puras, sin dependencias externas."""


class IngestionDomainError(Exception):
    """Base de los errores del dominio de ingesta."""


class UnsupportedSourceTypeError(IngestionDomainError):
    """Se lanza cuando no hay un extractor de texto para el
    source_type de la fuente (por ejemplo xlsx, html, csv, json, xml,
    api, base_de_datos en esta iteración — ver README, limitaciones
    conocidas). imagen_escaneada sí tiene extractor desde Módulo 5
    (ImageTextExtractor), aunque sin OCR configurado no produce texto
    (ver EmptyExtractionError, no este error)."""

    def __init__(self, source_type: str):
        super().__init__(
            f"No hay un extractor de texto disponible para el tipo de fuente {source_type!r} "
            "en esta iteración."
        )
        self.source_type = source_type


class EmptyExtractionError(IngestionDomainError):
    """Se lanza cuando la extracción no produjo texto utilizable
    (archivo vacío, PDF escaneado sin capa de texto, etc.)."""

    def __init__(self, source_id: str):
        super().__init__(
            f"La extracción de la fuente {source_id!r} no produjo texto utilizable "
            "(¿archivo vacío o escaneado sin OCR?)."
        )
        self.source_id = source_id


class ExtractionNotFoundError(IngestionDomainError):
    """Se lanza al intentar fragmentar una fuente que todavía no ha
    sido extraída."""

    def __init__(self, source_id: str):
        super().__init__(f"La fuente {source_id!r} todavía no tiene texto extraído; extráela primero.")
        self.source_id = source_id


class SourceLocationUnreadableError(IngestionDomainError):
    """Se lanza cuando `Source.location` no apunta a un archivo legible
    (ruta inexistente, apunta a un directorio en vez de un archivo, o
    sin permisos de lectura). Antes de esto, el OSError crudo del
    sistema de archivos (p. ej. "[Errno 21] Es un directorio: '...'")
    llegaba tal cual hasta la UI -- funcional (no tumbaba la app), pero
    un mensaje técnico en vez de decir con claridad qué corregir
    (hallazgo real de validación visual: se registró una fuente con la
    carpeta contenedora en "Ubicación" en vez de la ruta completa del
    archivo, incluyendo su nombre)."""

    def __init__(self, source_id: str, location: str, detail: str):
        super().__init__(
            f"No se pudo leer el archivo de la fuente {source_id!r} en la ubicación "
            f"{location!r}: {detail}. Verifica que 'Ubicación' sea la ruta completa al "
            "archivo (incluyendo su nombre), no solo la carpeta que lo contiene -- puedes "
            "corregirla registrando la fuente de nuevo."
        )
        self.source_id = source_id
        self.location = location


class OcrEngineUnavailableError(IngestionDomainError):
    """Se lanza cuando hace falta OCR para una página de PDF sin capa
    de texto, pero el motor real (Tesseract) o alguna de sus
    dependencias (pytesseract, Pillow, PyMuPDF para rasterizar la
    página) no está disponible en este entorno. No detiene toda la
    extracción -- PdfTextExtractor la captura por página y sigue con
    el resto del documento, dejando esta razón en las advertencias en
    vez de un error técnico crudo."""

    def __init__(self, detail: str):
        super().__init__(detail)


class TokenizerError(IngestionDomainError):
    """Se lanza cuando el tokenizador real (ítem 7 de la evaluación de
    madurez post-8-etapas) no está disponible -- paquete no instalado,
    o falta la descarga inicial de la codificación sin conexión a
    internet (ver infrastructure/tokenization/tiktoken_counter.py).
    FragmentSource la captura y usa la aproximación por palabras como
    respaldo (ver domain.ingestion.splitting.word_count); no detiene
    la fragmentación."""

    def __init__(self, detail: str):
        super().__init__(detail)
