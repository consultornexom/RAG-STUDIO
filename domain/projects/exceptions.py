"""Excepciones del contexto Proyectos. Puras, sin dependencias externas."""


class ProjectDomainError(Exception):
    """Base de todos los errores del dominio de proyectos."""


class ProjectNotFoundError(ProjectDomainError):
    def __init__(self, project_id: str):
        super().__init__(f"No existe un proyecto con id={project_id!r}")
        self.project_id = project_id


class DuplicateProjectError(ProjectDomainError):
    def __init__(self, name: str):
        # Ronda 88: mensaje en lenguaje de usuario y sin los espacios
        # sobrantes que el nombre pueda traer (Project.name los recorta).
        super().__init__(
            f"Ya existe un proyecto llamado {name.strip()!r} en esta instalación. Elija otro nombre."
        )
        self.name = name


class InvalidStatusTransitionError(ProjectDomainError):
    def __init__(self, current: str, target: str):
        super().__init__(f"Transición de estado no permitida: {current} -> {target}")
        self.current = current
        self.target = target


class IntegrityViolationError(ProjectDomainError):
    """Se lanza cuando un .agentproj no verifica su hash o manifiesto."""


class ProjectIdCollisionError(ProjectDomainError):
    """Auditoría Ronda 48 (pruebas reales con documentos de Licenciatura/):
    import_project() nunca comprobaba si el project_id de destino ya
    tenía datos reales en disco -- un paquete cuyo manifiesto declarara
    (a propósito o por accidente) el id de un proyecto ya existente
    mezclaba silenciosamente sus archivos con los del proyecto
    existente, sin ninguna advertencia. Se lanza en vez de escribir
    nada cuando ese id ya pertenece a un proyecto registrado.

    Ronda 88 (2026-10-02): el mensaje anterior pedía "indicar un id nuevo
    (new_project_id)", algo que la interfaz no permitía hacer. Ahora la
    interfaz ofrece importar como copia (id nuevo generado
    automáticamente) y el mensaje lo explica en esos términos."""

    def __init__(self, project_id: str, existing_name: str = ""):
        nombre = f" ({existing_name!r})" if existing_name else ""
        super().__init__(
            f"Este paquete corresponde a un proyecto que ya está en esta instalación{nombre}, "
            f"id={project_id!r}. Importarlo encima mezclaría sus archivos. Puede importarlo "
            "como copia: se le asigna un identificador nuevo y el proyecto existente no se toca."
        )
        self.project_id = project_id
        self.existing_name = existing_name


class ImportResidueError(ProjectDomainError):
    """Ronda 88 (2026-10-02, hallazgo real de usuario): una importación
    anterior falló DESPUÉS de copiar los archivos del paquete (por
    ejemplo por un nombre de proyecto repetido), y dejó en
    projects/<id>/ una carpeta que no está registrada como proyecto.
    Antes, cualquier reintento chocaba con ProjectIdCollisionError sin
    salida desde la interfaz. Ahora se informa qué pasó y se ofrece
    apartar esa carpeta (se mueve, no se borra) y continuar."""

    def __init__(self, project_id: str):
        super().__init__(
            f"Hay restos de una importación anterior incompleta de este paquete (carpeta del "
            f"proyecto id={project_id!r} sin registrar en la lista de proyectos). Puede apartarlos "
            "y continuar: se mueven a la carpeta 'residuos_importacion' de la instalación, no se borran."
        )
        self.project_id = project_id


class ImportNameCollisionError(ProjectDomainError):
    """Ronda 88 (2026-10-02, hallazgo real de usuario): el nombre del
    proyecto del paquete ya lo usa otro proyecto de esta instalación.
    Antes se descubría al final, como un IntegrityError crudo de SQLite
    ("UNIQUE constraint failed: project_index.name"), y dejaba los
    archivos copiados en disco (ver ImportResidueError). Ahora se detecta
    antes de copiar nada y la interfaz pide otro nombre."""

    def __init__(self, name: str, suggested_name: str):
        super().__init__(
            f"Ya existe un proyecto llamado {name!r} en esta instalación. Para importar el paquete, "
            f"elija otro nombre (por ejemplo {suggested_name!r}). El proyecto existente no se modifica."
        )
        self.name = name
        self.suggested_name = suggested_name


