# Actualización 2026.10.01.4.7 — Certificaciones RAW coherentes

Esta actualización corrige exclusivamente la lectura de RT, Sernageomin y DGMN desde la API del sistema de planificación.

## Qué corrige
- Lee RT, Sernageomin y DGMN directamente desde las llaves RAW de cada respuesta de API, incluso si distintos tipos de equipo usan nombres diferentes.
- Evita interpretar fechas (por ejemplo 30-09-2026) como si fueran días restantes.
- Cuando un equipo aparece repetido en más de un endpoint, toma el trío RT/Sernageomin/DGMN desde un mismo registro completo, evitando mezclar valores antiguos o parciales.
- Mantiene sin cambios contratos, movimientos, auditoría, búsqueda y lógica de faenas.

## Archivos a subir a GitHub
- enaex/processing.py
- enaex/aliases.py
- enaex/ui/common.py
- tests/test_core.py

Después del commit: Streamlit > Manage app > Reboot app y luego Ctrl+F5.

La barra lateral debe mostrar:
`Versión 2026.10.01.4.7 · CERTIFICACIONES RAW COHERENTES`

## Verificación
En `Diagnóstico de columnas GPS` aparecerá una tabla adicional llamada `Lectura documental directa desde la API` con RT, Sernageomin y DGMN, las columnas RAW detectadas y la cantidad de valores válidos.
