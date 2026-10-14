# Informe de conformidad — NEXOM Knowledge Package v1.0.0

**Fecha:** 2026-09-24
**Ejecutado por:** RAG Studio (asistente de desarrollo)
**Entorno:** Python 3.10.12; `jsonschema==4.26.0`, `rfc3339-validator==0.1.4`, `rfc8785==0.1.4`, `cryptography==50.0.1` (según `requirements.lock.txt`)
**Comando:** `bash verificar_conformidad.sh`, ejecutado desde `ejemplo_v1.0.0/`
**Resultado:** **CONFORMIDAD v1.0.0: PASS** (código de salida 0)

## 1. Identificación

| Elemento | Valor |
|---|---|
| Contrato | NEXOM Knowledge Package `v1.0.0`: 16 artefactos normativos en `contrato_v1.0.0/` |
| SHA-256 de `contrato_v1.0.0/SHA256SUMS` | `863844f7b6f264cfdc45974b9a9f0ab4e92a830d01b70e9634958fde6b675208` |
| Paquete de ejemplo `package_id` | `urn:nexom:package:3e884f2d7c9a6f5d76ddeffda135f2db` |
| `manifest.schema_version` | `1.0.0` |
| `knowledge_base_id` | `5f9d5e2a-7b4a-4e1a-9c3a-1a2b3c4d5e6f` |
| `content_digest` | `2932dd2fc04bb544f6d92bad75c386bdbaf415e424212df5a670200ddbeb5102` |
| SHA-256 del ZIP `nexom-knowledge-package-demo-v1.0.0.zip` | `5dff57bb41680e2a5cf4a39b40ca99d641ef5beeda810d7bce3c1a58db91cbff` |
| SHA-256 de `SHA256SUMS_EJEMPLO` | `72f6f01a968e17a143b7c18e996c5d8d3c48c9ddc1a5be53f256cc68ae50ea8f` |
| Contenido | 4 sources, 6 chunks, 4 evidences, 1 media, 1 intent, 1 guardrail, 3 acceptance cases |
| `exporter_version` | `0.0.0-preview-rag-inc-00-v1.0.0` |
| `signature.key_id` | `demo-key-rag-inc-00-v1.0.0-NO-USAR-EN-PRODUCCION` (clave DEMO) |
| `signature.signer` | `RAG Studio (paquete de ejemplo, RAG-INC-00 v1.0.0)` |
| `signature.signed_at` | `2026-09-24T12:00:00+00:00` |
| Sidecars (en `delivery/`) | `nexom-knowledge-package-demo-v1.0.0.content.sha256`, `nexom-knowledge-package-demo-v1.0.0.sig`, `nexom-knowledge-package-demo-v1.0.0.pubkey_DEMO.pem`, `nexom-knowledge-package-demo-v1.0.0.zip.sha256` |
| SHA-256 de `verificar_conformidad.sh` | `2e60671007799d435064801e2e6f8bde74dfab09dbd3122a304d6282e026d785` |
| SHA-256 de `requirements.lock.txt` | `c9f8bb792efb25272fa6f6eeef41b426830b84704f3a9237fc087bbb3ac7594d` |
| Log completo de la corrida | `Informe_Conformidad_v1.0.0.log`, SHA-256 `b2b1e6dc1c2a05c32b30ea4dbd9acb4ac2326a50b3c9acd4b700a479f3eafad4`. Registra fecha UTC, sistema, versión de Python y de las dependencias, hash del script, salida íntegra y código de salida |

## 2. Resultados

| Comprobación | Resultado |
|---|---|
| 16 artefactos normativos contra `SHA256SUMS` | 16/16 OK |
| Archivos del ejemplo y de QA contra `SHA256SUMS_EJEMPLO` | 23/23 OK |
| Validador, directorio | 165 comprobaciones, 0 errores |
| Validador, directorio + `--trusted-key-id` | 166 comprobaciones, 0 errores |
| Validador, ZIP + `--zip-sha256-file` | 167 comprobaciones, 0 errores |
| Validador, ZIP + `--zip-sha256-file` + `--trusted-key-id` | 168 comprobaciones, 0 errores |
| Suite (19 casos negativos + caso base) | 20/20 correctos |

Contraprueba: en una copia desechable se alteró un byte de `schemas/chunk.schema.json` y el script terminó con `schemas/chunk.schema.json: FAILED`, `CONFORMIDAD v1.0.0: FAIL` y código de salida 1. El script detecta una manipulación del contrato publicado.

## 3. Salida del validador y de la suite (extracto; la salida íntegra está en el log)

