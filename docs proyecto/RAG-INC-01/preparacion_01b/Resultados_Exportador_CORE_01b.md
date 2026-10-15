# RAG-INC-01b · Incremento 1 — Exportador CORE del NEXOM Knowledge Package v1.0.0

Fecha: 2026-10-15 · Rama `rag-inc-01/01b`, creada desde `c775c03` · **Sin commit, sin tag, sin push.** No incluye 01c ni 01d.

## 1. Diseño

| Capa | Archivo | Contenido |
|---|---|---|
| Dominio | `domain/knowledge_package/` | `SnapshotDescriptor` (DTO inmutable), `KnowledgePackageExportResult`, errores tipados y puerto `KnowledgePackageExporter` |
| Aplicación | `application/knowledge_package/commands/export_knowledge_package.py` | `ExportKnowledgePackage.execute(project_id, snapshot_id, tenant, output_dir)` y la forma funcional `export_knowledge_package(...)` |
| Infra | `infrastructure/exporters/nexom_knowledge_package.py` | `NexomKnowledgePackageExporter` |
| Infra | `infrastructure/exporters/nexom_kp_v1_0_0/id_scheme.py` | Copia **byte a byte** del `id_scheme.py` firmado (`559847df…a8ba8`), con prueba de hash |
| Puerto/repo | `ProjectSnapshotRepository.get(project_id, snapshot_id)` | Única operación nueva; el repositorio sigue siendo de solo inserción (prueba de arquitectura) |
| App | `AppContext.knowledge_package_export` | Conectado en `bootstrap`. Sin interfaz de usuario |
| Dependencia | `rfc8785==0.1.4` | `pyproject.toml` y `requirements.txt`; la usa el `id_scheme.py` firmado. Es la misma versión fijada en el `requirements.lock.txt` del contrato |

**Flujo de la exportación:**

1. `tenant` obligatorio (se recortan espacios; nunca hay valor por defecto).
2. El registro `ProjectSnapshot` se carga una sola vez.
3. La carpeta registrada y su `project.db` deben existir.
4. Se **copia** el `project.db` (y su `-wal`, si existe) a un temporal y se lee solo la copia. La instantánea no se abre: no se crean `-shm`/`-wal` en ella.
5. Compuertas (sección 3).
6. Construcción de los registros.
7. Staging en `output_dir/.nkp-staging-<uuid>/`: `checksums.json`, `content_digest`, ZIP determinista y relectura del ZIP comparando cada entrada.
8. Publicación sin sobrescribir:
   - primero el ZIP, luego el sidecar `<paquete>.content.sha256`;
   - se usa `os.link`, y si el sistema de archivos no tiene enlaces duros, se reserva el nombre con `open(x)` y se hace `os.replace`;
   - ante cualquier fallo se retira lo publicado y siempre se borra el staging.
9. Si ya existe alguno de los dos nombres finales, `OutputExistsError` sin tocar nada.

**Salida:**
- `nexom-knowledge-package-<32 hex del package_id>.zip`: 13 archivos internos, 11 de datos más `manifest.json` y `checksums.json`.
- `….content.sha256`: sidecar externo, fuera del paquete. Sin firma (F-1 pendiente).

## 2. Artefactos y reglas de identidad (mapeo del Alcance §5)

