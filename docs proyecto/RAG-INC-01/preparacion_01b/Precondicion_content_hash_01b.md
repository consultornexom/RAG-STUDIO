# RAG-INC-01b — Precondición obligatoria: `content_hash` (INC01-R1)

Estado: **documentada; se implementa junto con el exportador NKP de 01b** (todavía no autorizado).

## Motivo

El contrato NEXOM Knowledge Package v1.0.0 define

```
source.id = uuid5(lineage_id, version_key)
version_key = "content:<content_hash>"                      si hay hash
            = "noncontent:<title>|<source_type>|<updated_at>" si no
```

Sin `content_hash`, el `source.id` portable cambia al editar cualquier dato de la fuente o al validarla. NEXOM eligió rellenar los hashes heredados (opción B) con el servicio explícito `DocumentService.backfill_content_hashes` (acción "Completar huellas de contenido…" en la pestaña Fuentes).

## Gate del exportador (01b)

Antes de escribir nada, el exportador comprueba el `project.db` de la instantánea:

1. **Fuente basada en archivo con `content_hash` NULL → no exportar NKP.**
   - Son basadas en archivo todos los tipos salvo `api` y `base_de_datos`.
2. **`source.id` portable duplicado dentro de la instantánea → no exportar NKP.**
   - Se recalcula con la fórmula del contrato.
   - Cubre las colisiones `colisión_mismo_linaje` que el relleno deja sin resolver a propósito.

En ambos casos:
- es un error tipado;
- la exportación queda sin efectos (no se crea el paquete);
- lista las fuentes implicadas;
- muestra el mensaje: **"rellene huellas y publique una instantánea nueva"**.

## Instantáneas

- El relleno trabaja sobre el proyecto vivo. **Nunca modifica instantáneas publicadas**: son inmutables, y el exportador lee el `project.db` de la instantánea.
- Después del relleno hay que **publicar una instantánea nueva** antes de la primera exportación NKP.
- Las instantáneas anteriores al relleno no pasarán el gate (punto 1).
