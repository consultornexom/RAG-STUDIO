# Registro de firma — Contrato NEXOM Knowledge Package v1.0.0 y Alcance RAG-INC-01

**Estado del expediente:** CERRADO. Registro **congelado** desde el 2026-09-24; no se modifica. Su SHA-256 final consta en `RAG-INC-01/preparacion_01a/Preparacion_Hito_01a.md` y se incorporará al informe de puerta de 01a.
**Fecha efectiva:** 2026-09-24
**Registrado por:** RAG Studio (asistente de desarrollo), a partir de los documentos entregados por NEXOM el 2026-09-24. Última actualización: 2026-09-24, al incorporar la Ratificación V2 como vigente, aplicar precisiones documentales 1.0.x y registrar la confirmación de identidad del "Consultor NEXOM".

## 1. Documentos y hashes

| Documento | Estado | Ubicación | SHA-256 |
|---|---|---|---|
| Declaración de aceptación v1.0.0, rev. 4.1 | Canónico sin firmar | `Declaracion_Aceptacion_NEXOM_Knowledge_Package_v1.0.0.pdf` | `a80e159692c5879e4f4046b0eb7934abc77477058bf1f20a6f7dce2b6b55e6de` |
| Declaración de aceptación v1.0.0, rev. 4.1 | **Firmado** | `firmados/Declaracion_Aceptacion_NEXOM_Knowledge_Package_v1.0.0_FIRMADO.pdf` | `d7aad77097cebaacd6d3f643e5f98a8cef1d86976c5fb54a452631a398c823d7` |
| Alcance RAG-INC-01, rev. 4.1 | Canónico sin firmar | `Alcance_RAG-INC-01_Exportador_NEXOM_Knowledge_Package.pdf` | `b50b2212fdcd894621e02ef1a4509d2f1ba822062ebde843117e27ef797dc5f9` |
| Alcance RAG-INC-01, rev. 4.1 | **Firmado** | `firmados/Alcance_RAG-INC-01_Exportador_NEXOM_Knowledge_Package_FIRMADO.pdf` | `c463350c4ae1460bd09d175df1a09d0c077584d5cd3320c44def79abba7b8df9` |
| Ratificación, primera versión | **Superseded**, conservada sin eliminar | `RATIFICACION.pdf` | `1a490a282ac2994b4e5269a5b6d402da7b04e7ce1a6952ea2a06be21554eb59c` |
| Ratificación V2 | **Vigente** | `firmados/Ratificacion_NEXOM_Knowledge_Package_v1.0.0_y_RAG-INC-01.pdf` | `ceabbfa5217e9cac65bcdd8e7c084e674da6a6a6ab584ffb4c5751ec61a29045` |
| Paquete `v1.0-rc3.2` | Evidencia de aceptación inmutable | `RAG-INC-00_NEXOM_Knowledge_Package_v1.0-rc3.2.zip` | `78db21b10c8a12906784e111747bebe304f230abebcecc834eb030e6f3ff81cc` |

Las rutas son relativas a `docs proyecto/NEXOM_Knowledge_Package_v1/`.

La Ratificación V2 se entregó con el nombre `Ratificacion_NEXOM_Knowledge_Package_v1.0.0_y_RAG-INC-01.pdf.pdf`. Se renombró y se trasladó a `firmados/` sin modificar sus bytes: el SHA-256 anterior y el posterior son idénticos (`ceabbfa5…9045`).

En la raíz de la carpeta quedan además dos copias de los PDF firmados con el prefijo `FIRMADO ` en el nombre. Son byte a byte idénticas a las de `firmados/` (mismos SHA-256) y se conservan sin eliminarlas.

## 2. Firmantes y roles

| Persona | Rol | Documentos |
|---|---|---|
| Ing. Alejandro Montes | NEXOM — responsable del contrato | Declaración, Alcance |
| Ing. Alejandro Montes | NEXOM Agent Runtime — responsable de AR-INC-00; en la Ratificación, "Responsable de Runtime / Apoderado Técnico Autorizado" | Declaración, Ratificación V2 |
| Rafael González | Socio Consultor, por NEXOM — Representación y Gobierno Corporativo | Ratificación V2 |
| Rafael González (firma como "Consultor NEXOM") | RAG Studio — responsable técnico | Declaración, Alcance |

**Identidad del "Consultor NEXOM": CONFIRMADA.** La Ratificación V2 reconoce como definitivos los PDF firmados por sus respectivos SHA-256, pero no identifica nominalmente al firmante denominado "Consultor NEXOM". En comunicación administrativa del 24 de septiembre de 2026, NEXOM declaró:

> "El firmante identificado como Consultor NEXOM corresponde a Rafael González, Socio Consultor de NEXOM, quien actuó como responsable técnico de RAG Studio."

Esta confirmación completa la identificación administrativa del firmante sin modificar ni requerir una nueva firma de los PDF definitivos.

