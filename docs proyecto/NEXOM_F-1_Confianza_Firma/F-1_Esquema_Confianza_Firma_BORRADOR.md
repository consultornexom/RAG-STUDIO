# F-1 — Esquema de confianza y firma productiva del NEXOM Knowledge Package

**Estado:** BORRADOR v0.1 para trabajo conjunto RAG Studio + Agent Runtime. No es una especificación aprobada ni autoriza implementación.
**Revisión:** v0.1 con observaciones de NEXOM del 2026-09-24 (Anexo A). Pasa a v0.2 cuando la sesión conjunta cierre las decisiones de arquitectura del Anexo A y las F1-D1 a F1-D8.
**Fecha:** 2026-09-24
**Origen:** asunto diferido F-1 de la Declaración de aceptación v1.0.0 (sección 3.2) y condición de firma "Estado productivo".
**Principio:** F-1 es una especificación conjunta. Ninguna de las partes la implementa unilateralmente. Mientras F-1 no esté aprobado, los paquetes tienen integridad técnica, pero no autenticidad del productor, y no se presentan como entregas productivas autenticadas.

---

## 1. Punto de partida: qué garantiza hoy v1.0.0 y qué no

| Aspecto | Estado en v1.0.0 |
|---|---|
| Qué se firma | La cadena `checksums_json_hash + ":" + content_digest` (Ed25519). |
| Qué queda cubierto por la firma | Todo el contenido del paquete. `content_digest` incorpora `checksums.json`, que cubre `manifest.json`, y con él `package_id` y `schema_version`. |
| Qué **no** queda cubierto | Los campos `key_id`, `signer` y `signed_at` del propio sidecar `.sig`. Pueden cambiarse sin invalidar la firma. Por eso hoy `signed_at` no sirve para decidir sobre expiración o revocación, y `signer` es solo informativo. |
| Ubicación de la firma | Sidecar externo al paquete, sin circularidad. Es correcto y se conserva. |
| Clave pública | Se entrega por línea de comandos (`--public-key`); `--trusted-key-id` es solo defensa en profundidad. No existe almacén de confianza. |
| Formato del sidecar | `signature.schema.json` es estricto (`additionalProperties: false`, `algorithm = ed25519`). Añadirle campos invalidaría sidecars `1.0.0`. |

**Consecuencia de diseño:** F-1 no debe alterar el sidecar `.sig` de v1.0.0. Se propone un **sidecar nuevo y adicional** (sección 4). Como los sidecars son externos al paquete, un consumidor `1.0` que no lo conozca no se ve afectado. Esto encaja en una versión **1.1.0** del contrato: artefacto nuevo opcional más una opción nueva en el validador, sin cambiar qué paquetes `1.0.0` son válidos.

## 2. Autoridad emisora y jerarquía de claves

- **Raíz de confianza NEXOM** (clave raíz, fuera de línea). Solo firma el almacén de confianza (sección 5). Nunca firma paquetes.
- **Claves de firma operativas**, una por productor y entorno, por ejemplo `nexom-ragstudio-prod-2026-01`. Firman paquetes. Las emite NEXOM y se registran en el almacén de confianza.
- **Separación de entornos:** `demo`, `test` y `prod` son entornos distintos, con claves distintas. Un consumidor en `prod` rechaza toda clave que no sea `prod`.

*Decisión abierta F1-D1:* quién custodia la raíz y con qué procedimiento de ceremonia (dos personas, soporte fuera de línea).

## 3. Custodia de la clave privada operativa

- Nunca se guarda dentro de un proyecto, un paquete, `docs proyecto/` ni el repositorio.
- En RAG Studio (aplicación de escritorio, puede operar sin conexión), la opción base es el almacén de credenciales del sistema operativo. Un HSM o token es opcional para clientes que lo exijan.
- La firma es una operación explícita y auditada (sección 9), separada de la exportación: exportar no implica firmar.

*Decisión abierta F1-D2:* si RAG Studio firma localmente o envía el `content_digest` a un servicio de firma de NEXOM.

## 4. Objeto firmado y formato: sobre de firma v2

Nuevo sidecar `<paquete>.nkpsig.json`, externo al paquete y definido por un schema nuevo `signature_envelope.schema.json`:

