"""Validación previa al arranque del runtime (Ronda 92).

Ejecuta exactamente la misma validación que `create_app_from_env`, sin
arrancar el servicio ni cargar modelos, e imprime la configuración
resuelta (sin secretos) o la lista de problemas:

    python -m interfaces.api.check_config
    python -m interfaces.api.check_config --verificar-huella

Código de salida 0 si se puede arrancar, 1 si no. `--verificar-huella`
recalcula la huella de contenido de la instantánea y la compara con la
registrada al publicarla (conviene usarlo ANTES del primer arranque:
el índice local puede reescribir archivos internos al abrirse).
"""
from __future__ import annotations

import argparse
import os
import sys

from .runtime_config import RuntimeConfigurationError, load_runtime_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m interfaces.api.check_config", description=__doc__)
    parser.add_argument("--verificar-huella", action="store_true", help="compara la huella de la instantánea")
    args = parser.parse_args(argv)

    from app.configuration import default_base_dir

    try:
        config = load_runtime_config(
            os.environ, default_home=str(default_base_dir()), verify_fingerprint=args.verificar_huella,
        )
    except RuntimeConfigurationError as exc:
        print(f"NO LISTO\n{exc}", file=sys.stderr)
        return 1
    print("LISTO para arrancar el runtime de RAG STUDIO")
    for linea in config.summary_lines():
        print(f"  {linea}")
    for aviso in config.warnings:
        print(f"  AVISO: {aviso}")
    if args.verificar_huella and config.pinned and not config.pinned.content_fingerprint:
        print("  AVISO: la instantánea no registra huella de contenido; no se pudo verificar.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
