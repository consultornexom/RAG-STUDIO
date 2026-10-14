# Congelamiento del corpus UDL para el hito 01a

**Fecha y hora:** 2026-09-24T19:32:52Z
**Decisión de NEXOM (2026-09-24):** C es el corpus principal, B el secundario y A el canario de migración. Los tres se congelan por hash y no se consultan hasta el inicio formal de 01a.
**Método:** solo se calcularon hashes de archivos. No se abrió ninguna base de datos para congelar, no se copió ningún dato y no se consultó contenido.

## 1. Hashes congelados

| Id | Papel | Ubicación | Tamaño | SHA-256 |
|---|---|---|---|---|
| C | **Corpus principal**: INC01-R6, volumen y OCR | `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/Prueba_B_Cobertura_OCR_25_programas.agentproj` | 60 679 116 B | `091573130ecf06bbb6f9948d501cf556500d3dec6da485ffe6e1e694b5b4eaa7` |
| B | **Corpus secundario**: contraste con otro paquete real | `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/Prueba_A_E2E_Oferta_Academica_UDL.agentproj` | 11 316 381 B | `e7d81510240ade50eb834fe4a752245cff280c537750f5b1d4e24d7c4e0f4ebe` |
| A | **Canario de migración**: proyecto instalado en esquema `0020` | `data/projects/42ac4489-e6c6-4185-b912-7e8540f69f54/` ("AGENTE UDL") | 21 archivos | Inventario: `A_AGENTE_UDL_SHA256SUMS_2026-09-24.txt`. SHA-256 del inventario: `d6130f8d9438e322315d0f4e02c1796232a87f587324de7b9b6c2bc9759ccc57`. `project.db`: `4b4bac22f7f940eb06ec18a9ef17177a3208a64c464eea805be352b30e47e925` (425 984 B, modificado por última vez el 2026-08-21) |

Las rutas son relativas a la raíz de RAG Studio.

**A es un directorio vivo.** Sus 21 archivos incluyen `project.db`, el índice Qdrant, una fuente original y 16 archivos `.fuse_hidden*`, que son residuos del sistema de archivos. El inventario excluye `project.db-shm` y `project.db-wal`, porque SQLite los maneja como transitorios. Al iniciar 01a se tomará la copia de trabajo de A y se comparará con este inventario. Si difiere porque la aplicación se usó entretanto, se registra un congelamiento nuevo con su justificación antes de medir.

## 2. Incidencia registrada: archivos auxiliares de SQLite en A

**Estado: CERRADA como observación procedimental, sin impacto lógico** (dictamen de NEXOM del 2026-09-24). No hay corrupción del corpus ni modificación lógica de datos.

En sesiones anteriores, la versión de Alembic de A (`0020`) se leyó abriendo `project.db` con `mode=ro`. En modo WAL, esa apertura crea o actualiza `project.db-shm` y `project.db-wal` aunque no escriba en la base. Sus fechas de modificación (2026-09-24 13:14 y 13:19, hora local) coinciden con esas lecturas.

- `project.db` **no cambió**: su fecha de modificación sigue siendo 2026-08-21 y su hash es el de la tabla.
- `project.db-wal` mide 0 bytes, así que no contiene transacciones pendientes.
- No se eliminó nada.

Se reprodujo en una base sintética: `mode=ro` crea `-shm` y `-wal`, y `mode=ro&immutable=1` no crea ninguno.

**Precaución con `immutable=1`.** Solo es correcto sobre una copia realmente inmóvil y consistente. `immutable=1` le indica a SQLite que el archivo no cambiará, y puede hacer que ignore actividad en el WAL. **Nunca se usa sobre una base viva.**

### 2.1 Obtención de la copia consistente de A (al iniciar 01a)

1. Cerrar RAG Studio y cualquier proceso que tenga abierto el proyecto.
2. Confirmar que no hay escritores activos: ningún proceso con `project.db` abierto.
3. Usar preferentemente uno de estos dos mecanismos, que producen una copia transaccionalmente consistente:
   - la API de respaldo de SQLite (`sqlite3.Connection.backup`), con la base de origen abierta en `mode=ro`, **sin** `immutable`;
   - el respaldo de la aplicación (`BackupProject`). Antes de empaquetar hace `PRAGMA wal_checkpoint(TRUNCATE)` sobre la base viva (`infrastructure/filesystem/packager.py:50-66`) y excluye los archivos `-wal`/`-shm`/`-journal`. Es una escritura de consolidación sobre el original: con el WAL en 0 bytes no cambia datos, pero debe registrarse.
4. Si se hace una copia física, confirmar antes que el WAL está vacío o consolidado: `project.db-wal` de 0 bytes, o un checkpoint hecho por la propia aplicación.
5. Crear la copia fuera de `data/`.
6. Calcular el hash de la copia.
7. Solo entonces abrirla con `mode=ro&immutable=1`.

Los 16 archivos `.fuse_hidden*` de A indican que en algún momento hubo archivos eliminados que un proceso mantenía abiertos. **No se borran a mano.** Antes de copiar A hay que asegurarse de que los procesos relacionados están cerrados.

El congelamiento de la sección 1 vale como **referencia física**. La copia consistente creada al iniciar 01a será la **línea base lógica definitiva** de A.

## 3. Línea base anterior a 0021 para B y C

La versión de Alembic interna de B y C no se ha inspeccionado. Al iniciar 01a:

1. Extraer una copia desechable de cada `.agentproj`.
2. Si su `project.db` está antes de `0020`, llevar esa copia a `0020` con la versión vigente de RAG Studio y verificarla.
3. Congelar el resultado como línea base anterior a 0021. Se registran dos hashes: el del `.agentproj` original (tabla de la sección 1), que no se sustituye, y el del `project.db` ya en `0020`, como nueva línea base.
4. Ejecutar `0021` solo sobre esa línea base.

Así, un fallo de una migración anterior no se atribuye a `0021`.
