# RAG-INC-01 — Preparación del hito 01a (sin inicio formal)

**Estado:** PREPARACIÓN. El hito 01a **no ha comenzado**.
**Fecha:** 2026-09-24 (revisión 3: política de colisiones de identidad, precauciones de copia de SQLite y preparación de Git)
**Condición de inicio formal:** PASS de la importación de humo del ejemplo `1.0.0` en Agent Runtime, que completa el paso 4 de la sección 10 de la Declaración firmada. Hasta entonces rige la decisión de NEXOM del 2026-09-24: se prepara sin ejecutar cambios.

> **Actualización 2026-10-14 — condición de humo SATISFECHA.** NEXOM confirmó: importación de humo **PASS / COMPATIBLE**, sin errores. Runtime commit `5db676e0e292fb09c08bb9258436829ceb28ec3a`; paquete `nexom-knowledge-package-demo-v1.0.0.zip`, SHA-256 `5dff57bb41680e2a5cf4a39b40ca99d641ef5beeda810d7bce3c1a58db91cbff`; `schema_version` `1.0.0`. Registro: `NEXOM_Knowledge_Package_v1/ejemplo_v1.0.0/Registro_Humo_Runtime_v1.0.0.md`. NEXOM autorizó **solo el cierre de precondiciones** (registro, control de versiones, addendum, corpus, línea base). La migración `0021` y cualquier cambio productivo de 01a **siguen sin autorizarse**. Estado de cada precondición: `Cierre_Precondiciones_01a.md`.

## 1. Qué incluye y qué no incluye esta preparación

**Hecho en esta preparación:**

- inventario de candidatos para la medición en UDL;
- consultas de medición redactadas (`consultas_medicion_01a.sql`), comprobadas solo contra una base sintética en memoria y no contra datos reales;
- matriz de casos de prueba;
- procedimiento de respaldo y restauración;
- criterios de PASS/FAIL;
- plantilla del informe de la puerta de 01a;
- checklist de arranque.

**No se ha ejecutado nada de lo siguiente, ni se ejecutará antes del inicio formal:**

- migración `0021`;
- cambios en entidades, repositorios o casos de uso;
- relleno de `knowledge_base_id` o de `lineage_id`;
- consultas de medición sobre bases reales o sus copias;
- pruebas que abran en escritura cualquier `project.db`;
- implementación de `preserve`, `fork` o del bloqueo entre procesos;
- creación de ramas con código.

Para confirmar que no se tocó código, se comprobó que ningún archivo bajo `domain/`, `application/`, `infrastructure/`, `ui/`, `interfaces/`, `app/`, `workers/`, `migrations/` ni `tests/` es más reciente que la publicación del contrato.

## 2. Candidatos para la medición en UDL (decisión INC01-D6)

Inventario hecho solo con lecturas de metadatos: listado de archivos, hashes y la versión de Alembic, leída con `mode=ro`. No se consultó contenido. Esa lectura de A actualizó sus archivos auxiliares `-shm`/`-wal`, sin cambiar `project.db` (`Congelamiento_Corpus_UDL.md`, sección 2).

| Candidato | Ubicación | Tamaño | Identificación |
|---|---|---|---|
| A. Proyecto instalado "AGENTE UDL" | `data/projects/42ac4489-e6c6-4185-b912-7e8540f69f54/` | 961 KB | Alembic `0020`. Proyecto pequeño; puede contener pocas fuentes |
| B. `Prueba_A_E2E_Oferta_Academica_UDL.agentproj` | `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/` | 11.3 MB | SHA-256 `e7d81510240ade50eb834fe4a752245cff280c537750f5b1d4e24d7c4e0f4ebe` |
| C. `Prueba_B_Cobertura_OCR_25_programas.agentproj` | `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/` | 60.7 MB | SHA-256 `091573130ecf06bbb6f9948d501cf556500d3dec6da485ffe6e1e694b5b4eaa7` |

**Decisión de NEXOM (2026-09-24):** los tres candidatos se usan, cada uno para una pregunta distinta, y los tres quedaron congelados por hash (`Congelamiento_Corpus_UDL.md`):

| Candidato | Papel | Pregunta que responde |
|---|---|---|
| C | Corpus principal | INC01-R6, volumen y OCR |
| B | Corpus secundario | Si los resultados se repiten en otro paquete real |
| A | Canario de migración, sobre una copia | Migración directa desde un proyecto instalado en `0020` |

Si B o C están antes de `0020`, la actualización a `0020` se hace y se congela aparte, antes de `0021` (`Congelamiento_Corpus_UDL.md`, sección 3). Así, un fallo de una migración anterior no se atribuye a `0021`.

