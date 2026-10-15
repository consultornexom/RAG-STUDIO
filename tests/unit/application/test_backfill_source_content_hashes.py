"""RAG-INC-01 — relleno de content_hash: reglas puras de clasificación y caso
de uso con dobles en memoria (decisión NEXOM sobre INC01-R1, opción B)."""
from __future__ import annotations

import pytest

from application.documents.commands.backfill_source_content_hashes import BackfillSourceContentHashes
from domain.documents.content_hash_backfill import BackfillStatus, clasificar
from domain.documents.entities import Source, SourceType
from domain.documents.exceptions import OriginalCopyMissingError, OriginalCopyUnreadableError
from domain.documents.ports import BackfillReportStore, SourceContentHashWriter, SourceOriginalHasher

from .fakes_documents import InMemorySourceRepository


def _f(sid, lineage, h=None, tipo=SourceType.PDF):
    return Source(id=sid, project_id="p", title=f"T{sid}", source_type=tipo, lineage_id=lineage, content_hash=h)


# ------------------------------------------------------------ clasificar

def test_clasificar_estados_basicos():
    fuentes = [_f("a", "L1"), _f("b", "L2", h="hb"), _f("c", "L3", tipo=SourceType.API), _f("d", "L4"), _f("e", "L5")]
    r = {x.source_id: x for x in clasificar(
        fuentes, {"a": "ha"},
        {"d": (BackfillStatus.SIN_COPIA_ORIGINAL, "falta"), "e": (BackfillStatus.ILEGIBLE, "x")},
    )}
    assert r["a"].status == BackfillStatus.RELLENADA and r["a"].content_hash == "ha"
    assert r["b"].status == BackfillStatus.YA_TENIA
    assert r["c"].status == BackfillStatus.NO_APLICA
    assert r["d"].status == BackfillStatus.SIN_COPIA_ORIGINAL
    assert r["e"].status == BackfillStatus.ILEGIBLE


def test_mismo_hash_distinto_linaje_incluye_hash_existente_de_otro_linaje():
    fuentes = [_f("a", "L1"), _f("b", "L2", h="h")]
    r = {x.source_id: x for x in clasificar(fuentes, {"a": "h"}, {})}
    assert r["a"].status == BackfillStatus.CONTENIDO_COMPARTIDO_ENTRE_LINAJES
    assert r["a"].related_source_ids == ["b"]
    assert r["b"].status == BackfillStatus.YA_TENIA


def test_mismo_hash_mismo_linaje_tres_candidatas_ninguna_se_rellena():
    fuentes = [_f("a", "L"), _f("b", "L"), _f("c", "L"), _f("x", "M")]
    r = {x.source_id: x for x in clasificar(fuentes, {"a": "h", "b": "h", "c": "h", "x": "h"}, {})}
    for sid in "abc":
        assert r[sid].status == BackfillStatus.COLISION_MISMO_LINAJE
    assert r["a"].related_source_ids == ["b", "c"]
    # x (otro linaje) se rellena; las colisionadas no cuentan como "compartido"
    # porque no quedarán con hash.
    assert r["x"].status == BackfillStatus.RELLENADA


def test_caso_mixto_y_hash_vacio():
    fuentes = [_f("a", "L", h="h"), _f("b", "L"), _f("c", "M", h="")]
    r = {x.source_id: x for x in clasificar(fuentes, {"b": "h"}, {})}
    assert r["b"].status == BackfillStatus.COLISION_MISMO_LINAJE and r["b"].related_source_ids == ["a"]
    assert r["a"].status == BackfillStatus.YA_TENIA and r["a"].related_source_ids == ["b"]
    assert r["c"].status == BackfillStatus.YA_TENIA and "vacío" in r["c"].detail


# --------------------------------------------------------- caso de uso

