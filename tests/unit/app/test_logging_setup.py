"""Pruebas unitarias de install_global_exception_hooks (ítem 5 de la
segunda evaluación de madurez post-8-etapas, ver bitácora en README):
sys.excepthook/threading.excepthook deben registrar la excepción en el
log en vez de perderla, salvo KeyboardInterrupt.

También cubre la corrección de Ronda 11 en `configure_logging` (ver su
docstring): antes de esa ronda, un `logging.getLogger(__name__)`
cualquiera (el patrón que ya usaba el resto del código) nunca llegaba
al archivo -- solo lo que se escribía directamente sobre el objeto
"ragstudio" devuelto por `configure_logging`."""
from __future__ import annotations

import logging
import sys
import threading
from unittest.mock import MagicMock

import pytest

from app.logging_setup import configure_logging, install_global_exception_hooks


@pytest.fixture
def _restore_hooks():
    original_excepthook = sys.excepthook
    original_threading_excepthook = threading.excepthook
    yield
    sys.excepthook = original_excepthook
    threading.excepthook = original_threading_excepthook


def test_install_global_exception_hooks_logs_uncaught_exceptions(_restore_hooks):
    fake_logger = MagicMock()
    install_global_exception_hooks(fake_logger)

    try:
        raise ValueError("fallo simulado sin capturar")
    except ValueError:
        exc_info = sys.exc_info()

    sys.excepthook(*exc_info)

    assert fake_logger.critical.called
    _, kwargs = fake_logger.critical.call_args
    assert kwargs["exc_info"] == exc_info


def test_install_global_exception_hooks_does_not_log_keyboard_interrupt(_restore_hooks):
    fake_logger = MagicMock()
    install_global_exception_hooks(fake_logger)

    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        exc_info = sys.exc_info()

    sys.excepthook(*exc_info)

    assert not fake_logger.critical.called


def test_install_global_exception_hooks_logs_uncaught_thread_exceptions(_restore_hooks):
    fake_logger = MagicMock()
    install_global_exception_hooks(fake_logger)

    def _boom():
        raise RuntimeError("fallo simulado en un hilo")

    thread = threading.Thread(target=_boom, name="hilo-de-prueba")
    thread.start()
    thread.join(timeout=2.0)

    assert fake_logger.critical.called
    args, kwargs = fake_logger.critical.call_args
    assert "hilo-de-prueba" in args
    assert kwargs["exc_info"][0] is RuntimeError


@pytest.fixture
def _restore_root_logger():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers.clear()
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


def test_configure_logging_captures_records_from_any_module_logger(tmp_path, _restore_root_logger):
    # Regresión de Ronda 11: antes de la corrección, solo lo escrito
    # directamente sobre el objeto devuelto por configure_logging
    # llegaba al archivo -- un logger de módulo cualquiera (el patrón
    # usado en el resto del código) se perdía en silencio.
    configure_logging(tmp_path, level="INFO")

    module_logger = logging.getLogger("un.modulo.cualquiera.no.relacionado.con.ragstudio")
    module_logger.info("mensaje de un modulo cualquiera")

    log_content = (tmp_path / "ragstudio.log").read_text(encoding="utf-8")
    assert "mensaje de un modulo cualquiera" in log_content
    assert "un.modulo.cualquiera.no.relacionado.con.ragstudio" in log_content


def test_configure_logging_accepts_a_custom_filename(tmp_path, _restore_root_logger):
    configure_logging(tmp_path, level="INFO", filename="ragstudio-api.log")

    logging.getLogger(__name__).info("mensaje del runtime de la API")

    assert (tmp_path / "ragstudio-api.log").exists()
    assert not (tmp_path / "ragstudio.log").exists()


def test_configure_logging_quiets_known_noisy_third_party_loggers(tmp_path, _restore_root_logger):
    configure_logging(tmp_path, level="INFO")

    assert logging.getLogger("urllib3").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").getEffectiveLevel() == logging.WARNING
