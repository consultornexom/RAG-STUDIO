# Alcance de RAG-INC-01 — Exportador NEXOM Knowledge Package v1.0.0 en RAG Studio

**Documento:** Alcance para firma conjunta con la Declaración de aceptación del contrato v1.0.0
**Estado:** VERSIÓN FINAL PARA FIRMA, revisión 4.1 (solo documental). Incorpora las decisiones de NEXOM del 23-09-2026, las siete correcciones de su revisión de la revisión 2, la resolución de INC01-D7 y la corrección de INC01-R6. No se implementa nada antes de la firma.
**Fecha:** 23 de septiembre de 2026
**Contrato de referencia:** NEXOM Knowledge Package `v1.0.0` (artefactos normativos y hashes en la sección 4.1 de la Declaración)
**Base técnica:** lectura directa del código actual de RAG Studio (rutas citadas en cada punto) y del Informe de validación de interoperabilidad de Agent Runtime.

---

## 1. Objetivo

Que RAG Studio exporte cualquier proyecto real como un NEXOM Knowledge Package **perfil CORE** que el validador de referencia `v1.0.0` acepte con 0 errores y que Agent Runtime importe sin cambios de su lado.

El incremento no cambia el contrato. Si durante la implementación algo del contrato resulta insuficiente, se documenta como propuesta de cambio (Declaración, sección 8). No se resuelve con lógica propia del exportador.

## 2. Organización: un incremento, cuatro hitos con puerta de aprobación

Con `v1.0.0`, un paquete sin `metadata_schema.json`, `evidence.jsonl`, `conversational_bundle.json`, `access_hierarchy.json` u otro archivo obligatorio **no es válido**. El RAG-INC-01 mínimo del análisis previo (solo manifest, sources y chunks) ya no es aceptable con el criterio "validador con 0 errores".

Por decisión INC01-D1, RAG-INC-01 es **un solo incremento con cuatro hitos**:

| Hito | Contenido | Puerta |
|---|---|---|
| 01a | Identidades persistentes y migración `0021` | Revisión de NEXOM antes de 01b |
| 01b | Modelo y exportador CORE | Revisión de NEXOM antes de 01c |
| 01c | Contrato vendorizado y prueba de conformidad | Revisión de NEXOM antes de 01d |
| 01d | Pruebas, verificación con datos reales e importación de humo | Aceptación del incremento |

La migración `0021` no se libera en ninguna instalación productiva hasta completar 01d. Mientras tanto se ejecuta solo en entornos de desarrollo y sobre copias de proyectos.

## 3. Hallazgo que condiciona el alcance: faltan dos identidades persistentes

- `knowledge_base_id` no existe. `Project.id` (`domain/projects/entities.py:58`) no sirve para este papel porque no es estable entre instalaciones: `ImportProject` acepta `new_project_id` (`application/projects/commands/import_project.py:20-41`).
- `lineage_id` no existe. `RegisterSource` (`application/documents/commands/register_source.py`) crea la fuente nueva con `supersedes_source_id` pero no hereda ninguna identidad lógica.

Las dos se guardan en `project.db`, donde ya viven `project` (`ProjectRecord`, `infrastructure/database/models.py:68`), `source`, `index_info` y las demás tablas del contrato. Por eso viajan con las instantáneas y con `.agentproj`. La migración de `project.db` queda autorizada por la decisión INC01-D2.

## 4. Alcance incluido

### Hito 01a — Identidades persistentes

Migración `migrations/project/versions/0021_nexom_identities.py` (la última actual es `0020_chunk_image_relative_path.py`). Se ejecuta por etapas y dentro de una transacción:

