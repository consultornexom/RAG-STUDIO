# ADR — NEXOM Knowledge Package v1.0-rc3.2 (RAG-INC-00: parche de alineación)

**Documento:** Architecture Decision Record — contrato de interoperabilidad entre RAG Studio y NEXOM Agent Runtime
**Estado del contrato:** `v1.0-rc3.2` — **candidato; tres brechas de validación cerradas en total (dos en rc3.1, una en rc3.2), aún NO cerrado como v1.0.** El contrato como diseño no cambió de fondo en ninguna de las dos rondas — son parches puntuales sobre el validador y los schemas.
**Fecha:** 21 de septiembre de 2026
**Responde a:** una segunda auditoría independiente, esta vez sobre `v1.0-rc3.1`, que reprodujo los resultados positivos (161/162 comprobaciones, 0 errores, firma Ed25519 válida, 19/19 casos de la suite negativa) pero demostró, con la misma metodología de aislamiento (recalculando `checksums.json` tras cada mutación), una brecha adicional: `acceptance_cases.jsonl` resolvía la fuente de una `expected_evidence_id` leyendo `evidence.source_id` directamente en vez de vía `evidence.chunk_id` (la relación real) — una evidencia con `chunk_id` de una fuente `confidencial` pero `source_id` falseado a una fuente `publica` eludía la verificación de acceso. También señaló que las cadenas de versión (`manifest.schema_version`, `exporter_version`, nombres de sidecars, `signature.key_id`/`signer`) seguían diciendo `rc3` en `rc3.1`, mientras el ADR ya declaraba `rc3.1` — una inconsistencia que habría hecho ambiguo el informe firmado de `AR-INC-00`. Y cuatro ajustes documentales menores (ver sección 0.4).
**Alcance de este incremento:** `validate_knowledge_package.py` (resolución de evidencia vía `chunk_id` + integridad referencial `evidence.source_id`), `test_negative_cases.py` (caso 19 nuevo), `generate_example.py` (cadena de versión unificada en tres constantes: `RC_TAG`/`SCHEMA_VERSION`/`FILE_TAG`), `acceptance_case.schema.json` (referencia de sección corregida), este ADR y el LEEME. `id_scheme.py` y el resto de los 14 schemas no cambiaron de fondo. **No se modificó `project.db`, Qdrant interno, ningún exportador existente de RAG Studio ni la interfaz de usuario.**

Esta ronda, igual que `rc3` y `rc3.1`, **no rediseña la arquitectura**. Lo resuelto en rondas anteriores (separación de capas, IDs portables, canonicalización RFC 8785, sidecars externos, perfiles, capacidades/omisiones bidireccionales, `FormatChecker`, igualdad de conjuntos de archivos, continuidad de `logical_id`, recomputo de `source.id`, validación completa de `acceptance_cases`) **no se repite en detalle aquí** — sigue vigente sin cambios; las secciones 1-9 de este mismo documento son ese detalle. Este ADR se reescribe completo en cada ronda (no es un diff sobre el anterior) precisamente porque el `.zip` de la ronda previa se retira al entregar la siguiente — por diseño, este documento es la única fuente completa y vigente, y no remite a ningún artefacto retirado.

---

## 0. Las brechas cerradas en rc3.1 y rc3.2

### 0.1 `source.id` no se recomputaba

`id_scheme.py` define, desde `rc2`, que `source.id` (identidad de *versión*, distinta del `logical_id` opaco) es **determinista**: `portable_source_id(lineage_id, version_key)`, donde `version_key` se deriva de `content_hash`/`title`/`source_type`/`updated_at`. El paquete de ejemplo siempre cumplió esta fórmula. Pero `validate_lineage_continuity` en `rc3` solo comprobaba que `id` tuviera **forma** de URN válido — nunca recomputaba la fórmula y la comparaba.

Se demostró sustituyendo el `id` de una fuente por un UUID arbitrario y propagando ese cambio de forma **internamente consistente** a todos sus dependientes (`chunks.jsonl`, `evidence.jsonl`, `media.jsonl`, `source_metadata.jsonl`, `acceptance_cases.jsonl`) y a `checksums.json`. Resultado antes de la corrección: `ERRORES: 0`. Un exportador podía, en teoría, asignar identidades de versión arbitrarias y el validador las aceptaría, contradiciendo la promesa central de IDs portables y recomputables.