class _Hasher(SourceOriginalHasher):
    def __init__(self, tabla):
        self.tabla = tabla

    def sha256_of_original(self, project_id, source):
        valor = self.tabla[source.id]
        if isinstance(valor, Exception):
            raise valor
        return valor


class _Writer(SourceContentHashWriter):
    def __init__(self, repo, solo=None, error=None):
        self.repo, self.solo, self.error, self.recibido = repo, solo, error, None

    def fill_missing(self, project_id, hashes):
        self.recibido = dict(hashes)
        if self.error:
            raise self.error
        escritos = set()
        for sid, h in hashes.items():
            if self.solo is not None and sid not in self.solo:
                continue
            f = self.repo.get(project_id, sid)
            if f.content_hash is None:
                self.repo.save(f.model_copy(update={"content_hash": h}))
                escritos.add(sid)
        return escritos


class _Store(BackfillReportStore):
    def __init__(self, error=None):
        self.guardados, self.error = [], error

    def save(self, project_id, report):
        if self.error:
            raise self.error
        self.guardados.append(report)
        return f"/reports/{len(self.guardados)}.json"


def _repo(*fuentes):
    repo = InMemorySourceRepository()
    for f in fuentes:
        repo.save(f)
    return repo


def test_caso_de_uso_clasifica_lecturas_y_escribe_solo_lo_permitido():
    repo = _repo(_f("a", "L1"), _f("b", "L2"), _f("c", "L3"), _f("d", "L4", h="hd"))
    hasher = _Hasher({"a": "ha", "b": OriginalCopyMissingError("b"), "c": OriginalCopyUnreadableError("c", "x")})
    writer, store = _Writer(repo), _Store()
    informe = BackfillSourceContentHashes(repo, hasher, writer, store).execute("p")
    assert writer.recibido == {"a": "ha"}
    estados = {r.source_id: r.status.value for r in informe.results}
    assert estados == {"a": "rellenada", "b": "sin_copia_original", "c": "ilegible", "d": "ya_tenía"}
    assert (informe.missing_before, informe.missing_after) == (3, 2)
    assert informe.report_path == "/reports/1.json" and store.guardados[0]["escritura"] == "aplicada"


def test_fuente_completada_por_otro_proceso_se_reclasifica():
    repo = _repo(_f("a", "L1"), _f("b", "L2"))
    writer = _Writer(repo, solo={"a"})
    informe = BackfillSourceContentHashes(repo, _Hasher({"a": "ha", "b": "hb"}), writer, _Store()).execute("p")
    r = {x.source_id: x for x in informe.results}
    assert r["a"].status == BackfillStatus.RELLENADA
    assert r["b"].status == BackfillStatus.YA_TENIA and "otro proceso" in r["b"].detail


def test_escritura_fallida_guarda_informe_revertido_y_propaga():
    repo = _repo(_f("a", "L1"))
    store = _Store()
    with pytest.raises(RuntimeError):
        BackfillSourceContentHashes(repo, _Hasher({"a": "ha"}), _Writer(repo, error=RuntimeError("x")), store).execute("p")
    assert store.guardados[0]["escritura"] == "revertida"
    assert repo.get("p", "a").content_hash is None


def test_fallo_al_guardar_informe_no_deshace_la_escritura():
    repo = _repo(_f("a", "L1"))
    informe = BackfillSourceContentHashes(
        repo, _Hasher({"a": "ha"}), _Writer(repo), _Store(error=OSError("disco lleno")),
    ).execute("p")
    assert informe.report_path is None and repo.get("p", "a").content_hash == "ha"


def test_sin_fuentes_pendientes_no_escribe():
    repo = _repo(_f("a", "L1", h="h"), _f("b", "L2", tipo=SourceType.BASE_DE_DATOS))
    writer = _Writer(repo)
    informe = BackfillSourceContentHashes(repo, _Hasher({}), writer, _Store()).execute("p")
    assert writer.recibido == {} and informe.write_outcome == "sin_cambios" and informe.missing_after == 0