```json
{
  "format": "nkp-signature-envelope/1",
  "statement": {
    "content_digest": "…",
    "checksums_json_hash": "…",
    "package_id": "urn:nexom:package:…",
    "schema_version": "1.0.0",
    "key_id": "nexom-ragstudio-prod-2026-01",
    "environment": "prod",
    "signer": "RAG Studio / <organización>",
    "signed_at": "2026-10-01T12:00:00Z"
  },
  "algorithm": "ed25519",
  "signature": "<base64 de Ed25519 sobre RFC8785(statement)>"
}
```

- Se firma la **serialización RFC 8785 de `statement`**, con la misma canonicalización que ya usa `id_scheme.py`. Así `key_id`, `environment`, `signer` y `signed_at` quedan autenticados, lo que cierra la brecha de la sección 1.
- `package_id` y `schema_version` se repiten en `statement` para que el verificador los compare con el `manifest.json` antes de extraer.
- **Sin circularidad:** el sobre firma `content_digest`, nunca a sí mismo. `checksums.json` no lo incluye.
- **Volver a firmar no cambia el paquete:** pasar de DEMO a producción es emitir un sobre nuevo; `content_digest` y el ZIP no cambian.
- El `.sig` de v1.0.0 puede seguir acompañando al paquete por compatibilidad, pero en `prod` solo cuenta el sobre v2.

*Decisión abierta F1-D3:* si se admite más de una firma (productor más un revisor NEXOM) desde la primera versión.

## 5. Almacén de confianza (trust store)

Archivo `nkp_trust_store.json`, distribuido fuera de banda, versionado y **firmado por la raíz NEXOM**:

| Campo por clave | Descripción |
|---|---|
| `key_id` | Identificador único |
| `public_key` | Ed25519 en base64 (32 bytes) |
| `environment` | `demo` \| `test` \| `prod` |
| `owner` | Productor autorizado (p. ej. RAG Studio de una organización concreta) |
| `valid_from` / `valid_until` | Ventana en la que la clave puede firmar |
| `status` | `active` \| `retired` \| `revoked` |
| `retired_at` | Solo si `retired`: momento desde el que la clave deja de firmar |
| `revoked_at` / `revocation_reason` | Solo si `revoked` |

Campos globales: `store_version` (monótono), `issued_at`, `next_update_before` y la firma de la raíz. El Runtime rechaza un almacén con `store_version` menor que el último aceptado, lo que evita que se reinstale uno anterior.

## 6. Reglas de verificación (fail-closed, antes de importar)

El consumidor en `prod` acepta un paquete solo si **todas** estas reglas se cumplen, en este orden:

1. El almacén de confianza tiene firma válida de la raíz y no está vencido (`next_update_before`).
2. El sobre cumple `signature_envelope.schema.json`.
3. `key_id` existe en el almacén con `environment = prod`. Según su `status`: si es `active`, se acepta; si es `retired`, solo si `signed_at` es anterior a `retired_at`; si es `revoked`, solo si `signed_at` es anterior a `revoked_at` (regla 4). *Decisión abierta F1-D8:* si, en su lugar, una revocación invalida todas las firmas de la clave, con independencia de la fecha.
4. `signed_at` está dentro de `[valid_from, valid_until]` de la clave y, si fue revocada, antes de `revoked_at`.
5. La firma Ed25519 sobre RFC 8785(`statement`) es válida.
6. `content_digest` y `checksums_json_hash` coinciden con los recalculados del paquete, con el validador de referencia.
7. `package_id` y `schema_version` del sobre coinciden con `manifest.json`.
8. El paquete pasa el validador de referencia con 0 errores.

Cualquier fallo rechaza la importación sin alterar el estado del Runtime. No hay degradación silenciosa a "importar sin verificar".

## 7. Rotación, expiración, revocación y compromiso

- **Rotación planificada:** se emite la clave nueva, se publica un almacén con ambas y se marca la anterior como `retired`. Los paquetes firmados antes de retirarla siguen siendo verificables.
- **Expiración:** `valid_until` obligatorio, con duración a acordar (F1-D4).
- **Compromiso de una clave:** se marca `revoked` con un `revoked_at` conservador (el último momento en que se sabe que la clave estaba segura) y se publica de inmediato un almacén nuevo. Se rechazan los paquetes firmados a partir de `revoked_at`. Los paquetes firmados antes pueden volver a firmarse con la clave nueva sin cambiar su contenido.
- **Límite conocido:** sin un sellado de tiempo independiente, `signed_at` lo declara quien firma. Ante una clave comprometida, no hay forma de descartar fechas retroactivas; de ahí el `revoked_at` conservador. *Decisión abierta F1-D5:* si se incorpora un sellado de tiempo de terceros o del propio NEXOM.

