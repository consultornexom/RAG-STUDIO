"""Ronda 104b, Etapa 0: identidad del código (versión, commit, huella)."""
import json

from infrastructure.build_info import (
    compute_code_fingerprint, compute_package_fingerprints, current_code_identity, resolve_code_identity,
)


def _codigo(tmp_path, contenido=b"x = 1\n"):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "ragstudio"\nversion = "9.9.9"\n')
    for paquete in ("domain", "application"):
        (tmp_path / paquete).mkdir()
        (tmp_path / paquete / "m.py").write_bytes(contenido)
    return tmp_path


def test_sin_git_ni_build_info_el_commit_es_desconocido_y_lo_dice(tmp_path):
    identidad = resolve_code_identity(_codigo(tmp_path))
    assert identidad.version == "9.9.9"
    assert identidad.commit is None and identidad.commit_source is None
    assert "commit" in identidad.unknown and "dirty" in identidad.unknown
    assert identidad.fingerprint and identidad.fingerprint_source == "calculada"
    assert [p for p, _ in identidad.package_fingerprints] == ["application", "domain"]


def test_build_info_tiene_prioridad(tmp_path):
    raiz = _codigo(tmp_path)
    (raiz / "build_info.json").write_text(json.dumps(
        {"version": "1.2.3", "commit": "abc123", "dirty": False, "generated_at": "2026-11-17T00:00:00+00:00"}))
    identidad = resolve_code_identity(raiz)
    assert (identidad.commit, identidad.commit_source, identidad.dirty, identidad.version) == (
        "abc123", "build_info", False, "1.2.3")
    assert identidad.unknown == ()


def test_huella_independiente_del_sistema_operativo_y_sensible_al_contenido(tmp_path):
    huellas = {}
    for nombre, contenido in (("lf", b"x = 1\ny = 2\n"), ("crlf", b"x = 1\r\ny = 2\r\n"), ("otro", b"x = 3\n")):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        huellas[nombre] = compute_code_fingerprint(_codigo(carpeta, contenido))
    assert huellas["lf"] == huellas["crlf"] != huellas["otro"]
    assert set(compute_package_fingerprints(tmp_path / "lf")) == {"domain", "application"}


def test_carpeta_sin_codigo_no_tiene_huella(tmp_path):
    assert compute_code_fingerprint(tmp_path) is None


def test_identidad_del_proceso_no_incluye_rutas():
    identidad = current_code_identity().to_dict()
    assert identidad["version"] and identidad["fingerprint"]
    assert "/" not in json.dumps({k: v for k, v in identidad.items() if k != "build_generated_at"}).replace(
        "\\/", "")
