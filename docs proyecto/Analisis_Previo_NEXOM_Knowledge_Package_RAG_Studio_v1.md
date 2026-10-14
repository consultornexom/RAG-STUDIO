# Análisis previo — NEXOM Knowledge Package en RAG STUDIO

**Documento:** Análisis técnico previo (respuesta al "Primer paso solicitado al desarrollador", sección 11 de la propuesta NEXOM)
**Versión:** 1.0
**Fecha:** 21 de septiembre de 2026
**Basado en:** *Propuesta de ajuste arquitectónico de RAG Studio — Exportación estándar del NEXOM Knowledge Package para interoperabilidad con Agent Runtime 1.0* (NEXOM, v1.0, 21-09-2026)
**Alcance de esta etapa:** análisis puro sobre el código real de RAG STUDIO. **No se modificó ningún archivo de código**, no se migraron embeddings, no se descargaron modelos, no se tocó Qdrant interno ni `project.db`, no se cambió ninguna interfaz de usuario y no se realizó commit, push, tag ni release — en cumplimiento estricto de la sección 13 ("Restricciones de esta etapa") de la propuesta.

Toda afirmación de este documento está respaldada por lectura directa del código fuente real de RAG STUDIO (rutas y líneas exactas citadas en cada sección), no por inferencia sobre lo que "debería" existir.

---

## 1. Arquitectura actual relevante

RAG STUDIO sigue arquitectura hexagonal (ADR-001): `domain/` (entidades y puertos, sin dependencias externas), `application/` (casos de uso, orquesta dominio + puertos), `infrastructure/` (adaptadores concretos: SQLAlchemy, Qdrant, sistema de archivos, proveedores de embeddings), `ui/` (Qt, solo llama a `application/`), `interfaces/api/` (Runtime HTTP del widget conversacional).

Persistencia: dos bases SQLite independientes. `application.db` (global, `GlobalBase`) para catálogo de proyectos e instalación; `project.db` (una por proyecto, `ProjectBase`) para todo el conocimiento de ese proyecto — fuentes, chunks, metadata, diseño conversacional, calidad, liberaciones. Ambas se versionan con Alembic (`migrations/global/`, `migrations/project/`), nunca con `Base.metadata.create_all()`.

Índice vectorial: un adaptador único, `QdrantLocalVectorStore` (`infrastructure/vectorstores/qdrant_local_store.py`), que envuelve `qdrant_client` en modo local/embebido (`QdrantClient(path=...)`, sin servidor), persistido en `projects/<id>/indexes/qdrant/`.

Embeddings: un único proveedor de producción, `fastembed` (`infrastructure/embeddings/fastembed_provider.py`), sin llamadas a API externas.

Exportación/entregable: **contrario a lo que sugiere su nombre, el paquete `infrastructure/exporters/` existe pero está vacío** (`infrastructure/exporters/__init__.py` es solo un docstring de una línea). Toda la lógica real de empaquetado vive hoy en `infrastructure/filesystem/` (cuatro exportadores distintos, ver sección 2) y en `domain/release/` + `domain/projects/` (entidades y puertos). Esto es en sí mismo un hallazgo relevante para el ajuste propuesto: el directorio que un desarrollador nuevo esperaría usar para el nuevo `KnowledgePackageExporter` ya existe como paquete Python vacío, listo para recibir la implementación nueva sin necesidad de crear una carpeta.

## 2. Flujo actual de generación/exportación

Existen **cuatro exportadores/empaquetadores independientes**, sin relación entre sí, cada uno con su propio puerto y adaptador:

