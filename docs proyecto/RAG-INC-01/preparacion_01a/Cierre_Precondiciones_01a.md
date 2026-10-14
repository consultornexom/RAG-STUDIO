# RAG-INC-01 — Cierre de precondiciones del hito 01a

**Fecha:** 2026-10-14
**Autorización vigente (NEXOM, 2026-10-14):** solo el cierre de precondiciones. La migración `0021` y los cambios productivos de 01a **no están autorizados**.
**Estado del archivo:** creado después del commit de línea base; queda **sin commit** en la rama `rag-inc-01/01a` hasta nueva autorización.

> **Actualización 2026-10-14 (decisiones NEXOM):** D-1 **RESUELTA** (opción a: UI preserve/fork autorizada en 01a); D-2 **DIFERIDA A 01b**; D-3 **CERRADA** (corpus D congelado). Estado: **READY FOR 0021**, pendiente de autorización expresa. Ver sección 8.

## 1. Smoke PASS

Registrado en `NEXOM_Knowledge_Package_v1/ejemplo_v1.0.0/Registro_Humo_Runtime_v1.0.0.md` (SHA-256 `1b27c395a1ce36873413ab11d66855c24618f00a36123025df432bf258331a6e`) y en la sección 5 del Informe de Conformidad.

- Runtime commit: `5db676e0e292fb09c08bb9258436829ceb28ec3a`.
- Paquete: `nexom-knowledge-package-demo-v1.0.0.zip`, SHA-256 `5dff57bb…cbff`, verificado localmente.
- `schema_version`: `1.0.0`.
- Resultado: PASS / COMPATIBLE.

No se modificó el contrato firmado.

**Pendiente:** archivar el informe técnico completo del Runtime cuando se reciba.

## 2. Control de versiones: revisión previa

### 2.1 Contenido revisado (por contenido, no solo por nombre)

| Elemento | Qué contiene | Decisión |
|---|---|---|
| `Licenciatura/` | 25 PDF escaneados (sin capa de texto) de planes de estudio oficiales de la Universidad (por ejemplo `der.pdf`: Licenciatura en Derecho, plan de estudios por cuatrimestre). Las pruebas solo lo mencionan en comentarios; ningún test lo lee. | **Excluir.** Es documentación del cliente, no código ni documentación del proyecto. |
| `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/` | Dos `.agentproj` reales (11.3 MB y 60.7 MB) con `project.db`, índices y originales del cliente. Son los corpus B y C congelados. | **Excluir.** Son datos del cliente y su integridad se controla por hash, no por Git. |
| `docs proyecto/RAG4_Fase-1_Benchmark/prototipo/trabajo/` (≈ 418 MB) | Copias de PDF del cliente, proyectos de trabajo, bases SQLite y una caché de modelo de 235 MB. | **Excluir.** Los scripts del prototipo (fuera de `trabajo/`) sí se versionan. |
| `Actualizacion_2026-09-0*/` (3 carpetas, ≈ 18 MB) | Copias históricas del árbol (código y documentos de septiembre). | **Excluir.** Son respaldos; quedan en el respaldo fechado. |
| `data/` (2.5 GB) | Instalación real: `application.db`, `runtime.db`, proyectos (incluye el corpus A), logs, modelos. | **Excluir.** |
| `modelos_ragstudio/` (241 MB), `build/`, `dist/`, `*.egg-info` | Modelos y artefactos de construcción. | **Excluir.** |
| `.coverage`, `.coverage.claude.*`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `__pycache__/` | Cachés y reportes de herramientas. | **Excluir.** |
| Bases `*.db`, `*.sqlite`, auxiliares `-wal`/`-shm` | Solo aparecen en las carpetas excluidas y en `.mypy_cache`. No hay fixtures de pruebas con bases. | **Excluir** (en cualquier ubicación). |
| Índices Qdrant | Solo dentro de `data/` y de carpetas excluidas. | Excluidos por su ubicación. |
| Tres `.docx` de hallazgos en la raíz (`contrato de integracion.docx`, `inconsistencia_en_contrato.docx`, `Revisar identidad de package…docx`) | Entradas recibidas de NEXOM para las Rondas 94–95. | **Excluir** como temporales. Si deben conservarse, moverlos a `docs proyecto/hallazgos/`. |
| `RAG_STUDIO_Manual_de_Usuario.docx/.pdf`, `RAG_STUDIO_Reporte_Ronda93_Caso_Failed.docx/.pdf` | Documentación entregable. | **Versionar.** |
| `_respaldos_rag_inc_01/` | Respaldo fechado de esta preparación. | **Excluir.** |

