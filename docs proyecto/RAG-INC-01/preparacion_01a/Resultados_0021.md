# RAG-INC-01a — Resultados del incremento 0021 (identidades NEXOM)

**Fecha:** 2026-10-14
**Rama:** `rag-inc-01/01a`, sobre `74b132a` (`rag-inc-01-baseline`). **Sin commit**, por instrucción de NEXOM.
**Autorización:** solo la migración `0021` y los cambios mínimos para soportarla. Fuera de alcance de este incremento: `identity_policy`, UI, bloqueo, `KnowledgeBaseIdentityCollisionError`, exportador, 01b–01d.

## 1. Limpieza previa

Restaurados desde `74b132a`:
- `RAG_STUDIO_Reporte_Ronda93_Caso_Failed.docx` y `.pdf`;
- `.gitignore`.

Tras la restauración, `git status` solo mostraba los documentos de preparación de 01a.

## 2. Cambios

| Archivo | Cambio |
|---|---|
| `migrations/project/versions/0021_nexom_identities.py` (nuevo) | Migración (sección 3) |
| `domain/projects/entities.py` | `Project.knowledge_base_id` (UUID4 por defecto) |
| `domain/documents/entities.py` | `Source.lineage_id` (UUID4 por defecto) |
| `infrastructure/database/models.py` | Columnas `project.knowledge_base_id` (NOT NULL, única) y `source.lineage_id` (NOT NULL, índice) |
| `infrastructure/database/repositories.py` | Mapeo de `knowledge_base_id`. No se sobrescribe al actualizar un proyecto existente |
| `infrastructure/database/document_repositories.py` | Mapeo de `lineage_id`. No se sobrescribe al actualizar una fuente |
| `application/documents/commands/register_source.py` | R-01: una sucesora con `supersedes_source_id` válido copia el `lineage_id` de su predecesora. Sin supersesión válida, conserva el UUID4 nuevo |
| `tests/integration/test_migration_0021_nexom_identities.py` (nuevo) | 15 pruebas: M-01 a M-08, rollback, ids locales, R-01 a R-03 |
| `tests/integration/test_alembic_migrations.py` | Fixture que activa la bandera de downgrade de pruebas: estas pruebas bajan de head sobre bases temporales |
| `docs proyecto/RAG-INC-01/preparacion_01a/medir_y_migrar_corpus_01a.py` (nuevo) | Herramienta de evidencia: copia, verifica, migra y mide un corpus |

**Justificación de los cambios fuera de la migración:** sin el mapeo en modelos y repositorios, crear proyectos o fuentes fallaría contra las columnas NOT NULL. Sin R-01, cada fuente nueva rompería la regla "una familia, un `lineage_id`" que la migración establece.

## 3. Diseño de `0021`

1. Lee las fuentes, calcula las familias y detecta ciclos **antes de cualquier cambio**.
   - Un ciclo, incluido S→S, aborta con `MigracionIdentidadesError`.
   - Una referencia rota hace de la fuente la raíz de su propia cadena y queda en el log (`ragstudio.migraciones.0021`).
   - Las ramificaciones se admiten y se registran.
2. Agrega las columnas como anulables.
3. Rellena con UUID4: uno por proyecto y uno por familia.
4. Verifica que no queden nulos, que cada cadena tenga un solo linaje y que `knowledge_base_id` no se repita.
5. Impone NOT NULL con `batch_alter_table`. Crea `uq_project_knowledge_base_id` e `ix_source_lineage_id`. Los índices existentes de `source` se conservan.
6. Repite la comprobación final sobre el esquema definitivo.

**Atomicidad:** todo ocurre dentro de un `SAVEPOINT` de SQLite que también contiene el `UPDATE alembic_version`. Ante cualquier error se hace `ROLLBACK TO` y la base queda exactamente en `0020`. Lo comprueban las pruebas con fallo inyectado después del relleno y después del NOT NULL.

**`downgrade()`:** se niega, salvo con `RAGSTUDIO_PERMITIR_DOWNGRADE_0021=1`, que solo se usa sobre bases desechables.

