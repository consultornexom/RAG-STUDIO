# RAG-INC-01c — Conformidad contractual del NEXOM Knowledge Package v1.0.0

Fecha: 2026-10-15 · Rama `rag-inc-01/01c`, creada desde `5eec7d6` (`rag-inc-01/01b` sin cambios) · **Sin commit, sin tag, sin push.** No incluye 01d, Runtime ni Testing Agent, y no toca el corpus B.

## 1. Vendorización formal

Ubicación: `contracts/nexom_knowledge_package/v1_0_0/`, con la misma disposición que usa `verificar_conformidad.sh` del contrato publicado: `schemas/`, `common/`, `validator/`, `example_package/`, `delivery/`. Son **38 copias byte a byte**; ninguna se editó.

El índice `contracts/nexom_knowledge_package/VENDORIZADO_v1_0_0.json` registra, por archivo: ruta, origen, SHA-256 esperado y su fuente, SHA-256 incorporado y resultado de la comparación. La prueba `tests/unit/contracts/test_vendored_contract.py` falla ante cualquier diferencia o ante archivos sin registrar.

| Grupo | Archivos | Hash esperado (fuente) | Resultado |
|---|---|---|---|
| Normativos | 14 schemas, `common/id_scheme.py`, `validator/validate_knowledge_package.py` | Declaración v1.0.0 §4.1 (= `contrato_v1.0.0/SHA256SUMS`) | **16/16 coinciden** |
| QA (§4.2) | `requirements.lock.txt` (`c9f8bb79…594d`), `validator/test_negative_cases.py` (`b0eeec1e…380a`) | Declaración §4.2 | **2/2 coinciden** |
| Fixture oficial 1.0.0 | 13 archivos de `example_package/`, 4 sidecars de `delivery/`, ZIP de ejemplo | `ejemplo_v1.0.0/SHA256SUMS_EJEMPLO` | **18/18 coinciden** |
| Listas de hashes | `SHA256SUMS`, `SHA256SUMS_EJEMPLO` | Copia de la lista publicada (no tienen hash firmado propio) | **2/2 iguales a la fuente** |

**`id_scheme.py`:** `559847df560b8033b20a4e797ca32448320eef8d84f81cb654bcad6c1a942ba8`, verificado de nuevo.
- La copia anticipada en 01b (`infrastructure/exporters/nexom_kp_v1_0_0/`) **se consolidó**: se eliminó, y el exportador usa ahora el `id_scheme.py` vendorizado. Hay una sola copia en el repositorio.
- Una prueba exige que sea el mismo módulo que carga el exportador.

**Carga de los artefactos.** `contracts/nexom_knowledge_package/__init__.py` solo los localiza y carga desde su archivo (`importlib`). No contiene lógica del contrato.

**Comportamiento propio del validador firmado (no modificado).** Al cargarse agrega `<v1_0_0>/common` a `sys.path` e importa `id_scheme`.

**Dependencias de ejecución nuevas** (las mismas versiones que `requirements.lock.txt`): `jsonschema==4.26.0` y `rfc3339-validator==0.1.4`. Sin `rfc3339-validator` el validador aborta, y la compuerta da FAIL.

**Empaquetado:**
- `pyproject.toml`: incluye el paquete `contracts` y sus datos.
- `packaging/ragstudio.spec`: el contrato va como datos, más los imports ocultos.
- ruff excluye `contracts/nexom_knowledge_package/v1_0_0`, porque son artefactos firmados que no se pueden "limpiar".

## 2. Compuerta de conformidad

| Capa | Archivo | Contenido |
|---|---|---|
| Dominio | `domain/knowledge_package/conformance.py` | `ConformanceStatus` (PASS/FAIL), `ConformanceCategory`, `ConformanceIssue(categoría, mensaje, origen)`, `ConformanceReport` (estado, versión de contrato, comprobaciones OK, errores, resumen) |
| Puerto | `KnowledgePackageConformanceValidator.validate(package_path, content_digest_file)` | — |
| Infra | `infrastructure/exporters/nkp_conformance.py` | `ContractV1ConformanceValidator` |
| Error | `ContractConformanceError` | Lleva el reporte completo |

**Funcionamiento de `ContractV1ConformanceValidator`** (las tres partes deben salir sin errores para dar PASS):

