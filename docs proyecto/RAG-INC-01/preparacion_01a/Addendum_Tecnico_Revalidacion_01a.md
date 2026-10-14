# RAG-INC-01 — Addendum técnico de revalidación del hito 01a

**Fecha:** 2026-10-14
**Naturaleza:** documental. No modifica el contrato NEXOM Knowledge Package v1.0.0 ni el Alcance firmado. No implementa nada.
**Motivo:** el Alcance se redactó sobre el código del 23-09-2026. Entre el 29-09 y el 08-10-2026 (Rondas 86 a 96) el código de RAG Studio cambió en zonas que toca 01a. Este addendum revisa, contra el código actual, cada referencia y cada decisión de diseño de 01a.

---

## 1. Referencias de archivos y líneas actualizadas

| Referencia en el Alcance | Estado actual | Comentario |
|---|---|---|
| `domain/projects/entities.py:58` (`Project.id`) | Igual: línea 58 | Sin cambio |
| `application/projects/commands/import_project.py:20-41` | Docstring 1-24; `ImportProject` 54-108; `execute` 59-108 | Rediseñado en la Ronda 88 (sección 2) |
| `application/documents/commands/register_source.py:37-40` (duplicado por `content_hash`) | Líneas 44-47 | Desplazado por `find_by_content_hash` (Ronda 92). Lógica igual |
| `register_source.py:53-73` (sucesora con `supersedes_source_id` inexistente) | Líneas 59-80 | Lógica igual |
| `application/documents/queries/get_source_lineage.py:42-57` | Igual, empieza en 42 | Sin cambio |
| `infrastructure/database/models.py:68` (`ProjectRecord`) | Igual: 68. `SourceRecord`: 109 | Sin cambio |
| `infrastructure/filesystem/packager.py:50-66` (checkpoint WAL) | Líneas 53-71 | Desplazado. Lógica igual |
| Última migración `0020_chunk_image_relative_path.py` | Igual. `0021` no existe | Sin cambio |
| `migrations/.../0012_metadata_value_change_deletable.py` (patrón `batch_alter_table`) | Existe | Sin cambio |
| `application/projects/commands/clone_project.py`, `delete_project.py` (`ProjectInUseError`), `backup_project.py` | Existen con el mismo comportamiento | Sin cambio |

## 2. Cambios en la importación de proyectos posteriores a la firma (Ronda 88, 02-10-2026)

Hallazgo real de usuario: importar un `.agentproj` con nombre repetido dejaba la importación a medias. Desde entonces:

1. **Detección previa de colisiones, antes de copiar nada** (`ImportProject.execute`):
   - id de un proyecto registrado, activo o archivado → `ProjectIdCollisionError`; la UI ofrece "importar como copia" con un `new_project_id` nuevo;
   - carpeta del id con restos de un intento fallido → `ImportResidueError`; la UI ofrece apartarlos (`quarantine_project_data`) y continuar;
   - nombre repetido → `ImportNameCollisionError` con un nombre sugerido.
2. **Copia atómica** (`FilesystemProjectPackager.import_project`): se extrae a `projects/.importando_<id>_<uuid>/`, se reescribe la identidad dentro del `project.db` extraído (`_rewrite_identity`, que cambia `project_id` en **todas** las tablas y el nombre) y solo al final se renombra a `projects/<id>/`. Si algo falla, se borra la carpeta temporal.
3. **Registro todo o nada:** si `ProjectRepository.save` falla, `discard_project_data` borra lo copiado.
4. La UI (`ui/projects/panel.py`, ~líneas 430-490) reintenta en un ciclo con las opciones que elige el usuario.

## 3. Cómo se integra `identity_policy = preserve | fork`

Con la estructura de la Ronda 88 la integración es más simple que la prevista en el Alcance, sin cambiar sus reglas:

| Regla del Alcance | Punto de integración en el código actual |
|---|---|
| Política no indicada → aborta antes de leer o modificar datos | Primera línea de `ImportProject.execute`, antes de `verify_integrity` |
| `preserve` con `knowledge_base_id` existente (activo o archivado) → `KnowledgeBaseIdentityCollisionError` sin modificar datos | Nueva comprobación 1d en la misma fase de detección previa (después de 1a-1c). El `knowledge_base_id` del paquete se lee del `project.db` del ZIP sin escribir en `projects/` (extracción en memoria o a un temporal fuera de `projects/`) |
| `fork` → `knowledge_base_id` nuevo y un `lineage_id` nuevo por familia, conservando quién supersede a quién | Dentro de `_rewrite_identity`, sobre la copia temporal, en la misma transacción que ya reescribe `project_id`. Hereda la atomicidad de la Ronda 88 |
| `fork` con `project_id` existente sin `new_project_id` → `ProjectIdCollisionError` | Ya ocurre así (comprobación 1a) |
| Bloqueo real del sistema operativo sobre "comprobar → importar → registrar", con tiempo máximo y una segunda comprobación antes de confirmar | Envuelve `ImportProject.execute` completo. La segunda comprobación va justo antes de `ProjectRepository.save` |

**Rollback y copia fallida.** Se mantienen la extracción a una carpeta temporal y el borrado ante cualquier fallo (Ronda 88). La reescritura de identidades de `fork` ocurre antes del renombrado final, así que un fallo nunca deja un proyecto con identidades a medias. La migración `0021` conserva el `downgrade()` protegido del Alcance. La vuelta atrás real se hace restaurando un respaldo.

## 4. Elementos agregados después de la firma que 01a debe considerar

| Elemento (ronda) | Relación con 01a | Efecto |
|---|---|---|
| `knowledge_base_id` reservado (`null`) en `manifest.json` del **paquete de entrega al cliente**, bloque `identity`, con `grouping_key: "project_id"` (Ronda 95) | No es el paquete NKP; es el entregable del runtime de RAG Studio. El contrato de integración promete que `knowledge_base_id` "llegará con RAG-INC-01" | Llenarlo y cambiar la clave de agrupación toca el paquete de entrega, que no forma parte del Alcance (sección 5, decisión D-2) |
| `snapshot_identity.json` en cada instantánea (Ronda 92) | Lleva `project_id`, versión, modelo y huella; no lleva `knowledge_base_id`. La instantánea copia `project.db`, que después de `0021` contendrá `knowledge_base_id` | Sin efecto en 01a. Agregarlo al archivo de identidad sería una mejora de 01b o posterior |
| Registro de lotes `lotes_importados.jsonl` en la carpeta del proyecto (Ronda 92) | Viaja en `.agentproj`. Guarda ids **locales** de fuente y huellas de lote | `fork` no cambia ids locales de fuente, así que el registro sigue siendo válido. Sin efecto en el esquema |
| Una versión nueva de un lote de RAG CONTENT **no** supersede automáticamente a la anterior (Ronda 92, por diseño) | Cada documento de la versión nueva recibe un `lineage_id` nuevo, salvo que el usuario marque "Sustituye a" | No cambia 01a. Para 01b significa que Runtime verá documentos lógicos nuevos en cada versión de lote no vinculada. Conviene que la medición X-03 lo reporte |
| Resolución portable de `original_copy_path` (Ronda 92) | Lectura, sin cambio de esquema | Sin efecto |
| Columnas de diagnóstico en `runtime.db` (Ronda 93) | Otra base, sin Alembic | Sin efecto |
| Deduplicación por `content_hash` en la importación de carpetas (Ronda 92, sin cambios de regla) | Reduce, no elimina, el caso M-05b | Sin efecto en las reglas |

## 5. Decisiones que el Alcance no resuelve frente al código actual

**D-1. Importación desde la interfaz. — RESUELTA: opción (a) aprobada por NEXOM (2026-10-14).** El Alcance hace `identity_policy` **obligatorio y sin valor por defecto** ("no indicada → aborta") y deja la UI fuera de alcance ("Sin cambios en la UI"). Pero la UI de escritorio llama hoy a la importación (Ronda 88) y, desde la Ronda 88, su opción "Importar como copia" crea un `project_id` nuevo **conservando** el contenido. Si 01a se implementa tal cual:
- toda importación desde la UI abortaría por falta de política (regresión funcional visible para el usuario);
- "Importar como copia" equivale semánticamente a `fork` (otra base), pero la UI no lo sabría.

