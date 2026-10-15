# Relleno de `content_hash` (INC01-R1, opción B) — resultados

Fecha: 2026-10-14 · Rama `rag-inc-01/01a` sobre `3d508ef` · **Sin commit, sin tag, sin push.** El exportador NKP no está implementado.

## 1. Diseño

**Caso de uso** `BackfillSourceContentHashes(project_id)`, expuesto como `DocumentService.backfill_content_hashes`:

1. Lista las fuentes del proyecto.
2. Para cada fuente basada en archivo con `content_hash IS NULL`, calcula el SHA-256 de los bytes de `<proyecto>/sources/original/<source_id>.<ext>`. **Nunca usa `location`.** Un fallo de lectura no detiene a las demás fuentes.
3. Clasifica con la regla de duplicados (sección 2).
4. Escribe en **una transacción**, solo donde el hash sigue NULL.
5. Guarda un informe JSON en `<proyecto>/reports/content_hash_backfill_<UTC>_<sufijo>.json`. También lo guarda si la escritura se revirtió.
6. Devuelve el informe.

**Capas:**

| Capa | Archivo | Contenido |
|---|---|---|
| Dominio | `domain/documents/content_hash_backfill.py` | Estados, informe y regla de clasificación pura |
| Dominio | `domain/documents/ports.py` | Puertos `SourceOriginalHasher`, `SourceContentHashWriter`, `BackfillReportStore` |
| Dominio | `domain/documents/exceptions.py` | Excepciones |
| Infra | `infrastructure/filesystem/source_original_hasher.py` | Busca la copia por id. Si hay varias, solo vale la que nombra `original_copy_path`; si no, `ilegible` |
| Infra | `infrastructure/database/content_hash_writer.py` | Escritura condicional en una transacción (ver abajo) |
| Infra | `infrastructure/filesystem/backfill_report_store.py` | JSON atómico (archivo temporal + `os.replace`) |

**Escritor** (`content_hash_writer.py`). Una sola transacción `BEGIN IMMEDIATE`:

1. `UPDATE … SET content_hash=? WHERE id=? AND content_hash IS NULL`: nunca sobrescribe.
2. Comprobación final: ninguna fuente escrita puede compartir `(lineage_id, content_hash)` con otra. Si ocurre, `ROLLBACK` y `ContentHashBackfillConflictError`.
3. `COMMIT`. Ante cualquier excepción, `ROLLBACK`.
4. No toca `updated_at`.

**Interfaz.** Botón "Completar huellas de contenido…" en Fuentes: pide confirmación y muestra un resumen al terminar. No se ejecuta automáticamente después de importar.

**Propiedades:**
- **Idempotente.** Una segunda ejecución escribe `sin_cambios` y reporta `ya_tenía`.
- **Concurrencia.** Dos rellenos o un alta simultánea se serializan con `BEGIN IMMEDIATE` y `busy_timeout`. Si otro proceso completó la fuente antes, se reporta `ya_tenía`.

## 2. Estados del informe y regla de duplicados

| Estado | Significado | ¿Escribe? |
|---|---|---|
| `rellenada` | Hash calculado y guardado | Sí |
| `contenido_compartido_entre_linajes` | Mismo hash que otra fuente de **otro** linaje (los `source.id` son distintos, está permitido) | Sí |
| `ya_tenía` | Ya tenía hash (o lo completó otro proceso). No se modifica | No |
| `no_aplica` | `api` / `base_de_datos` | No |
| `sin_copia_original` | No existe `sources/original/<id>.*` | No |
| `ilegible` | La copia existe pero no se puede leer, es un directorio o es ambigua | No |
| `colisión_mismo_linaje` | Mismo hash que otra fuente del **mismo** linaje: mismo `source.id`. No se rellena **ninguna** del grupo. Incluye el caso mixto, cuyo hash existente no se toca. No se resuelve automáticamente | No |

Campos del JSON:
- `escritura`: `aplicada`, `sin_cambios` o `revertida`;
- `error`;
- `faltantes_antes` y `faltantes_despues`;
- `conteos`, con los 7 estados;
- `fuentes[]`: `source_id`, `titulo`, `source_type`, `lineage_id`, `estado`, `content_hash`, `detalle`, `relacionadas`.

