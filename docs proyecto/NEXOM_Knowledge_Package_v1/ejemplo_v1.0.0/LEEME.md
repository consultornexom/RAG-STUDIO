# NEXOM Knowledge Package v1.0.0 — paquete de ejemplo y conformidad

Paquete de ejemplo del contrato NEXOM Knowledge Package **v1.0.0**, publicado tras la *Declaración de aceptación* firmada el 2026-09-24 (sección 5). Ni este paquete ni los scripts de esta carpeta son normativos. El contrato normativo está en `../contrato_v1.0.0/`: 16 artefactos, verificables con `SHA256SUMS`.

## Contenido

```
example_package/                          Paquete CORE: 13 archivos internos
                                           (12 de datos y manifiesto + checksums.json)
delivery/                                 Sidecars externos:
  nexom-knowledge-package-demo-v1.0.0.content.sha256   content_digest
  nexom-knowledge-package-demo-v1.0.0.sig              firma Ed25519 con clave DEMO
  nexom-knowledge-package-demo-v1.0.0.pubkey_DEMO.pem  clave pública DEMO
  nexom-knowledge-package-demo-v1.0.0.zip.sha256       SHA-256 de los bytes del ZIP
nexom-knowledge-package-demo-v1.0.0.zip   El mismo paquete como ZIP
generate_example.py                       Generador del ejemplo (no normativo)
qa/test_negative_cases.py                 Suite automatizada: 19 casos negativos + 1 caso base
requirements.lock.txt                     Dependencias fijadas del validador
verificar_conformidad.sh                  Verificación reproducible completa
SHA256SUMS_EJEMPLO                        Hashes de todo lo anterior
Informe_Conformidad_v1.0.0.md             Resultado de la verificación
```

## Diferencias respecto del paquete auditado rc3.2

1. **Etiqueta de versión.** `manifest.schema_version = "1.0.0"`. `exporter_version`, los nombres de sidecars, `key_id` y `signer` usan `v1.0.0`.
2. **AC-003** pasa de `match_policy = "exact"` con listas esperadas vacías a `contains` + `must_not_retrieve` (acción A-3 de la Declaración). El caso ahora verifica solo la propiedad de denegación y no depende de ningún umbral de relevancia del consumidor.
3. En consecuencia, `checksums.json`, `content_digest`, la firma DEMO y los sidecars son nuevos.

El paquete `v1.0-rc3.2` (ZIP con SHA-256 `78db21b1…81cc`) no se modificó: sigue archivado como evidencia de aceptación.

## Cómo verificar

```bash
pip install -r requirements.lock.txt
bash verificar_conformidad.sh
```

El script verifica los hashes del contrato y del ejemplo, y ejecuta el validador de referencia sobre el directorio y el ZIP, con y sin `--trusted-key-id`. Espera 0 errores en los cuatro casos. Después corre la suite de 19 casos negativos más el caso base, que debe reportar `RESUMEN: 20/20 casos correctos`. Termina con `CONFORMIDAD v1.0.0: PASS` y código de salida 0, o con `FAIL` y código 1 si cualquier comprobación falla.

## Límites

La clave de firma es **DEMO**. Estos paquetes tienen integridad técnica, pero no autenticidad del productor, y **no deben presentarse como entregas productivas autenticadas** hasta resolver F-1 (Declaración, sección 3.2).
