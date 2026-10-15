"""RAG-INC-01c — el contrato NKP v1.0.0 vendorizado es byte a byte el firmado."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contracts.nexom_knowledge_package import (
    ID_SCHEME_PATH,
    SCHEMAS_DIR,
    V1_0_0_DIR,
    VALIDATOR_PATH,
    VENDORED_INDEX,
    load_id_scheme,
)

RAIZ = Path(__file__).resolve().parents[3]
FIRMADOS_41 = {
    "schemas/acceptance_case.schema.json": "7cb0cf09e1b153c895bf3e5130713a7ca1588afa475d0f6d499eab4110a27581",
    "schemas/access_hierarchy.schema.json": "92e2c6ac9eb3b33527e4728447ad1c0bc9b882913d0b26c96ec63f62fd4a4b25",
    "schemas/checksums.schema.json": "bef9d65d5c210f72a5fe04daa8a5af0d7ec378551e22f9d5d698be7b7d282c46",
    "schemas/chunk.schema.json": "169d8f6d05dad78624ec8f0aa06276022b6aa83588c76922a775ce7ccd788999",
    "schemas/conversational_bundle.schema.json": "d72f8ff680d4895d5628bf4b9a58980ef222b521196f284ebfdc00561f0e5ef5",
    "schemas/embedding_spaces.schema.json": "b9468913bb640f28a284d99eb17a36e1c704aecb304679fa9e44186f2f04a753",
    "schemas/evidence.schema.json": "043ec0dd5448bd1dd3229dfcb72002cb01704d31f890ca2651ee70bda9569b00",
    "schemas/indexes.schema.json": "d981e3e622d641965c15997e2e0f78165a1ae099b065d7849c3e419235b43ac0",
    "schemas/manifest.schema.json": "46dee8ed56f809f9e5acda005a259a53a9d2af74561996c3c74691683913c463",
    "schemas/media.schema.json": "c3ed9324203bbc2147ad342f78886c17d6af4f5991f7d8aec7caa9a6b57ec9fc",
    "schemas/metadata_schema.schema.json": "c443b7bcc26356a4a7daf58769cb71049fe284f77b80fe0af38e7c442266f7e1",
    "schemas/signature.schema.json": "bb583efda303eb2b81d43ebc0c83710bcf6bba9485c1a7cb6acc1dd3bc8a55f1",
    "schemas/source.schema.json": "8a61ecce31d1fc2207a342e7a9c8dabfb3970f324f2c5ebb51891b2ec087cd90",
    "schemas/source_metadata.schema.json": "4b9bcbf3242d7e701595e377cd41f05a3a67657445acf2cf5e7988276832fde3",
    "common/id_scheme.py": "559847df560b8033b20a4e797ca32448320eef8d84f81cb654bcad6c1a942ba8",
    "validator/validate_knowledge_package.py": "96f18a4fa5105e94dae9d894cd6f6b63ad1a035d747cfff2568af227af9eef74",
}
"""Declaración de aceptación v1.0.0 §4.1 (transcrito; independiente del índice vendorizado)."""
FIRMADOS_42 = {
    "requirements.lock.txt": "c9f8bb792efb25272fa6f6eeef41b426830b84704f3a9237fc087bbb3ac7594d",
    "validator/test_negative_cases.py": "b0eeec1e217fc402bb30f2fb816364a88d18d4861eff90736a832a701c54380a",
}


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


@pytest.mark.parametrize("ruta,esperado", sorted({**FIRMADOS_41, **FIRMADOS_42}.items()))
def test_artefacto_firmado_identico(ruta, esperado):
    assert _sha(V1_0_0_DIR / ruta) == esperado


def test_id_scheme_sigue_siendo_el_firmado_y_es_el_que_usa_el_exportador():
    assert _sha(ID_SCHEME_PATH) == "559847df560b8033b20a4e797ca32448320eef8d84f81cb654bcad6c1a942ba8"
    from infrastructure.exporters import nexom_knowledge_package as exportador

    assert Path(exportador.k.__file__).resolve() == ID_SCHEME_PATH
    assert exportador.k is load_id_scheme()
    assert not (RAIZ / "infrastructure" / "exporters" / "nexom_kp_v1_0_0").exists()  # copia de 01b consolidada


def test_indice_vendorizado_completo_y_coincidente():
    indice = json.loads(VENDORED_INDEX.read_text(encoding="utf-8"))
    entradas = {e["ruta"]: e for e in indice["archivos"]}
    en_disco = {p.relative_to(V1_0_0_DIR).as_posix() for p in V1_0_0_DIR.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    assert set(entradas) == en_disco  # ni archivos sin registrar ni registros sin archivo
    for ruta, e in entradas.items():
        actual = _sha(V1_0_0_DIR / ruta)
        assert actual == e["sha256_esperado"] == e["sha256_incorporado"] and e["coincide"], ruta
        origen = RAIZ / e["origen"]
        if origen.exists():
            assert _sha(origen) == actual, f"{ruta} difiere de su fuente publicada {e['origen']}"
    normativos = {r for r, e in entradas.items() if "§4.1" in e["fuente_del_esperado"]}
    assert normativos == set(FIRMADOS_41)
    assert {r: entradas[r]["sha256_esperado"] for r in FIRMADOS_41} == FIRMADOS_41


def test_sha256sums_del_contrato_verifica_la_copia():
    for linea in (V1_0_0_DIR / "SHA256SUMS").read_text().splitlines():
        if linea.strip():
            esperado, ruta = linea.split(None, 1)
            assert _sha(V1_0_0_DIR / ruta.strip()) == esperado


def test_exactamente_14_schemas_y_validador_presente():
    assert len(list(SCHEMAS_DIR.glob("*.schema.json"))) == 14
    assert VALIDATOR_PATH.is_file()