1. Agregar `project.knowledge_base_id` y `source.lineage_id` como columnas **anulables**.
2. **Relleno consistente, transaccional y persistente**:
   - cada proyecto recibe un `knowledge_base_id` UUID4;
   - cada cadena de supersesión recibe un único `lineage_id` UUID4, asignado a la raíz y copiado a todas sus descendientes. El recorrido usa la misma lógica que `GetSourceLineage` (`application/documents/queries/get_source_lineage.py:42-57`);
   - una fuente cuyo `supersedes_source_id` apunta a un id inexistente (caso previsto en `register_source.py:53-73`) se trata como raíz de su propia cadena y queda en el log de la migración.

   Los valores son UUID4, así que el relleno **no es determinista**: aplicar la migración dos veces sobre la misma base daría valores distintos. Lo que se garantiza es consistencia dentro de cada cadena y persistencia una vez escrito.
3. Verificar: ninguna fila queda sin valor, cada cadena tiene un solo `lineage_id` y no hay ciclos en `supersedes_source_id`. Si aparece un ciclo, la migración aborta y revierte la transacción completa, sin asignar identidades arbitrarias.
4. Imponer `NOT NULL` reconstruyendo las tablas con `op.batch_alter_table`, porque SQLite no admite `ALTER COLUMN`. Es el mismo patrón que ya usa `0012_metadata_value_change_deletable.py`.
5. Crear índices y restricciones: `knowledge_base_id` único e índice sobre `source.lineage_id`.
6. Comprobación final de las condiciones del paso 3 sobre el esquema definitivo.

**Downgrade protegido.** Revertir `0021` elimina identidades, y reaplicarla generaría ids distintos que romperían la continuidad con cualquier paquete ya exportado. Por eso `downgrade()` se niega a ejecutarse con un error explícito. Solo acepta una bandera de anulación que usan las pruebas sobre copias desechables. La vuelta atrás en una instalación real se hace **restaurando un respaldo completo** (`application/projects/commands/backup_project.py` ya existe), nunca con `alembic downgrade`.

**Dominio y aplicación:**

- `Project.knowledge_base_id` y `Source.lineage_id` pasan a ser campos obligatorios; un objeto nuevo recibe UUID4 por defecto.
- `RegisterSource`: con un `supersedes_source_id` válido, **copia** el `lineage_id` de la fuente anterior. Sin él, conserva el UUID4 nuevo.
- Los repositorios SQLAlchemy (`infrastructure/database/document_repositories.py` y el de proyectos) mapean las columnas nuevas.

**Política de identidades (decisión INC01-D3).** RAG Studio nunca decide en silencio.

`ImportProject.execute` recibe un parámetro obligatorio `identity_policy` con dos valores posibles, `preserve` y `fork`. El resultado depende de la política solicitada y de si la identidad ya existe en la instalación:

| Política solicitada | ¿Ya existe en la instalación un proyecto (activo o archivado) con el mismo `knowledge_base_id`? | Resultado |
|---|---|---|
| `preserve` | No | Importa conservando `knowledge_base_id` y todos los `lineage_id` |
| `preserve` | Sí | Aborta con el error tipado `KnowledgeBaseIdentityCollisionError`, sin modificar ningún dato |
| `fork` | Sí o no | Regenera `knowledge_base_id` y un `lineage_id` nuevo por cadena, manteniendo quién supersede a quién. Importa como base independiente |
| No indicada | Cualquier estado | Aborta antes de leer o modificar datos |

- El caso de uso **no pide un modo de forma interactiva**, porque la UI está fuera de alcance. Devuelve el error tipado y el llamador decide si reintenta con `fork`.
- Con `fork`, regenerar `lineage_id` cambia también los `source.id` y `chunk.id` portables de la copia. Es lo esperado: la copia es otra base de conocimiento. Si además el `project_id` ya existe, se aplica la regla vigente de `ImportProject`: hay que indicar `new_project_id` o se lanza `ProjectIdCollisionError`.
- `CloneProject` (`application/projects/commands/clone_project.py`) crea un `Project` nuevo sin copiar fuentes, así que recibe un `knowledge_base_id` nuevo por construcción. Se agrega una prueba que lo fija.