| Archivo | Origen y reglas |
|---|---|
| `manifest.json` | `package_id` según la convención del Alcance: 32 hex del SHA-256 RFC 8785 de `{kb, snapshot_id, tenant, schema_version, exporter_version}`. Además: `schema_version` = `1.0.0`; `exporter_version` = `1.0.0` (constante propia); `knowledge_version` = `str(snapshot.version)`; `created_at` = `snapshot.created_at`; `project_revision` = `project.updated_at`; `project_id_origin` = `project.id`; `parent_package_id` = null; `profile` = CORE; `counts` con los 7 conteos que verifica el validador. `capabilities` y `omissions` siguen las reglas bidireccionales |
| `sources.jsonl` | `logical_id` = `urn:nexom:source-logical:<lineage_id>`; `id` = `portable_source_id(lineage_id, source_version_key(...))`. `supersedes_source_id` se convierte a id portable. Campos `original_*` según CORE. No se exportan `location` ni `original_copy_path` |
| `chunks.jsonl` | `id` = `portable_chunk_id`. Enlaces previo, siguiente y padre convertidos a ids portables. `inherited_metadata` con claves `urn:nexom:field:…`. Imagen: `image_relative_path` = `assets/images/<archivo>` |
| `source_metadata.jsonl` | Campos `multiple` (`a|b`) → lista. `field_definition_id` (URN) más `field_code`. Valores de catálogo verificados |
| `metadata_schema.json` | Esquema activo de mayor versión. `parent_entry_id` → `parent_entry_code`. Sin esquema activo: `schema_version_local` = 1 y listas vacías (ver riesgo 5) |
| `evidence.jsonl` | Un `citation_anchor`/`derived` por cada chunk indexable (ni `padre` ni `imagen`). `source_id` = el del chunk |
| `media.jsonl` | Chunks de imagen: solo descriptor (`included_in_package=false`), con el checksum del binario real de la instantánea |
| `conversational_bundle.json` | Intenciones, reglas, variables y canalizaciones con URN. Los códigos de variable y canalización se convierten a URN; una referencia rota bloquea |
| `embedding_spaces.json` | Desde `index_info`. `normalization` = `unknown_not_verified`; `preprocessing` según el modelo conocido (e5 → `query: `/`passage: `; desconocido → null); `dtype` float32; `fingerprint` null |
| `indexes.json` | `flat_cosine` (Qdrant local), `points_count` de `index_info`, `covers_chunk_types` = tipos presentes salvo `padre`/`imagen` |
| `access_hierarchy.json` | Orden generado desde `_ACCESS_LEVEL_RANK` del dominio y `rule` constante del contrato |
| `acceptance_cases.jsonl` | Vacío (decisión INC01-D5 del Alcance) |
| `checksums.json` | SHA-256 de cada archivo canónico RFC 8785 vía `id_scheme.py`. No se incluye a sí mismo |

No se generan identidades durante la exportación: `knowledge_base_id` y `lineage_id` se leen de la instantánea. Todo lo demás se deriva con las fórmulas firmadas.

**`origin_package_id`:** el contrato v1.0.0 **no lo define**. La procedencia que sí define es:
- `manifest.project_id_origin` (trazabilidad, nunca en fórmulas);
- `manifest.parent_package_id` (null en RAG-INC-01);
- `manifest.snapshot_id`;
- `sources[].origin_id`.

Se implementó exactamente eso y no se agregó `origin_package_id`.

## 3. Compuertas previas (cualquiera aborta sin escribir en `output_dir`)

| Compuerta | Error |
|---|---|
| `tenant` vacío | `MissingTenantError` |
| Instantánea no registrada (o de otro proyecto) | `SnapshotNotFoundError` |
| Registrada, pero sin carpeta o sin `project.db` (caso histórico de UDL) | `SnapshotDirectoryMissingError` |
| `project.db` de otro proyecto, o esquema anterior a 0021 | `SnapshotInconsistentError` |
| `knowledge_base_id` o `lineage_id` ausente, inválido o en mayúsculas | `MissingIdentityError` |
| Fuente basada en archivo con `content_hash` NULL o `''` | `MissingContentHashError`: *"La instantánea contiene fuentes sin huella de contenido. Complete las huellas … y publique una instantánea nueva antes de exportar."* |
| Sin `index_info`; chunk no imagen con texto vacío; `source_authority` < 1; `structured_content` que no es objeto | `ContractConstraintError` |
| Referencias internas rotas (supersesión, campo, catálogo, padre de catálogo, variable, canalización, enlace de chunk, binario de imagen) | `BrokenReferenceError` |
| Id portable duplicado (fuentes, chunks, evidencias, media, campos, catálogos, intenciones, reglas, variables, canalizaciones, valores de metadatos) | `PortableIdentityCollisionError`, con las entidades implicadas. No se resuelve automáticamente |
| Nombre final ya existente | `OutputExistsError` |

## 4. Reproducibilidad

- **Byte a byte:** la misma instantánea con el mismo tenant, contrato y `EXPORTER_VERSION` produce los mismos 13 archivos, el mismo `checksums.json`, `content_digest` y `package_id`, y **el mismo ZIP**. Se logra así:
  - `created_at` viene de la instantánea;
  - registros ordenados por id;
  - JSON canónico RFC 8785;
  - entradas del ZIP ordenadas, con fecha fija 1980-01-01, `create_system=3`, permisos 0644 y DEFLATE de nivel 6.
- **Variable legítimamente:**
  - otro tenant da otro `package_id`, con las mismas identidades lógicas;
  - otra instantánea da otro `snapshot_id`, `knowledge_version`, `created_at` y `project_revision`;
  - los `source.id` se conservan si el contenido no cambió (verificado entre dos instantáneas con un cambio de estado de validación de por medio).
