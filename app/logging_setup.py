"""Registro estructurado (ADR-001, sección 12 / Documento Maestro,
sección 9: nunca registrar credenciales ni datos sensibles).

Corrección (Ronda 11, ver Validacion_observaciones_RAG_STUDIO.md):
la versión anterior de `configure_logging` adjuntaba los handlers al
logger llamado literalmente "ragstudio" y le poní­a `propagate =
False`. Eso solo capturaba los mensajes de quien tuviera una
referencia directa a ESE objeto (como `context.logger` en
`app/bootstrap.py`) -- pero casi todo el resto del código (por
ejemplo `application/runtime/commands/handle_incoming_message.py`,
`application/plugins/commands/register_plugin.py`,
`ui/ingestion/panel.py`) usa el patrón estándar de Python
`logging.getLogger(__name__)`, que crea loggers con nombres como
"application.runtime.commands.handle_incoming_message" -- una rama
de la jerarquía de logging COMPLETAMENTE distinta de "ragstudio", no
un descendiente suyo. Esos mensajes nunca pasaban por los handlers de
"ragstudio": se perdían en el logger raíz (sin handlers propios) salvo
por el `lastResort` de Python, que solo imprime a stderr y solo desde
WARNING hacia arriba. Confirmado de forma empírica antes de este
arreglo: un `logger.info(...)` de un módulo cualquiera no aparecía en
`ragstudio.log` en absoluto, y un `logger.warning(...)` solo se veía
por consola, nunca en el archivo.

La corrección es el patrón estándar de Python para este caso:
configurar los handlers en el logger RAÍZ (nombre vacío) en vez de en
uno con nombre propio. Así, cualquier `logging.getLogger(__name__)` de
cualquier módulo de la aplicación -- presente o futuro, sin tener que
acordarse de nada especial al escribirlo -- propaga hacia arriba hasta
la raíz y queda capturado. El efecto secundario es que las
bibliotecas de terceros que también usan `getLogger(__name__)`
(SQLAlchemy, urllib3, huggingface_hub, qdrant_client...) EMPIEZAN a
propagar hacia la raíz también; se bajan explícitamente a WARNING
(`_QUIET_THIRD_PARTY_LOGGERS`) para no ahogar la señal propia de la
aplicación con ruido de librerías, sin silenciarlas del todo (un error
real de esas librerías sigue viéndose)."""
from __future__ import annotations

import logging
import re
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SENSITIVE_PATTERNS = [
    re.compile(r"(password|passwd|token|api[_-]?key|secret)\s*=\s*\S+", re.IGNORECASE),
]
_REDACTED = "[REDACTADO]"

# Bibliotecas de terceros conocidas por ser ruidosas en INFO/DEBUG --
# bajarlas a WARNING evita ahogar el propio registro de la aplicación
# ahora que todo propaga hasta la raíz (ver corrección de Ronda 11
# arriba). No es una lista cerrada: si otra biblioteca resulta
# ruidosa en el futuro, se agrega aquí, no se apaga el mecanismo.
_QUIET_THIRD_PARTY_LOGGERS = [
    "urllib3", "httpx", "httpcore", "huggingface_hub", "qdrant_client",
    "sqlalchemy.engine", "alembic",
]


class RedactSensitiveDataFilter(logging.Filter):
    """Defensa adicional: si algo con pinta de credencial llega a un log,
    se redacta en vez de escribirse en texto plano."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(message):
                record.msg = pattern.sub(lambda m: m.group(0).split("=")[0] + f"={_REDACTED}", message)
                record.args = ()
        return True


def configure_logging(
    logs_dir: str | Path, level: str = "INFO", filename: str = "ragstudio.log",
) -> logging.Logger:
    """Configura el logger RAÍZ (ver corrección de Ronda 11 en el
    docstring del módulo) y devuelve un logger de conveniencia
    (todavía llamado "ragstudio", para no romper a quien ya guarda
    esta referencia, p. ej. `AppContext.logger`) -- escribir en él o
    en cualquier `logging.getLogger(__name__)` de cualquier módulo
    tiene, a partir de esta corrección, exactamente el mismo efecto.

    `filename` es parametrizable (por defecto "ragstudio.log", el
    nombre histórico de la app de escritorio) para que un proceso
    hermano -- como `interfaces/api/`, que puede compartir el mismo
    `logs_dir` si se apunta a la misma instalación -- escriba en un
    archivo propio (p. ej. "ragstudio-api.log") en vez de competir por
    la rotación del mismo archivo desde dos procesos distintos."""
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        logs_dir / filename, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactSensitiveDataFilter())

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RedactSensitiveDataFilter())

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    for name in _QUIET_THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    return logging.getLogger("ragstudio")


def install_global_exception_hooks(logger: logging.Logger) -> None:
    """Instala `sys.excepthook`/`threading.excepthook` para que
    cualquier excepción no capturada explícitamente (fuera de los
    `try`/`except` de application/UI, o dentro de un hilo de
    `workers.jobs.ThreadJobRunner` que igual se le escape a su propio
    manejador) quede registrada en el log en vez de perderse sin dejar
    rastro -- ítem 5 de la segunda evaluación de madurez post-8-etapas
    (ver bitácora en README). Antes de este ítem, un crash así no
    dejaba nada utilizable para diagnosticar un problema real del
    usuario -- ahora al menos queda en `ragstudio.log` con el
    traceback completo, junto con el resto de lo que haya pasado antes
    (mismo archivo que ya redacta credenciales -- ver
    `RedactSensitiveDataFilter`).

    `KeyboardInterrupt` (Ctrl+C) se deja pasar al manejador por
    defecto sin registrarse como un error: es una interrupción
    intencional del usuario, no un fallo que alguien necesite
    diagnosticar."""

    def _handle_uncaught(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Excepcion no capturada -- la aplicacion puede haberse cerrado de forma "
            "anormal. Revisa este traceback, o exporta un diagnostico para soporte.",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _handle_uncaught_in_thread(args) -> None:
        thread_name = args.thread.name if args.thread is not None else "hilo desconocido"
        logger.critical(
            "Excepcion no capturada en un hilo en segundo plano (%s).",
            thread_name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _handle_uncaught
    threading.excepthook = _handle_uncaught_in_thread