**Restaurar conservando identidades sobre una instalación que ya tiene esa base.** RAG-INC-01 **no implementa reemplazo ni sobrescritura**. Archivar el proyecto existente no sirve: un proyecto archivado conserva su `knowledge_base_id` y sigue provocando la colisión, y excluir los archivados de la detección permitiría dos copias locales con la misma identidad portable.

Tampoco sirve hoy el flujo "respaldar, eliminar e importar con `preserve`" con los comandos actuales. `DeleteProject` (`application/projects/commands/delete_project.py`) solo elimina proyectos **sin fuentes** y lanza `ProjectInUseError` en cualquier otro caso, así que un proyecto real no puede eliminarse desde la aplicación. Por tanto, en RAG-INC-01:

- restaurar con `preserve` solo es posible en una instalación donde esa identidad no existe (otra máquina o una instalación nueva);
- si la identidad ya existe en la instalación, la única vía es `fork`;
- la eliminación definitiva de proyectos con fuentes y cualquier modo de reemplazo o sobrescritura **no están autorizados en RAG-INC-01** (decisión INC01-D7).

**Detección de colisiones: escaneo local con exclusión mutua.** No se agrega un índice global en `application.db`: sería una segunda fuente de verdad y una segunda migración, sin evidencia de problemas de escala. El escaneo de los `project.db` instalados se acepta con estas condiciones:

1. Un **bloqueo real del sistema operativo** sobre un archivo del directorio de la instalación (bloqueo exclusivo de rango o archivo, no un archivo centinela cuya sola existencia signifique "bloqueado") cubre toda la secuencia **comprobar → importar → registrar**. El sistema operativo lo libera automáticamente al cerrar el descriptor o al terminar el proceso, así que un cierre abrupto no deja la instalación bloqueada. La espera tiene un **tiempo máximo**; al agotarse, la importación falla con el error tipado `ImportLockTimeoutError` sin haber modificado datos. Hoy RAG Studio no tiene una utilidad de bloqueo entre procesos, así que se crea una. Si necesita una dependencia nueva, se declara en la puerta de 01a.
2. El escaneo incluye proyectos activos y archivados. No incluye las copias de `snapshots/`, que no son proyectos instalados.
3. **Fail-closed:** si algún `project.db` instalado no puede abrirse o leerse, la importación aborta. No se asume "sin colisión".
4. La comprobación se repite inmediatamente antes de confirmar el registro del proyecto importado.
5. Toda colisión detectada queda en el log técnico, con el `knowledge_base_id`, el proyecto existente y la política solicitada.

### Hito 01b — Modelo y exportador CORE

- `domain/knowledge_package/`: entidades inmutables de los registros del contrato y el puerto `KnowledgePackageExporter`, sin dependencias de infraestructura.
- `application/knowledge_package/commands/export_knowledge_package.py`, con esta firma:

  ```
  export_knowledge_package(project_id, snapshot_id, tenant, output_dir)
  ```

  - `tenant` es **obligatorio**. Si falta o está vacío, la exportación falla. No se infiere del nombre del proyecto ni se usa un valor como `default` (decisión INC01-D4).
  - `project_id` es necesario porque el repositorio de instantáneas se consulta por proyecto (`SqlAlchemyProjectSnapshotRepository`, `infrastructure/database/release_repositories.py:78-110`).
- **Fuente de datos.** Todos los datos contractuales se leen del `project.db` contenido en la instantánea: `knowledge_base_id` y demás campos de `project`, fuentes, chunks, metadata, artefactos conversacionales e `IndexInfo`. El exportador nunca mezcla la instantánea con un `Project` vivo ni con el proyecto en edición.
- **Descriptor de la instantánea.** El `id`, `version`, `created_at` y `snapshot_dir` se toman del registro `ProjectSnapshot`, que vive en el `project.db` del proyecto vivo. El `project.db` copiado no lo contiene, porque `PublishProjectSnapshot` copia el directorio antes de guardar ese registro (`application/release/commands/publish_project_snapshot.py:45-51`). Son metadatos descriptivos de la instantánea, no contenido. Su inmutabilidad se convierte en precondición comprobable:
  - el repositorio ya es de solo inserción: el puerto `ProjectSnapshotRepository` (`domain/release/ports.py:44-56`) no tiene operación de actualización y `save` hace un `INSERT`. RAG-INC-01 agrega solo una lectura por id y ninguna operación de actualización. Una prueba de arquitectura falla si aparece una;
  - el registro se carga **una sola vez** al iniciar la exportación, como DTO inmutable;
  - se verifica que `snapshot.project_id` coincide con el `project.id` del `project.db` copiado;
  - se verifica que `snapshot_dir` existe y es exactamente el directorio del que se lee el `project.db`;
  - cualquier inconsistencia aborta la exportación.
