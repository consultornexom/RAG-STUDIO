"""Excepciones del contexto Documentos. Puras, sin dependencias externas."""


class DocumentDomainError(Exception):
    """Base de todos los errores del dominio de documentos."""


class SourceNotFoundError(DocumentDomainError):
    def __init__(self, source_id: str):
        super().__init__(f"No existe una fuente con id={source_id!r}")
        self.source_id = source_id


class DuplicateSourceError(DocumentDomainError):
    """Se lanza cuando el hash de contenido ya existe para el proyecto
    y no se declaró explícitamente como sustitución de otra fuente."""

    def __init__(self, content_hash: str):
        super().__init__(
            f"Ya existe una fuente registrada con exactamente el mismo contenido en este "
            f"proyecto (huella de contenido {content_hash!r}). Si es una versión nueva del "
            'mismo documento, vuelve a registrarla indicando en "Esta fuente sustituye a" '
            "cuál es la fuente anterior."
        )
        self.content_hash = content_hash


class InvalidValidationTransitionError(DocumentDomainError):
    def __init__(self, current: str, target: str):
        super().__init__(f"Transición de estado de validación no permitida: {current} -> {target}")
        self.current = current
        self.target = target


class SourceStructuralFieldsLockedError(DocumentDomainError):
    """Se lanza al intentar cambiar `location` o `source_type` de una
    fuente que ya tiene una extracción guardada (contexto Ingesta).

    Cambiar el archivo o tipo detrás de una fuente después de haber
    extraído su texto dejaría la extracción, los fragmentos y el
    índice vectorial ya construidos apuntando en silencio a un
    contenido distinto al que en realidad hay ahora en esa ruta -- sin
    ningún aviso, no como el error ruidoso (aunque técnico) que se
    obtenía antes al intentar extraer desde una ruta mal capturada.
    RAG STUDIO ya tiene un mecanismo pensado para "este documento
    cambió de verdad": registrar una fuente nueva indicando
    `supersedes_source_id` -- eso preserva el historial en vez de
    reescribirlo. Ver README, bitácora, y RAG STUDIO.odt sobre el
    principio de trazabilidad documental."""

    def __init__(self, source_id: str):
        super().__init__(
            f"La fuente {source_id!r} ya tiene texto extraído; no se puede cambiar su "
            "ubicación ni su tipo sin invalidar en silencio la extracción, los fragmentos "
            "y el índice ya construidos. Si el documento cambió de verdad, registra una "
            'fuente nueva indicando en "Esta fuente sustituye a" que sustituye a esta -- '
            "eso conserva la trazabilidad en vez de reescribir el historial."
        )
        self.source_id = source_id


class OriginalCopyMissingError(DocumentDomainError):
    """RAG-INC-01 (relleno de content_hash): no existe la copia del original
    de la fuente en <proyecto>/sources/original/."""

    def __init__(self, source_id: str, detalle: str = ""):
        super().__init__(
            f"No hay copia del original de la fuente {source_id!r} en sources/original/ del proyecto."
            + (f" {detalle}" if detalle else "")
        )
        self.source_id = source_id
        self.detalle = detalle


class OriginalCopyUnreadableError(DocumentDomainError):
    """La copia del original existe pero no se pudo leer (o es ambigua)."""

    def __init__(self, source_id: str, causa: str):
        super().__init__(f"No se pudo leer la copia del original de la fuente {source_id!r}: {causa}")
        self.source_id = source_id
        self.causa = causa


class ContentHashBackfillConflictError(DocumentDomainError):
    """Al escribir, otra fuente del mismo linaje ya tenía el mismo hash
    (p. ej. registrada por otro proceso durante el relleno). La escritura se
    revirtió completa; volver a ejecutar el relleno la reclasifica."""

    def __init__(self, source_ids: list[str]):
        super().__init__(
            "El relleno de huellas se revirtió sin escribir nada: al escribir apareció una colisión de "
            f"contenido dentro del mismo linaje para {', '.join(sorted(source_ids))}. Vuelva a ejecutarlo."
        )
        self.source_ids = list(source_ids)