**Bandera de pruebas:** `RAGSTUDIO_0021_FALLO_DE_PRUEBA` inyecta un fallo en una etapa concreta. Sin la variable no tiene efecto.

## 4. Corpus (solo copias; originales verificados sin cambios por hash después de migrar)

| | A (canario) | B (secundario) | C (principal) | D (AGENTE UDL) |
|---|---|---|---|---|
| Origen | `_respaldos_rag_inc_01/corpus_A_42ac4489_2026-10-14/`, copia idéntica al inventario congelado | `.agentproj` `e7d81510…4ebe` | `.agentproj` `09157313…4eaa7` | `evidencia.tar.gz` `95516301…1897` |
| Alembic inicial | 0020 | 0016 | 0016 → 0020 en la copia (línea base 0020: `28e88220…e18b`) | (0020 según congelamiento) |
| Alembic final | **0021** | 0016: no llega a 0020 por `0017`; tras la corrección autorizada: **0021** (sección 9) | **0021** | **no ejecutado** |
| `knowledge_base_id` | `ed4e456d-a28e-489a-9bc1-e7b79ac2b587` | — | `d873fb39-fa51-4e87-9627-0ba802f7ccb7` | — |
| Fuentes / `lineage_id` distintos | 1 / 1 | 5 / 5 familias (en memoria) | 25 / 25 | — |
| Nulos (`lineage_id` / `knowledge_base_id`) | 0 / 0 | — | 0 / 0 | — |
| Ciclos | 0 | 0 | 0 | — |
| Colisiones `source.id` / `chunk.id` portables | 0 / 0 | 0 / 0 (en memoria) | 0 / 0 | — |
| `project_id`, ids de fuente y de chunk | Sin cambio | — | Sin cambio | — |
| NOT NULL final | Sí | — | Sí | — |
| `integrity_check` | ok | ok (copia) | ok | — |
| SHA-256 tras migrar (copia) | `0a18a53f…a3a8` | — | `7fd0c97d…97d2` | — |

**Corpus B (hallazgo, no corregido).** La migración **anterior** `0017_test_case_unique_code` falla en la copia con `UNIQUE constraint failed: test_case.project_id, test_case.code`. El proyecto tiene dos casos de prueba `UDL-001` y dos `UDL-002`.
- Es el comportamiento documentado de `0017` ("este caso debe resolverse a mano renombrando uno de los dos códigos").
- No es un defecto de `0021`. Según `Congelamiento_Corpus_UDL.md` §3, no se le atribuye.
- No se corrigieron los datos.
- Las mediciones de B se hicieron en solo lectura sobre la copia en `0016`, y M-05b con familias calculadas en memoria con la misma función de la migración.

**Corpus D.** La evidencia congelada (`evidencia.tar.gz`) está en el equipo macOS y no es accesible desde este entorno. La herramienta acepta el `.tar.gz` directamente:

```
python3 "docs proyecto/RAG-INC-01/preparacion_01a/medir_y_migrar_corpus_01a.py" --corpus D \
  --origen <ruta>/evidencia.tar.gz \
  --sha256-origen 95516301a5cf7f49461a94b44683c6799fa88a7958b12bf2c91919ccca331897 \
  --sha256-project-db ca45dd6f96b50fd336951f8176559cb13af2e098e579b85a5a2eefbf342d354a \
  --out <carpeta_nueva>
```

## 5. Mediciones

| Medición | A | B | C |
|---|---|---|---|
| **X-01 / INC01-R6**: chunks no imagen con texto vacío | 0 | 0 | 0 |
| Informativo: solo espacios | 0 | 0 | 0 |
| **X-02 / INC01-R1**: fuentes sin `content_hash` | **1 de 1** | **5 de 5** | **25 de 25** |
| **X-03**: raíces / con supersesión / referencias rotas / ramificaciones / ciclos / profundidad máx. | 1/0/0/0/0/1 | 5/0/0/0/0/1 | 25/0/0/0/0/1 |
| X-03: sucesoras con igual contenido (2f) / hermanas en colisión (2g) / familias con varias cabezas (2h) | 0/0/0 | 0/0/0 | 0/0/0 |
| **M-05b**: colisiones portables `source` / `chunk` | 0/0 | 0/0 | 0/0 |