- `infrastructure/exporters/nexom_knowledge_package.py` genera los **13 archivos internos** del paquete CORE (12 de datos y manifiesto, más `checksums.json`) con la implementación de referencia `id_scheme.py` (URNs, RFC 8785, `content_digest`). Genera también el **sidecar externo** `*.content.sha256`, que no forma parte del paquete. No hay que confundir estos 13 archivos con los 14 JSON Schemas del contrato. El paquete `infrastructure/exporters/` existe hoy vacío, así que no choca con los cuatro exportadores actuales.
- **Versión del exportador.** `exporter_version` es la versión propia del exportador NKP: una constante del módulo del exportador que se incrementa solo cuando cambia su salida. No se usa la versión de `ragstudio` (`pyproject.toml`), para que un cambio ajeno en la aplicación no altere los paquetes.
- **Determinismo.** `manifest.created_at` = `snapshot.created_at`. La garantía es la siguiente: la misma instantánea, con el mismo `tenant`, el mismo contrato y la misma `exporter_version`, procesada por la implementación canónica, **produce el mismo** `content_digest`. Si cambia cualquiera de esos cuatro elementos, el digesto puede cambiar.

### Hito 01c — Contrato vendorizado y prueba de conformidad

Los artefactos se copian al repositorio de código, por ejemplo en `contracts/nexom_knowledge_package/v1_0_0/`, en dos grupos:

| Grupo | Artefactos | Control |
|---|---|---|
| Normativos | 14 schemas, `id_scheme.py`, `validate_knowledge_package.py` | Una prueba compara sus SHA-256 con la sección 4.1 de la Declaración y falla ante cualquier diferencia |
| Reproducibilidad y QA | `requirements.lock.txt` (`c9f8bb79…594d`), `validator/test_negative_cases.py` (`b0eeec1e…380a`) | Hash registrado. Pueden evolucionar sin cambiar la versión del contrato, pero cada cambio se registra |

`id_scheme.py` es el módulo compartido por el exportador y las pruebas. **Las fórmulas normativas** definidas en `id_scheme.py` **no se reimplementan.** La generación de `package_id` (sección 5) es una convención no normativa propia del exportador RAG Studio: se implementa una sola vez, en el exportador, y está cubierta por pruebas deterministas.

### Hito 01d — Pruebas y verificación

Ver sección 7.

## 5. Mapeo archivo por archivo (perfil CORE)