**Corrección** (`validate_lineage_continuity`, `validate_knowledge_package.py`): para cada fuente, se extrae `lineage_id` de `logical_id`, se recomputa `version_key = source_version_key(content_hash, title, source_type, updated_at)`, se recomputa `expected_id = portable_source_id(lineage_id, version_key)` y se exige igualdad estricta con `source.id`. Esto no cambia ninguna fórmula — hace cumplir la que ya estaba documentada y aprobada.

### 0.2 `acceptance_cases.jsonl` no validaba tres de sus cuatro listas de IDs

`rc3` cruzaba `expected_source_ids` contra `access_hierarchy.json` (que un caso no pudiera esperar una fuente por encima del `user_access_level` de la prueba), pero dejaba sin verificar de la misma forma a `expected_chunk_ids` y `expected_evidence_ids` — solo se comprobaba que existieran, no que su fuente fuera autorizable. Y `must_not_retrieve` no se verificaba en absoluto.

Se demostraron dos casos: (a) `must_not_retrieve` apuntando a un id inexistente en el paquete — una prueba de denegación que "aprueba vacío", prohibiendo algo que de todas formas nunca podría recuperarse; (b) un caso con `user_access_level=publico`, `expected_source_ids=[]` (vacío, evadiendo el único chequeo que sí existía) pero `expected_chunk_ids` apuntando a un chunk de una fuente `confidencial`. Ambos: `ERRORES: 0` antes de la corrección.

**Corrección** (`validate_acceptance_semantics`): `expected_chunk_ids` se resuelve hasta su fuente (vía `chunk.source_id`) y `expected_evidence_ids` hasta chunk y luego fuente (vía `evidence.chunk_id` → `chunk.source_id`), aplicando la misma regla de `access_hierarchy` que ya regía para `expected_source_ids`. `must_not_retrieve` ahora debe contener únicamente ids que existan realmente como `source`/`chunk`/`evidence` del paquete. Adicionalmente, `acceptance_case.schema.json` agrega `uniqueItems: true` a las cuatro listas y restringe `must_not_retrieve` a los tres patrones URN reconocidos (antes aceptaba cualquier string).

Ambas correcciones (0.1 y 0.2) fueron verificadas con la misma metodología de aislamiento que las detectó: recalculando `checksums.json` tras la mutación, para confirmar que el rechazo proviene específicamente de la verificación corregida y no de un efecto colateral.

### 0.3 `evidence.jsonl` no se resolvía vía `chunk_id` (rc3.2)

`EvidenceRecord` tiene tanto `chunk_id` como `source_id` — el segundo es una copia informativa que RAG Studio ya conoce al momento de generar la evidencia, pero la relación *real* de la que depende el control de acceso es `evidence.chunk_id → chunk.source_id`. `validate_acceptance_semantics`, al resolver la fuente de un `expected_evidence_id` para aplicar `access_hierarchy`, leía `evidence.source_id` directamente — una copia que la ronda `rc3.1` nunca verificó contra el dato real.

Se demostró falseando `evidence.source_id` a una fuente `pública` en una evidencia cuyo `chunk_id` seguía apuntando a un chunk de la fuente `confidencial`, y declarando esa evidencia como esperada en un caso de usuario `publico`. Resultado antes de la corrección: `ERRORES: 0` — una evidencia podía, en los hechos, "cambiarse de fuente" sin que nada lo detectara.

**Corrección, en dos capas independientes:**

1. `source_for_evidence()` en `validate_acceptance_semantics` ahora resuelve **siempre** vía `evidence.chunk_id → chunk.source_id`, nunca vía `evidence.source_id`.
2. `validate_referential_integrity` agrega un chequeo separado: `evidence.source_id` debe coincidir con el `source_id` real del chunk que referencia. Así la inconsistencia es un error en sí misma, no solo un dato que la resolución correcta ignora en silencio.

Verificado con la misma metodología de aislamiento (checksums recalculados) que las brechas anteriores, y añadido como caso 19 de la suite automatizada.

### 0.4 Ajustes documentales (no bloqueantes, incluidos en este parche)