### 2.2 Secretos

- Búsqueda por nombre: los únicos `.pem` son tres claves **públicas DEMO** del contrato, que se versionan por excepción explícita. No hay `.env`, `.key`, `.p12` ni `.pfx`.
- Búsqueda por contenido en los 710 archivos que entran al commit: claves privadas, tokens (`sk-`, `ghp_`, `AKIA`, `xox*`), contraseñas y claves de API con valor. Solo dos coincidencias, ambas falsos positivos: el texto del propio procedimiento ("BEGIN PRIVATE KEY") y una cita histórica del valor de ejemplo `cambia-esto-por-una-clave-secreta` en `Validacion_observaciones_RAG_STUDIO.md`.
- Los cuatro ZIP versionados del contrato no contienen claves privadas.
- **Resultado: sin bloqueos.**

### 2.3 `.gitignore` definitivo

Parte de `gitignore_propuesto.txt` y agrega las exclusiones de la tabla 2.1 y `htmlcov/`, `*.sqlite3`, `*.p12`, `*.pfx`. El `.gitignore` anterior era un subconjunto: excluía `data/` pero tenía el error `.agentproj` en lugar de `*.agentproj`.

**Riesgos:**
- Excluir `Licenciatura/` deja dos pruebas de OCR documentadas con esos PDF sin reproducibilidad desde Git (hoy se omiten si falta el archivo).
- Excluir `trabajo/` deja fuera los JSON de resultados del benchmark RAG4. Están en el respaldo fechado.

## 3. Respaldo fechado y control de versiones

| Elemento | Valor |
|---|---|
| Respaldo fechado | `_respaldos_rag_inc_01/RAG_STUDIO_arbol_pre-baseline_2026-10-14.tar.gz`, 339 618 836 B, SHA-256 `eee246f16d8b91117033a22414654ba51903c3e53bd4093f9f56fcd36a63078a`, `gzip -t` OK. Árbol completo sin `data/`, `.venv/`, `modelos_ragstudio/`, la caché de modelo del benchmark ni cachés de herramientas. Incluye `Licenciatura/`, `PRUEBAS…/` y `Actualizacion_*`. |
| Lista exacta de archivos del commit | `_respaldos_rag_inc_01/baseline_archivos_commit_2026-10-14.txt` (710 archivos, 18.9 MB) |
| `git init` | Sí: local, sin remoto (`git remote` vacío). Configuración local `core.createObject=rename`, necesaria en este disco FUSE; el modo por defecto con enlaces duros dejaba objetos ilegibles. `core.fileMode=false`, `core.autocrlf=false`. |
| Commit de línea base | `74b132ae872a3b1ec16a2b93b2c3bb69c956caa6` ("RAG-INC-01: línea base previa al hito 01a") |
| Etiqueta | `rag-inc-01-baseline` (anotada) |
| Rama de trabajo | `rag-inc-01/01a` (activa). También existe `master` en el mismo commit. |
| `git fsck` | Sin errores |
| Push | No |

## 4. Línea base formal (sobre `74b132a`)

| Herramienta | Versión | Resultado |
|---|---|---|
| pytest (unitarias) | 9.1.1 | 925 passed, 6 skipped |
| pytest (integración, 8 tandas) | 9.1.1 | 423 passed, 13 skipped |
| pytest (smoke) | 9.1.1 | 15 passed, 2 skipped |
| ruff | 0.16.1 | All checks passed |
| mypy | 2.3.1 | 22 errores en 7 archivos: `infrastructure/database/runtime_repositories.py` 12, `application/rag/queries/hybrid_search.py` 2, `application/rag/service.py` 2, `application/runtime/commands/issue_widget_token.py` 2, `infrastructure/extraction/ocr_engine.py` 2, `application/ingestion/commands/fragment_source.py` 1, `infrastructure/database/migrations.py` 1 |