| Archivo del paquete | Origen (en el `project.db` de la instantánea) | Notas de mapeo |
|---|---|---|
| `manifest.json` | `project`, registro `ProjectSnapshot`, conteos recalculados | `package_id`: ver abajo; `knowledge_base_id` desde `project`; `knowledge_version` = `str(snapshot.version)`; `snapshot_id` = `snapshot.id`; `project_id_origin` = `project.id`; `project_revision`: ver abajo; `parent_package_id` = `null`; `exporter_version` = versión del exportador NKP; `tenant` = parámetro obligatorio; `profile` = `CORE`; `capabilities`/`omissions` con las mismas reglas bidireccionales del validador |
| `sources.jsonl` | `source` | `logical_id` desde `lineage_id`; `id` = `portable_source_id(lineage_id, version_key)`; `supersedes_source_id` remapeado a id portable; `location` y `original_copy_path` no se exportan; campos `original_*` según las reglas CORE |
| `chunks.jsonl` | `chunk` | `id` = `portable_chunk_id`; `previous/next/parent_chunk_id` remapeados; `inherited_metadata` con claves `field_definition_id` (URN); `pipeline_version` no se exporta |
| `source_metadata.jsonl` | `source_metadata_value` | Los valores de campos `multiple` se guardan como códigos separados por barra vertical (docstring de `SourceMetadataValue`; `set_source_metadata_value.py:49-50`) y se exportan como lista. `field_id` local se exporta como `field_definition_id` (URN) más `field_code` |
| `metadata_schema.json` | `metadata_schema`, `field_definition`, `catalog`, `catalog_entry` | `parent_entry_id` (id interno) se traduce a `parent_entry_code`; `schema_version_local` = `MetadataSchema.version` |
| `evidence.jsonl` | Proyección de `chunk` + `source` | Sin tabla nueva. `citation_anchor` / `derived`; `source_id` siempre igual al del chunk (regla rc3.2) |
| `media.jsonl` | Chunks con `image_relative_path` | Solo descriptor. `included_in_package = false` en CORE; checksum del binario real de la instantánea |
| `conversational_bundle.json` | `intent`, `guardrail_rule`, `conversational_variable`, `channeling_scheme` | Referencias por nombre o código convertidas a URNs. Una referencia rota hace fallar la exportación con un error claro |
| `embedding_spaces.json` | `index_info` + perfil de embeddings | `dimensions` desde `index_info`. Si la instantánea no tiene índice, la exportación se rechaza. `distance_metric = cosine`; `normalization = unknown_not_verified` salvo que se verifique (M-2 de la Declaración) |
| `indexes.json` | `index_info` + colecciones conocidas | `covers_chunk_types` refleja la cobertura textual real |
| `access_hierarchy.json` | `AccessLevel` y `_ACCESS_LEVEL_RANK` (`domain/documents/entities.py:60-68`) | Se genera desde el rango del dominio, no a mano |
| `acceptance_cases.jsonl` | — | **Vacío en RAG-INC-01** (decisión INC01-D5). Se comprobó que el validador acepta un archivo vacío con `counts.acceptance_cases = 0` (0 errores) |
| `checksums.json` | Calculado | RFC 8785 vía `id_scheme.py` |
| sidecar `*.content.sha256` | Calculado | Fuera del paquete. Sin firma productiva (Declaración F-1) |

**Campos del manifiesto que el contrato exige y el mapeo anterior no definía.** Se fijan aquí para que no se inventen durante la implementación:

- `package_id` = `urn:nexom:package:` seguido de los primeros 32 caracteres hexadecimales del SHA-256 de la serialización RFC 8785 de este objeto:

  ```
  {"knowledge_base_id": ..., "snapshot_id": ..., "tenant": ...,
   "schema_version": ..., "exporter_version": ...}
  ```

  Cumple el patrón `^urn:nexom:package:[0-9a-f]{32}$` de `manifest.schema.json` y es determinista con las mismas entradas que la garantía de determinismo del hito 01b. Es una convención de RAG Studio, no una fórmula del contrato: no se añade a `id_scheme.py`, que es normativo.
- `project_revision` = `project.updated_at` del `project.db` de la instantánea, en ISO 8601 UTC con offset. RAG Studio no tiene hoy un campo de revisión explícito. Es un dato descriptivo, no un detector de cambios: la instantánea se identifica por `snapshot_id` y `knowledge_version`.
- `parent_package_id` = `null` en RAG-INC-01, como permite el schema. Construir una cadena real de paquetes exige guardar un historial de exportaciones y queda para un incremento posterior.

Se verificó que los valores de enumeración de RAG Studio coinciden con los del contrato: `SourceType` (13), `SourceValidationStatus` (6), `AccessLevel` (4), tipos de chunk y acciones de guardrail. No hace falta tabla de traducción.

## 6. Fuera de alcance