- `acceptance_case.schema.json` remitía a "ADR sección 7" para el protocolo `AR-INC-00`; corregido a la sección 9 (donde vive desde `rc3.1`).
- Las cadenas de versión de `generate_example.py` (`manifest.schema_version`, `exporter_version`, nombre de los sidecars, `signature.key_id`, `signature.signer`) estaban hardcodeadas por separado y quedaron en `rc3` mientras `rc3.1` ya se declaraba como tal en el ADR/LEEME. Se unificaron en tres constantes (`RC_TAG`, `SCHEMA_VERSION`, `FILE_TAG`) definidas una sola vez al inicio del script, para que esto no vuelva a desalinearse. `test_negative_cases.py` además descubre los sidecars por sufijo (`*.content.sha256`) en vez de por nombre de versión hardcodeado, así que tampoco requiere edición manual en la próxima ronda.
- Referencia de este mismo ADR al `.zip` de `rc3` (retirado) como lugar donde se "conserva el historial" — corregida (ver el segundo párrafo de este documento).
- Conteos del LEEME y de la sección de verificación actualizados a los números reales de esta ronda (sección 10).

---

## El hallazgo que originó rc3

El revisor reprodujo, contra `v1.0-rc2`, cuatro casos que el schema-level validation dejaba pasar con **0 errores**:

```
created_at = "not-a-date"                              -> 0 errores
original_included=false, original_omission_reason=null -> 0 errores
media.included_in_package=true sin el binario real      -> 0 errores
manifest.counts.chunks=999 (real: 6)                     -> 0 errores
```

Los cuatro son ahora, en `v1.0-rc3.2`, rechazados por el validador — reproducible con `validator/test_negative_cases.py` (sección 10). El resto de este documento explica por qué cada uno pasaba y qué se corrigió.

## 1. `FormatChecker` real + autochequeo de 14 schemas (corrección 1)

**Causa raíz del caso `created_at="not-a-date"`:** la librería `jsonschema` **no valida `format: date-time` a menos que se cumplan dos condiciones simultáneas**: (a) se pase explícitamente `format_checker=Draft202012Validator.FORMAT_CHECKER` al construir el validador, y (b) el paquete opcional `rfc3339-validator` esté instalado. Sin ambas, la validación de formato es un **no-op silencioso** — el validador de rc2 pasaba `format_checker` en algunos puntos pero no en todos, y `rfc3339-validator` no estaba en las dependencias documentadas, así que en la práctica nunca se ejecutaba. Esto se confirmó empíricamente antes de corregir nada: con el paquete instalado y el `format_checker` explícito, la misma cadena inválida sí produce error; sin cualquiera de los dos, no.

Corrección: `validate_knowledge_package.py` ahora construye **todo** validador (los 14 schemas, más el de `signature.schema.json` para el sidecar) a través de una única función `make_validator()` que siempre pasa `format_checker=Draft202012Validator.FORMAT_CHECKER`. `rfc3339-validator` pasa a ser dependencia obligatoria, fijada en `requirements.lock.txt`, y el validador **se niega a arrancar** (error controlado, no falla en silencio) si no está instalado.

Además, se agrega un autochequeo de arranque, ejecutado antes de tocar ningún paquete: deben existir **exactamente 14** archivos `*.schema.json` en `schemas/` (el nuevo `access_hierarchy.schema.json`, sección 8, eleva el conteo de 13 a 14) y los 14 deben pasar `Draft202012Validator.check_schema()`. Esto cierra la clase de error de rc1 ("el ADR dice catorce, hay doce") de raíz: el conteo ya no es una afirmación en prosa, es una aserción que corre en cada ejecución.

## 2. Perfiles y originales: reglas cruzadas, no solo un `if/then/else` de schema (corrección 2)

rc2 introdujo el `if/then/else` de `source.schema.json` que fuerza `original_relative_path=null` cuando `original_included=false`, pero **no** forzaba que `original_omission_reason` fuera distinto de `null` en ese mismo caso — de ahí que el caso demostrado por el revisor pasara. Se corrige en dos niveles:

**Nivel schema** (`source.schema.json`, rama `else`): ahora exige explícitamente `"original_omission_reason": {"not": {"const": null}}` cuando `original_included=false`. Esto por sí solo ya rechaza el caso del veredicto.

