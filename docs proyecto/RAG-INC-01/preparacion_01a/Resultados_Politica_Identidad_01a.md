# RAG-INC-01a — Política de identidad en la importación: resultados

Fecha: 2026-10-14 · Rama `rag-inc-01/01a` sobre `a208d8b` (0021) · **Sin commit, sin tag, sin push.**

## 1. Diseño final

**Política obligatoria.** `ImportProject.execute(..., identity_policy=...)` acepta `"preserve"` o `"fork"` (o el enum `IdentityPolicy`; se ignoran mayúsculas y espacios). Si falta, está vacía o no es válida, lanza `MissingIdentityPolicyError` antes de abrir el paquete.

**Preserve (importación normal).**

1. Verifica la integridad del paquete.
2. Lee `knowledge_base_id` del `project.db` del paquete, en una copia temporal de solo lectura fuera de la instalación.
3. Si un proyecto de la instalación, activo o archivado, ya tiene ese kb, lanza `KnowledgeBaseIdentityCollisionError`. Esta comprobación va antes de las de id, residuos y nombre. No escribe nada.
4. Siguen las comprobaciones de la Ronda 88 (id, residuos, nombre).
5. Se conservan `knowledge_base_id` y todos los `lineage_id`. Nunca se sobrescribe ni se genera una identidad nueva.

**Fork ("Importar como copia").**

- `knowledge_base_id` nuevo (UUID4).
- **Regla de linaje:** un `lineage_id` nuevo (UUID4) por cada `lineage_id` distinto del paquete. Las fuentes que compartían linaje comparten el nuevo, así que se conservan las familias.
- `supersedes_source_id` y todos los ids locales quedan intactos, salvo `project_id` si se pide uno nuevo.
- Si el `project_id` ya existe, se exige `new_project_id` (`ProjectIdCollisionError`). La UI siempre envía uno nuevo.
- La copia convive con el original y no lo toca.

**Colisión de identidad.** Se comprueba dos veces, ambas bajo el bloqueo:

- antes de copiar (solo con preserve);
- justo antes de registrar (con ambas políticas; cubre también los paquetes anteriores a 0021).

La comprobación es fail-closed: si no puede listar los proyectos, lanza `ImportIdentityCheckError`. Cada colisión deja una advertencia en el log técnico con el kb, el proyecto existente y la política.

**Atomicidad.** Todo ocurre en `projects/.importando_<id>_<uuid>`, en este orden:

1. extraer el paquete;
2. `upgrade_project` de la copia (nuevo: hace atómicos los paquetes anteriores a 0021 y cualquier fallo de migración);
3. reescribir el `project_id`;
4. fork de identidades;
5. leer el `Project`;
6. renombrar a la carpeta final.

Ante cualquier excepción se borra la copia temporal. Si después falla `ensure_project_layout`, se borra la carpeta final. Si falla la segunda comprobación o `repository.save`, `discard_project_data`.

**Bloqueo entre procesos** (`infrastructure/filesystem/import_lock.py`). Es un bloqueo exclusivo del sistema operativo sobre `<instalación>/.importacion.lock`:

- POSIX: `fcntl.flock(LOCK_EX|LOCK_NB)`.
- Windows: `msvcrt.locking(LK_NBLCK)`.
- Reintenta cada 50 ms hasta 30 s y luego lanza `ImportLockTimeoutError` sin cambios.
- Cubre la operación lógica completa: comprobar, importar, segunda comprobación y registrar.
- El sistema operativo lo libera al cerrar el descriptor o al morir el proceso. La existencia del archivo no significa nada.
- También excluye entre hilos, porque cada `hold()` abre su propio descriptor. No depende de `threading.Lock`.
- Se conecta en `app/bootstrap.py`.

**UI (D-1)** (`ui/projects/import_flow.py`, sin Qt; `panel._on_import` solo aporta los diálogos):

- La importación normal envía `preserve`.
- `KnowledgeBaseIdentityCollisionError` abre el diálogo "El proyecto ya existe en esta instalación (misma identidad)". Explica que el paquete conserva una identidad ya presente, indica qué proyecto la tiene y pregunta "¿Importarlo como copia?".
  - Sí: `fork` con un `project_id` UUID nuevo.
  - Cancelar: nada.
  - No se muestra como error genérico y nunca se hace fork sin aceptación.
- `ProjectIdCollisionError` ofrece la misma copia (fork).
- Residuos y nombre: igual que en la Ronda 88; se conserva la política elegida.
- No se cambió ninguna otra pantalla.

## 2. Pruebas nuevas