- Interfaz de usuario. Esto incluye el selector de `identity_policy` al importar y el botón de exportación. Solo se entregan casos de uso y servicios.
- Reemplazo o sobrescritura en `ImportProject`, y eliminación definitiva de proyectos con fuentes (INC01-D7).
- Encadenamiento de paquetes mediante `parent_package_id` y el historial de exportaciones que requiere.
- Perfiles `AUDIT` y `PREINDEXED`, vectores portables, binarios originales e imágenes dentro del paquete.
- Firma productiva y almacén de confianza (Declaración F-1).
- Casos de aceptación derivados de `TestCase`. Van en un incremento posterior con su propia especificación, porque `TestCase` (`domain/quality/entities.py:68`) no tiene `user_access_level` ni chunks esperados.
- Cambiar el modelo de embeddings de RAG Studio, o incorporar `min_score` o cualquier umbral de relevancia (Informe §5 y §10).
- Modificar los cuatro exportadores existentes, Qdrant embebido o el formato `.agentproj`.
- Compensar en RAG Studio comportamientos propios del Runtime (Informe §14 y §17).

## 7. Criterios de aceptación

1. **Conformidad.** Los paquetes exportados desde (a) un proyecto de prueba construido en la suite y (b) una instantánea del proyecto UDL, usada localmente (INC01-D6), pasan el validador `v1.0.0` con 0 errores, como directorio y como ZIP.
2. **Contrato intacto.** La prueba de hashes del hito 01c pasa.
3. **Continuidad de identidad.**
   - Registrar una versión nueva de una fuente conserva `logical_id` y cambia `source.id`.
   - Exportar dos veces la misma instantánea con el mismo `tenant`, contrato y `exporter_version` da el mismo `content_digest` y el mismo `package_id`.
   - En dos instantáneas sucesivas se conservan `logical_id` y los `source.id`/`chunk.id` cuyo contenido no cambió.
4. **Migración por etapas.**
   - `0021` se aplica sobre copias de `project.db` reales, incluida la de UDL.
   - Al terminar, ninguna fila tiene identidad nula y cada cadena comparte un único `lineage_id`.
   - Un ciclo provocado en una copia hace abortar la migración sin dejar cambios parciales.
   - `downgrade()` se niega a ejecutarse sin la bandera de anulación de pruebas.
5. **Política de identidades.** Hay una prueba por cada fila de la tabla de políticas del hito 01a:
   - `preserve` sin colisión conserva ambas identidades;
   - `preserve` con colisión, contra un proyecto activo y contra uno archivado, lanza `KnowledgeBaseIdentityCollisionError` sin modificar datos;
   - `fork`, con y sin colisión, regenera las identidades y mantiene la estructura de supersesión;
   - `ImportProject` sin `identity_policy` falla antes de tocar datos.
6. **Atomicidad de la detección.**
   - Dos importaciones concurrentes con la misma identidad y `preserve` dan exactamente una importación exitosa y una colisión.
   - Un `project.db` instalado ilegible hace abortar la importación (fail-closed).
   - Si otro proceso retiene el bloqueo más allá del tiempo máximo, la importación falla con `ImportLockTimeoutError` sin modificar datos.
   - Si un proceso que retiene el bloqueo termina de forma abrupta, una importación posterior obtiene el bloqueo sin intervención manual.
   - Cada colisión queda en el log técnico.
7. **Aislamiento e invariantes de la instantánea.**
   - Modificar el proyecto vivo después de publicar la instantánea no cambia el paquete exportado.
   - Un registro `ProjectSnapshot` con `project_id` o `snapshot_dir` que no coincide con la instantánea hace abortar la exportación.
   - Una prueba de arquitectura verifica que el repositorio de instantáneas no expone operaciones de actualización.
