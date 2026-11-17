# Ronda 104b: cierre de la Etapa 0 (trazabilidad y reproducibilidad)

**Decisión de NEXOM:** se acepta y se cierra funcionalmente la Etapa 0, dentro del alcance autorizado.

**Registro:** documental, sin cambios de código.

## Validación realizada por NEXOM

| Concepto | Valor informado |
|---|---|
| Plataforma | Windows |
| Proyecto | AGENTE UDL - LOTE01_Bachillerato, instantánea v2 |
| Commit ejecutado | `40be219542c46d8f8901aca8e99991469bb7edda` |
| Procedimiento de recuperación | `r102` |
| Huella de la instantánea | `fingerprint_matches = true` |
| Reranking | modelo no disponible; `applied = false` |
| `execution` en `/messages` | se recibe correctamente con la clave operativa |
| Fragmentos | el Runtime registra la secuencia de los cinco fragmentos recuperados |
| Unicode | el texto se recupera correctamente |
| Persistencia en `runtime.db` | verificada con el trace `bccc81c9-3a43-4cf4-b119-2622092ff609` |

## Correspondencia con las pruebas de aceptación de la autorización

| # | Criterio | Estado |
|---|---|---|
| 1 | Mismo orden de fragmentos antes y después | Verificado en el desarrollo: 28 consultas de LOTE01, 0 diferencias (`orden_antes_etapa0.json`, `orden_despues_etapa0.json`) |
| 2 | `/messages` conserva sus campos y agrega los diagnósticos | Verificado en desarrollo y por NEXOM (`execution` con clave operativa) |
| 3 | Bases históricas siguen funcionando | Verificado en desarrollo (prueba con `runtime.db` de esquema anterior) |
| 4 | Simulador y Runtime muestran el reranking efectivo | Verificado; en el Runtime de NEXOM: sin modelo, no aplicado |
| 5 | Los datos identifican versión, instantánea y configuración | Verificado por NEXOM: commit, `r102`, huella de instantánea, trace `bccc81c9-…` en `runtime.db` |
| 6 | Sin fallos nuevos | Verificado en desarrollo (informe de implementación, sección 3) |

## Estado

- **Commit:** `40be219`, publicado en `origin/main`.
- **Etapas que siguen sin autorizar ni implementar:**
  - Etapa 1 (corrección Y);
  - Etapa 2 (resolución de referencias R);
  - Etapa 3 (cualquier modificación del reranking).
- **Comportamiento por defecto:** sin cambios.
- **Siguiente actividad autorizada:** diagnóstico documental de la disponibilidad de las evidencias E1–E7 del incidente 493c8033 (`Disponibilidad_Evidencias_493c8033.md`), sin reconstrucciones que modifiquen las evidencias originales.