1. **Integridad del contrato vendorizado.** Verifica los 16 normativos contra su hash firmado. Si alguno difiere, devuelve FAIL de categoría `contrato` (fail-closed).
2. **Validador firmado en proceso.** Ejecuta `run_validation`; sus errores se clasifican por su etiqueta (`[schema]`, `[checksums]`, `[sidecar]`, `[ids]`, `[referencial]`, `[archivos]`, `[conteos]`, `[perfil]`, `[omisiones]`, `[aceptacion]`, `[seguridad-zip]`…). Si el validador aborta o falla por cualquier motivo, el resultado es FAIL, nunca PASS.
3. **Unicidad de identificadores (comprobación de RAG Studio, más estricta).** Revisa cada colección JSONL (`id` o `case_id`), cada lista del bundle conversacional, los campos y catálogos de `metadata_schema.json` (y los `value_code` de cada catálogo), `embedding_spaces.json` e `indexes.json`.

**Integración con el exportador.** El flujo es: exportador CORE → ZIP y sidecar en staging → relectura del ZIP → **compuerta sobre el ZIP y el sidecar tal como se publicarían** → solo con PASS se publican.
- Con FAIL: `ContractConformanceError` con el diagnóstico; no se publican ni ZIP ni sidecar, y el staging se borra.
- La compuerta es obligatoria: sin una explícita, el exportador usa la del contrato.
- El resultado PASS viaja en `KnowledgePackageExportResult.conformance`.

## 3. Revisión de las 5 interpretaciones de 01b

| # | Decisión | Clasificación | Evidencia contractual |
|---|---|---|---|
| 1 | Evidencia solo para chunks indexables (ni `padre` ni `imagen`; sí `encabezado`) | **AMBIGUA — se eleva a NEXOM** | `evidence.schema.json` y el validador no fijan qué chunks deben tener evidencia. El Alcance §5 solo dice "Proyección de chunk + source". El ejemplo oficial 1.0.0 crea evidencia para chunks `texto`/`tabla` y **no** para su `encabezado` ni su `imagen`, mientras que el exportador sí la crea para `encabezado`. Válido en ambos casos (ERRORES 0), pero el conjunto citable es una decisión semántica que el contrato no fija. **No se cambió.** |
| 2 | `covers_chunk_types` = tipos presentes salvo `padre`/`imagen` | **CONFORME** | Declaración §6.5: un chunk cuyo tipo no figura en `covers_chunk_types` "se conserva e importa, pero no se indexa textualmente", así que el campo describe lo que el índice cubre. RAG Studio nunca indexa `padre` (`index_source.py`), e `imagen` va en otra colección (O-8: "Conforme"). |
| 3 | `preprocessing` solo para los modelos conocidos; desconocido → `null` | **CONFORME** | `embedding_spaces.schema.json` admite `preprocessing` null y prefijos null. Los valores emitidos son los que RAG Studio usa realmente (`fastembed_provider.py`). M-2 recomienda declarar solo datos verificados, y no se inventan prefijos. |
| 4 | Sin espacio de embeddings para imágenes | **CONFORME** | El schema no exige declarar espacios de imagen. Si `image_retrieval=true`, el validador exige binarios e índice que cubra `imagen`; aquí es `false`, con `MEDIA_BINARIES_NOT_INCLUDED` declarado. Declaración O-8 ("Conforme; recuperación visual diferida, F-2") y aclaración 6.4. |
| 5 | Registros contractuales construidos como diccionarios en infraestructura | **CONFORME** (frente al contrato) | El contrato regula la forma serializada (schemas), no la representación interna. Desde 01c todo paquete pasa los 14 schemas firmados antes de publicarse. Se aparta de una nota de arquitectura del Alcance ("entidades inmutables"), que no es normativa del contrato. |

## 4. `origin_package_id`

**Confirmado: no forma parte del NKP v1.0.0.** No aparece en ninguno de los 14 schemas (`manifest.schema.json` tiene `additionalProperties: false` y no lo declara), ni en `id_scheme.py` ni en el validador. No se introduce.

La procedencia contractual queda así:
- `manifest.project_id_origin`: proyecto origen; solo trazabilidad, nunca en fórmulas.
- `manifest.parent_package_id`: cadena de paquetes; null en RAG-INC-01.
- `manifest.snapshot_id`: instantánea exportada.
- `sources[].origin_id`: id interno de cada fuente.

Si el Runtime necesita un `origin_package_id` propio, corresponde al Runtime, fuera del paquete.

## 5. Resultados

| Paquete | Compuerta | Validador firmado |
|---|---|---|
| Fixture completa (exportador): ZIP y directorio, con sidecar | **PASS** | **ERRORES: 0** (158 OK) |
| Fixture mínima (exportador, sin esquema de metadatos): ZIP y directorio | **PASS** | **ERRORES: 0** (72 OK) |
| Fixture oficial del contrato 1.0.0 (directorio y ZIP) | **PASS** | **ERRORES: 0** |
| Suite negativa firmada (QA §4.2) sobre la copia vendorizada | — | **20/20** (19 negativos + base) |
| Prueba controlada A (copia, tras el relleno; **no es 01d**) | **PASS** (72) | **ERRORES: 0** |
| Prueba controlada C (copia, tras el relleno; **no es 01d**) | **PASS** (768) | **ERRORES: 0** |