- **Límite:** el SHA del ZIP depende de la implementación de zlib. `content_digest`, que es el digesto contractual, no depende de la compresión.

## 5. Validador firmado v1.0.0 (prueba externa, sin modificarlo)

| Paquete | Resultado |
|---|---|
| Proyecto sintético completo: cadena de versiones, confidencial, API sin archivo, imagen, catálogo jerárquico, campo múltiple, metadatos heredados, tabla estructurada, padre, intención, regla, variable, canalización. Como ZIP, como directorio y con `--content-digest-file` | **ERRORES: 0** (158 OK) |
| Proyecto mínimo | **ERRORES: 0** |
| Prueba controlada con copia real A, tras el relleno de huellas (**no es 01d**) | **ERRORES: 0** (72 OK) |
| Prueba controlada con copia real C, tras el relleno (**no es 01d**) | **ERRORES: 0** (768 OK; 25 fuentes, 76 chunks) |
| Prueba controlada con copia real B | **Bloqueada por la compuerta** (riesgo 4) |
| C importada **sin** relleno | `MissingContentHashError` con 25 fuentes; salida vacía |

En A y C: dos exportaciones dan ZIP idéntico y la instantánea queda intacta (huella de contenido igual antes y después). Las copias se hicieron en temporales, a partir de orígenes verificados por hash, y los originales no se tocaron.

## 6. Pruebas nuevas (37)

- **`tests/integration/test_nkp_core_exporter.py` (29):**
  - exportación mínima y completa, validadas como ZIP, directorio y sidecar;
  - proyecto sin esquema de metadatos → `schema_version_local` = 1, paquete válido (decisión NEXOM, §9);
  - estructura del ZIP y checksums;
  - manifest e identidades;
  - metadata, embeddings, acceso, bundle, aceptación, media y evidencia;
  - repetición byte a byte;
  - dos instantáneas con ids estables;
  - instantánea no modificada;
  - tenant obligatorio;
  - instantánea inexistente; registrada sin carpeta o sin `project.db`;
  - `content_hash` NULL o vacío; fuente sin archivo que no requiere huella;
  - `knowledge_base_id` inválido (3 casos);
  - instantánea anterior a 0021; `project.db` de otro proyecto;
  - `lineage_id` inválido (2);
  - `source.id` y `chunk.id` duplicados;
  - referencias rotas, texto vacío y falta de índice;
  - salida existente;
  - fallo en el ZIP, en la verificación y al publicar el sidecar, sin restos, con un reintento exitoso después.
- **`tests/unit/application/test_export_knowledge_package.py` (8):**
  - tenant (3);
  - instantánea inexistente o de otro proyecto;
  - DTO inmutable;
  - repositorio de solo inserción;
  - `id_scheme` copiado idéntico al firmado;
  - `package_id` determinista.
- **Apoyo:** `tests/integration/nkp_export_fixtures.py`.

## 7. Regresión (línea base tras el relleno de huellas: 944/9 · 479/14 · 15/2 · ruff limpio · mypy 22/7)

| Suite | Resultado |
|---|---|
| Unitarias | 952 passed, 9 skipped (+8) |
| Integración (17 tandas) | 507 passed, 14 skipped (+28); más la prueba explícita de §9: 508 |
| Smoke | 15 passed, 2 skipped |
| ruff (código y pruebas) | All checks passed. `ruff check .`: los mismos 14 avisos históricos de `docs proyecto/` |
| mypy | 22 errores en los mismos 7 archivos |

## 8. Riesgos y puntos para NEXOM

1. **`id_scheme.py` copiado en 01b.**
   - El Alcance exige que el exportador use la implementación de referencia, sin reimplementar las fórmulas.
   - Pero la vendorización formal es del hito 01c.
   - Se copió **solo** `id_scheme.py`, byte a byte y con prueba de hash, en `infrastructure/exporters/nexom_kp_v1_0_0/`.
   - Los 14 schemas, el validador y la prueba de conformidad quedan para 01c.
   - **Requiere confirmación de NEXOM.**
