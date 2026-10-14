# RAG-INC-00 — NEXOM Knowledge Package v1.0-rc3.2 (parche de alineación)

Quinta vuelta del incremento **RAG-INC-00**. Una segunda auditoría independiente, esta vez sobre `v1.0-rc3.1`, reprodujo los resultados positivos (161/162 comprobaciones, 0 errores, firma válida, 19/19 casos negativos) pero, con la misma metodología de aislamiento (`checksums.json` recalculado tras cada mutación), encontró que `acceptance_cases.jsonl` resolvía la fuente de una evidencia esperada leyendo `evidence.source_id` directamente en vez de vía `evidence.chunk_id` (la relación real) — permitiendo que una evidencia de un chunk confidencial "pareciera" pública. También señaló que las cadenas de versión (`schema_version`, sidecars, `key_id`, `signer`) seguían diciendo `rc3` cuando el ADR ya declaraba `rc3.1`, y cuatro inconsistencias documentales menores. Este entregable, **`v1.0-rc3.2`**, cierra las tres cosas. **No modifica ningún archivo de código de RAG Studio ni rediseña el contrato.**

## Contenido de esta carpeta / .zip

```
ADR_NEXOM_Knowledge_Package_v1.md/.docx/.pdf   Documento principal -- seccion 0.3
                                                 documenta la brecha de evidencia;
                                                 0.4 las 4 correcciones documentales;
                                                 seccion 9 AR-INC-00 integro.
schemas/                                        14 JSON Schema (draft 2020-12);
                                                 acceptance_case.schema.json:
                                                 referencia de seccion corregida
                                                 (7 -> 9).
common/id_scheme.py                             Sin cambios de fondo.
example_package/                                Paquete de ejemplo (perfil CORE),
                                                 regenerado; cadenas de version
                                                 (schema_version, exporter_version)
                                                 ahora dicen rc3.2 consistentemente.
delivery/                                        Sidecars EXTERNOS, nombrados
                                                 *-v1.0-rc3.2.*
validator/validate_knowledge_package.py         Validador de referencia -- evidence
                                                 se resuelve SIEMPRE via chunk_id,
                                                 mas chequeo referencial separado.
validator/test_negative_cases.py                Suite automatizada: 20 casos
                                                 negativos + 1 caso base positivo
                                                 (caso 19 nuevo); descubre los
                                                 sidecars por sufijo, no por nombre
                                                 de version hardcodeado.
generate_example.py                             Cadena de version unificada en
                                                 RC_TAG/SCHEMA_VERSION/FILE_TAG
                                                 (una sola fuente de verdad).
requirements.lock.txt                           Versiones exactas de dependencias.
```

## Cómo validar el paquete de ejemplo

```bash
pip install -r requirements.lock.txt --break-system-packages
```

```bash
PKG=nexom-knowledge-package-demo-v1.0-rc3.2
python3 validator/validate_knowledge_package.py example_package \
    --content-digest-file "delivery/${PKG}.content.sha256" \
    --signature-file "delivery/${PKG}.sig" \
    --public-key "delivery/${PKG}.pubkey_DEMO.pem"
```

Debe reportar `ERRORES: 0` (165 comprobaciones; 166 con `--trusted-key-id`). En modo `.zip` son 166 (167 con `--trusted-key-id`):

```bash
cd example_package && zip -q -X -r ../entrega.zip . && cd ..
python3 validator/validate_knowledge_package.py entrega.zip \
    --content-digest-file "delivery/${PKG}.content.sha256" \
    --signature-file "delivery/${PKG}.sig" \
    --public-key "delivery/${PKG}.pubkey_DEMO.pem"
```

## Cómo correr la suite de pruebas negativas

```bash
python3 validator/test_negative_cases.py
```

19 casos negativos (los 18 de `rc3.1` más el caso 19: `evidence.source_id` no coincide con la fuente real de su `chunk_id`), cada uno mutando una copia del paquete válido y confirmando que el validador la rechaza, más el paquete base sin mutar aceptado (20 aserciones en total). Debe reportar `RESUMEN: 20/20 casos correctos`.

## Qué falta para cerrar el contrato v1.0

Un solo punto: **`AR-INC-00`**, el protocolo de 7 pasos reproducido íntegramente en la sección 9 del ADR, ejecutado por el equipo de Agent Runtime contra `example_package/`, sobre `v1.0-rc3.2`. Las cadenas de versión del paquete (`schema_version`, sidecars, firma) ahora son consistentes entre sí, así que el informe firmado del paso 7 puede certificar sin ambigüedad qué versión evaluó. Mientras no se reciba ese informe, este contrato sigue siendo `v1.0-rc3.2`, no `v1.0`.

## Siguiente paso recomendado

Autorizar y ejecutar `AR-INC-00` (del lado de Agent Runtime) sobre `v1.0-rc3.2`. **No** se recomienda autorizar `RAG-INC-01` todavía, ni otra ronda de rediseño del contrato — las fórmulas y la estructura del contrato ya eran correctas en rondas anteriores; lo que faltaba, en cada ronda, era que el validador las hiciera cumplir con precisión sobre cuál campo es la relación real y que las cadenas de versión no introdujeran ambigüedad en el informe firmado de aceptación.