**Lectura:**
- INC01-R6 = 0 en los tres, así que no bloquea 01b.
- M-05b = 0, así que no bloquea 01b.
- **INC01-R1 afecta al 100% de las fuentes** de los tres corpus. Ninguna tiene `content_hash`, de modo que su `source.id` portable depende de `title|source_type|updated_at`, y cualquier edición de la fuente lo cambiará. Esto es lo que el Alcance mandaba "medir y documentar". No bloquea 01a. Debe considerarse antes de 01b: NEXOM decide si se acepta o si se rellena `content_hash` en un incremento aparte.
- Ningún corpus tiene supersesiones reales. La lógica de familias se ejercitó con bases sintéticas (M-02 a M-07).

## 6. Regresión (sobre la rama, sin commit)

| | Línea base `74b132a` | Ahora |
|---|---|---|
| pytest unitarias | 925 passed / 6 skipped | 925 / 6 |
| pytest integración | 423 / 13 | **438 / 13** (+15 nuevas de 0021) |
| pytest smoke | 15 / 2 | 15 / 2 |
| ruff | limpio | limpio |
| mypy | 22 errores, 7 archivos | 22 errores, 7 archivos |

## 7. Riesgos nuevos

1. **Esta copia del código migra a 0021 cualquier proyecto que abra.** Si se ejecuta la aplicación de escritorio desde esta carpeta, `data/projects/42ac4489…` (el original del corpus A) pasaría a 0021. No hay downgrade. Existe un respaldo de solo lectura en `_respaldos_rag_inc_01/corpus_A_42ac4489_2026-10-14/`. **No ejecutar la app desde esta carpeta hasta 01d.**
2. **Hasta implementar `identity_policy` y su detección, "Importar como copia" duplica `knowledge_base_id`** dentro de una misma instalación. Es la colisión que debe detectar el siguiente incremento.
3. **Corpus B no puede abrirse en esta versión** sin corregir manualmente sus códigos de caso duplicados (efecto de `0017`, anterior a 01a).
4. **INC01-R1 al 100%** (sección 5).
5. Los `.agentproj` exportados con esta versión llevan `project.db` en 0021. Una versión anterior de RAG Studio no los entiende. La compatibilidad se gestiona en 01d.

## 8. Estado

**Migración 0021: PASS** en sintéticos (M-01 a M-08, rollback), A y C.

**Estado: BLOCKED.**
- D no se ha ejecutado: falta acceso a `evidencia.tar.gz`.
- B no llega a `0020` por `0017`: requiere decisión de NEXOM. Opciones: aceptar B como no aplicable, corregir sus códigos sobre una copia de prueba, o sustituirlo.

Ningún bloqueo es un defecto de `0021`.

## 9. Actualización 2026-10-14 (tarde) — decisión NEXOM sobre B y D

### 9.1 Corpus B — corrección solo en una copia descartable

- **B original: intacto.** `.agentproj` `e7d81510…4ebe` verificado antes y después.
- **Corrección: solo en una copia descartable** (`/tmp`), nunca en el congelado.
- **Motivo:** desbloquear la migración preexistente `0017_test_case_unique_code`.