Opciones:
- **(a)** Autorizar una adaptación mínima de la UI dentro de 01a: importación normal = `preserve`; "Importar como copia" = `fork`; manejar `KnowledgeBaseIdentityCollisionError` ofreciendo `fork`. Afecta un archivo de UI y el Manual.
- **(b)** Mantener la UI fuera y que la fachada de aplicación pase `preserve` por defecto solo para la UI, sin cambiar el caso de uso obligatorio. `KnowledgeBaseIdentityCollisionError` se mostraría como error genérico, sin reintento guiado.
- **(c)** Deshabilitar la importación desde la UI hasta un incremento posterior.

> **Resolución de D-1 (NEXOM, 2026-10-14).** Se autoriza que 01a incluya la adaptación mínima de la UI:
> importación normal → `identity_policy = "preserve"`; "Importar como copia" → `identity_policy = "fork"`;
> si `preserve` produce `KnowledgeBaseIdentityCollisionError`, la UI permite continuar por el flujo "Importar como copia" (`fork`).
> No modifica el contrato v1.0.0 ni las reglas de `preserve`/`fork`; es una adaptación mínima para evitar una regresión
> funcional y queda autorizada explícitamente como parte de 01a. Propuesta de RAG Studio, pendiente de confirmar: actualizar la sección 4.3 del Manual de Usuario para describir los dos modos.

**D-2. Paquete de entrega al cliente. — DIFERIDA A RAG-INC-01b (NEXOM, 2026-10-14).** Decidir si 01a (o 01b) llena `identity.knowledge_base_id` en el `manifest.json` de entrega y si `grouping_key` pasa de `project_id` a `knowledge_base_id`. Cambiar la clave afecta a NEXOM Testing Agent (Ronda 95). Opción conservadora: llenar el campo sin cambiar `grouping_key` hasta acordarlo con Testing Agent.

> **Resolución de D-2 (NEXOM, 2026-10-14).** Durante 01a: no cambiar `grouping_key`; no modificar la integración
> actual con Testing Agent; no usar el paquete de entrega del widget como sustituto del NEXOM Knowledge Package. Si
> `knowledge_base_id` existe después de `0021`, su incorporación al `manifest.json` del paquete de entrega se analiza
> en 01b o en una decisión posterior específica.

**D-3. Corpus D. — CERRADA (2026-10-14): confirmado por NEXOM y congelado (`project.db` `ca45dd6f…354a`; ver `Cierre_Precondiciones_01a.md`, sección 8.3).** NEXOM incorporó como corpus adicional el proyecto real AGENTE UDL `6073eda1-…`, posterior a la preparación. No cambia gates. Requiere congelamiento por hash (ver `Cierre_Precondiciones_01a.md`).

Ninguna de estas decisiones cambia el contrato v1.0.0, ni las reglas de `preserve`/`fork`, ni la migración `0021`, ni los criterios de PASS de 01a. D-1 sí toca una exclusión explícita del Alcance ("Sin cambios en la UI"): implementar 01a literalmente rompe una función existente de la aplicación.

---

## Conclusión

**Evaluación original (2026-10-14): REQUIERE DECISIÓN NEXOM**, por D-1: el Alcance dice a la vez "`identity_policy` obligatorio" y "sin cambios en la UI", y la UI actual importa proyectos.

**Estado tras las decisiones de NEXOM (2026-10-14): ALCANCE SIN CAMBIO** en todo lo contractual y técnico de 01a (contrato v1.0.0, migración `0021`, reglas de `preserve`/`fork`, bloqueo, criterios de PASS), con **una ampliación autorizada expresamente**: la adaptación mínima de la UI de importación (D-1, opción a); la nota del Manual queda como propuesta a confirmar. D-2 queda diferida a 01b y D-3 confirmada; su congelamiento es una precondición de ejecución de `0021`, no un cambio de alcance.
