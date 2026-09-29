# Actualización certificaciones críticas + Salvador/Rajo Inca

## Qué corrige

1. Certificaciones críticas se calculan directamente desde el sistema de planificación/API.
2. Se muestran solo documentos en amarillo o rojo: vencidos o con 30 días o menos.
3. Se incluyen todos los tipos de equipo, sin filtrar por contrato: camiones fábrica, PMO/PMOCAM, auxiliares Enaex, equipos en arriendo y otros.
4. Se elimina por completo el bloque "Documentos sin fecha registrada".
5. Rajo Inca se consolida como Salvador para cumplimiento contractual y vista por faena.
6. Versión visible: 2026.09.28.1 · CERTIFICACIONES + RAJO INCA.

## Subida a GitHub

Subir a la raíz del repositorio el contenido de la actualización, conservando las carpetas:

- app_v2.py
- enaex/aliases.py
- enaex/processing.py
- enaex/ui/alerts.py
- enaex/ui/common.py
- tests/test_core.py

Hacer commit directo a main. Luego en Streamlit reiniciar la app y pulsar "Recargar Excel y GPS".

## Verificación

La barra lateral debe mostrar:

Versión 2026.09.28.1 · CERTIFICACIONES + RAJO INCA

En Alertas > Certificaciones críticas ya no debe existir "Documentos sin fecha registrada".
Solo deben aparecer RT, Sernageomin y DGMN vencidas o con <=30 días.

En contratos, todos los AUGER/QUADRA reportados como "Rajo Inca" deben sumarse dentro de "Salvador".
