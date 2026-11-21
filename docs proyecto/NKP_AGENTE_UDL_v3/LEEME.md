# Exportación NKP v1.0.0 CORE — AGENTE UDL, instantánea v3

**Herramienta de operación:** `exportar_nkp_instantanea.py`. No es código del producto: usa el exportador existente tal cual, incluida su compuerta de conformidad.

**Garantías:**
- **No modifica nada:** no publica instantáneas, no abre la instalación con la aplicación (no aplica migraciones) y no modifica el proyecto ni la instantánea.
- **Huella:** la calcula antes y después; si cambia, falla.
- **Escritura:** solo escribe en la carpeta `--salida`, que debe ser nueva.

## Requisitos

Ejecutar en la máquina donde está la instalación de RAG Studio que contiene AGENTE UDL (`RAGSTUDIO_HOME`), con:
- el entorno virtual de RAG Studio;
- el código en un commit que incluya esta herramienta.

No requiere dependencias nuevas: `rfc8785`, `jsonschema` y `rfc3339-validator` ya están en `requirements.txt`.

## Paso 1: verificar (sin entregar nada)

```bat
cd <carpeta de RAG Studio>
python "docs proyecto\NKP_AGENTE_UDL_v3\exportar_nkp_instantanea.py" verificar ^
  --instalacion "<RAGSTUDIO_HOME>" ^
  --project-id b17cc73c-16f1-4b76-a4e0-7711108a68c9 --version 3 ^
  --huella sha256:ec1f84eca2418a470b8151f0dbc4bb99332096f9b78a5d001e0c9a337eb258fd ^
  --salida "C:\temp\nkp_udl_v3_verificacion"
```

**Resultado esperado:** `PRECONDICIONES: OK` y `verificacion.json` con:
- el **snapshot_id real** de la v3 y la lista de instantáneas registradas;
- la huella calculada y la declarada;
- las precondiciones del exportador:
  - migración 0021 y `knowledge_base_id`;
  - fuentes de archivo sin `content_hash` (debe ser 0);
  - índice;
- conteos: fuentes, fragmentos, intenciones y reglas;
- el procedimiento guardado en la instantánea (debe decir `r106`);
- un ensayo completo del exportador, con un tenant de prueba que se descarta: `compuertas: PASS` y conformidad `0 errores`.

**Si dice `DETENIDO (precondición)`:** no continuar e informar el mensaje. Si la única salida fuera publicar otra instantánea, requiere autorización.

## Paso 2: exportar (con el tenant confirmado y el snapshot_id del paso 1)

```bat
python "docs proyecto\NKP_AGENTE_UDL_v3\exportar_nkp_instantanea.py" exportar ^
  --instalacion "<RAGSTUDIO_HOME>" ^
  --project-id b17cc73c-16f1-4b76-a4e0-7711108a68c9 --version 3 ^
  --snapshot-id <snapshot_id del paso 1> ^
  --huella sha256:ec1f84eca2418a470b8151f0dbc4bb99332096f9b78a5d001e0c9a337eb258fd ^
  --tenant <tenant confirmado> ^
  --salida "C:\temp\nkp_udl_v3"
```

**Entrega**, en `--salida`:

| Archivo | Contenido |
|---|---|
| `nexom-knowledge-package-<id>.zip` | El paquete |
| `nexom-knowledge-package-<id>.content.sha256` | Sidecar con el `content_digest` |
| `validacion_oficial.txt` | Salida completa del validador oficial v1.0.0 (debe terminar en `ERRORES: 0`) |
| `trazabilidad.json` | Ver detalle abajo |

**Contenido de `trazabilidad.json`:**
- **Relación de identidades:** `snapshot_id` → huella de la instantánea → `package_id` y `content_digest`.
- **Datos del paquete:** SHA-256 del ZIP y del sidecar; manifest (`schema_version 1.0.0`, `profile CORE`, versión, ids, conteos, omisiones).
- **Validación:** el índice de RAG Studio como referencia y las comprobaciones, con resultado `PASS` o `FAIL`.

**Determinismo:** repetir la exportación con la misma instantánea y el mismo tenant produce el mismo ZIP byte a byte.