## 8. Funcionamiento local y sin conexión

- La verificación no requiere red: basta el almacén de confianza local vigente.
- La frescura se garantiza con `next_update_before`. Vencido ese plazo, el consumidor en `prod` rechaza la importación hasta recibir un almacén nuevo.

## 9. Auditoría

Cada verificación, aceptada o rechazada, registra:

- SHA-256 del ZIP;
- `content_digest`;
- `package_id`;
- `key_id`;
- `store_version`;
- resultado;
- código de error;
- fecha y hora;
- versión del verificador.

Cada firma registra en RAG Studio:

- `content_digest`;
- `key_id`;
- `signed_at`;
- operador.

## 10. Códigos de error (propuesta)

| Código | Condición |
|---|---|
| `TRUST_STORE_INVALID` | Almacén con firma inválida o schema incorrecto |
| `TRUST_STORE_STALE` | Pasado `next_update_before`, o `store_version` menor que el último aceptado |
| `ENVELOPE_INVALID` | El sobre no cumple su schema |
| `KEY_UNKNOWN` | `key_id` no está en el almacén |
| `KEY_WRONG_ENVIRONMENT` | La clave no es del entorno del consumidor (p. ej. `demo` en `prod`) |
| `KEY_REVOKED` | Firma posterior a `revoked_at` |
| `KEY_NOT_VALID_AT_SIGNING_TIME` | `signed_at` fuera de la ventana de validez |
| `SIGNATURE_INVALID` | La firma Ed25519 no verifica |
| `DIGEST_MISMATCH` | `content_digest` o `checksums_json_hash` no coinciden con lo recalculado |
| `MANIFEST_MISMATCH` | `package_id` o `schema_version` no coinciden con el manifiesto |
| `PACKAGE_INVALID` | El validador de referencia reporta errores |

## 11. Pruebas negativas mínimas

Debe haber al menos una por código de error. Además:

- sobre válido con `signed_at` manipulado: la firma debe fallar;
- sobre DEMO presentado en `prod`;
- almacén anterior reinstalado;
- clave revocada con `signed_at` anterior y posterior a la revocación;
- paquete válido con un sobre de otro paquete;
- `.sig` v1.0.0 válido sin sobre v2 en `prod`: rechazo.

## 12. Transición de paquetes DEMO a producción

1. Los paquetes DEMO actuales (rc3.2 y el ejemplo `1.0.0`) conservan su valor como evidencia técnica y **no se convierten en productivos**.
2. Un paquete productivo se exporta de nuevo o se vuelve a firmar con una clave `prod` mediante un sobre v2. El contenido no cambia.
3. Hasta la aprobación de F-1, el Runtime en producción no debe aceptar automáticamente ningún paquete.

## 13. Impacto contractual previsto

*Esta sección queda sujeta a la decisión A-1 del Anexo A: la propuesta de NEXOM es definir primero un perfil de confianza separado y no ligarlo todavía a NKP 1.1.0.*

- Nuevos artefactos: `signature_envelope.schema.json` y `trust_store.schema.json`, más una opción de verificación en el validador de referencia.
- No se modifica ningún artefacto `1.0.0`. El `.sig` actual sigue siendo válido para `demo` y `test`.
- Encaje propuesto: contrato **1.1.0**, con nueva prueba de interoperabilidad centrada en la verificación.

## 14. Decisiones abiertas para la sesión conjunta

| Id | Decisión |
|---|---|
| F1-D1 | Custodia y ceremonia de la clave raíz |
| F1-D2 | Firma local en RAG Studio o servicio de firma NEXOM |
| F1-D3 | Una firma o varias (productor + revisor) |
| F1-D4 | Vigencia de las claves operativas y periodicidad del almacén |
| F1-D5 | Sellado de tiempo independiente, sí o no |
| F1-D6 | Canal de distribución del almacén de confianza hacia el Runtime |
| F1-D7 | Si la firma se aplica por exportación o por liberación aprobada |
| F1-D8 | Alcance de una revocación: solo firmas posteriores a `revoked_at`, o todas las firmas de la clave |

## 15. Siguiente paso propuesto

