"""Copia byte a byte de `common/id_scheme.py` del contrato firmado NEXOM
Knowledge Package v1.0.0 (SHA-256 559847df560b8033b20a4e797ca32448320eef8d84f81cb654bcad6c1a942ba8,
`docs proyecto/NEXOM_Knowledge_Package_v1/contrato_v1.0.0/SHA256SUMS`).

El Alcance firmado de RAG-INC-01 exige que el exportador use la
implementación de referencia y que las fórmulas normativas no se
reimplementen. Este paquete trae SOLO ese módulo; la vendorización completa
del contrato (14 schemas y validador) y su prueba de conformidad son del
hito 01c. tests/unit/infrastructure/test_nkp_id_scheme_vendored.py falla si
el archivo difiere del firmado. NO EDITAR id_scheme.py."""
