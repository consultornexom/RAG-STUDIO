"""Excepciones del contexto Metadatos."""


class MetadataDomainError(Exception):
    """Base de los errores del dominio de metadatos."""


class FieldDefinitionNotFoundError(MetadataDomainError):
    def __init__(self, field_id: str):
        super().__init__(f"No existe la definición de campo field_id={field_id!r}")
        self.field_id = field_id


class DuplicateFieldIdError(MetadataDomainError):
    def __init__(self, field_id: str):
        super().__init__(f"Ya existe un campo con field_id={field_id!r} en este esquema")
        self.field_id = field_id


class CatalogNotFoundError(MetadataDomainError):
    def __init__(self, catalog_id: str):
        super().__init__(f"No existe el catálogo catalog_id={catalog_id!r}")
        self.catalog_id = catalog_id


class CatalogEntryNotFoundError(MetadataDomainError):
    def __init__(self, catalog_id: str, value_code: str):
        super().__init__(f"El catálogo {catalog_id!r} no tiene la entrada {value_code!r}")


class DuplicateCatalogEntryError(MetadataDomainError):
    """Se lanza al intentar agregar una entrada con un value_code que ya
    existe en ese catálogo -- la base de datos ya lo impide con una
    restricción de unicidad real (uq_catalog_entry_code), pero sin esta
    verificación previa la UI/API recibía un IntegrityError crudo de
    SQLAlchemy en vez de un error de dominio legible (auditoría
    profunda, ronda posterior a la 76 -- mismo criterio que
    DuplicateFieldIdError)."""

    def __init__(self, catalog_id: str, value_code: str):
        super().__init__(f"Ya existe una entrada con value_code={value_code!r} en el catálogo {catalog_id!r}")
        self.catalog_id = catalog_id
        self.value_code = value_code


class SchemaAlreadyExistsError(MetadataDomainError):
    def __init__(self, project_id: str):
        super().__init__(f"Ya existe un esquema de metadatos activo para el proyecto {project_id!r}")
        self.project_id = project_id


class InvalidMetadataValueError(MetadataDomainError):
    """Se lanza cuando un valor no respeta su FieldDefinition: tipo,
    obligatoriedad o pertenencia a catálogo."""


class CatalogInUseError(MetadataDomainError):
    """Se lanza al intentar borrar un catálogo referenciado por al
    menos una FieldDefinition del esquema activo."""

    def __init__(self, catalog_id: str):
        super().__init__(
            f"No se puede eliminar el catálogo {catalog_id!r}: al menos un campo del "
            "esquema todavía lo referencia. Cambia o elimina esos campos primero."
        )
        self.catalog_id = catalog_id


class CatalogRequiredForFieldTypeError(MetadataDomainError):
    """Se lanza al intentar crear/editar un campo de tipo catálogo
    (selección única, selección múltiple o catálogo jerárquico) sin
    indicar catalog_id. Reemplaza, con un mensaje de dominio claro, el
    pydantic.ValidationError crudo que lanzaría FieldDefinition
    directamente (ver domain.metadata.entities) -- el mismo problema,
    pero con el mismo estilo de error que el resto de la aplicación
    (hallazgo real durante validación visual, ver README bitácora)."""

    def __init__(self, field_id: str, data_type: str):
        super().__init__(
            f"El campo {field_id!r} es de tipo {data_type!r} y necesita un catálogo "
            "asociado. Selecciona un catálogo antes de guardar (créalo primero en la "
            "pestaña Catálogos si todavía no existe)."
        )
        self.field_id = field_id
        self.data_type = data_type


class CatalogEntryInUseError(MetadataDomainError):
    """Se lanza al intentar borrar -- o, desde la Ronda 3/4 (punto 13 de
    Validacion_observaciones_RAG_STUDIO.md), cambiar el código de -- una
    entrada de catálogo que ya está guardada como valor de metadatos de
    alguna fuente. `action` deja el mensaje correcto para ambos casos
    sin duplicar la excepción."""

    def __init__(self, catalog_id: str, value_code: str, action: str = "eliminar"):
        super().__init__(
            f"No se puede {action} la entrada {value_code!r} del catálogo {catalog_id!r}: "
            "al menos una fuente todavía tiene ese valor asignado."
        )
        self.catalog_id = catalog_id
        self.value_code = value_code
        self.action = action


class SourceMetadataValueNotFoundError(MetadataDomainError):
    """Se lanza al intentar desasociar (DeleteSourceMetadataValue) un
    valor que ya no existe para esa fuente/campo -- por ejemplo si se
    borró entre que se listó "Valores actuales" en la UI y que se pulsó
    "Quitar valor" (Ronda 6, punto 23, hallazgo real de usuario)."""

    def __init__(self, source_id: str, field_id: str):
        super().__init__(
            f"La fuente {source_id!r} no tiene ningún valor asignado para el campo {field_id!r}"
        )
        self.source_id = source_id
        self.field_id = field_id


class FieldInUseError(MetadataDomainError):
    """Se lanza al intentar borrar un campo del esquema que ya tiene al
    menos un valor asignado en alguna fuente del proyecto (observación
    real de usuario, ver docs proyecto/Validacion_observaciones_RAG_STUDIO.md,
    punto 11: hasta ahora un campo creado por error quedaba permanente,
    sin ninguna forma de corregirlo desde la interfaz). Mismo criterio
    que CatalogEntryInUseError: no se permite borrar algo que ya tiene
    datos reales capturados, para no dejar valores huérfanos."""

    def __init__(self, field_id: str):
        super().__init__(
            f"No se puede eliminar el campo {field_id!r}: al menos una fuente ya tiene un "
            "valor asignado para este campo. Si de verdad necesitas corregirlo, crea un "
            "campo nuevo con la definición correcta."
        )
        self.field_id = field_id