| Exportador | Puerto (`domain/`) | Adaptador (`infrastructure/filesystem/`) | Disparado desde |
|---|---|---|---|
| Instantánea (snapshot) | `ProjectSnapshotPublisher` (`domain/release/ports.py:58`) | `FilesystemProjectSnapshotPublisher` (`project_snapshot_publisher.py:29`) | "Publicar instantánea…" (`ui/release/panel.py:127`) |
| Paquete de entrega al cliente | `DeploymentPackager` (`domain/release/ports.py:71`) | `FilesystemDeploymentPackager` (`deployment_packager.py:39`) | "Exportar paquete de entrega al cliente…" (`ui/release/panel.py:140`) |
| Entregables de gobernanza (Etapa 7) | `ReleasePackager` (`domain/release/ports.py:29`) | `FilesystemReleasePackager` (`release_packager.py:34`) | "Exportar entregables…" (`ui/release/panel.py:105`) |
| Paquete de proyecto `.agentproj` | `ProjectPackager` (`domain/projects/ports.py`) | `FilesystemProjectPackager` (`packager.py`) | `ExportProject` (`application/projects/commands/export_project.py`) |

**Instantánea (`ProjectSnapshot`, `domain/release/entities.py:99`):** copia de solo lectura, versionada (`snapshots/<project_id>/v<n>/`). El publicador fuerza `PRAGMA wal_checkpoint(TRUNCATE)` sobre `project.db` y ejecuta `shutil.copytree(project_dir, destination)` — **copia binaria completa y literal** de `project.db`, del índice `indexes/qdrant/` y de todas las subcarpetas del proyecto (`sources/`, `chunks/`, `pipelines/`, `rules/`, `tests/`, `runs/`, `evidence/`, `reports/`, `manifest.json`). Ninguna transformación a formato intermedio.

**Paquete de entrega al cliente (`DeploymentPackage`, `domain/release/entities.py:134`):** `entrega-<project_id>-v<version>.zip` con `manifest.json`, `INFORME_ENTREGA.md`, `GUIA_DESPLIEGUE.md`, `CONTRATO_INTEGRACION.md`, `.env.example`, `widget-embed.html`, más una carpeta `instantanea/` que es la copia recursiva completa del snapshot — **`project.db` viaja literalmente dentro del zip** como `instantanea/project.db`, confirmado byte a byte por `tests/integration/test_deployment_package_end_to_end.py` (líneas 59-66 y 127-132). Es, de los cuatro, el que más se acerca al propósito de NEXOM (transportar conocimiento operable hacia un runtime externo), pero en su forma actual está lejos de ser neutral.

**Entregables de gobernanza:** `release-<id>.zip` con `manifest.json`, `dictamen.txt`, `checklist.json` y un JSON por cada uno de los ocho entregables formales (evidencia de proceso, ya en JSON neutral) — explícitamente **no incluye el índice de búsqueda** (documentado en el tooltip de `ui/release/panel.py:115`). No es un candidato a paquete de conocimiento, pero es un precedente útil de "export ya neutral" dentro del propio código.

**`.agentproj` (`FilesystemProjectPackager`):** el más cercano a "verificable" — genera un `PackageManifest` (`domain/projects/packaging.py:26-65`) con SHA-256 por archivo y huella del propio manifiesto — pero sigue empaquetando `project.db` e `indexes/qdrant/` en crudo (`packager.py:90`, `project_dir.rglob("*")`), y su reimportación exige reabrir ese mismo `project.db` con SQLAlchemy. Verificable en integridad de bytes, pero no neutral: solo otra instalación de RAG STUDIO puede leerlo.

**Conclusión de esta sección:** hoy no existe ningún exportador que produzca un formato realmente neutral y portable (JSON/JSONL + manifiesto, sin SQLite propio ni Qdrant embebido). Los cuatro caminos existentes o bien empaquetan los formatos internos tal cual, o bien (el de gobernanza) exportan datos neutrales pero deliberadamente sin el conocimiento operable (fuentes/chunks/índice).

## 3. Estructura del entregable actual

El entregable que más se parece al objetivo de NEXOM —`entrega-<project_id>-v<version>.zip`— tiene hoy esta estructura real (confirmada por `deployment_packager.py` y el test de integración):