Una sesión conjunta RAG Studio + Runtime para resolver F1-D1 a F1-D8. Después, RAG Studio redacta la versión 0.2 con los schemas del sobre y del almacén, y la matriz de pruebas. La implementación se autoriza en un incremento propio, separado de RAG-INC-01.

---

## Anexo A — Observaciones de NEXOM del 2026-09-24 (entrada para la sesión conjunta)

Las siguientes observaciones de arquitectura deben resolverse antes de la v0.2. Se recogen tal como las planteó NEXOM; la sesión conjunta decide.

**A-1. Perfil de confianza separado del formato del paquete.** Definir primero el **NEXOM Knowledge Package Trust Profile 1.0**, que reúne el sobre de firma, el almacén de confianza, las reglas de verificación, la rotación, la revocación y la política productiva. El paquete sigue con `schema_version = 1.0.0`. Más adelante, NKP 1.1.0 puede declarar compatibilidad con el perfil. Así no se confunden tres versiones distintas: la de la estructura del paquete, la del validador y la del protocolo de autenticidad. Sustituiría la propuesta de la sección 13.

**A-2. Hash del archivo de transporte dentro de `statement`.**

```json
"archive": { "media_type": "application/zip", "sha256": "..." }
```

Permite comprobar la autenticidad del ZIP antes de abrirlo. El orden en producción sería:

1. verificar el almacén de confianza;
2. verificar el sobre;
3. comprobar el hash del ZIP sin abrirlo;
4. inspeccionar el ZIP de forma segura;
5. validar su contenido;
6. importar.

`archive` sería opcional en el schema general, porque se admite la entrega como directorio, pero obligatorio en entregas ZIP productivas.

**A-3. `producer_id` en lugar de confiar en `signer`.** Por ejemplo `"producer_id": "urn:nexom:producer:ragstudio:nexom"`. El Runtime lo compara con el `owner` autorizado de la clave en el almacén. `signer` queda solo como etiqueta visible.

**A-4. Formato exacto de la firma del almacén de confianza.** Especificar:

- el payload canónico firmado, con la misma estructura de sobre: `{ "store": {…}, "root_key_id": "…", "algorithm": "ed25519", "signature": "<firma de RFC8785(store)>" }`;
- los campos excluidos de la canonicalización;
- `root_key_id`;
- la huella de la clave raíz;
- el procedimiento de rotación de la raíz.

**A-5. Revocación segura (resuelve F1-D8).** Una clave `revoked` invalida **todas** sus firmas, salvo que exista un sello de tiempo confiable anterior al compromiso. `revoked_at` con `signed_at` autodeclarado no basta para conservar firmas anteriores. Las claves `retired` sí conservan sus firmas previas mientras no haya evidencia de compromiso. Si se adopta, las reglas 3 y 4 de la sección 6 cambian en la v0.2.

**A-6. Antirretroceso del almacén de confianza.** El `store_version` monótono solo funciona si el Runtime guarda protegido el último valor aceptado. Hay que especificar:

- dónde se persiste ese valor;
- cómo sobrevive a reinicios;
- qué ocurre al restaurar un respaldo antiguo del Runtime;
- qué reloj se considera confiable para `next_update_before`;
- cómo se recupera una instalación sin conexión cuyo almacén venció.

### Recomendaciones de NEXOM para F1-D1 a F1-D8

| Decisión | Recomendación de NEXOM |
|---|---|
| F1-D1 | Raíz fuera de línea, ceremonia de dos personas y dos respaldos cifrados en ubicaciones separadas |
| F1-D2 | DEMO y test, firma local. Producción, servicio de firma NEXOM o token criptográfico |
| F1-D3 | Una sola firma de productor en la primera versión; varias firmas en una evolución posterior |
| F1-D4 | Claves operativas de 12 meses; almacén de confianza actualizado como máximo cada 30 días |
| F1-D5 | Sin sellado de tiempo externo al principio, con revocación total ante compromiso |
| F1-D6 | Almacén inicial incluido con el Runtime; actualizaciones fuera de banda firmadas por la raíz |
| F1-D7 | Firmar solo liberaciones aprobadas, no toda exportación |
| F1-D8 | Revocación total de la clave, salvo firmas con sello de tiempo confiable anterior (A-5) |

**Estado:** F-1 no se implementa. La salida de la sesión conjunta es la v0.2 de esta especificación, con los schemas del sobre y del almacén y su matriz de pruebas.