**Negativos.** Hay un solo defecto por caso; se recalculan los checksums y el sidecar salvo cuando el defecto es justamente ese.

| Caso | Compuerta | Categoría | Validador firmado |
|---|---|---|---|
| schema roto (`chunk_type` inválido) | FAIL | schema | rechaza |
| manifest inválido (`package_id` sin URN) | FAIL | schema | rechaza |
| checksum roto | FAIL | checksum | rechaza |
| content_digest roto | FAIL | content_digest | rechaza |
| `source.id` incorrecto (UUID arbitrario propagado) | FAIL | ids | rechaza |
| `chunk.id` incorrecto (texto alterado) | FAIL | ids | rechaza |
| **id duplicado** (chunk repetido, conteo ajustado) | **FAIL** | unicidad | **acepta (ERRORES: 0)**, ver §6 |
| archivo requerido faltante | FAIL | schema | rechaza |
| archivo inesperado | FAIL | estructura | rechaza |
| referencia rota | FAIL | referencia | rechaza |
| cardinalidad incorrecta | FAIL | cardinalidad | rechaza |
| metadata schema inválido | FAIL | referencia | rechaza |
| embeddings inválidos (`dimensions=0`) | FAIL | schema | rechaza |
| índice sin espacio | FAIL | referencia | rechaza |
| access hierarchy inválida | FAIL | schema | rechaza |
| conversational bundle inválido | FAIL | referencia | rechaza |
| acceptance case inválido | FAIL | aceptación | rechaza |
| ZIP manipulado: entrada extra | FAIL | zip | rechaza |
| ZIP manipulado: contenido alterado | FAIL | ids + checksum | rechaza |
| Duplicados en `sources`, `intents` y entradas de catálogo | FAIL | unicidad | (no comparado) |
| Contrato vendorizado alterado | FAIL | contrato | — |
| Exportador con defecto real (regla de acceso alterada) | FAIL, sin publicar nada | schema | — |

**Equivalencia.** Válido → válido en todos los casos. Inválido → inválido en todos, **salvo los identificadores repetidos**: ahí la compuerta rechaza y el validador firmado acepta. No hay ningún falso PASS de la compuerta.

## 6. Hallazgo para NEXOM: el validador firmado no detecta identificadores repetidos

`validate_knowledge_package.py` v1.0.0 indexa los registros con diccionarios por `id` (`{s["id"]: s for s in …}`). Si un registro aparece dos veces y `manifest.counts` se ajusta, todas las comprobaciones pasan: un consumidor que confíe solo en el validador aceptaría un paquete con identidades ambiguas.

- **No se modifica el contrato.** La compuerta de RAG Studio lo rechaza: es más estricta y nunca más laxa.
- La unicidad solo es explícita en el contrato para `source_metadata.id` ("única por fuente+campo") y para `manifest.files` (`uniqueItems`).
- Hacerla cumplir en el validador sería un cambio de validación que, según la política §8 de la Declaración, corresponde a una versión futura (1.x).
- **A decisión de NEXOM.**

## 7. Pruebas nuevas (52)

- `tests/unit/contracts/test_vendored_contract.py` (22):
  - 18 artefactos firmados (§4.1 y §4.2);
  - `id_scheme` firmado, que es el que usa el exportador;
  - índice completo y coincidente;
  - `SHA256SUMS`;
  - 14 schemas.
- `tests/integration/test_nkp_conformance.py` (30):
  - fixtures válidas (2);
  - fixture oficial;
  - suite negativa firmada 20/20;
  - 17 negativos con equivalencia;
  - unicidad (3);
  - manipulación del ZIP (2);
  - contrato alterado;
  - exportador no publica con FAIL;
  - compuerta real ante un defecto del exportador;
  - compuerta por defecto.
- Apoyo: `tests/integration/nkp_conformance_cases.py`.
- Ajustadas a la consolidación: `test_export_knowledge_package.py`, `test_nkp_core_exporter.py`, `nkp_export_fixtures.py` (usan el contrato vendorizado).

## 8. Regresión (línea base posterior a 01b: 952/9 · 507/14 [508 con la prueba explícita de §9 de 01b] · 15/2 · ruff limpio · mypy 22/7)

| Suite | Resultado |
|---|---|
| Unitarias | **974 passed, 9 skipped** (+22) |
| Integración | **538 passed, 14 skipped** (+30 sobre 508) |
| Smoke | 15 passed, 2 skipped |
| ruff (código, pruebas y `contracts/` propio) | All checks passed. `ruff check .`: los mismos **14 avisos históricos** de `docs proyecto/` (el contrato vendorizado está excluido) |
| mypy | **22 errores en los mismos 7 archivos** |