```
entrega-<project_id>-v<n>.zip
├── manifest.json
├── INFORME_ENTREGA.md
├── GUIA_DESPLIEGUE.md
├── CONTRATO_INTEGRACION.md
├── .env.example
├── widget-embed.html
└── instantanea/
    ├── project.db                    (SQLite completo, esquema interno RAG STUDIO)
    ├── manifest.json                 (manifiesto de proyecto, formato propio)
    ├── sources/{original,extracted,normalized}/
    ├── chunks/
    ├── indexes/qdrant/                (SQLite + pickle de qdrant_client, formato de terceros)
    ├── pipelines/  rules/  tests/  runs/  evidence/  reports/
```

`evidence/` existe como carpeta reservada en el layout (`infrastructure/filesystem/paths.py:28`) pero, según la búsqueda realizada en este análisis, **ningún módulo escribe hoy en ella** — no hay una entidad `EvidenceRecord` poblándola (ver sección 5).

## 4. Mapa RAG Studio → NEXOM Knowledge Package

Usando los componentes mínimos que NEXOM define en su Tabla 11:

| Componente NEXOM | Origen real en RAG STUDIO | Disponibilidad |
|---|---|---|
| `KnowledgePackageManifest` | `PackageManifest` (`domain/projects/packaging.py:26`, ya con `format_version`, SHA-256) + `IndexInfo` + datos del proyecto (`Project`) | Precedente fuerte, campos a completar |
| `SourceRecord` | `Source` (`domain/documents/entities.py:137`) / tabla `source` | Casi 1:1, con exclusiones (sección 5) |
| `ChunkRecord` | `Chunk` (`domain/ingestion/entities.py:217`) / tabla `chunk` | Casi 1:1, con exclusiones (sección 5) |
| `EvidenceRecord` | **No existe como entidad propia.** Se puede derivar de `Chunk` (`source_id`, `page_start/page_end`, `section_title`) + `Source` (`source_authority`, `valid_from/valid_to`) | A construir por proyección, no por nueva tabla |
| `EmbeddingDescriptor` | `IndexInfo` (`domain/rag/entities.py:106`: `embedding_provider`, `embedding_model`, `dimensions`) | Parcial — faltan `distance_metric`, `revision`, `normalization`, `preprocessing`, `dtype`, `fingerprint` |
| `IndexDescriptor` | `IndexInfo` (parcial) + constantes hoy fijas en `qdrant_local_store.py` (`Distance.COSINE`, nombre de colección) | A formalizar, hoy disperso entre dominio y adaptador |
| `ConversationalArtifactBundle` | `Intent`, `GuardrailRule`, `ConversationalVariable`, `ChannelingScheme` (`domain/conversational/entities.py`) | Datos completos y ya neutrales (JSON en columnas), falta el agregador/query de exportación |

## 5. Campos disponibles y campos faltantes

**`SourceRecord` → `Source`** (`domain/documents/entities.py`, tabla `source`): `id`, `project_id`, `title`, `source_type` (13 valores), `location`, `owner_area`, `access_level`, `language`, `version` (documentado como no usado), `content_hash`, `validation_status`, `valid_from`, `valid_to`, `source_authority`, `supersedes_source_id`, `original_copy_path`, `document_type_code`, `created_at`, `updated_at`.
Portables sin cambio: `title`, `source_type`, `owner_area`, `access_level`, `language`, `content_hash`, `validation_status`, `valid_from`, `valid_to`, `source_authority`, `document_type_code`, timestamps.
A excluir o transformar: `id`/`project_id` (locales, deben tratarse como identificadores de correlación, no claves universales), `location` (ruta/URL local, potencialmente inaccesible fuera de la máquina origen), `original_copy_path` (ruta relativa dentro del proyecto local — para portabilidad real hay que empaquetar el binario junto con el registro, no solo la ruta), `supersedes_source_id` (requiere mapeo si se exportan varias fuentes a la vez).