2. **Dependencia nueva `rfc8785==0.1.4`**, necesaria para la canonicalización. `jsonschema` no se añade: el exportador no valida contra los schemas internamente. Eso queda para 01c; hoy la validación es la del validador firmado en las pruebas.
3. **Registros como diccionarios.** El Alcance menciona "entidades inmutables de los registros" en el dominio. Aquí los registros se construyen como diccionarios en infraestructura, con el contrato como referencia. El dominio solo contiene el DTO de la instantánea, el resultado y los errores.
4. **El corpus B no es exportable sin corregir datos.** Tiene 3 intenciones con nombre duplicado (6 registros, creados dos veces con 4 minutos de diferencia). `intent.id = uuid5(kb, name)` colisiona y la compuerta bloquea, como pide el punto 4. No se tocaron datos. **Antes de 01d, NEXOM debe decidir** si se depuran los duplicados en la fuente. El mismo riesgo aplica a reglas, catálogos, variables y canalizaciones con nombre o código repetido.
5. **`schema_version_local` = 1 cuando no hay esquema de metadatos activo** (B y C no lo tienen). El contrato exige un entero ≥ 1. Se usa 1 porque es como RAG Studio representa un esquema vacío recién creado (corpus A). **A confirmar.**
6. **Interpretaciones de mapeo, a confirmar:**
   - evidencia solo para chunks indexables;
   - `covers_chunk_types` y `structured_retrieval` derivados de los chunks presentes;
   - `preprocessing` solo para los dos modelos conocidos;
   - no se declara un espacio de embeddings de imagen (CORE no transporta binarios; `image_retrieval=false`).
7. **Bloqueos esperables con datos reales:**
   - valores de metadatos de campos que ya no están en el esquema activo;
   - chunks no imagen con texto vacío (INC01-R6 midió 0);
   - instantáneas anteriores a 0021 o al relleno de huellas.

   En todos los casos hay que publicar una instantánea nueva tras corregir.
8. **Ruta de la instantánea.** `snapshot_dir` es la ruta absoluta registrada. Si la instalación se movió (por ejemplo, la de Mac), la carpeta no se encontrará y la exportación falla con un error claro. No se intenta adivinar otra ruta. D no se probó aquí.
9. **Publicación de dos archivos.** Hay una ventana mínima en la que el ZIP final existe sin su sidecar. Si publicar el sidecar falla, el ZIP se retira. Los consumidores deben exigir el sidecar.

## 9. Decisiones NEXOM previas al commit (2026-10-15)

1. **`id_scheme.py` anticipado en 01b: APROBADO.**
   - Debe seguir idéntico byte a byte a la referencia firmada, con su prueba de hash (`test_id_scheme_vendorizado_identico_al_firmado`).
   - No se modifican, reinterpretan ni reimplementan sus fórmulas.
   - Se aprueba también `rfc8785==0.1.4`.
   - La vendorización formal completa (14 schemas, validador y pruebas de conformidad) **sigue perteneciendo a 01c**.
2. **Corpus B: no bloquea este commit.**
   - La colisión de `intent.id` (3 nombres duplicados, 6 registros) es real, y que el exportador la bloquee es lo correcto.
   - No se modifican el exportador, la fórmula ni los datos.
   - Se registra como **saneamiento de datos requerido antes de 01d**; la forma de depurarlo se decidirá por separado.
3. **`schema_version_local = 1` sin esquema de metadatos: APROBADO.**
   - Interpretación NEXOM: la versión 1 es el estado inicial del esquema local, aunque esté vacío. Nunca 0 ni null.
   - Prueba explícita: `test_proyecto_sin_esquema_de_metadatos_usa_version_local_1`, que da un paquete válido con ERRORES: 0.
4. **`origin_package_id`** no se agrega: no forma parte del contrato v1.0.0. Se mantiene solo la procedencia contractual: `project_id_origin`, `parent_package_id`, `snapshot_id` y `source.origin_id`.

**Interpretaciones para revisión formal en 01c (sin cambios en este commit):**
- evidencia solo para chunks indexables;
- `covers_chunk_types` derivado de los chunks presentes;
- prefijos de embeddings solo para los modelos conocidos;
- sin espacio de embeddings para imágenes;
- registros contractuales construidos como diccionarios en infraestructura.

**Riesgos aceptados para este commit (no se corrigen aquí):**
1. B requiere sanear sus intenciones antes de 01d.
2. Valores de metadatos cuyo campo ya no existe pueden bloquear datos reales.
3. Las instantáneas con rutas históricas que ya no existen fallan de forma explícita.
4. D todavía no se ha probado con el exportador.
5. Hay una ventana mínima entre la publicación del ZIP y la del sidecar, mitigada retirando el ZIP si falla el sidecar.
6. El SHA del ZIP puede variar entre implementaciones o versiones de zlib; `content_digest` permanece estable.