**Nivel validador** (`validate_profile_and_originals`, nuevo): cruza `original_included`/`original_omission_reason` contra `manifest.profile`, no solo contra los otros campos del mismo `SourceRecord`. Bajo `CORE`, la única razón válida es `not_applicable_profile_core` — cualquier otra (aunque no sea `null`) es rechazada. Bajo `AUDIT`, las razones válidas son `license`/`confidential`/`size_limit`/`no_binary_source`/`other` — `not_applicable_profile_core` bajo `AUDIT` es en sí mismo un error (la razón "no aplica por ser CORE" no tiene sentido en un paquete `AUDIT`). `PREINDEXED` no tiene razones válidas porque **no está implementado en v1.0** — cualquier paquete que declare ese perfil es rechazado directamente.

**Límite de tamaño, ahora definitivo:** rc2 dejaba "50 MB sugeridos, a confirmar con NEXOM" como texto abierto. Se fija como política de `v1.0`: **50 MB (52 428 800 bytes) por archivo original incluido bajo `AUDIT`**, verificado contra el tamaño real en disco del archivo referenciado por `original_relative_path`. Un original que exceda el límite y aun así se declare `original_included=true` es rechazado; la forma correcta de manejarlo es `original_included=false` con `original_omission_reason="size_limit"`.

## 3. Igualdad exacta de conjuntos de archivos + conteos reales (corrección 3)

**Causa raíz de los casos `media.included_in_package=true` sin binario y `manifest.counts.chunks=999`:** ninguna de las dos cosas viola ningún JSON Schema — son inconsistencias *entre* archivos, no dentro de uno. rc2 no tenía ninguna verificación que cruzara "lo que un registro declara" contra "lo que realmente existe en el paquete".

Se agrega `validate_file_set_and_counts`, que calcula y compara **cuatro conjuntos** de nombres de archivo:

```
manifest.files            -- lo que el manifiesto declara que existe
checksums.files ∪ {checksums.json}
                            -- lo que checksums.json tiene hash de, más si mismo
archivos fisicos           -- lo que realmente hay en el directorio/zip
activos declarados         -- media.jsonl (included_in_package=true) +
                               sources.jsonl (original_included=true)
```

Los cuatro deben ser consistentes: `manifest.files` debe ser exactamente igual a `checksums.files + {checksums.json}` (ni de más ni de menos); todo archivo de `manifest.files` debe existir físicamente (si no, error explícito de "declarado pero ausente" — cierra el caso 3); todo archivo físico debe estar en `manifest.files` (si no, error de "archivo no declarado" — nunca puede haber un extra silencioso); todo activo declarado por `media.jsonl`/`sources.jsonl` debe aparecer tanto en `manifest.files` como en `checksums.files` como físicamente presente — un binario declarado incluido pero inexistente (el caso exacto del veredicto) ahora produce tres errores distintos, uno por cada conjunto con el que es inconsistente.

Sobre los conteos: `manifest.counts` (sources/chunks/evidence/media/intents/guardrail_rules/acceptance_cases) se recalcula **desde los registros efectivamente cargados** de cada `.jsonl`/bundle, nunca desde el número que el propio manifiesto afirma. `manifest.counts.chunks=999` contra 6 chunks reales ahora produce un error explícito con ambos números.

En modo `.zip`, se agregan dos verificaciones adicionales sobre las entradas del archivo antes de extraer nada: **nombres de entrada duplicados** (dos entradas con el mismo nombre dentro del mismo zip — ambiguo y potencial vector de manipulación) y **entradas cifradas** (bit de cifrado del flag de la entrada activado — no soportado, se rechaza).

## 4. `logical_id` opaco: ya no se recomputa, se verifica continuidad (corrección 4)

rc2 tenía un defecto de fondo, no solo de implementación: `source_logical_id` se derivaba **caminando `supersedes_source_id` dentro de la exportación actual** hasta encontrar la raíz de la cadena. Esto funciona mientras el paquete incluya el historial completo — pero si una exportación futura solo contiene la versión vigente de una fuente (sin su historial, por ejemplo porque las versiones superseded ya se purgaron o simplemente no se seleccionaron para ese export), el algoritmo tomaría esa versión como si fuera la raíz y produciría un `logical_id` **distinto** del que la misma fuente tuvo en una exportación anterior que sí incluía el historial — rompiendo silenciosamente la identidad lógica que todo el punto 2b de rc2 pretendía garantizar.