| Paso | Detalle |
|---|---|
| Origen verificado | SHA-256 `e7d81510240ade50eb834fe4a752245cff280c537750f5b1d4e24d7c4e0f4ebe` |
| Duplicados (`project_id` `9a3a0a10-b678-41a2-b758-db1503ad7399`) | `UDL-001`: `7d0d1783-08ef-481a-ad73-fa53febca005` (20:11:41) y `c1e2b6ed-db92-4b4d-9262-bc0c772e7961` (20:15:46). `UDL-002`: `26ef51a4-8428-409d-b282-2a21692d88d7` (20:11:41) y `c3f4f479-d07c-4dec-88cb-2f35daaf13af` (20:15:46). Los dos pares son idénticos campo a campo salvo `id` y fechas: la segunda ocurrencia es un duplicado del mismo caso creado cuatro minutos después |
| Renombrado (solo la segunda ocurrencia, por `created_at`) | `c1e2b6ed…` `UDL-001` → `UDL-001-02`; `c3f4f479…` `UDL-002` → `UDL-002-02` (registro en `_respaldos_rag_inc_01/0021_corpus/B_corregido/registro_correccion.json`) |
| Alcance de la corrección | Comparación tabla por tabla, copia antes contra copia después: solo cambió `test_case.code` en esas dos filas. Esquema idéntico. Se conservó el modo WAL del encabezado. `updated_at` no se tocó. Los 6 `evaluation_result_item` históricos que citan `UDL-001`/`UDL-002` **no se modificaron**, por instrucción |
| SHA-256 de `project.db` antes / después de corregir | `124d174438d850a381580e42be5473e1ea445c9086635869add66e6fd4ba81e6` / `5e1e1263d74cf974e4ce67ffd5bc716a6e539d58c1e96853c09cf8efcf024c19` |
| Migraciones | `0016` → `0017` … `0020` sin errores. Línea base 0020: `b264360a2428e6a59747d1c4e6fac3f22d1cca04491a8fbc853f746681200c6f`. Después, `0021` |
| **0021** | **PASS** |
| `knowledge_base_id` | `ac4e2c80-f824-4a2f-92ae-96e2cce17ff1` |
| Fuentes / `lineage_id` distintos / nulos / ciclos / colisiones | 5 / 5 / 0 / 0 / 0 (`source` y `chunk`) |
| `project_id`, ids de fuente y de chunk | Sin cambio |
| NOT NULL / `integrity_check` | Sí / ok |
| SHA-256 de la copia migrada | `6b9e74b5fe67c3880f75f71b1fbe6451afe605833df98e8f2144234d6b6de2d3` |

No apareció ningún otro problema anterior a `0021`.

### 9.2 Corpus D — no ejecutado (evidencia no disponible en este equipo)

`evidencia.tar.gz` no está en ninguna carpeta accesible desde el equipo del desarrollador. Según la instrucción de NEXOM, se entrega la herramienta para ejecutarla donde está la evidencia:

- `_respaldos_rag_inc_01/entrega_validacion_D/RAG_STUDIO_codigo_0021_validacion_D.zip`, SHA-256 `98f74bb87ad254fa4a64ab5849a454529c75878e24b704b6ce1cfcc8b9edfb63`. Contiene el código de la rama 01a (716 archivos versionables), incluidos `0021` y `medir_y_migrar_corpus_01a.py`, y las instrucciones en `README_VALIDACION_D.md`.
- Se comprobó de punta a punta en este equipo: se generó una evidencia sintética con `congelar_corpus_D.py` (mismo formato `.tar.gz`), se extrajo el ZIP en una carpeta limpia y se ejecutó la herramienta. Resultado: `0021` PASS, origen sin cambios.
- Alternativa equivalente: copiar `evidencia.tar.gz` a la carpeta de RAG Studio del desarrollador y ejecutar ahí el mismo comando.

### 9.3 INC01-R1

**INC01-R1 = MEDIDO. Resultado: 100% de las fuentes sin `content_hash` en A, B y C** (1/1, 5/5, 25/25). No se corrige en 01a. La decisión (aceptarlo o abrir un incremento para `content_hash`) queda diferida hasta antes de autorizar 01b.

### 9.4 Regresión final (sin commit)

Unitarias 925/6; integración 438/13; smoke 15/2; ruff limpio; mypy 22 errores en 7 archivos. Sin cambios respecto del estado anterior.

### 9.5 Estado