**`ChunkRecord` → `Chunk`** (`domain/ingestion/entities.py`, tabla `chunk`): `id`, `project_id`, `source_id`, `chunk_index`, `text`, `token_count`, `section_title`, `page_start`, `page_end`, `chunk_type` (9 valores), `previous_chunk_id`/`next_chunk_id`/`parent_chunk_id`, `structured_content`, `semantic_summary`, `inherited_metadata`, `pipeline_version`, `created_at`, `image_relative_path`.
Portables sin cambio: `chunk_index`, `text`, `token_count`, `section_title`, `page_start`, `page_end`, `chunk_type`, `structured_content`, `semantic_summary`, `inherited_metadata`, `created_at`.
A excluir o transformar: `id`/`project_id`/`source_id` (locales, requieren re-mapeo — el propio código documenta que "los identificadores nunca se prometen estables entre corridas"), `image_relative_path` (requiere empaquetar el binario de imagen real), `pipeline_version` (trazabilidad técnica interna, no contenido). Ninguna de las relaciones `previous/next/parent_chunk_id` tiene FK real en SQLite — son convención aplicativa, lo cual simplifica remapearlas al exportar.

**Metadata** (cinco tablas: `MetadataSchema`, `FieldDefinition`, `Catalog`, `CatalogEntry`, `SourceMetadataValue`, más historial `MetadataValueChange`): no hay columnas fijas tipo "programa" o "campus" — todo campo de negocio vive como `FieldDefinition` (con `catalog_id` cuando el tipo lo exige) y su valor vigente como `SourceMetadataValue`. Para que el paquete sea auto-descriptivo fuera de la instalación origen, **hay que exportar el `FieldDefinition` completo (con su `Catalog`/`CatalogEntry` si aplica), no solo el valor** — de lo contrario el Runtime recibiría pares clave-valor sin saber qué significan ni cómo validarlos. Esto confirma directamente el requisito de la propuesta (sección 5): "los metadatos específicos del cliente deben viajar como metadata configurada por proyecto, no como atributos permanentes del Core".

**`ConversationalArtifactBundle`** (`domain/conversational/entities.py`): `Intent` (`positive_examples`, `negative_examples`, `required_variables`, `optional_variables`, `clarifying_questions` como `dict[str,str]`, `response_rule`, `resolution_mode`, `risk_level`), `GuardrailRule` (`conditions: list[RuleCondition]`, `action`, `priority`), `ConversationalVariable` y `ChannelingScheme`. Ya se serializan como JSON en columnas `String`/`Text` — son, de las siete entidades del contrato NEXOM, las que menos transformación necesitan. Faltante real: no existe hoy ningún query/comando que agregue las cuatro entidades de un proyecto en un solo bundle exportable (`application/conversational/` no tiene ningún `export_*`), y los vínculos entre ellas son por nombre/código como texto libre, sin `ForeignKey` — el bundle exportado debe decidir si preserva esa misma laxitud o la valida al construirse.