8. **Tenant.** Exportar sin `tenant` o con `tenant` vacío falla.
9. **Neutralidad.** El paquete se lee solo con `json`/`zipfile` de la biblioteca estándar, sin `sqlalchemy` ni `qdrant_client`.
10. **Negativas del productor.** Estos casos producen errores de exportación explícitos, no paquetes inválidos: una fuente con `supersedes_source_id` roto, una referencia conversacional rota, una instantánea sin índice, un `value_code` que contenga una barra vertical y un chunk no imagen con texto vacío. En todos los casos el error se produce antes de escribir el paquete: no queda ningún paquete parcial.
11. **Regresión.** La suite existente de RAG Studio, `ruff` y `mypy` quedan sin cambios de resultado, y la suite negativa del contrato sigue en 20/20.
12. **Interoperabilidad de humo.** El Runtime importa un paquete real exportado por RAG-INC-01 y reporta integridad válida. No es un nuevo AR-INC-00.
13. **Manifiesto completo.** `package_id`, `project_revision` y `parent_package_id` siguen exactamente las reglas de la sección 5, y `exporter_version` es la constante del exportador NKP.

## 8. Riesgos y cómo se tratan

| Id | Riesgo | Tratamiento |
|---|---|---|
| INC01-R1 | `version_key` usa `updated_at` cuando la fuente no tiene `content_hash`, así que editar el título o el nivel de acceso cambiaría `source.id` | Medir en UDL cuántas fuentes no tienen `content_hash` y documentar el efecto. Cambiar la fórmula sería un cambio de contrato |
| INC01-R2 | Fechas sin zona horaria, que `format: date-time` rechaza | Mitigado: las columnas usan `UTCDateTime` desde la Ronda 83 (`infrastructure/database/utc_datetime.py`). Una prueba falla si alguna fecha exportada no lleva offset |
| INC01-R3 | Multivalor guardado con barra vertical y contrato con lista | Se exporta separando por la barra vertical. Una prueba rechaza cualquier `value_code` que la contenga |
| INC01-R4 | Relleno sobre datos históricos inconsistentes | Relleno por etapas con verificación de ciclos y transacción única; ensayo previo sobre copias |
| INC01-R5 | `dimensions` se infiere al cargar el modelo | Se toma de `index_info` de la instantánea. Sin índice, la exportación se rechaza |
| INC01-R6 | Chunks no imagen con texto vacío violarían `chunk.schema.json` | Medirlo en UDL antes de iniciar 01b. Si existe algún chunk no imagen con texto vacío, la exportación aborta con un error explícito y no genera ningún paquete. La fuente deberá corregirse o reprocesarse; si el caso es legítimo, se elevará una propuesta de cambio contractual. RAG-INC-01 no excluye chunks silenciosamente |
| INC01-R7 | Identidades regeneradas por un downgrade seguido de un upgrade | `downgrade()` protegido y restauración solo desde respaldo |
| INC01-R8 | Dos bases activas con el mismo `knowledge_base_id` | Detección de colisión obligatoria que incluye proyectos archivados, y política explícita `preserve`/`fork` |
| INC01-R9 | Carrera entre dos importaciones concurrentes | Bloqueo real del sistema operativo sobre la secuencia comprobar → importar → registrar, con tiempo máximo y liberación automática; segunda comprobación antes de confirmar; prueba de concurrencia |
| INC01-R10 | Un `project.db` instalado ilegible oculta una colisión | Fail-closed: la importación aborta |
| INC01-R11 | Confundir integridad con autenticidad | Sección 9: completar 01d no habilita entregas productivas autenticadas mientras F-1 esté pendiente |

## 9. Estado productivo al completar RAG-INC-01

Completar 01d **autoriza el exportador y la interoperabilidad técnica**. **No convierte los paquetes en entregas autenticadas para producción.** El paquete lleva checksums y `content_digest`, pero quien lo modifique puede recalcularlos: eso da integridad técnica, no autenticidad del productor. La aceptación automática de paquetes en producción queda condicionada a F-1 (esquema de confianza y firma conjunto, Declaración sección 3.2).

## 10. Entregables

