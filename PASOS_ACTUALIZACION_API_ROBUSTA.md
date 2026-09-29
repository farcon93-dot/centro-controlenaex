# Actualización 2026-09-29.2

Esta actualización corrige tres problemas sin cambiar la lógica contractual ni las demás pantallas:

1. Recuperación de endpoints de la API: limita concurrencia, reintenta timeouts y hace una segunda pasada de recuperación. Esto evita que una faena quede sin sus AUGER/QUADRA por una respuesta intermitente.
2. Lugar: amplía alias y agrega detección por esquema/contenido para variantes de llave usadas por distintos endpoints.
3. Fecha retorno a operación: amplía alias y detecta llaves abreviadas o alternativas.

La interfaz avisará claramente si, aun después de reintentos, quedó una fotografía parcial de la API.

## Actualizar
Subir a la raíz del repositorio el contenido del ZIP, conservar `app_v2.py` como Main file path en Streamlit, hacer commit a main y luego Reboot app.

La barra lateral debe indicar:
`Versión 2026.09.29.2 · API ROBUSTA + LUGAR/RETORNO`