Corrección de fondo: `lineage_id` pasa a ser un valor **opaco y persistente**. Se asigna una sola vez (UUID4, sin fórmula determinista) cuando una fuente raíz se crea en RAG Studio, y toda versión que la supersede simplemente **copia** el mismo valor — nunca se recalcula, ni en RAG Studio (responsabilidad de `RAG-INC-01`, un campo nuevo persistido junto al `SourceRecord`) ni en el exportador ni en el validador. `logical_id` (`urn:nexom:source-logical:<lineage_id>`) hereda esta propiedad.

El validador ya **no intenta recomputar** `logical_id` desde el contenido del paquete (es opaco por diseño, no se puede). En su lugar, `validate_lineage_continuity` verifica **continuidad de cadena**: si `A.supersedes_source_id = B` y ambas están presentes en el mismo paquete, deben compartir `logical_id` — si no, la cadena está rota y se rechaza, independientemente de si el paquete tiene el historial completo o no. Esto es estrictamente más robusto que recomputar: sigue detectando una cadena corrupta dentro de un mismo export, sin depender de que exportaciones futuras incluyan todo el pasado.

## 5. `field_definition_id` como clave relacional real (corrección 5)

rc2 nombraba el campo `field_id` en `source_metadata.jsonl` pero en la práctica seguía siendo el código local legible (`"campus"`), no un identificador portable — la clave de relación real dependía de un string elegido por el administrador del proyecto, no de un URN verificable. Se corrige renombrando y separando responsabilidades:

```
source_metadata.jsonl:  field_definition_id (urn:nexom:field:<uuid>) -- CLAVE REAL
                         field_code ("campus")                        -- informativo, viaja aparte
chunk.inherited_metadata: { "<field_definition_id URN>": "<value>", ... }
                         -- ya NO se indexa por field_code local
```

Ambos schemas (`source_metadata.schema.json`, `chunk.schema.json`) exigen el patrón `^urn:nexom:field:[0-9a-f-]{36}$` — `chunk.schema.json` lo hace con `propertyNames` sobre las claves de `inherited_metadata`, de forma que un chunk que use `"campus"` como clave (el caso demostrado por el veredicto) es rechazado directamente a nivel de schema, sin necesitar lógica adicional. El validador además verifica que todo `field_definition_id` referenciado exista realmente como `id` de un `FieldDefinition` en `metadata_schema.json`, y que el `field_code` informativo coincida con el `field_id` local del mismo `FieldDefinition` (consistencia, no relación).

## 6. Sidecar de firma validado contra su propio schema (corrección 6)

rc2 leía `signature.json`/`.sig` y usaba sus campos directamente — un sidecar malformado (por ejemplo, sin el campo `signature`) no producía un error claro, sino potencialmente un `KeyError` sin controlar. Se corrige validando el sidecar **contra `signature.schema.json` antes de usar cualquiera de sus campos**: si no cumple, se reporta como error de schema (con la ruta y el mensaje exactos) y no se intenta leer nada más de él.

Se agrega además `--trusted-key-id`, argumento opcional de línea de comandos: si se entrega, el validador confirma que `signature.key_id` coincide con el valor esperado. Esto es **defensa en profundidad, no un almacén de confianza** — el ADR es explícito en que, en producción, Agent Runtime debe resolver la clave pública desde su propio almacén de confianza (indexado por `key_id`, gestionado fuera de este contrato), nunca aceptar como prueba de identidad una clave pública entregada junto con el paquete. La clave `*.pubkey_DEMO.pem` de este entregable es válida solo para pruebas de este mismo paquete de ejemplo.

## 7. `capabilities`/`omissions`: verificación bidireccional de los 4 códigos (corrección 7)

rc2 solo verificaba una dirección de un único código (`MEDIA_BINARIES_NOT_INCLUDED`, cuando hay imágenes sin binario). Se extiende a los 4 códigos definidos, en **ambas direcciones**: si la condición aplica y el código no está declarado, error; si el código está declarado pero la condición **no** aplica (omisión declarada falsamente, por ejemplo para simular una degradación que no existe), también error.