- Código de los hitos 01a–01c y pruebas del hito 01d.
- Migración `0021` con su procedimiento de restauración desde respaldo, que sustituye al downgrade.
- Un informe de verificación por hito para la puerta de NEXOM. El de 01d incluye los resultados del validador y el `content_digest` de los paquetes de prueba y UDL, el resultado de las suites y de `ruff`/`mypy`, los datos medidos para INC01-R1 y el resultado de la importación de humo. La medición de INC01-R6 (chunks no imagen con texto vacío en UDL) se entrega antes, en el informe de la puerta de 01a, porque condiciona el inicio de 01b.
- Entrada en la bitácora del proyecto y actualización del README técnico.
- Sin cambios en la UI ni en el Manual de Usuario.

## 11. Decisiones adoptadas

Recomendadas por NEXOM el 23-09-2026. Entran en vigor con la firma.

| Id | Decisión | Resolución |
|---|---|---|
| INC01-D1 | Organización | Un solo RAG-INC-01 con cuatro hitos y puerta de aprobación de NEXOM al cierre de cada uno |
| INC01-D2 | Migración `0021` | Autorizada, por etapas, con downgrade protegido; no se libera en producción antes de completar 01d |
| INC01-D3 | Importación y duplicación | `identity_policy` obligatoria. `preserve` aborta con un error tipado si hay colisión; `fork` siempre regenera; sin política se aborta. Detección por escaneo local con bloqueo real del sistema operativo, tiempo máximo y fail-closed. Sin reemplazo ni sobrescritura (tablas y condiciones del hito 01a; INC01-D7) |
| INC01-D4 | `tenant` | Parámetro obligatorio de exportación; falla si falta |
| INC01-D5 | Acceptance cases en exportaciones reales | Archivo vacío en RAG-INC-01; derivación desde `TestCase` en un incremento posterior |
| INC01-D6 | Proyecto UDL | Uso local controlado: los datos no salen del equipo y solo se reporta el resultado |
| INC01-D7 | Restaurar con `preserve` en una instalación que ya contiene esa base | **No autorizado en RAG-INC-01.** NEXOM no autoriza en este incremento la eliminación definitiva de proyectos con fuentes ni un modo de reemplazo o sobrescritura. La restauración con `preserve` queda limitada a instalaciones donde el `knowledge_base_id` no exista; cuando ya exista, se usa `fork`. Una futura capacidad de reemplazo se diseñará como un incremento independiente con respaldo verificado, confirmación explícita, eliminación integral (fuentes, metadatos, instantáneas, respaldos, índices Qdrant, originales, medios y registros globales), auditoría y pruebas de recuperación ante fallo parcial |
| INC01-D8 | Campos del manifiesto `package_id`, `project_revision`, `parent_package_id` y `exporter_version` | Reglas de la sección 5 y del hito 01b |

## 12. Relación con las recomendaciones del Informe (§15)

| Recomendación del Informe | Cómo la atiende RAG-INC-01 |
|---|---|
| 1. Contrato versionado y validable | Hito 01c: artefactos normativos vendorizados con hashes verificados |
| 2. `checksums` y `content_digest` independientes | `id_scheme.py` y sidecar externo |
| 3. IDs auto-verificables y relaciones explícitas | Hito 01a y mapeo de la sección 5 |
| 4. Jerarquía de acceso y denegación por defecto explícitas | `access_hierarchy.json` generado desde el dominio |
| 5. `covers_chunk_types` como contrato de indexabilidad | `indexes.json` con la cobertura real |
| 6. Descripción completa del espacio de embeddings | `embedding_spaces.json` desde `index_info`; INC01-R5 |
| 7. Acceptance cases portables | Incremento posterior (INC01-D5) |
| 8. Intents y guardrails como datos | Bundle serializado desde entidades |
| 9. Esquema de confianza productivo conjunto | Diferido (Declaración F-1) |

## 13. Firmas

| Rol | Nombre | Firma | Fecha |
|---|---|---|---|
| NEXOM — responsable del contrato | | | |
| RAG Studio — responsable técnico | | | |
