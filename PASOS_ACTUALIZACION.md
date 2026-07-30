# Actualización: movimientos semanales y capacidad de talleres

Esta actualización modifica únicamente los siguientes archivos del repositorio:

- `app.py`
- `enaex/processing.py`
- `enaex/ai_service.py`
- `enaex/ui/movements.py`
- `enaex/ui/common.py`
- `tests/test_core.py` (pruebas; no es necesario para ejecutar la app, pero conviene reemplazarlo)

## Cambios incluidos

1. Bajadas y subidas tomadas solo de la hoja `Mov. equipos`.
2. Una sola bajada y una sola subida por camión.
3. Eliminación de la columna `Origen` en la pantalla.
4. Análisis por semana calendario, de lunes a domingo.
5. Proyección de capacidad por taller: inicio, bajadas, subidas, máximo y cierre semanal.
6. Alertas de sobrecapacidad.
7. Recomendación automática de redistribución.
8. Botón opcional para obtener una recomendación adicional con Gemini.
9. Las fichas técnicas también usan las fechas de `Mov. equipos` como fechas válidas de movimiento.

## Publicación

Después de reemplazar los archivos en GitHub, Streamlit debería reiniciar la aplicación automáticamente. Si no lo hace, abre la aplicación, entra en `Manage app` y pulsa `Reboot app`.