```
MEDIA_BINARIES_NOT_INCLUDED  <-> existe media.jsonl con included_in_package=false
ORIGINALS_NOT_INCLUDED       <-> existe alguna fuente con original_included=false
VECTORS_NOT_INCLUDED         <-> perfil CORE/AUDIT (v1.0 nunca transporta vectores reales
                                  bajo estos perfiles; PREINDEXED no está implementado)
EVIDENCE_NOT_VERIFIED        <-> todos los registros de evidence.jsonl son verification_status=derived
```

`EVIDENCE_NOT_VERIFIED` es, específicamente, una omisión que el paquete de ejemplo de rc2 debía declarar y no declaraba (sus 4 registros de evidencia son todos `derived` — RAG Studio no tiene hoy ningún flujo de verificación editorial) — corregido tanto en `generate_example.py` como exigido ahora por el validador.

Adicionalmente: si `capabilities.image_retrieval=true`, el validador exige que **todas** las imágenes de `media.jsonl` tengan `included_in_package=true` (no solo algunas) y que exista al menos un índice en `indexes.json` cuyo `covers_chunk_types` incluya `"imagen"` — declarar capacidad de recuperación visual sin binarios completos ni índice que la cubra es, ahora, un error, no una posibilidad silenciosa.

## 8. Semántica ejecutable de `acceptance_cases.jsonl` + `access_hierarchy.json` (corrección 8)

`acceptance_case.schema.json` ahora **exige** (campos requeridos, no opcionales) `top_k` (cuántos resultados pedir), `match_policy` (`contains`: todo lo esperado debe aparecer, se permiten extras; `exact`: el conjunto debe ser exactamente igual; `ranked`: el orden esperado debe respetarse dentro de `top_k`) y `minimum_recall` (fracción mínima de `expected_chunk_ids` que debe recuperarse). Antes de esta corrección, "el caso pasa" dependía de una interpretación no escrita de qué contaba como éxito — ahora es una condición matemática verificable por cualquier implementación de Agent Runtime sin tener que adivinar la intención de RAG Studio.

Se agrega `access_hierarchy.json` (schema nuevo, `access_hierarchy.schema.json`), porque dejar el orden de niveles de acceso implícito en el orden textual de un `enum` de JSON Schema era una suposición no garantizada por la especificación (el orden de un `enum` no tiene semántica definida) y por tanto no verificable de forma confiable por Agent Runtime:

```json
{
  "order": ["publico", "interno", "confidencial", "restringido"],
  "rule": "Un usuario con user_access_level X puede acceder a fuentes cuyo access_level tenga indice <= indice(X) en `order`. Denegacion por defecto: cualquier access_level no reconocido, o ausencia de user_access_level, deniega el acceso -- nunca se asume el nivel mas permisivo."
}
```

El validador cruza cada caso de `acceptance_cases.jsonl` contra esta jerarquía: si un caso declara `expected_source_ids` que incluye una fuente cuyo `access_level` está por encima del `user_access_level` de la propia prueba, el caso está mal formado y se rechaza — un caso de aceptación nunca debería, por construcción, esperar que se devuelva algo que la propia jerarquía prohibiría.

Este esquema eleva el conteo de schemas de 13 (rc2) a **14** (rc3). `acceptance_case.schema.json` se endureció de nuevo en `rc3.1` (sección 0.2): `uniqueItems: true` en las cuatro listas de IDs, y `must_not_retrieve` restringido a los tres patrones URN reconocidos.

## 9. El protocolo `AR-INC-00`, íntegro

`rc3` definía este protocolo remitiendo a "la sección 7 del ADR de `rc2`" — una referencia que dejó de ser autosuficiente en cuanto `rc2` fue reemplazado por `rc3` (y, más tarde, retirado de la carpeta de entrega). Se reproduce aquí íntegramente, sin cambios de fondo respecto de la versión original, para que este documento no dependa de ningún ADR anterior.

