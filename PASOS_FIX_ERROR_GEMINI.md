# Fix auditoría cruzada + Gemini

1. Subir el contenido de esta carpeta al repositorio GitHub, reemplazando los archivos existentes.
2. Commit sugerido: `Corrige error de auditoría cruzada y actualiza Gemini`.
3. En Streamlit > Manage app > Settings > Secrets, usar:
   `GEMINI_MODEL = "gemini-3.8-flash"`
4. Mantener `GEMINI_API_KEY` con la clave real.
5. Reboot app y luego Ctrl+F5.
6. Confirmar versión: `2026.09.29.4.1 · FIX AUDITORÍA + GEMINI 3.8`.

El cruce de datos funciona aunque Gemini esté deshabilitado. Gemini solo interpreta/prioriza las discrepancias calculadas por la aplicación.