Gate de 01a: no aumentar errores de mypy ni cambiar resultados de pytest y ruff respecto de esta línea base. Los 22 errores de mypy no se corrigen en 01a.

## 5. Migraciones

`migrations/project/versions/` termina en `0020_chunk_image_relative_path.py`. `0021` no existe. No cambió durante este cierre.

## 6. Corpus

| Id | Estado | Evidencia (2026-10-14) |
|---|---|---|
| A (canario, instalado) | Íntegro | `project.db` `4b4bac22…e925`; inventario de 21 archivos idéntico al del 24-09; `project.db-wal` de 0 bytes |
| B (secundario) | Íntegro | `e7d81510…4ebe` |
| C (principal) | Íntegro | `09157313…4eaa7` |
| D (AGENTE UDL `6073eda1-268d-48bd-8257-e6d3fef4f981`, adicional) | **Congelado (2026-10-14)** | `project.db` `ca45dd6f96b50fd336951f8176559cb13af2e098e579b85a5a2eefbf342d354a` (1 654 784 B). Detalle en la sección 8.3 |

**Procedimiento para congelar D (lo ejecuta el operador o RAG Studio con acceso a esa instalación):**

1. Cerrar RAG Studio y cualquier runtime que lo use.
2. Desde RAG Studio: Proyectos → seleccionar AGENTE UDL → Respaldar. Registrar que el checkpoint WAL es una escritura de consolidación.
3. O copiar la carpeta `projects/6073eda1-…/` después de confirmar `project.db-wal` de 0 bytes.
4. Calcular el SHA-256 del `.agentproj` o del inventario de la carpeta.
5. Llevar a este documento:
   - ruta y `project.db` con su SHA-256;
   - versión de Alembic (leída con `mode=ro&immutable=1` sobre la copia);
   - número de fuentes y de chunks;
   - instantáneas existentes, con su `snapshot_identity.json`;
   - `lotes_importados.jsonl`.

## 7. Addendum técnico

`Addendum_Tecnico_Revalidacion_01a.md`, incluido en el commit de línea base. Resultado: **REQUIERE DECISIÓN NEXOM** (D-1: importación desde la UI frente a `identity_policy` obligatorio y "sin cambios en la UI").

## 8. Decisiones NEXOM del 2026-10-14 y estado posterior

### 8.1 D-1 — RESUELTA (opción a)

01a incluye la adaptación mínima de la UI de importación: importación normal → `preserve`; "Importar como copia" → `fork`; ante `KnowledgeBaseIdentityCollisionError`, la UI ofrece continuar como copia (`fork`). No cambia el contrato ni las reglas. Addendum actualizado.

### 8.2 D-2 — DIFERIDA A 01b

Durante 01a no se cambia `grouping_key`, no se modifica la integración con Testing Agent y el paquete de entrega del widget no sustituye al NEXOM Knowledge Package.

### 8.3 D-3 — CERRADA: corpus D congelado

Congelamiento ejecutado por NEXOM en la instalación real de macOS con `congelar_corpus_D.py`. RAG Studio no abrió ni modificó el proyecto original.

| Dato | Valor |
|---|---|
| Proyecto | AGENTE UDL |
| `project_id` | `6073eda1-268d-48bd-8257-e6d3fef4f981` |
| Instalación | `/Users/alejandromontesmoreno/Documents/sistemas/udl/version_beta/20261011/RAG_STUDIO_3/data_AGENTE_UDL` |
| `project.db` SHA-256 | `ca45dd6f96b50fd336951f8176559cb13af2e098e579b85a5a2eefbf342d354a` |
| `project.db` bytes | 1 654 784 |
| WAL original | inexistente |
| Alembic | `0020` |
| Fuentes | 35 |
| Chunks | 668 |
| Instantáneas en disco | v2, v3, v4, v5 |
| Instantáneas registradas en la BD | v1, v2, v3, v4, v5 |
| Instantánea más reciente | v5 |
| `lotes_importados.jsonl` | no existe |
| `integrity_check` | ok |
| `evidencia.tar.gz` SHA-256 | `95516301a5cf7f49461a94b44683c6799fa88a7958b12bf2c91919ccca331897` |
| `informe_corpus_D.json` SHA-256 | `c57f8d8c6651ac9283caed9d58e48527d457c474a8967907e2501713e8eb2242` |