> **`AR-INC-00` — Prueba de compatibilidad del NEXOM Knowledge Package.** A ejecutar por el equipo de Agent Runtime, no por RAG Studio. Protocolo:
>
> 1. Validar el paquete de ejemplo con `validate_knowledge_package.py` — cero errores.
> 2. Importarlo en un almacenamiento vacío.
> 3. Reconstruir su índice desde `chunks.jsonl` usando el `EmbeddingSpace` declarado.
> 4. Ejecutar los tres casos de `acceptance_cases.jsonl` y confirmar evidencia/citas/jerarquía/filtros/guardrail exactamente como se declaran (semántica `top_k`/`match_policy`/`minimum_recall`, sección 8).
> 5. Confirmar que su importador aplica denegación por defecto (caso `AC-003`, que ejercita `must_not_retrieve`) y no una lista negra ad-hoc.
> 6. Confirmar que su importador rechaza una copia manipulada del paquete (chunk con texto alterado tras generar su id, ver `test_negative_cases.py` caso 17) y un `.zip` con path traversal (caso 18).
> 7. Emitir un informe firmado con: versión del contrato (`schema_version`), `content_digest` del paquete usado, versión de su propio importador, resultados de los 3 casos de aceptación, y cualquier desviación encontrada.

`AR-INC-00` es un incremento corto y de bajo riesgo — no toca RAG Studio en absoluto — y es la pieza que falta para que el contrato deje de depender solo de quien exporta. Su condición de salida es el informe firmado del paso 7; sin él, el contrato no se congela como `v1.0` (roadmap, más abajo).

## Endurecimientos no bloqueantes incluidos en esta ronda

- El sidecar de digesto se renombra de `<paquete>.sha256` a **`<paquete>.content.sha256`**, eliminando la ambigüedad con un eventual hash de los bytes crudos del `.zip`. Se agrega soporte opcional (`--zip-sha256-file`) para verificar además un **`<paquete>.zip.sha256`** real de los bytes del contenedor, cuando el paquete se distribuye como `.zip`.
- `content_digest` se calcula canonicalizando una **estructura JSON** (`{"checksums_json_hash": ..., "files": {...}}`) en vez de concatenar texto `"ruta:hash"` — elimina cualquier ambigüedad teórica si un nombre de archivo futuro contuviera `:` o un salto de línea.
- `requirements.lock.txt` fija versiones exactas (`jsonschema==4.26.0`, `rfc3339-validator==0.1.4`, `rfc8785==0.1.4`, `cryptography==50.0.1`) para que "pasa en mi máquina" no dependa de qué versión resolvió `pip` ese día.
- El validador ya no puede terminar en una traceback sin controlar: `main()` atrapa cualquier excepción no anticipada (entrada malformada, JSON inválido, sidecars ausentes) y la reporta como mensaje legible con código de salida 1, nunca como una traza de Python cruda.
- Las pruebas negativas dejan de ser prosa descriptiva y pasan a ser un script ejecutable y reproducible (sección 10), y descubren sus sidecars por sufijo en vez de por nombre de versión hardcodeado (sección 0.4).

## 10. Verificación de este mismo entregable

**Matriz positiva, reproducible por cualquiera con este `.zip`:**

- Paquete de ejemplo regenerado (4 fuentes incluida la cadena de versión, 6 chunks, 4 evidencias, 1 media, 3 `acceptance_cases`) — **0 errores**: 165 comprobaciones como directorio, 166 como `.zip` (la comprobación adicional es el allowlist dinámico del zip). Con `--trusted-key-id` se suma 1 comprobación más (166/167).
- Todas las cadenas de versión del paquete (`manifest.schema_version=1.0.0-rc3.2`, `exporter_version`, nombre de los sidecars, `signature.key_id`, `signature.signer`) son consistentes entre sí y con este ADR (sección 0.4).
- Autochequeo de arranque: 14/14 schemas válidos como JSON Schema 2020-12.

**Matriz negativa, `validator/test_negative_cases.py` — 19 casos negativos, cada uno mutando una copia del paquete válido y afirmando que el validador lo rechaza (código de salida 1), más el caso base sin mutar afirmando que se acepta (código 0) — 20 aserciones en total. El caso 19 es nuevo en `rc3.2`:**

