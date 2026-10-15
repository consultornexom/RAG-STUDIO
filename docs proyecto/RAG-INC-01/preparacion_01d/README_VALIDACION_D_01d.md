# RAG-INC-01d · Fase 1: corpus D en la instalación real (macOS)

Este procedimiento lo ejecuta **NEXOM en el equipo donde vive AGENTE UDL**. El entorno de RAG Studio no tiene acceso a esa instalación.

## Garantías

- **Antes de empezar, cierre RAG Studio.**
- **No abre la instalación original con la aplicación**, así que no la migra, y **no escribe nada en ella**. Lee el `project.db` vivo y la instantánea v5 desde copias temporales.
- **No modifica instantáneas históricas.** La instantánea nueva se publica dentro de una **copia** de la instalación: `<out>/instalacion`.
- Al terminar comprueba que el original no cambió: el hash del `project.db` vivo y de su `-wal`, y la huella de la carpeta de v5.
- No toca Runtime.

## Requisitos

- El código de RAG Studio de la rama `rag-inc-01/01d`. Es el ZIP que acompaña a este documento: `RAG_STUDIO_codigo_01d_F1.zip`.
- Python ≥ 3.10 con las dependencias de `requirements.txt` de ese código. Como mínimo, las nuevas de la compuerta de conformidad:

  ```
  pip install "jsonschema==4.26.0" "rfc3339-validator==0.1.4" "rfc8785==0.1.4"
  ```

## Ejecución

```
cd <codigo_descomprimido>
python3 "docs proyecto/RAG-INC-01/preparacion_01d/preparar_candidato_D.py" \
  --instalacion-original "/Users/alejandromontesmoreno/Documents/sistemas/udl/version_beta/20261011/RAG_STUDIO_3/data_AGENTE_UDL" \
  --project-id 6073eda1-268d-48bd-8257-e6d3fef4f981 \
  --tenant nexom-udl-candidato \
  --out ~/validacion_01d/corpus_D
```

`--out` debe ser una carpeta que todavía no exista. La copia de la instalación ocupa lo mismo que el original.

## Segunda ejecución: saneamiento autorizado de D (DATA_DEFECT)

NEXOM confirmó que la intención "Consultar programa específico" declara en `optional_variables` dos códigos huérfanos, `modalidad` y `nivel_academico`: no existen como variables conversacionales. Autorizó un solo cambio, y solo en una **copia nueva**: `optional_variables` pasa de `["modalidad", "nivel_academico"]` a `[]`.

No se tocan `required_variables`, `clarifying_questions`, ejemplos, prioridad, riesgo, regla ni modo. No se crean variables.

```
python3 "docs proyecto/RAG-INC-01/preparacion_01d/preparar_candidato_D.py" \
  --instalacion-original "/Users/alejandromontesmoreno/Documents/sistemas/udl/version_beta/20261011/RAG_STUDIO_3/data_AGENTE_UDL" \
  --project-id 6073eda1-268d-48bd-8257-e6d3fef4f981 \
  --tenant nexom-udl-candidato \
  --out ~/validacion_01d/corpus_D_saneado \
  --vaciar-optional-variables-de "Consultar programa específico" \
  --optional-variables-esperadas '["modalidad", "nivel_academico"]'
```

**Orden de ejecución.** La herramienta procede así:
1. copia la instalación completa a `<out>/instalacion`;
2. aplica el saneamiento **a la copia**, todavía en 0020;
3. migra solo la copia a 0021;
4. publica una instantánea nueva en la copia;
5. exporta dos veces y aplica la compuerta 01c;
6. comprueba que el original no cambió.

**Comprobaciones del saneamiento** (`sanear_optional_variables.py`). Cualquier discrepancia aborta sin escribir:
- nunca toca una ruta dentro de la instalación original;
- debe existir exactamente 1 intención con ese nombre;
- su valor actual debe ser **exactamente** el esperado;
- los códigos que se quitan no deben existir como variables;
- después del cambio, solo cambió esa columna de esa fila (todas las demás intenciones y la tabla de variables quedan idénticas) e `integrity_check` = ok.

**Trazabilidad.** El saneamiento queda registrado en `informe_D.json → saneamiento_copia`:
- `project_id`, `intent_id` e `intent_name`;
- `optional_variables` antes y después;
- SHA-256 del `project.db` de la copia antes y después;
- `integrity_check`.

## Qué devolver a RAG Studio

1. La salida de consola completa. Termina en `PASS` o `FAIL`.
2. `~/validacion_01d/corpus_D/informe_D.json` y su SHA-256 (`shasum -a 256 informe_D.json`).
3. `~/validacion_01d/corpus_D/candidato/informe_candidato.json`.
4. El paquete candidato y su sidecar, desde `candidato/a/`: `nexom-knowledge-package-<id>.zip` y `.content.sha256`.

## Resultado esperado

**Parte 1.** Se espera:
- `alembic_vivo = 0020`: la instalación real no se migró;
- `fuentes_sin_huella = 0`;
- v5 con su carpeta física y `snapshot_identity.json` correspondiente;
- `con_0021 = false`, y por tanto las compuertas `BLOQUEADA` con `SnapshotInconsistentError`, porque v5 es anterior a las identidades persistentes. Eso confirma que v5 no se puede exportar y que hace falta una instantánea nueva.

**Parte 2.** En la copia, la instantánea nueva es la v6. El paquete debe dar:
- compuerta 01c `PASS`;
- validador firmado con `ERRORES: 0`;
- reproducibilidad `true` en todo.

**Parte 3.** `original_intacto`, todo en `true`.

Cualquier otro resultado se reporta tal cual, sin corregir nada en el original.