## 3. Validación real (solo copias verificadas; orígenes intactos)

Herramienta: `validar_backfill_corpus.py`. Evidencia, fuera de Git: `_respaldos_rag_inc_01/backfill_corpus/{A,B,C}/`.

| Corpus | Origen (SHA-256 verificado) | Faltantes | Estados | Hash verificado contra la copia | `updated_at` / `lineage_id` | 2.ª ejecución | `integrity_check` | Resultado |
|---|---|---|---|---|---|---|---|---|
| A | `project.db` `4b4bac22…e925` | **1 → 0** | 1 `rellenada` | 1/1 | Sin cambio | `sin_cambios` | ok | **PASS** |
| B | `.agentproj` `e7d81510…4ebe` (*) | **5 → 0** | 5 `rellenada` | 5/5 | Sin cambio | `sin_cambios` | ok | **PASS** |
| C | `.agentproj` `09157313…4eaa7` | **25 → 0** | 25 `rellenada` | 25/25 | Sin cambio | `sin_cambios` | ok | **PASS** |

(*) B solo llega a 0021 con la corrección de `test_case.code` autorizada por NEXOM para 0017, aplicada **solo a la copia**.

No apareció ninguna colisión ni ningún archivo faltante. D no requiere relleno (0/35).

SHA-256 de `informe_backfill.json`:
- A: `a34e16f0…4c17`
- B: `548e579b…80c8`
- C: `b93a17f9…456b`

## 4. Riesgos

1. **`content_hash` vacío (`''`).** No es NULL, así que, según la regla autorizada, no se modifica: queda como `ya_tenía` con una advertencia en el detalle. Medido: 0 casos en A/B/C. El gate de 01b debe tratar `''` como faltante, porque la fórmula lo trata como "sin hash".
2. **Brecha preexistente, no corregida aquí.** Corregir `location` antes de la primera extracción vuelve a copiar el original, pero no recalcula el hash de las fuentes que ya lo tienen. Si la extensión cambió, el relleno ve dos copias y solo usa la que nombra `original_copy_path`; si ninguna coincide, la marca `ilegible`.
3. **Ejecución en el hilo de la interfaz.** Corre con cursor de espera, igual que Importar carpeta. En proyectos con muchos PDF grandes la ventana se queda esperando unos segundos.
4. **Deduplicación más estricta.** Tras el relleno, volver a registrar el mismo archivo de una fuente heredada da `DuplicateSourceError`, igual que con las fuentes nuevas.
5. **Instantáneas.** Las existentes no se tocan y no pasarán el gate de 01b. Hay que publicar una nueva después del relleno.
6. **Informe no guardado.** Si falla el guardado del informe (por ejemplo, disco lleno), la escritura confirmada se conserva. La interfaz avisa "No se pudo guardar el informe" y el detalle queda en el log.
7. **Fallos preexistentes en pruebas de Metadatos con Qt (fuera de alcance).** Al ejecutar las pruebas de interfaz con las bibliotecas Qt/EGL cargadas, fallan dos casos de `tests/unit/ui/test_metadata_conversational_field_refresh.py` con `CatalogRequiredForFieldTypeError`:
   - `test_metadata_field_combo_refreshes_when_schema_is_created_after_project_selection`;
   - `test_metadata_field_combo_does_not_refresh_without_the_signal_connected`.

   Son preexistentes: se reproducen igual sin los cambios de este incremento. Se comprobó retirando temporalmente los cambios del árbol de trabajo y volviendo a ejecutar las mismas pruebas: 2 failed, 117 passed. Con los cambios: 2 failed, 122 passed; los 5 casos de más son pruebas nuevas del relleno.

   En la suite normal se omiten, porque el sandbox no tiene las bibliotecas Qt/EGL. Por eso no figuran en los conteos de regresión (unitarias 944 passed / 9 skipped). No pertenecen al alcance de este incremento y no se corrigieron.
