# Actualización 2026.09.29.3 — Certificaciones robustas

Esta actualización modifica únicamente la lectura y presentación de certificaciones críticas.

## Qué cambia
- RT, Sernageomin y DGMN se toman desde la ficha consolidada de cada equipo.
- Se combinan distintas variantes de columnas que puede entregar la API (por ejemplo `D. RT`, `dias_rt`, etc.).
- Si la API no trae el dato para un equipo, se conserva como respaldo una fecha válida del historial de planificación.
- Solo aparecen documentos vencidos, que vencen hoy, o con 30 días o menos.
- Se eliminan por completo los registros sin fecha/días válidos.
- La vista diferencia: Camión fábrica, Polvorín, Auxiliar Enaex y Equipo en arriendo.
- `AFI` se clasifica como equipo en arriendo; un AFI que contiene PMO/PMOCAM se clasifica como Polvorín.

## Archivos que reemplaza
- app_v2.py
- enaex/aliases.py
- enaex/processing.py
- enaex/ui/alerts.py
- enaex/ui/common.py
- tests/test_core.py

## Después de subir a GitHub
1. Commit directo a `main`.
2. Esperar 1–2 minutos.
3. Streamlit > Manage app > Reboot app.
4. Ctrl+F5.
5. Verificar en la barra lateral: `Versión 2026.09.29.3 · CERTIFICACIONES ROBUSTAS`.
