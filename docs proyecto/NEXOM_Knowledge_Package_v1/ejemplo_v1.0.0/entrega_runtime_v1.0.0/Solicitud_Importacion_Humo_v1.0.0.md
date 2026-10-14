# Solicitud de importación de humo — NEXOM Knowledge Package v1.0.0

**De:** RAG Studio
**Para:** NEXOM Agent Runtime, a la atención del responsable del Runtime
**Fecha:** 2026-09-24 (revisión 3: entrega autocontenida en `entrega_runtime_v1.0.0/` y precisión sobre la prueba de R-4)
**Referencia:** Declaración de aceptación v1.0.0, sección 10, paso 4 ("se ejecutan el validador, la suite 20/20 y la importación de humo")

## 1. Objeto

Solicitamos importar el paquete de ejemplo `1.0.0` en Agent Runtime y emitir un informe con el resultado. Con el PASS de esta importación se completa el paso 4 de la secuencia firmada. Solo entonces RAG Studio inicia formalmente el hito 01a de RAG-INC-01.

No es una repetición de AR-INC-00. El contrato normativo es idéntico al aceptado. Esta prueba confirma que el ejemplo `1.0.0`, con su etiqueta de versión y AC-003 corregidos, se importa sin cambios en el Runtime.

## 2. Paquete a importar

| Elemento | Valor |
|---|---|
| Archivo | `nexom-knowledge-package-demo-v1.0.0.zip` |
| SHA-256 del ZIP | `5dff57bb41680e2a5cf4a39b40ca99d641ef5beeda810d7bce3c1a58db91cbff` |
| `content_digest` | `2932dd2fc04bb544f6d92bad75c386bdbaf415e424212df5a670200ddbeb5102` |
| `package_id` | `urn:nexom:package:3e884f2d7c9a6f5d76ddeffda135f2db` |
| `schema_version` | `1.0.0` |
| Sidecars externos | `nexom-knowledge-package-demo-v1.0.0.content.sha256`, `nexom-knowledge-package-demo-v1.0.0.sig`, `nexom-knowledge-package-demo-v1.0.0.pubkey_DEMO.pem`, `nexom-knowledge-package-demo-v1.0.0.zip.sha256` |
| Contrato de referencia | `CONTRATO_v1.0.0_SHA256SUMS`: copia byte a byte de `contrato_v1.0.0/SHA256SUMS`, el inventario de los 16 artefactos normativos. SHA-256 = `863844f7b6f264cfdc45974b9a9f0ab4e92a830d01b70e9634958fde6b675208` |
| Manifiesto de entrega | `MANIFIESTO_ENTREGA_v1.0.0.sha256`: SHA-256 de los otros siete archivos de la entrega (sección 2.1) |

Antes de importar, el Runtime debe comprobar que el ZIP recibido tiene exactamente el SHA-256 indicado. Si no coincide, no debe importarlo y debe informarlo.

### 2.1 Archivos entregados

La entrega es la carpeta autocontenida `entrega_runtime_v1.0.0/`, sin subcarpetas ni rutas relativas hacia fuera de ella. Contiene **ocho archivos**. El manifiesto cubre **siete**, porque no puede cubrirse a sí mismo:

| Archivo | Contenido | En el manifiesto |
|---|---|---|
| `nexom-knowledge-package-demo-v1.0.0.zip` | Paquete a importar | Sí |
| `nexom-knowledge-package-demo-v1.0.0.content.sha256` | `content_digest` | Sí |
| `nexom-knowledge-package-demo-v1.0.0.sig` | Firma Ed25519 con clave DEMO | Sí |
| `nexom-knowledge-package-demo-v1.0.0.pubkey_DEMO.pem` | Clave pública DEMO | Sí |
| `nexom-knowledge-package-demo-v1.0.0.zip.sha256` | SHA-256 de los bytes del ZIP | Sí |
| `CONTRATO_v1.0.0_SHA256SUMS` | Referencia contractual: inventario de los 16 artefactos normativos | Sí |
| `Solicitud_Importacion_Humo_v1.0.0.md` | Esta solicitud | Sí |
| `MANIFIESTO_ENTREGA_v1.0.0.sha256` | Inventario de los siete anteriores | No (es el propio manifiesto) |

