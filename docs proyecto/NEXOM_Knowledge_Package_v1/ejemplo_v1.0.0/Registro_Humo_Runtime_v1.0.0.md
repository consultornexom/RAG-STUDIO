# Registro del resultado de la importación de humo — NEXOM Knowledge Package v1.0.0

**Fecha de registro:** 2026-10-14
**Registrado por:** RAG Studio, con base en la confirmación oficial de NEXOM recibida en esa fecha.
**Referencia:** Declaración de aceptación v1.0.0, sección 10, paso 4; `Solicitud_Importacion_Humo_v1.0.0.md` (revisión 3).

## 1. Resultado comunicado por NEXOM

| Elemento | Valor |
|---|---|
| Runtime (commit) | `5db676e0e292fb09c08bb9258436829ceb28ec3a` |
| Paquete | `nexom-knowledge-package-demo-v1.0.0.zip` |
| SHA-256 del paquete | `5dff57bb41680e2a5cf4a39b40ca99d641ef5beeda810d7bce3c1a58db91cbff` |
| `schema_version` | `1.0.0` |
| Resultado | **PASS / COMPATIBLE** |
| Errores | Ninguno |

Verificación local al registrar: el SHA-256 de `nexom-knowledge-package-demo-v1.0.0.zip` en esta carpeta sigue siendo `5dff57bb…cbff`, igual al importado.

## 2. Efecto

- El paso 4 de la sección 10 de la Declaración (validador, suite 20/20 e importación de humo) queda **completo**.
- Queda satisfecha la condición formal de inicio de RAG-INC-01a ligada al Runtime.
- La implementación de 01a (migración `0021` y cambios productivos) **sigue sin autorizarse** hasta la autorización expresa de NEXOM. Solo se autorizó el cierre de precondiciones.

## 3. Pendiente documental

El informe técnico completo del Runtime (los 13 puntos de la solicitud, sección 3, incluida la evidencia de R-4) no se recibió como archivo. Cuando NEXOM lo entregue, se archiva en esta carpeta con su SHA-256 y se referencia aquí, sin modificar este registro.

## 4. Integridad

- No se modificó ningún artefacto del contrato firmado (`contrato_v1.0.0/`), ni el ZIP, ni sus sidecars, ni `SHA256SUMS_EJEMPLO`.
- `Informe_Conformidad_v1.0.0.md` recibió una sección 5 que referencia este registro. Su SHA-256 antes de la actualización era `05611bb24bab8e451f2009e60e5af7bde42b3ce98ca6ce3ec3414cafa10e6c82`.
