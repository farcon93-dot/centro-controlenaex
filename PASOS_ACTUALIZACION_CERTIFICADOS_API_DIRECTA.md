# Actualización 2026.09.30.4.6 — Certificaciones API directa

## Objetivo
Corregir Certificaciones críticas para que use exclusivamente la información actual del sistema de planificación/API (D: RT, D: Sernageomin y D: DGMN), evitando fechas históricas del Excel que podían generar falsos vencimientos.

## Cambios
- Certificaciones críticas usa `data.gps` directamente.
- Se muestran solo documentos con días <= 30.
- Días negativos = Vencida.
- Día 0 = Vence hoy.
- 1 a 30 días = Vence pronto.
- Más de 30 días = no aparece.
- Se mantienen separados Camión fábrica, Polvorín, Auxiliar Enaex y Equipo en arriendo.
- Se amplía reconocimiento de encabezados RT/Sernageomin (incluye SGMN) y DGMN.
- No se usan fechas históricas del Excel para esta pantalla.

## Archivos a subir
- app_v2.py
- enaex/processing.py
- enaex/ui/alerts.py
- enaex/ui/common.py
- tests/test_core.py

## Commit sugerido
`Corrige certificados críticos usando API de planificación`

## Verificación
Después del commit:
1. Streamlit > Manage app > Reboot app.
2. Ctrl + F5.
3. La barra lateral debe mostrar `Versión 2026.09.30.4.6 · CERTIFICACIONES API DIRECTA`.