**Lectura de bases:** toda consulta usa `mode=ro&immutable=1` y **solo sobre copias inmóviles y consistentes**, obtenidas según `Congelamiento_Corpus_UDL.md`, sección 2.1. `immutable=1` nunca se usa sobre una base viva. Con solo `mode=ro`, SQLite crea o actualiza los archivos `-shm`/`-wal`, como se observó en A. Esa incidencia quedó cerrada como observación procedimental, sin impacto lógico.

## 2 bis. Semántica de linaje no lineal (decisión de NEXOM del 2026-09-24)

> Un linaje es una familia de versiones con una raíz común; no tiene que ser una cadena estrictamente lineal. Puede contener ramificaciones, pero nunca ciclos. Todos los descendientes de la misma raíz comparten `lineage_id` y, por tanto, `logical_id`.

Controles que 01a aplica y reporta, sin corregir ni elegir nada por su cuenta:

- número de ramas por familia y de cabezas (fuentes que nadie supersede), con cuántas están `validado` (consultas 2c y 2h);
- ramas con contenidos distintos y ramas o sucesoras con contenido idéntico (consultas 2f y 2g);
- cada versión produce el `source.id` portable correcto: recomputo con `id_scheme.py`;
- ciclos prohibidos: `0021` aborta (consulta 2d, casos M-06 y M-07);
- ninguna rama se elige en silencio como "actual";
- advertencia de calidad cuando una familia tiene varias cabezas activas.

**Hallazgo que hay que resolver antes de 01b (caso M-05b).** `RegisterSource` permite registrar una sucesora con el **mismo `content_hash`** que la fuente que supersede. Solo lanza `DuplicateSourceError` cuando la fuente existente con ese hash no es la que se supersede (`application/documents/commands/register_source.py:37-40`). Esa sucesora comparte `lineage_id` con su predecesora, y con él el `version_key` (`content:<hash>`). Por eso las dos producirían el **mismo `source.id` portable**, y con textos iguales, los mismos `chunk.id`. Es decir, el paquete tendría ids duplicados.

Lo mismo ocurre entre hermanas sin `content_hash` que tengan el mismo título, tipo y `updated_at`. La prueba sintética de la consulta 2f muestra además que predecesora y sucesora pueden diferir en `access_level`.

**Política aprobada por NEXOM (2026-09-24), fijada ahora y sin esperar la medición:**

> RAG-INC-01 rechaza cualquier exportación en la que dos registros produzcan el mismo `source.id` o el mismo `chunk.id` portable.

| Opción | Decisión |
|---|---|
| a. Rechazar la exportación | **Aprobada** |
| b. Deduplicar condicionalmente | **Descartada.** Pierde `origin_id` y trazabilidad local. Puede dejar una sucesora cuyo `supersedes_source_id` apunte a su propio id portable, es decir, una autosupersesión. Dos registros aparentemente iguales pueden ser eventos históricos distintos. Cualquier diferencia futura de metadatos o de acceso convertiría la deduplicación en una decisión de seguridad |
| c. Cambiar `version_key` | **Diferida** a una versión contractual nueva (`id_scheme.py` es normativo) |

**Error tipado: `PortableIdentityCollisionError`.** Debe incluir:

- tipo de entidad (`source` o `chunk`);
- id portable calculado;
- ids locales implicados;
- `lineage_id`;
- `version_key`;
- campos exportables que difieren entre los registros;
- acciones sugeridas (corregir o reprocesar la fuente, retirar la sucesora redundante, o elevar una propuesta de versión contractual).

La detección se hace **antes de escribir cualquier archivo del paquete**, así que nunca queda una exportación parcial.

La medición de UDL (consultas 2f y 2g) ya no decide la política: dice cuántos casos hay y cómo remediarlos. Si encuentra colisiones, **01b queda bloqueado** hasta corregir los datos o aprobar una versión nueva del contrato. M-05b no hace fallar 01a, porque 01a mide y migra identidades pero no exporta.

## 3. Procedimiento de respaldo y restauración

Se aplica a cada copia de trabajo:

1. Copiar la fuente congelada (el `.agentproj` o el directorio del proyecto) a un directorio de trabajo desechable fuera de `data/`.
2. Calcular el SHA-256 del original y de la copia, y comprobar que coinciden.
3. Guardar un segundo respaldo intacto en un directorio de respaldos con permisos de solo lectura.
4. Registrar en el inventario de copias: origen, hash, destino, fecha y responsable (checklist, sección 8).
5. **Restaurar** es descartar el directorio de trabajo y volver a copiar desde el respaldo, verificando otra vez el hash. Nunca se usa `alembic downgrade`: `0021` lo bloquea por diseño (Alcance, hito 01a).
6. Terminadas las pruebas, confirmar que el hash del original congelado no cambió.