## 9. Riesgos pendientes

1. **Validador firmado y duplicados** (§6): la compuerta lo cubre; la corrección del validador queda a decisión de NEXOM, para una versión futura.
2. **Interpretación 1 (evidencia)**: AMBIGUA, elevada sin cambios.
3. **`sys.path` y módulo `id_scheme`.** El validador firmado modifica `sys.path` del proceso al cargarse y registra un módulo global `id_scheme`. Es comportamiento del artefacto firmado y no se cambia. No hay colisión de nombres en RAG Studio.
4. **Ejecutable PyInstaller.** El `.spec` ya incluye el contrato y las dependencias, pero el ejecutable no se generó ni se probó en este incremento. Si faltara algo, la compuerta da FAIL (fail-closed) y no se exporta nada.
5. **Dependencias fijadas** a las versiones del lock del contrato (`jsonschema==4.26.0`, `rfc3339-validator==0.1.4`, `rfc8785==0.1.4`). Una actualización requiere repetir la conformidad.
6. **Siguen vigentes los riesgos aceptados en 01b:** B requiere saneamiento antes de 01d, D sin probar, rutas históricas, ventana ZIP/sidecar y zlib.

## 10. Decisiones NEXOM previas al commit (2026-10-15)

1. **Identificadores repetidos: se mantiene la compuerta de unicidad.** Un NKP v1.0.0 generado por RAG Studio es liberable solo si:

   ```
   validador firmado v1.0.0 = PASS
   + comprobación de unicidad RAG Studio = PASS
   ```

   Si cualquiera falla, la conformidad de RAG Studio es FAIL y el paquete no se publica.
   - La comprobación de unicidad es una **salvaguarda adicional del productor RAG Studio. No es una modificación del contrato firmado.**
   - No se modifican el validador ni los schemas, ni se crea una versión nueva del contrato.
   - **Un PASS del validador firmado no implica por sí solo un PASS de la compuerta de RAG Studio.**
   - Se mantienen las pruebas negativas de unicidad: chunks, fuentes, intenciones y entradas de catálogo.
   - Una corrección futura del validador firmado queda fuera de 01c y requeriría el proceso de versionado contractual.
2. **Evidencia asociada a chunks: convención del productor.**
   - RAG Studio genera evidencia (`citation_anchor`/`derived`) para los chunks indexables (`texto`, `tabla`, `encabezado`, etc.), no para `padre` ni `imagen`. Es una **convención del productor RAG Studio, no una obligación contractual** del NKP v1.0.0.
   - El contrato no prescribe qué tipos de chunk llevan evidencia; el validador acepta ambas variantes, y la fixture oficial no genera evidencia para `encabezado`.
   - Ningún consumidor debe depender de que todos los chunks de un tipo tengan evidencia.
   - Se mantiene el comportamiento actual. La aceptación práctica se comprobará en 01d con paquetes reales y Runtime.
3. **Vendorización aceptada:** 38 archivos (16 normativos 16/16, 2 de QA 2/2, 18 de la fixture oficial 18/18, más `SHA256SUMS` y `SHA256SUMS_EJEMPLO`). Se acepta la sustitución de `infrastructure/exporters/nexom_kp_v1_0_0/id_scheme.py` por la copia única en `contracts/nexom_knowledge_package/v1_0_0/`.
4. **Regla final de publicación:** staging → validador firmado → unicidad RAG Studio → PASS → publicar ZIP y sidecar. Si falla cualquiera: no se publica, se limpia el staging y se devuelve el diagnóstico.
5. **Interpretaciones 2 a 5: CONFORMES**, con la evidencia contractual de §3.
6. **`origin_package_id` no pertenece al NKP v1.0.0.** La procedencia se mantiene con `project_id_origin`, `parent_package_id`, `snapshot_id` y `source.origin_id`.

**Riesgos aceptados para el cierre de 01c** (sin cambios en este commit):
1. El validador firmado no detecta por sí mismo identificadores repetidos.
2. La política de evidencia es una convención de RAG Studio.
3. El validador firmado modifica `sys.path` y registra `id_scheme`.
4. PyInstaller todavía no se ha probado.
5. Las dependencias contractuales quedan fijadas.
6. B sigue sin sanear.
7. D sigue sin probar con el exportador.
8. Instantáneas con rutas históricas que ya no existen.
9. Ventana entre la publicación del ZIP y la del sidecar.
10. Posibles diferencias del SHA del ZIP por zlib.
