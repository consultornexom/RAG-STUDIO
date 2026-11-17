"""Escribe `build_info.json` en la raíz del código (Ronda 104b, Etapa 0).

Úsese ANTES de preparar un ZIP de código, un paquete de despliegue o un
ejecutable, desde un checkout de git:

    python scripts/escribir_build_info.py

El archivo registra versión, commit, si había cambios sin commit y la
huella del código (ver infrastructure/build_info.py). Así un Runtime
instalado sin `.git` puede informar con qué código corre. No contiene
rutas, nombres de equipo, usuarios ni secretos. No se versiona en git
(está en .gitignore): se genera para cada entrega.

Con --verificar <carpeta> compara la huella del código de esa carpeta (p. ej.
un ZIP descomprimido o la instalación del Runtime) con la de este checkout.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from infrastructure.build_info import (  # noqa: E402
    BUILD_INFO_FILENAME, compute_package_fingerprints, resolve_code_identity,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", type=Path, help="carpeta de código a comparar con este checkout")
    a = ap.parse_args()
    if a.verificar:
        # Se comparan las carpetas presentes en ambos lados (la imagen del
        # Runtime no lleva ui/, por ejemplo).
        propia, otra = compute_package_fingerprints(RAIZ), compute_package_fingerprints(a.verificar.resolve())
        comunes = sorted(set(propia) & set(otra))
        iguales = [p for p in comunes if propia[p] == otra[p]]
        for paquete in comunes:
            print(f"{paquete:15} {'igual' if paquete in iguales else 'DISTINTA'}")
        print(f"solo en este checkout: {sorted(set(propia) - set(otra))}; solo en {a.verificar}: "
              f"{sorted(set(otra) - set(propia))}")
        ok = bool(comunes) and len(iguales) == len(comunes)
        print("COINCIDEN" if ok else "NO COINCIDEN")
        return 0 if ok else 1
    destino = RAIZ / BUILD_INFO_FILENAME
    if destino.exists():
        destino.unlink()  # que no se lea el anterior al resolver la identidad
    identidad = resolve_code_identity(RAIZ)
    if identidad.commit_source != "git":
        print("No se pudo leer el commit con git: ejecute este script desde un checkout de git.", file=sys.stderr)
        return 1
    datos = {
        "format": "ragstudio.build_info", "format_version": 1,
        "version": identidad.version, "commit": identidad.commit, "dirty": identidad.dirty,
        "code_fingerprint": identidad.fingerprint,
        "package_fingerprints": identidad.package_dict(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(datos, indent=2, ensure_ascii=False))
    if identidad.dirty:
        print("ADVERTENCIA: hay cambios sin commit; el commit no describe exactamente este código "
              "(la huella sí).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