## 4. Matriz de casos de prueba del hito 01a

Se construyen con bases sintéticas creadas por las pruebas, más las copias de UDL solo para medir.

| Id | Área | Caso | Resultado esperado |
|---|---|---|---|
| M-01 | Migración | Base `0020` vacía | Se aplica sin errores; columnas `NOT NULL`, `knowledge_base_id` único e índice en `lineage_id` |
| M-02 | Migración | Fuentes sin supersesión | Cada fuente recibe su propio `lineage_id` |
| M-03 | Migración | Cadena lineal A←B←C | Las tres comparten el mismo `lineage_id` |
| M-04 | Migración | Referencia rota (apunta a un id inexistente) | La fuente es raíz de su cadena y queda registrada en el log |
| M-05 | Migración | Ramificación (A superseded por B y por E) | A, B y E comparten `lineage_id`; se reportan la ramificación y el número de cabezas |
| M-05b | Migración / identidad | Sucesora con el mismo `content_hash` que su predecesora, o dos sucesoras con contenido idéntico | Se documenta que producen el mismo `source.id` portable y se listan los pares. Con cualquier colisión, 01b queda bloqueado hasta remediar los datos (sección 2 bis). No hace fallar 01a |
| M-06 | Migración | Ciclo X↔Y | Aborta y hace rollback completo, sin cambios parciales |
| M-07 | Migración | Auto-ciclo S→S | Aborta y hace rollback completo |
| M-08 | Migración | `downgrade()` sin bandera de pruebas | Se niega con un error explícito |
| M-09 | Migración | Copia real de UDL | Se aplica; cero identidades nulas; cadenas consistentes |
| R-01 | Dominio | `RegisterSource` con `supersedes_source_id` válido | Copia el `lineage_id` de la fuente anterior |
| R-02 | Dominio | `RegisterSource` sin supersesión | Genera un `lineage_id` nuevo |
| R-03 | Dominio | `CloneProject` | Genera un `knowledge_base_id` nuevo |
| P-01 | Importación | `preserve` sin colisión | Conserva ambas identidades |
| P-02 | Importación | `preserve` con colisión contra un proyecto activo | Lanza `KnowledgeBaseIdentityCollisionError` sin modificar datos |
| P-03 | Importación | `preserve` con colisión contra un proyecto archivado | Igual que P-02 |
| P-04 | Importación | `fork` sin colisión | Regenera las identidades y conserva la estructura de supersesión |
| P-05 | Importación | `fork` con colisión | Igual que P-04 |
| P-06 | Importación | Sin `identity_policy` | Aborta antes de tocar datos |
| P-07 | Importación | `fork` con `project_id` existente y sin `new_project_id` | `ProjectIdCollisionError` (regla vigente) |
| L-01 | Bloqueo | Dos importaciones concurrentes con `preserve` | Exactamente una se completa y la otra da colisión |
| L-02 | Bloqueo | Bloqueo retenido más allá del tiempo máximo | `ImportLockTimeoutError` sin modificar datos |
| L-03 | Bloqueo | Terminación abrupta del proceso que retiene el bloqueo | La siguiente importación obtiene el bloqueo sin intervención |
| L-04 | Bloqueo | `project.db` instalado ilegible | Aborta (fail-closed) |
| L-05 | Bloqueo | Colisión detectada | Queda en el log técnico con `knowledge_base_id`, el proyecto existente y la política |
| X-01 | Medición | INC01-R6 en UDL | Número de chunks no imagen con texto vacío (consultas 1a y 1b) |
| X-02 | Medición | INC01-R1 en UDL | Número de fuentes sin `content_hash` (consulta de R1) |
| X-03 | Medición | Estructura de linajes en UDL | Raíces, referencias rotas, ramificaciones, ciclos y profundidad máxima (consultas 2a a 2e); sucesoras con contenido idéntico, hermanas en colisión y familias con varias cabezas (2f a 2h) |

## 5. Criterios de PASS/FAIL de la puerta de 01a

**PASS** si se cumple todo lo siguiente:

- los casos M-01 a M-09, R-01 a R-03, P-01 a P-07 y L-01 a L-05 dan el resultado esperado;
- las mediciones X-01 a X-03 están completas y documentadas;
- la suite existente de RAG Studio, `ruff` y `mypy` no cambian de resultado;
- los hashes de los originales congelados no cambiaron;
- ninguna prueba abrió en escritura un `project.db` que no fuera una copia desechable.