| | Resultado |
|---|---|
| Migración 0021 | PASS |
| Validación corpus A | PASS |
| Validación corpus B | PASS (sobre una copia corregida y autorizada) |
| Validación corpus C | PASS |
| Validación corpus D | **PENDIENTE** (herramienta entregada) |

**Estado (sección 9): BLOCKED** solo por la ejecución de D. Superado en la sección 10.

## 10. Cierre 2026-10-14 — Corpus D PASS

### 10.1 Corpus D (ejecutado por NEXOM en macOS con la herramienta entregada)

- **D validado solo sobre una copia extraída de la evidencia congelada.** La herramienta verificó `evidencia.tar.gz` (`95516301…1897`) y `project.db` (`ca45dd6f…354a`) antes de extraer, y confirmó al final que el origen no cambió. No se tocaron `data_AGENTE_UDL` ni el `project.db` original.
- El código ejecutado es el del ZIP entregado (`98f74bb8…fb63`). Se comprobó que `0021_nexom_identities.py`, la herramienta, los modelos, las entidades, los repositorios y `register_source.py` del ZIP son **byte a byte iguales** a los del árbol actual. **`0021` no se modificó.**

| Dato | Valor |
|---|---|
| Alembic inicial / final | 0020 / 0021 |
| Migración | PASS |
| `knowledge_base_id` | `16134ec5-b2ed-4fe4-bcd9-373d3ddf5537` |
| Fuentes / chunks | 35 / 668 |
| `lineage_id` distintos / nulos | 35 / 0 |
| `knowledge_base_id` nulos | 0 |
| Ciclos / cadenas con linaje distinto | 0 / 0 |
| Colisiones portables `source` / `chunk` | 0 / 0 |
| `project_id`, ids de fuente y de chunk | Sin cambio |
| NOT NULL (`project.knowledge_base_id`, `source.lineage_id`) | Sí / Sí |
| `integrity_check` | ok |
| Origen sin cambio | Sí |
| `informe.json` SHA-256 | `84de50ba4a34aee016b22e2896162786b902ff3b437840c12ae7a973e36d387a` |

### 10.2 Tabla final

| Corpus | Base de la validación | Alembic | `knowledge_base_id` | Fuentes / linajes | Nulos / ciclos / colisiones | ids y `project_id` | `integrity_check` | 0021 |
|---|---|---|---|---|---|---|---|---|
| A | Copia del canario (inventario congelado) | 0020 → 0021 | `ed4e456d-…` | 1 / 1 | 0 / 0 / 0 | Sin cambio | ok | **PASS** |
| B | Copia **corregida** del `.agentproj` (solo `test_case.code` de dos duplicados); **original intacto** | 0016 → 0020 → 0021 | `ac4e2c80-…` | 5 / 5 | 0 / 0 / 0 | Sin cambio | ok | **PASS** |
| C | Copia del `.agentproj` | 0016 → 0020 → 0021 | `d873fb39-…` | 25 / 25 | 0 / 0 / 0 | Sin cambio | ok | **PASS** |
| D | Copia extraída de `evidencia.tar.gz` | 0020 → 0021 | `16134ec5-…` | 35 / 35 | 0 / 0 / 0 | Sin cambio | ok | **PASS** |

- Migración 0021 = **PASS**
- Validación corpus A = **PASS**
- Validación corpus B = **PASS** (solo sobre una copia corregida y autorizada; original intacto)
- Validación corpus C = **PASS**
- Validación corpus D = **PASS** (solo sobre una copia de la evidencia congelada)

**INC01-R1 = MEDIDO**: 100% de las fuentes sin `content_hash` en A, B y C. Para D, el valor quedó en su `informe.json` (`antes.R1`), pero no viene en el resumen recibido; conviene leerlo de ahí. Se difiere la decisión hasta antes de autorizar 01b; no se corrige en 01a.

**`0021` no se modificó** durante la validación.

## Estado: **READY FOR 0021 COMMIT REVIEW**

Sin commit, sin etiqueta y sin push hasta la autorización expresa de NEXOM.