```
01 created_at invalido                                    -> rechazado
02 original_omission_reason=null (falso)                   -> rechazado
03 media.included_in_package=true sin binario               -> rechazado
04 manifest.counts.chunks falso (999 vs 6)                  -> rechazado
05 activo declarado en manifest.files pero ausente          -> rechazado
06 activo fisico presente sin checksum declarado            -> rechazado
07 archivo fisico extra no declarado en manifest            -> rechazado
08 entrada duplicada dentro del .zip                        -> rechazado
09 sidecar .sig que no cumple signature.schema.json         -> rechazado
10 evidencia toda derived sin declarar la omision           -> rechazado
11 cadena de supersesion con logical_id distinto             -> rechazado
12 inherited_metadata con codigo local en vez de URN        -> rechazado
13 acceptance_case sin top_k                                 -> rechazado
14 source.id no determinista (rc3.1, seccion 0.1)            -> rechazado
15 must_not_retrieve inexistente (rc3.1, seccion 0.2)        -> rechazado
16 chunk esperado sobre nivel de acceso (rc3.1, sec 0.2)     -> rechazado
17 chunk con texto manipulado tras generar el id             -> rechazado
18 zip con path traversal (../../etc/evil.txt)               -> rechazado
19 evidence.source_id no coincide con su chunk (rc3.2, 0.3)  -> rechazado
00 paquete base, sin mutar                                   -> aceptado
```

Los casos 01-04 son los que el segundo revisor (tercer veredicto) demostró que `rc2` aceptaba; los casos 14-16 son los que la primera auditoría independiente (sobre `rc3`) demostró que seguían pasando; el caso 19 es el que la segunda auditoría independiente (sobre `rc3.1`, este documento, sección 0.3) demostró que seguía pasando. Los 20 están confirmados aquí como corregidos, no solo declarados corregidos, y cada uno se verificó con `checksums.json` recalculado tras la mutación para aislar el defecto específico que prueba.

## Qué NO se hizo en este incremento

No se modificó `project.db`, Qdrant embebido, ningún exportador existente, ni la interfaz de usuario. `lineage_id` y `knowledge_base_id` como campos persistidos siguen siendo, explícitamente, requisitos de implementación para cuando se autorice `RAG-INC-01` — no se creó ningún campo nuevo en el esquema real de RAG Studio en este incremento. Tampoco se rediseñó ningún aspecto del contrato: ni las fórmulas de `id_scheme.py` (ya eran correctas; lo que faltaba era que el validador las hiciera cumplir) ni la estructura de `acceptance_cases.jsonl`/`EvidenceRecord` (ya tenían los campos correctos; lo que faltaba era resolverlos y validarlos todos con el mismo rigor).

## Roadmap actualizado

1. **`RAG-INC-00` v1.0-rc3.2 (este documento).** Contrato, validador y ADR alineados, autosuficientes y con cadenas de versión consistentes; matriz positiva (165-167 comprobaciones según modo) y negativa (20 casos) reproducibles. **No se declara congelado.**
2. **`AR-INC-00` (sección 9, protocolo completo) — a ejecutar por NEXOM/Agent Runtime**, sobre `v1.0-rc3.2`. Condición de salida: informe firmado confirmando el protocolo de 7 pasos contra `example_package/`, y que certifique explícitamente `schema_version = 1.0.0-rc3.2` (ya sin la ambigüedad de versión que afectaba a `rc3.1`).
3. **Congelar `v1.0` formalmente.** Solo cuando (2) resulte aprobado: `Contract status = ACCEPTED`, `schema_version = 1.0.0`.
4. **`RAG-INC-01` — Exportación central.** Solo autorizable después de (3).

Este documento **no recomienda autorizar `RAG-INC-01` todavía**. Tampoco recomienda otra ronda de rediseño del contrato: la arquitectura, según los cuatro veredictos/auditorías recibidos hasta ahora, ya es correcta — lo que quedaba pendiente, en cada ronda, era que el validador hiciera cumplir exactamente lo que el ADR afirma, con precisión sobre CUÁL campo es la relación real (`chunk_id`, no la copia informativa `source_id`) y CUÁL versión certifica el informe firmado. `v1.0-rc3.2` es, con la evidencia disponible hasta ahora, el primer candidato para el que ambas cosas se sostienen bajo auditoría adversarial con aislamiento controlado — sin que eso sustituya la verificación independiente de Agent Runtime en `AR-INC-00`, que sigue siendo el único paso pendiente para declarar `v1.0`.