- `tests/integration/test_import_identity_policy.py`, 28 casos:
  - política ausente o inválida (5);
  - enum y mayúsculas;
  - preserve sin colisión;
  - colisión contra un proyecto activo, con otro id y otro nombre, más el log;
  - colisión contra un proyecto archivado;
  - prioridad de la colisión de identidad sobre la de id;
  - fork sin colisión (kb nuevo, familias y supersedes conservados, linajes disjuntos);
  - fork desde una identidad existente, coexistencia y tres bases distintas;
  - rollback preserve/fork × {registro, fork de identidades, migración, layout, segunda comprobación}, verificando índice, carpetas y `.importando_`, más el reintento posterior (10 casos; uno se omite porque no aplica);
  - paquete 0020 recibe identidades;
  - fallo de migración del paquete sin restos;
  - dos procesos (spawn) con la misma identidad: solo uno registra;
  - timeout del bloqueo con el bloqueo tomado por otro proceso;
  - liberación del bloqueo si el proceso muere;
  - exclusión dentro del mismo proceso.
- `tests/unit/ui/test_import_flow_identity_policy.py`, 8 casos:
  - normal → preserve;
  - colisión → explica y ofrece fork;
  - cancelar → nunca fork;
  - id → fork;
  - copia y nombre;
  - residuos y nombre con preserve;
  - otros errores se propagan;
  - panel real con Qt: cancelar, luego aceptar.
- **Control negativo** (manual): sin bloqueo, los dos procesos registran (`['ok','ok']`, dos proyectos con el mismo kb). Con bloqueo, `['KnowledgeBaseIdentityCollisionError','ok']`.

## 3. Regresión (línea base post-0021: 925/6 · 438/13 · 15/2 · ruff limpio · mypy 22/7)

| Suite | Resultado | Diferencia |
|---|---|---|
| Unitarias | 932 passed, 7 skipped | +7 nuevas; +1 skip (panel Qt: falta `libEGL` en el sandbox) |
| Integración (14 tandas) | 465 passed, 14 skipped | +27 nuevas; +1 skip (rollback de fork aplicado a preserve) |
| Smoke | 15 passed, 2 skipped | = |
| ruff (código y pruebas) | All checks passed | = |
| mypy | 22 errores en 7 archivos, los mismos | = |

La prueba del panel con Qt real pasó con las bibliotecas EGL cargadas temporalmente (12/12 junto con `test_projects_panel_button_states.py`).

## 4. Compatibilidad con paquetes reales (solo lectura, instalación temporal)

- `Prueba_B_Cobertura_OCR_25_programas.agentproj`, anterior a 0021:
  - preserve OK;
  - segundo preserve: `ProjectIdCollisionError`;
  - fork: kb distinto, 25 familias idénticas y linajes disjuntos;
  - original y paquete intactos.
- `Prueba_A_E2E_Oferta_Academica_UDL.agentproj`:
  - falla la migración **0017**, preexistente (códigos de caso de prueba repetidos; misma causa que el corpus B);
  - la instalación queda sin cambios.

## 5. Riesgos

1. **Encontrado y corregido.** Tras 0021, importar un paquete anterior a 0021 leía la columna `knowledge_base_id` inexistente. Un fallo de migración tras el rename dejaba carpeta. Ahora la copia se migra en staging.
2. **Encontrado y corregido.** Un fallo después del rename (`ensure_project_layout` o la lectura del registro) dejaba `projects/<id>/` sin registrar. Ahora el registro se lee antes del rename y la carpeta final se borra si el layout falla.
3. **Paquetes anteriores a 0021.** No traen identidad: preserve no tiene nada que conservar, y la identidad se asigna al importar (cada instalación obtiene un kb distinto). La segunda importación choca por id, no por identidad.
4. **Proyectos ya copiados antes de este incremento** con "Importar como copia" (Ronda 88) comparten kb con su original tras 0021. No bloquean nada existente, pero cualquier preserve futuro de ese kb chocará. Pendiente de decisión NEXOM si se quiere un diagnóstico o una reparación.
5. **El bloqueo es por instalación** (`base_dir`). Dos instalaciones distintas no se excluyen, y no lo necesitan. En sistemas de archivos de red, `flock` puede no ser fiable. Fuera del alcance de escritorio.
6. **La migración 0017 preexistente** impide importar paquetes con códigos de caso de prueba duplicados (Prueba_A). No es una regresión y no se corrige aquí.
7. **INC01-R1 (`content_hash`)**: sin cambios; sigue pendiente de decisión antes de 01b.