Para verificar la entrega completa, ejecutar dentro de la carpeta:

```
cd entrega_runtime_v1.0.0
sha256sum -c --strict MANIFIESTO_ENTREGA_v1.0.0.sha256
```

Debe producir 7/7 OK. El SHA-256 del propio manifiesto se comunica por un canal separado de la entrega.

Cambio relevante respecto de rc3.2: **AC-003** usa ahora `match_policy = "contains"` con listas esperadas vacías y `must_not_retrieve = [chunk confidencial, fuente confidencial]`. Ya no debería requerir un `min_score` para aprobar.

La firma es **DEMO**. La importación prueba interoperabilidad técnica, no autenticidad productiva (F-1).

## 3. Contenido mínimo del informe del Runtime

1. Versión o commit exacto del Runtime.
2. Sistema, fecha y hora de la ejecución, y configuración relevante: modelo de embeddings, dimensiones y parámetros de recuperación.
3. SHA-256 del ZIP recibido.
4. Resultado de la verificación del hash y del análisis seguro de la estructura del ZIP **antes de materializar archivos o modificar el estado del Runtime**. Para verificar `checksums.json` y `content_digest` se inspecciona el contenido del ZIP, pero no hace falta extraerlo al sistema de archivos. También el resultado de la firma DEMO.
5. Resultado de la importación y la persistencia, incluida la integridad referencial.
6. Resultado del cierre y la reapertura de la información persistida.
7. Resultado del reembedding y la indexación, con vectores generados y chunks indexables.
8. Estado final del índice y de la activación.
9. Resultado individual de AC-001, AC-002 y AC-003.
10. Evidencia de que AC-003 aplica `must_not_retrieve`: ningún id prohibido aparece en los resultados para `user_access_level = publico`.
11. Evidencia de R-4. No basta una confirmación verbal; el informe debe incluir:
    - la jerarquía cargada desde el `access_hierarchy.json` del paquete (`order` y `rule`, tal como se leyeron);
    - el orden interpretado por el Runtime y su correspondencia posición por posición con `order`;
    - el `user_access_level` usado en AC-003 (`publico`) y el nivel que el Runtime le asignó;
    - los ids devueltos por AC-003 y la comprobación de que ninguno de `must_not_retrieve` aparece;
    - un log o una prueba que demuestre que no se usó una tabla fija de traducción.

    La prueba de dependencia del archivo se hace como **prueba controlada del componente de autorización**, no como importación de un paquete manipulado. El informe debe separar tres cosas:
    - **Paquete original:** se valida y se importa sin ninguna modificación. Sus checksums y su `content_digest` siguen coincidiendo.
    - **Jerarquía alternativa inyectada en memoria:** se entrega directamente al componente de autorización (por ejemplo, con otro orden o sin el nivel `publico`) y se muestra que su decisión cambia en consecuencia. Eso demuestra que el comportamiento depende del archivo.
    - **Integridad:** ningún archivo del paquete original ni del ZIP se modificó para la prueba. Nunca se acepta un paquete cuyo checksum no coincida.
12. Cualquier umbral de relevancia utilizado, aunque AC-003 no deba depender de él.
13. Resultado final: `PASS` o `FAIL`.

## 4. Si el resultado es FAIL

Antes de cualquier cambio, el hallazgo debe clasificarse en una de estas cuatro categorías:

| Clasificación | Consecuencia |
|---|---|
| Defecto del Runtime | Se corrige en el Runtime y se repite la importación de humo |
| Defecto del ejemplo | RAG Studio corrige el ejemplo (no normativo), se publica un nuevo hash y se repite la conformidad |
| Ambigüedad contractual | Se documenta como aclaración 1.0.x si no cambia qué paquetes son válidos; si lo cambia, como propuesta de versión |
| Incompatibilidad real del contrato | Propuesta de cambio con versión nueva, según la política de la sección 8 de la Declaración |

El contrato **no se modifica automáticamente** ante un fallo del importador.

## 5. Uso del informe

El informe recibido se archiva en `ejemplo_v1.0.0/` junto al Informe de Conformidad, con su SHA-256, y se incorpora a él. Si el resultado es PASS, RAG Studio declara completado el paso 4 de la secuencia firmada e inicia formalmente el hito 01a.