class ProjectInUseError(ProjectDomainError):
    """Ronda 3 (punto 13) / Ronda 4 de Validacion_observaciones_RAG_STUDIO.md:
    hoy la única forma de "quitar de en medio" un proyecto es Archivar,
    una transición permanente -- no hay eliminación real. Se agrega
    borrado real, pero solo para un proyecto vacío (sin fuentes
    registradas): mismo criterio ya usado para campos y catálogos
    (bloquear si ya hay datos de negocio dependientes, para no perder
    trabajo por accidente)."""

    def __init__(self, project_id: str, source_count: int):
        super().__init__(
            f"No se puede eliminar el proyecto {project_id!r}: ya tiene {source_count} fuente(s) "
            "registrada(s). Si de verdad quieres dejar de usarlo, archívalo en vez de eliminarlo."
        )
        self.project_id = project_id
        self.source_count = source_count


class MissingIdentityPolicyError(ProjectDomainError):
    """RAG-INC-01a (Alcance firmado, decisión INC01-D3): importar un proyecto
    exige indicar explícitamente `identity_policy` ("preserve" o "fork").
    Sin ella, la importación aborta antes de leer o modificar datos: RAG
    Studio nunca decide en silencio qué hacer con la identidad."""

    def __init__(self, recibido: object = None):
        detalle = "" if recibido is None else f" (recibido: {recibido!r})"
        super().__init__(
            "Falta indicar cómo tratar la identidad del proyecto importado: "
            f"identity_policy debe ser 'preserve' o 'fork'{detalle}."
        )


class KnowledgeBaseIdentityCollisionError(ProjectDomainError):
    """RAG-INC-01a: el paquete conserva una identidad de base de conocimiento
    (`knowledge_base_id`) que ya tiene un proyecto de esta instalación,
    activo o archivado. Con `identity_policy="preserve"` la importación se
    detiene sin modificar nada; la alternativa es importarlo como copia
    (`identity_policy="fork"`), que le asigna una identidad nueva."""

    def __init__(self, knowledge_base_id: str, existing_project_id: str, existing_name: str = ""):
        nombre = f" «{existing_name}»" if existing_name else ""
        super().__init__(
            f"Este paquete conserva la identidad de una base de conocimiento que ya existe en esta "
            f"instalación: la del proyecto{nombre} (id={existing_project_id!r}). Importarlo tal cual "
            "dejaría dos proyectos con la misma identidad. Puede importarlo como copia: recibe una "
            "identidad nueva y el proyecto existente no se toca."
        )
        self.knowledge_base_id = knowledge_base_id
        self.existing_project_id = existing_project_id
        self.existing_name = existing_name


class ImportLockTimeoutError(ProjectDomainError):
    """RAG-INC-01a: otra importación (de este u otro proceso) tiene tomado el
    bloqueo de la instalación más allá del tiempo máximo. No se modificó nada."""

    def __init__(self, segundos: float):
        super().__init__(
            f"Otra importación de proyecto está en curso en esta instalación (se esperó {segundos:.0f} s). "
            "No se modificó nada; vuelva a intentarlo cuando termine."
        )
        self.segundos = segundos


class ImportIdentityCheckError(ProjectDomainError):
    """RAG-INC-01a (caso L-04): no se pudo leer la identidad de algún proyecto
    instalado, así que no puede garantizarse la ausencia de colisión. La
    importación aborta (fail-closed) sin modificar nada."""

    def __init__(self, project_id: str, causa: str):
        super().__init__(
            f"No se pudo verificar la identidad del proyecto instalado id={project_id!r} ({causa}). "
            "Por seguridad, la importación se detuvo sin modificar nada."
        )
        self.project_id = project_id