| Campo | Valor |
|---|---|
| Nombre completo | Rafael González |
| Función | Socio Consultor, NEXOM (Representación y Gobierno Corporativo); responsable técnico de RAG Studio en la Declaración y el Alcance |
| Confirmado por | NEXOM, mediante comunicación administrativa remitida desde `consultor@nexom.com.mx` durante la sesión de trabajo del 2026-09-24 |
| Fecha | 2026-09-24 |

Queda así resuelto el requisito de confirmarlo antes de cerrar la puerta de 01a.

## 3. Método de suscripción

- **Declaración y Alcance:** nombres, firmas y fechas escritos como texto en las celdas de firma, en PDF regenerados con LibreOffice Writer 26.2.5.2. No contienen firma digital PDF ni imagen de firma.
- **Ratificación V2:** rúbricas incorporadas como imágenes. No contiene firma digital PDF ni campos de firma (`AcroForm`). El PDF no permite determinar cómo se produjeron originalmente las rúbricas.
- **Validez:** la cláusula SEGUNDA de la Ratificación V2 declara este mecanismo como el medio acordado y válido de aprobación para gobierno interno, autorización técnica y ejecución del proyecto. Aclara también que no lo califica como firma electrónica avanzada.

## 4. Verificación de contenido

Se verificó la equivalencia material y visual de cada PDF firmado con su documento canónico. Las únicas diferencias son los datos añadidos en las celdas de firma, la paginación y diferencias no sustantivas en la extracción de texto que produce LibreOffice.

- **Método:** se comparó el texto extraído de ambos PDF sin considerar la maquetación, y se revisaron visualmente las páginas.
- **Límite del método:** la extracción de texto del Alcance firmado pierde el guion de dos rangos de líneas (por ejemplo, `ports.py:44-56`). Visualmente, los guiones aparecen correctamente en el PDF.
- **Declaración:** fuera de los campos de firma, no hay diferencias de contenido.
- **Alcance:** fuera de los campos de firma, la única diferencia es una repetición menos del encabezado de la tabla del hito 01c, porque con la nueva paginación esa tabla ya no se parte entre páginas.
- **Hashes internos:** los 20 SHA-256 citados en la Declaración aparecen completos e idénticos en el PDF firmado.

La Ratificación V2 identifica los dos PDF firmados por sus SHA-256 (`d7aad770…23d7` y `c463350c…8df9`), que coinciden con los de la sección 1.

## 5. Condiciones cerradas

- **R-4, jerarquía de acceso: CERRADA.** Cláusula QUINTA de la Ratificación V2: "En su carácter de responsable del Runtime, Alejandro Montes confirma que el importador interpreta el orden y las reglas de acceso declarados por cada paquete en access_hierarchy.json y que no depende de una tabla fija de traducción inglés/español." La redacción coincide con la condición de firma de la sección 10 de la Declaración. La primera ratificación (superseded) no la reproducía con esa precisión.
- **Doble función: INTENCIONAL.** Cláusulas TERCERA y CUARTA de la Ratificación V2. NEXOM declara que la concentración de roles en Alejandro Montes (responsable del contrato y responsable del Runtime) es una decisión organizativa deliberada, no un error ni un vicio de procedimiento, y que estaba facultado para actuar en ambos roles.
- **Carácter definitivo.** Cláusula PRIMERA: los dos PDF firmados, identificados por sus SHA-256, son las versiones finales y aceptadas.

## 6. Efectos

Desde el 2026-09-24:

- el contrato NEXOM Knowledge Package queda en estado `ACCEPTED`, con `schema_version = 1.0.0`;
- quedan en vigor las decisiones CON-D1 a CON-D4 de la Declaración y INC01-D1 a INC01-D8 del Alcance;
- queda autorizado RAG-INC-01 conforme a sus puertas;
- los intercambios productivos autenticados siguen sujetos a F-1.

## 7. Publicación posterior a la firma

| Elemento | Ubicación | Verificación |
|---|---|---|
| Contrato `v1.0.0`: 16 artefactos normativos | `contrato_v1.0.0/` | `sha256sum -c SHA256SUMS`: 16/16 OK. SHA-256 de `SHA256SUMS`: `863844f7b6f264cfdc45974b9a9f0ab4e92a830d01b70e9634958fde6b675208` |
| Ejemplo `1.0.0` y conformidad del productor | `ejemplo_v1.0.0/` | `Informe_Conformidad_v1.0.0.md`: PASS, con log completo en `Informe_Conformidad_v1.0.0.log`. ZIP `5dff57bb…cbff`; `content_digest` `2932dd2f…5102` |
| ADR de estado `v1.0.0` | `ADR_NEXOM_Knowledge_Package_v1.0.0.md` | Estado ACCEPTED y aclaraciones normativas (acción A-2) |
| Importación de humo en Agent Runtime | `ejemplo_v1.0.0/entrega_runtime_v1.0.0/` (solicitud rev. 3, manifiesto `0c43b51a…de78`) | **Pendiente** del Runtime. Hasta su PASS, el paso 4 de la sección 10 de la Declaración sigue abierto y el hito 01a no se inicia formalmente (decisión de NEXOM del 2026-09-24) |
