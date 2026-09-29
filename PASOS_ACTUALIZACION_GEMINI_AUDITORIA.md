# Actualización Gemini + Auditoría Cruzada

Versión esperada: **2026.09.29.4 · GEMINI + AUDITORÍA CRUZADA**

## Qué cambia

1. Corrige la detección de modelos Gemini para evitar falsos mensajes de "no compatible".
2. Agrega una auditoría determinística entre Sistema de planificación y Excel semanal.
3. Detecta:
   - Sistema = Faena / Excel = Taller.
   - Sistema = Taller / Excel = Faena.
   - Taller distinto entre ambas fuentes.
   - Fecha retorno del sistema distinta a fecha entrega/subida del Excel.
4. Gemini solo interpreta y prioriza discrepancias ya calculadas por la app.

## Secrets recomendados en Streamlit

Mantén tus claves reales y usa:

```toml
GEMINI_API_KEY = "TU_CLAVE_REAL"
GEMINI_MODEL = "gemini-2.5-flash"
```

No publiques la clave en GitHub.

## Subida

Sube el contenido de esta actualización a la raíz del repositorio y reemplaza los archivos existentes.
Haz commit a `main`, luego `Manage app -> Reboot app` en Streamlit.
