# Actualización 2026.09.29.4.2 — Gemini + asociación API de equipos

Cambios:
- Gemini deja de bloquearse por la validación previa de `models.get/list`.
- Si `GEMINI_MODEL` está vacío, usa `gemini-3.8-flash`.
- La disponibilidad real del modelo se valida recién al generar contenido, mostrando el error real si la clave/cuota falla.
- Se refuerza el cruce de un equipo de Excel con la API cuando el sistema agrega sufijos al nombre, por ejemplo `QUADRA-1060` vs `QUADRA-1060 AT Ex`.
- Si el mismo camión llega desde más de un endpoint, se fusionan Faena, Lugar, Condición, Estado, horas, certificaciones y fechas campo por campo.
- No se modifica la lógica contractual, movimientos ni certificaciones críticas.

## Streamlit Secrets
Recomendado:

GEMINI_MODEL = "gemini-3.8-flash"

Mantener la clave real en `GEMINI_API_KEY`.

## Después del commit
1. Manage app -> Reboot app.
2. Ctrl+F5.
3. Verificar versión `2026.09.29.4.2 · GEMINI + MATCH API EQUIPOS`.
4. Buscar un camión que antes mostraba `No reporta GPS` y revisar Faena/Lugar/Estado.
