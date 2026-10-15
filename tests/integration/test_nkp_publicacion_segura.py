"""RAG-INC-01d — publicación segura del NKP (defecto observado con B en un
sistema de archivos montado): el SHA-256 del ZIP se calcula en staging y el
proceso deja ZIP + sidecar, o ninguno."""
from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path

import pytest

from app.lifecycle import shutdown, start
from domain.knowledge_package.exceptions import OutputExistsError
from infrastructure.exporters import nexom_knowledge_package as modulo

from . import nkp_export_fixtures as fx

TENANT = "nexom-pruebas"
CLASE = modulo.NexomKnowledgePackageExporter


@pytest.fixture
def ctx(tmp_path):
    context = start(base_dir=tmp_path / "inst")
    yield context
    shutdown(context)


@pytest.fixture
def instantanea(ctx, tmp_path):
    p = fx.proyecto_completo(ctx, tmp_path)
    return p.project_id, ctx.release_service.publish_snapshot(p.project_id)


def _exportar(ctx, instantanea, salida):
    pid, snap = instantanea
    return ctx.knowledge_package_export.execute(pid, snap.id, TENANT, str(salida))


def _vacia(salida: Path) -> bool:
    return not salida.exists() or not any(salida.iterdir())


def test_sha_se_calcula_en_staging_y_nunca_sobre_el_zip_publicado(ctx, instantanea, tmp_path, monkeypatch):
    salida = tmp_path / "out"
    leidos: list[Path] = []
    real = modulo._sha256_archivo

    def registra(ruta):
        leidos.append(Path(ruta))
        return real(ruta)

    monkeypatch.setattr(modulo, "_sha256_archivo", registra)
    r = _exportar(ctx, instantanea, salida)
    zips = [p for p in leidos if p.suffix == ".zip"]
    assert zips and all(".nkp-staging-" in str(p) for p in zips)  # solo el ZIP en staging
    assert Path(r.zip_path) not in leidos
    assert r.zip_sha256 == hashlib.sha256(Path(r.zip_path).read_bytes()).hexdigest()  # se publicó sin cambios


def test_zip_final_no_legible_tras_publicarse_ya_no_afecta(ctx, instantanea, tmp_path, monkeypatch):
    """Reproduce el fallo de B: el ZIP recién publicado da FileNotFoundError
    al leerlo. Como el hash ya se obtuvo en staging, la exportación termina bien."""
    salida = tmp_path / "out"
    real = modulo._sha256_archivo

    def final_ilegible(ruta):
        if ".nkp-staging-" not in str(ruta) and str(ruta).endswith(".zip"):
            raise FileNotFoundError(errno.ENOENT, "simulado: archivo publicado aún no visible", str(ruta))
        return real(ruta)

    monkeypatch.setattr(modulo, "_sha256_archivo", final_ilegible)
    r = _exportar(ctx, instantanea, salida)
    assert sorted(p.name for p in salida.iterdir()) == sorted([Path(r.zip_path).name, Path(r.content_digest_path).name])
    monkeypatch.undo()
    assert r.zip_sha256 == hashlib.sha256(Path(r.zip_path).read_bytes()).hexdigest()


def test_fallo_al_publicar_el_zip_no_deja_nada(ctx, instantanea, tmp_path, monkeypatch):
    salida = tmp_path / "out"

    def falla(origen, destino):
        raise OSError(errno.EIO, "fallo simulado al publicar el ZIP")

    monkeypatch.setattr(CLASE, "_publicar_sin_sobrescribir", staticmethod(falla))
    with pytest.raises(OSError, match="publicar el ZIP"):
        _exportar(ctx, instantanea, salida)
    assert _vacia(salida)


def test_fallo_al_publicar_el_sidecar_retira_el_zip(ctx, instantanea, tmp_path, monkeypatch):
    salida = tmp_path / "out"
    real = CLASE._publicar_sin_sobrescribir

    def sidecar_falla(origen, destino):
        if str(destino).endswith(".content.sha256"):
            raise OSError(errno.EIO, "fallo simulado al publicar el sidecar")
        real(origen, destino)
        assert Path(destino).exists()  # el ZIP sí llegó a publicarse…

    monkeypatch.setattr(CLASE, "_publicar_sin_sobrescribir", staticmethod(sidecar_falla))
    with pytest.raises(OSError, match="sidecar"):
        _exportar(ctx, instantanea, salida)
    assert _vacia(salida)  # …y se retiró: ni ZIP, ni sidecar, ni staging


def test_sin_enlaces_duros_publica_por_reserva_y_rename(ctx, instantanea, tmp_path, monkeypatch):
    salida = tmp_path / "out"

    def sin_link(*a, **k):
        raise OSError(errno.EPERM, "sin enlaces duros (simulado)")

    monkeypatch.setattr(modulo.os, "link", sin_link)
    r = _exportar(ctx, instantanea, salida)
    assert r.zip_sha256 == hashlib.sha256(Path(r.zip_path).read_bytes()).hexdigest()
    assert len(list(salida.iterdir())) == 2  # ZIP + sidecar, sin staging


def test_fallo_del_rename_retira_la_reserva(ctx, instantanea, tmp_path, monkeypatch):
    salida = tmp_path / "out"
    real_replace = os.replace

    def sin_link(*a, **k):
        raise OSError(errno.EPERM, "sin enlaces duros (simulado)")

    def replace_falla(origen, destino):
        if str(destino).endswith(".zip") and ".nkp-staging-" not in str(destino):
            raise OSError(errno.EIO, "fallo simulado del rename")
        return real_replace(origen, destino)

    monkeypatch.setattr(modulo.os, "link", sin_link)
    monkeypatch.setattr(modulo.os, "replace", replace_falla)
    with pytest.raises(OSError, match="rename"):
        _exportar(ctx, instantanea, salida)
    assert _vacia(salida)  # ni la reserva vacía del ZIP ni el staging


def test_salida_existente_sigue_sin_sobrescribirse(ctx, instantanea, tmp_path):
    salida = tmp_path / "out"
    r = _exportar(ctx, instantanea, salida)
    antes = {p.name: p.read_bytes() for p in salida.iterdir()}
    with pytest.raises(OutputExistsError):
        _exportar(ctx, instantanea, salida)
    assert {p.name: p.read_bytes() for p in salida.iterdir()} == antes
    assert Path(r.zip_path).is_file()


def test_exportacion_normal_y_reproducible(ctx, instantanea, tmp_path):
    a = _exportar(ctx, instantanea, tmp_path / "a")
    b = _exportar(ctx, instantanea, tmp_path / "b")
    assert (a.package_id, a.content_digest, a.zip_sha256, a.counts) == (b.package_id, b.content_digest, b.zip_sha256, b.counts)
    assert Path(a.zip_path).read_bytes() == Path(b.zip_path).read_bytes()
    assert a.conformance is not None and a.conformance.passed