```
== 3. Validador de referencia
directorio: OK: 165 ERRORES: 0 exit=0
directorio + trusted-key-id: OK: 166 ERRORES: 0 exit=0
zip: OK: 167 ERRORES: 0 exit=0
zip + trusted-key-id: OK: 168 ERRORES: 0 exit=0
== 4. Suite positiva y negativa
[01_invalid_date] PASS (rechazado correctamente)
[02_omission_reason_null_falso] PASS (rechazado correctamente)
[03_media_incluida_sin_binario] PASS (rechazado correctamente)
[04_conteo_manifest_falso] PASS (rechazado correctamente)
[05_activo_declarado_ausente] PASS (rechazado correctamente)
[06_activo_sin_checksum] PASS (rechazado correctamente)
[07_archivo_extra_no_declarado] PASS (rechazado correctamente)
[08_entrada_duplicada_en_zip] PASS (rechazado correctamente)
[09_sidecar_no_cumple_schema] PASS (rechazado correctamente)
[10_evidencia_derivada_sin_omision] PASS (rechazado correctamente)
[11_cadena_logical_id_rota] PASS (rechazado correctamente)
[12_metadata_referencia_codigo_local] PASS (rechazado correctamente)
[13_falta_top_k_en_acceptance_case] PASS (rechazado correctamente)
[14_source_id_no_determinista] PASS (rechazado correctamente)
[15_must_not_retrieve_inexistente] PASS (rechazado correctamente)
[16_chunk_esperado_sobre_nivel_acceso] PASS (rechazado correctamente)
[17_chunk_texto_manipulado] PASS (rechazado correctamente)
[18_zip_path_traversal] PASS (rechazado correctamente)
[19_evidence_source_id_no_coincide_con_chunk] PASS (rechazado correctamente)
[00_baseline_valido] PASS (aceptado correctamente)

RESUMEN: 20/20 casos correctos

CONFORMIDAD v1.0.0: PASS
```

## 4. Pendiente: importación de humo en Agent Runtime

Este informe cubre solo lo verificable desde RAG Studio: la conformidad del productor. La interoperabilidad de `1.0.0` queda cerrada cuando se reciba el PASS de la importación de humo, cuya solicitud formal (revisión 3) viaja en la carpeta autocontenida `entrega_runtime_v1.0.0/`: 8 archivos, 7 cubiertos por `MANIFIESTO_ENTREGA_v1.0.0.sha256`. El SHA-256 del manifiesto es `0c43b51a9ff8d20d8558f23e02364b547233daca818b72ea3217c7ab7c73de78` y se comunica por un canal separado. La portabilidad se comprobó copiando la carpeta sola a un directorio aislado y ejecutando `sha256sum -c --strict`: 7/7 OK (`Verificacion_Entrega_Runtime_v1.0.0.log`, SHA-256 `638fee80ec47c488c0245fecd8657b324762c78a31de78f1145dfc0b5239778c`). El manifiesto anterior, `delivery/MANIFIESTO_ENTREGA_v1.0.0.sha256` (SHA-256 `eaafbd4a…ff76d2`), queda **superseded**: no era portable porque referenciaba `../contrato_v1.0.0/SHA256SUMS`. No debe enviarse; se conserva sin eliminar. Mientras tanto, el paso 4 de la sección 10 de la Declaración sigue abierto y **el hito 01a no se inicia formalmente**. El informe del Runtime debe registrar como mínimo:

- SHA-256 exacto del paquete importado: `5dff57bb…cbff` si se importa el ZIP; `content_digest` `2932dd2f…5102` en cualquier caso;
- versión o commit del Runtime;
- resultado de la integridad referencial;
- persistencia y relectura;
- reembedding e indexación;
- ejecución de AC-001, AC-002 y AC-003. AC-003 ahora usa `contains` + `must_not_retrieve` y no debería requerir `min_score`; si el Runtime aplica algún umbral, debe registrarlo;
- aplicación de `access_hierarchy.json`;
- resultado final PASS o FAIL.

El paquete se firmó con clave DEMO: la importación de humo prueba interoperabilidad técnica, no autenticidad productiva (F-1).

## 5. Actualización 2026-10-14: importación de humo completada

NEXOM confirmó oficialmente el resultado de la importación de humo en Agent Runtime: **PASS / COMPATIBLE**, sin errores. Runtime commit `5db676e0e292fb09c08bb9258436829ceb28ec3a`; paquete `nexom-knowledge-package-demo-v1.0.0.zip`, SHA-256 `5dff57bb41680e2a5cf4a39b40ca99d641ef5beeda810d7bce3c1a58db91cbff`; `schema_version` `1.0.0`. Con ello, la sección 4 queda cerrada y el paso 4 de la sección 10 de la Declaración, completo. Detalle y pendiente documental (informe técnico completo del Runtime) en `Registro_Humo_Runtime_v1.0.0.md`.