**FAIL** si falla cualquiera de esos casos o si una migración deja cambios parciales.

**Resultado de X-01 (INC01-R6).** No condiciona el PASS de 01a, pero sí decide si puede iniciarse 01b:

- cero chunks afectados: 01b puede solicitarse;
- uno o más: el informe los lista y NEXOM decide entre corregir o reprocesar las fuentes, o elevar una propuesta contractual si el caso es legítimo. RAG-INC-01 no excluye chunks silenciosamente.

**Ramificaciones.** Están admitidas (sección 2 bis). El informe reporta ramas y cabezas activas como advertencia de calidad.

**Colisiones de `source.id` o `chunk.id` (consultas 2f y 2g, caso M-05b).** No condicionan el PASS de 01a. Si hay alguna, 01b no puede iniciarse hasta que se remedien los datos, porque la política ya fijada es el rechazo (sección 2 bis).

**Criterios que se trasladan a 01b** (se agregan a los de aceptación del Alcance): unicidad completa de `source.id` y unicidad completa de `chunk.id` en todo paquete exportado. Cualquier violación produce `PortableIdentityCollisionError` antes de escribir.

**Identidad del "Consultor NEXOM": resuelta.** El 2026-09-24 quedó confirmado en el Registro de firma que es Rafael González, Socio Consultor. Ya no condiciona la puerta de 01a. El expediente de firma está cerrado y el Registro, congelado, con SHA-256 final `c5511924ab45a58b88fbcf9b94f5c370170a59bc201164b339e60a1d94d206c5`. Este hash se incorpora al informe de puerta de 01a.

## 6. Plantilla del informe de la puerta de 01a

```
# Informe de puerta — RAG-INC-01, hito 01a
Fecha / responsable / commit:
Inicio formal habilitado por: informe de humo del Runtime (hash: …, resultado: PASS)

1. Corpus usado: candidato, hash del original congelado, hash de la copia
2. Migración 0021: resultado M-01…M-09 y log de relleno (referencias rotas, ramificaciones)
3. Dominio: R-01…R-03
4. Importación: P-01…P-07
5. Bloqueo y colisiones: L-01…L-05
6. Mediciones: X-01 (INC01-R6, con detalle), X-02 (INC01-R1), X-03 (cadenas)
7. Regresión: suite, ruff, mypy (antes y después)
8. Integridad de los originales: hashes antes y después
9. Dependencias nuevas, si las hubo (p. ej. para el bloqueo)
10. Resultado: PASS / FAIL
11. Recomendación sobre 01b (condicionada a X-01)
```

## 7. Secuencia después del PASS de humo

1. Congelar los tres candidatos: comprobar que coinciden con `Congelamiento_Corpus_UDL.md` o volver a congelarlos con justificación.
2. Obtener la línea base de la suite, `ruff` y `mypy`.
3. Crear el punto de partida del código: respaldo fechado del árbol, `git init` local sin remoto, commit de línea base, etiqueta `rag-inc-01-baseline` y rama `rag-inc-01/01a` (`Procedimiento_Git_01a.md`).
   Primero, obtener la copia consistente de A (`Congelamiento_Corpus_UDL.md`, sección 2.1).
4. Medir X-01, X-02 y X-03 sobre copias, antes de modificar datos.
5. Ejecutar `0021` sobre copias; en B y C, sobre su línea base en `0020`.
6. Repetir las mediciones.
7. Ejecutar la matriz de casos.
8. Emitir el informe de puerta.
9. Someterlo a aprobación. No se inicia 01b sin ella.

## 8. Checklist de arranque (para el día del inicio formal)

- [x] Resultado de humo del Runtime recibido con PASS (2026-10-14, `Registro_Humo_Runtime_v1.0.0.md`). Pendiente: archivar el informe técnico completo cuando se reciba
- [x] Informe de Conformidad actualizado con el resultado del humo (sección 5)
- [x] Paso 4 de la sección 10 de la Declaración declarado completo
- [ ] Corpus UDL elegido por NEXOM y su hash registrado
- [ ] Respaldos creados, con hashes verificados y en directorio de solo lectura
- [ ] Inventario de copias completo (sección 3, paso 4)
- [ ] Línea base de la suite, `ruff` y `mypy` registrada antes de cualquier cambio
- [ ] **Control de versiones inicializado**, según `Procedimiento_Git_01a.md`, **después del PASS de humo**. Antes del PASS solo se dejan preparados el `.gitignore` propuesto y el procedimiento; no se ejecuta `git init`
- [ ] Consultas de medición revisadas