**`EmbeddingDescriptor`**: `IndexInfo` (`domain/rag/entities.py:106`) ya aporta `embedding_provider` (constante `"fastembed"`), `embedding_model` (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` por defecto, o `intfloat/multilingual-e5-large` si se activa el perfil asimétrico) y `dimensions` — pero este último **no es una constante declarada**, se infiere en runtime invocando el modelo (`fastembed_provider.py:139-140`). Faltan por completo: `distance_metric` (hoy hardcodeado como `Distance.COSINE` dentro del adaptador Qdrant, nunca expuesto en el dominio), `revision`, `normalization`, `preprocessing` (existe un equivalente parcial: los prefijos `query:`/`passage:` del perfil asimétrico, pero no está modelado como dato serializable), `dtype` y `fingerprint` (no existe ningún mecanismo de huella de configuración de embeddings en todo el repositorio).

**`IndexDescriptor`**: mismo punto de partida que `EmbeddingDescriptor` (`IndexInfo`), pero sin nombre de colección ni tipo de índice como campos de dominio — ambos están fijos hoy en el adaptador (`"chunks"`/`"chunks_imagenes"`, `Distance.COSINE`).

## 6. Tratamiento actual del índice y de pickle

El adaptador `QdrantLocalVectorStore` respeta bien la frontera hexagonal: el dominio nunca ve un `PointStruct` de Qdrant, solo `VectorPoint`/`VectorSearchHit` (`domain/rag/entities.py`). La traducción ocurre en un único punto (`upsert()`, `qdrant_local_store.py:178`).

**Confirmado por búsqueda exhaustiva: no hay ni un solo `import pickle` en código propio de RAG STUDIO** (domain/application/infrastructure/ui/interfaces). Todo el pickle real vive dentro de la dependencia de terceros `qdrant_client`, en `local/persistence.py` de la librería instalada: serializa cada punto completo (`models.PointStruct`) con `pickle.dumps()` y lo guarda como `BLOB` en una tabla SQLite propia del SDK (`storage.sqlite`). RAG STUDIO no controla ni documenta ese formato — lo hereda de la librería, versión a versión (`pyproject.toml` fija `qdrant-client>=1.19` porque versiones anteriores ni siquiera pueden deserializar un índice escrito por 1.19+).

Esto confirma exactamente la premisa de la propuesta: el pickle que hay que eliminar del contrato de interoperabilidad no está en el código de RAG STUDIO, sino en el formato de persistencia interno de Qdrant embebido que el paquete actual arrastra tal cual al exportar. La solución no es "quitar un `pickle.dumps()`" de RAG STUDIO (no existe ninguno propio), sino **no incluir `indexes/qdrant/` en el nuevo contrato de exportación** y sustituirlo por una serialización propia y documentada de los vectores (ver sección 7).

## 7. Estrategia propuesta de exportación

Un nuevo exportador (`KnowledgePackageExporter`, a ubicar en el paquete ya existente y vacío `infrastructure/exporters/`) que **lea desde los repositorios de dominio existentes** (no desde archivos), y escriba un directorio/zip con esta forma:

```
nexom_knowledge_package/
├── manifest.json          (KnowledgePackageManifest: package_id, schema_version,
│                            knowledge_version, created_at, source_system, tenant,
│                            counts, checksums)
├── sources.jsonl           (un SourceRecord neutral por línea)
├── chunks.jsonl             (un ChunkRecord neutral por línea)
├── evidence.jsonl           (EvidenceRecord derivado de chunk+source al exportar)
├── metadata_schema.json     (FieldDefinition + Catalog/CatalogEntry completos)
├── conversational_bundle.json  (Intent + GuardrailRule + ConversationalVariable + ChannelingScheme)
├── embedding_descriptor.json
├── index_descriptor.json
├── vectors.jsonl (opcional)  (id, vector, formato documentado — nunca pickle/PointStruct)
└── checksums.json           (SHA-256 por archivo + del manifest + del paquete completo)
```

Cada `*Record` se construye leyendo las entidades de dominio ya existentes (`Source`, `Chunk`, `FieldDefinition`, `Intent`, etc.) a través de sus repositorios actuales — no hace falta abrir `project.db` directamente ni tocar el esquema SQLAlchemy interno. El exportador es una nueva capa de lectura sobre datos ya existentes, exactamente como plantea la sección 9 de la propuesta NEXOM ("no es una reescritura de RAG STUDIO").

`export_format` adicional (mencionado en la propuesta, sección 9): se propone extender `ExportProject`/`application/projects/` con un parámetro de formato (`agentproj` actual vs. `nexom_knowledge_package` nuevo), o bien exponer el nuevo exportador como una acción independiente en `application/release/` junto a los otros tres empaquetadores ya existentes — a decidir en el primer incremento (RAG-INC-01, sección 10), ya que ambos encajan con el patrón de puertos/adaptadores ya establecido.

## 8. Compatibilidad hacia atrás

Ningún cambio de esta propuesta requiere modificar `project.db`, Qdrant embebido ni ninguno de los cuatro exportadores actuales — se añaden, no se sustituyen. La propia propuesta (sección 4, "Fuera del alcance inicial") ya descarta eliminar Qdrant/`project.db`, y el código confirma que es viable: el nuevo exportador leería por los mismos puertos de repositorio que ya usa el resto de la aplicación (`ProjectRepository`, `SourceRepository`, `ChunkRepository`, `IntentRepository`, etc.), sin ningún cambio de esquema.

Riesgo de compatibilidad a vigilar: `dimensions` de `IndexInfo` se infiere en runtime, no es una constante — si el `EmbeddingDescriptor` exportado debe ser fiable sin reabrir el modelo, hay que decidir si se calcula en el momento de exportar (requiere tener el modelo cargado) o se lee de `IndexInfo` ya persistido (más barato, pero depende de que el proyecto ya haya sido indexado).

## 9. Riesgos

- **`distance_metric` fijo, no versionado**: hoy es una constante de código (`Distance.COSINE`), no un dato de dominio. Si en el futuro se soporta otra métrica, todos los `IndexInfo`/paquetes ya exportados quedarán con una suposición implícita incorrecta salvo que se agregue el campo antes de generalizar.
- **Ausencia de `fingerprint`**: sin un hash de configuración de embeddings, dos exportaciones con el mismo `embedding_model` pero distinta `revision`/`normalization` (si en el futuro se soportaran) serían indistinguibles para el Runtime — riesgo de reutilización incorrecta de vectores.
- **Rutas/binarios de origen (`original_copy_path`, `image_relative_path`)**: si el paquete no empaqueta también los archivos binarios reales, cualquier consumidor pierde acceso a los originales — hay que decidir explícitamente si el contrato incluye binarios o solo referencias.
- **`evidence/` sin poblar hoy**: al no existir un `EvidenceRecord` real, la primera versión del `evidence.jsonl` se construirá por derivación (chunk+source), no por lectura directa de una tabla — cualquier cambio futuro a esa lógica de derivación debe mantenerse consistente entre exportaciones.
- **Metadata sin catálogo exportado se vuelve opaca**: si se exporta solo `SourceMetadataValue.value` sin el `FieldDefinition`/`CatalogEntry` correspondiente, el Runtime recibe códigos sin significado (ej. un `value_code` de catálogo sin su `label`).
- **Identificadores locales no estables entre corridas**: documentado explícitamente en el propio código de `FragmentSource` — cualquier consumidor externo no debe asumir que un `chunk_id` se mantiene igual entre dos exportaciones sucesivas del mismo proyecto.
- **Perfil de embeddings por proceso, no por proyecto** (ADR-002, sección 5): si dos proyectos exportados desde la misma instalación usaran perfiles distintos, hoy exigiría procesos de runtime de RAG STUDIO separados — relevante solo si NEXOM planea exportar proyectos con perfiles de embeddings distintos desde una misma instalación concurrente.

## 10. Incrementos sugeridos

1. **RAG-INC-01 — Manifest + SourceRecord + ChunkRecord.** Nuevo módulo en `infrastructure/exporters/` que lee `Source`/`Chunk` vía los repositorios existentes y escribe `manifest.json` + `sources.jsonl` + `chunks.jsonl` + `checksums.json`. Sin metadata, sin conversacional, sin embeddings todavía — valida el patrón de lectura-y-serialización antes de escalarlo.
2. **RAG-INC-02 — Metadata neutral.** Agrega `metadata_schema.json` (FieldDefinition + Catalog/CatalogEntry) y resuelve los valores de `SourceMetadataValue` a pares legibles (código + etiqueta).
3. **RAG-INC-03 — EvidenceRecord derivado + ConversationalArtifactBundle.** Construye `evidence.jsonl` por proyección de chunk+source (sin nueva tabla), y agrega el primer query agregador en `application/conversational/` que exporte Intent+GuardrailRule+ConversationalVariable+ChannelingScheme de un proyecto.
4. **RAG-INC-04 — EmbeddingDescriptor + IndexDescriptor formales.** Extiende `IndexInfo` (o crea una nueva entidad de dominio) con `distance_metric`, `revision`, `normalization`, `preprocessing`, `dtype`, `fingerprint` — primero como campos calculados/derivados al exportar, sin tocar el esquema de `project.db` si es posible mantenerlos fuera de SQLAlchemy en esta etapa.
5. **RAG-INC-05 — Vectores portables (opcional) + empaquetado físico.** `vectors.jsonl` (id, vector, sin `PointStruct`/pickle) leído vía el puerto `VectorStore` ya existente (`search`/lectura completa de una colección), más el zip/directorio final con checksums de integridad — nunca copia directa de `indexes/qdrant/`.
6. **RAG-INC-06 — `export_format` y pruebas de compatibilidad.** Expone la opción `nexom_knowledge_package` junto a los formatos existentes, y valida extremo a extremo que un paquete generado sea legible sin `qdrant_client` ni acceso a `project.db`.

## 11. Archivos existentes que habría que modificar

- `infrastructure/exporters/__init__.py` — dejará de estar vacío; aquí vive el nuevo exportador.
- `application/release/service.py` y/o `application/projects/commands/export_project.py` — exponer el nuevo formato de exportación junto a los ya existentes (`agentproj`, `release`, `deployment_package`).
- `domain/rag/entities.py` (`IndexInfo`) — candidato a extenderse con `distance_metric` y, si se decide persistir, `fingerprint`.
- `ui/release/panel.py` (o `ui/projects/`, según dónde se decida exponer la acción) — un nuevo botón/acción, si NEXOM quiere que sea accesible desde la interfaz en esta primera fase (la propuesta no lo exige explícitamente para el análisis, pero sí lo anticipa como parte del "flujo futuro de integración").
- `pyproject.toml` — si el nuevo exportador requiere alguna dependencia nueva para serializar vectores (p. ej. si se elige un formato distinto de JSONL).

## 12. Archivos nuevos que habría que crear

- `infrastructure/exporters/nexom_knowledge_package.py` (o similar) — el exportador propiamente dicho.
- `domain/exporters/` (nuevo subpaquete, si se decide modelar `KnowledgePackageManifest`, `EmbeddingDescriptor`, `IndexDescriptor`, `EvidenceRecord` como entidades de dominio propias en vez de dicts serializados directamente por el exportador) con sus entidades Pydantic.
- `application/conversational/queries/export_conversational_bundle.py` (o ubicación equivalente) — el agregador de Intent+GuardrailRule+ConversationalVariable+ChannelingScheme que hoy no existe.
- `application/exporters/` o `application/release/commands/export_knowledge_package.py` — caso de uso que orquesta el exportador nuevo.
- `tests/unit/infrastructure/test_nexom_knowledge_package_exporter.py` y `tests/integration/test_nexom_knowledge_package_export_end_to_end.py` (ver sección 13).

## 13. Propuesta de pruebas

- **Unitarias** por cada `*Record` neutral: dado un `Source`/`Chunk`/`Intent`/etc. de dominio con valores conocidos, verificar que el registro exportado contiene exactamente los campos portables esperados y omite los locales (rutas absolutas, ids no remapeados).
- **Integración, round-trip de checksums**: exportar un proyecto de prueba real (usando el mismo patrón ya establecido en `tests/integration/test_quality_repositories.py`/`test_runtime_repositories.py` de escribir fixtures directo por el repositorio real) y verificar que `checksums.json` coincide con un recálculo independiente de SHA-256 sobre cada archivo del paquete.
- **Integración, ausencia de dependencias prohibidas**: un test que abra el paquete exportado usando solo `json`/`zipfile` de la librería estándar (sin importar `qdrant_client` ni `sqlalchemy`) y confirme que es completamente legible — esto es, en la práctica, la prueba más directa de que se cumplió el objetivo de neutralidad de NEXOM.
- **Integración, compatibilidad de `EmbeddingDescriptor`**: exportar dos proyectos con distinto perfil de embeddings (`simetrico` vs. `asimetrico_e5_large`, ya soportados hoy) y verificar que los descriptores resultantes son distinguibles entre sí (dimensiones, modelo).
- **Integración, extremo a extremo con `evidence.jsonl` derivado**: verificar que cada evidencia exportada referencia un `source_id`/`chunk_id` presentes en el mismo paquete (integridad referencial dentro del propio export, ya que no hay FK real en `project.db`).
- **Regresión de no-modificación**: correr la suite existente completa (unitaria/smoke/integración) sin cambios de resultado, confirmando que el nuevo exportador no alteró ningún flujo existente — mismo criterio de verificación ya establecido en este proyecto para cada ronda de cambios.

---

## Respuesta a los criterios de éxito (sección 16 de la propuesta)

**1. Cómo exportar un NEXOM Knowledge Package sin romper RAG Studio.** Como una nueva capa de lectura en `infrastructure/exporters/` (hoy vacío) que consume los repositorios de dominio ya existentes — sin tocar `project.db`, Qdrant embebido, ni ninguno de los cuatro exportadores actuales. Ver secciones 7 y 10.

**2. Qué datos actuales pueden reutilizarse.** Prácticamente todo el contenido: `Source`, `Chunk`, `FieldDefinition`/`Catalog`/`CatalogEntry`/`SourceMetadataValue`, `Intent`/`GuardrailRule`/`ConversationalVariable`/`ChannelingScheme`, y `IndexInfo` como base de `EmbeddingDescriptor`. Ver sección 5.

**3. Qué datos nuevos deben generarse.** `EvidenceRecord` (por derivación de chunk+source, no nueva tabla), y los campos que faltan en `EmbeddingDescriptor`/`IndexDescriptor` (`distance_metric`, `revision`, `normalization`, `preprocessing`, `dtype`, `fingerprint`). Ver secciones 5 y 6.

**4. Cómo eliminar pickle del contrato de interoperabilidad.** No hay pickle propio que eliminar del código de RAG STUDIO (confirmado por búsqueda exhaustiva); el pickle real pertenece al formato interno de `qdrant_client`. La eliminación consiste en **no incluir `indexes/qdrant/` en el nuevo contrato** y sustituirlo por un `vectors.jsonl` opcional, propio y documentado. Ver sección 6.

**5. Cómo mantener compatibilidad hacia atrás.** El nuevo formato se añade como opción (`export_format`) junto a los cuatro exportadores ya existentes, sin modificar `project.db` ni el esquema Alembic — ningún proyecto existente requiere migración para poder exportarse en el nuevo formato. Ver sección 8.

**6. Cómo declarar correctamente el espacio de embeddings.** Extender `IndexInfo` (o una entidad nueva) con los campos faltantes listados en la sección 5, calculados en el momento de exportar a partir del `EmbeddingProvider` real (`fastembed_provider.py`), en vez de asumir constantes fijas como hace hoy el adaptador Qdrant con `Distance.COSINE`.

**7. Cuánto trabajo se requiere y cuáles son los principales riesgos.** Seis incrementos (sección 10), de complejidad creciente; el más simple (RAG-INC-01) es una serialización directa de datos ya modelados como Pydantic, el más delicado (RAG-INC-04) requiere decidir dónde vive `distance_metric`/`fingerprint` sin forzar una migración de esquema innecesaria. Riesgos principales listados en la sección 9 (fingerprint ausente, binarios de origen, identificadores no estables, metadata sin catálogo).

**8. En cuántos incrementos conviene implementar el ajuste.** Seis (RAG-INC-01 a RAG-INC-06, sección 10), cada uno entregable y verificable de forma independiente, siguiendo la misma disciplina de verificación (ruff/mypy/pytest + documentación) ya establecida en este proyecto.

---

*Siguiente paso, según la propia propuesta (sección 15): este documento queda como referencia de diseño para autorizar, en una etapa posterior y bajo instrucción explícita, los incrementos de implementación (RAG-INC-01 en adelante). No se ha modificado ni se modificará código de RAG STUDIO como parte de este análisis.*