**Observaciones** (solo se documentan; no se corrigen en esta etapa, por decisión de NEXOM):

1. **v1 está registrada en la BD pero no existe físicamente** en la instalación. El registro histórico apunta a una carpeta ausente.
   - Para 01a no tiene efecto: la migración `0021` no lee instantáneas.
   - A tener en cuenta en 01b: el exportador recibe `snapshot_id` explícito y debe fallar con un error claro si la carpeta no existe.
2. **`lotes_importados.jsonl` no existe.** Las fuentes de este corpus se registraron sin pasar por "Importar carpeta de RAG CONTENT…" después de la Ronda 92, o antes de ella. No hay procedencia de lotes que conservar. No afecta a `0021`.

**Evidencia:** conviene archivar en esta carpeta una copia de `informe_corpus_D.json`, para contrastar el hash `c57f8d8c…2242`. El `evidencia.tar.gz` se conserva fuera de Git, en el equipo de origen.

**Uso en 01a:** igual que A, el corpus D solo se mide y migra sobre una copia restaurada desde `evidencia.tar.gz`, verificada por hash. Nunca sobre la instalación original.

### 8.4 Estado del árbol de trabajo (`git status`, rama `rag-inc-01/01a`, sin commits nuevos)

- `M .gitignore`: modificado a las 12:45 fuera de esta sesión (no lo hizo RAG Studio). Agrega, sin el `/` inicial, las mismas cinco carpetas que ya estaban excluidas (`Actualizacion_*`, `Licenciatura/`, `PRUEBAS_…/`). Es redundante y sin efecto funcional.
- `D RAG_STUDIO_Reporte_Ronda93_Caso_Failed.docx` y `.pdf`: eliminados del árbol a las 12:45 fuera de esta sesión. Se conservan en el commit `74b132a`. Hay que decidir si la eliminación es intencional.
- Eliminados también los tres `.docx` de hallazgos de la raíz. Estaban excluidos, así que no afectan a Git.
- `M docs proyecto/RAG-INC-01/preparacion_01a/Addendum_Tecnico_Revalidacion_01a.md`: resolución de D-1, D-2 y D-3.
- `?? Cierre_Precondiciones_01a.md` y `?? congelar_corpus_D.py`: nuevos.

### 8.5 Estado final

| Precondición | Estado |
|---|---|
| Smoke PASS del ejemplo v1.0.0 en Runtime | Cumplida (registro y Conformidad §5) |
| Control de versiones (respaldo, `.gitignore`, `git init`, línea base, etiqueta, rama) | Cumplida (`74b132a`, `rag-inc-01-baseline`, `rag-inc-01/01a`, sin remoto) |
| Respaldo y procedimiento de copias | Definido; las copias de trabajo se crean al ejecutar 01a |
| Corpus A, B, C | Íntegros |
| Corpus D | **Congelado** |
| Línea base pytest/ruff/mypy | Registrada (925/423/15; ruff limpio; mypy 22) |
| Migraciones | head `0020`; `0021` inexistente |
| D-1 / D-2 / D-3 | Resuelta / diferida a 01b / cerrada |
| Contrato y Alcance | Sin cambios; ampliación autorizada solo para la UI de importación |

**Sin bloqueos contractuales ni técnicos.** Pendientes que no bloquean:

- archivar el informe técnico completo del smoke de Runtime cuando llegue;
- archivar `informe_corpus_D.json`;
- confirmar si la eliminación de los dos archivos del reporte de la Ronda 93 fue intencional;
- la línea redundante del `.gitignore` editada fuera de esta sesión.

## Estado de precondiciones: **READY FOR 0021**

La creación de `0021` y cualquier cambio productivo de 01a requieren todavía la **autorización expresa de NEXOM**. No se hizo ningún commit después de la línea base.
