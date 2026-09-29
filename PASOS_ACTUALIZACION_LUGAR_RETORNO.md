# Actualización Lugar + Fecha retorno a operación

## Qué corrige
- La vista "Ver por Faena" ahora puede leer `Lugar` desde más de una columna equivalente de la API (por ejemplo `Lugar` y `nombre_lugar`). Si una viene vacía, toma la otra.
- Elimina de la tabla las columnas `Última actualización` y `Faena reportada`.
- Agrega `Fecha retorno a operación` desde el sistema de planificación.
- Los valores vacíos de Lugar se muestran como `N/A`, nunca como `None`.

## Archivos a subir a GitHub
Sube el contenido de esta carpeta sobre la raíz del repositorio:

- `app_v2.py`
- `enaex/aliases.py`
- `enaex/processing.py`
- `enaex/ui/faenas.py`
- `enaex/ui/common.py`
- `tests/test_core.py`

Haz commit directo a `main`.

Mensaje sugerido:
`Corrige Lugar y agrega fecha retorno a operación por faena`

## Después en Streamlit
1. Espera 1–2 minutos.
2. Manage app -> Reboot app.
3. Ctrl+F5 en el navegador.
4. Pulsa `Recargar Excel y GPS`.
5. Confirma en la barra lateral: `Versión 2026.09.29.1 · LUGAR + RETORNO OPERACIÓN`.

## Validación esperada en Lomas Bayas
- QUADRA-71 AT Ex: Lugar `Faena`, retorno `02/10/2026`.
- QUADRA-88 AT Ex: Lugar `INDUMAR`, retorno `01/10/2026`.
- Los demás equipos con Lugar `Faena` en el sistema deberían dejar de aparecer como `None` si la API trae el valor en una columna alternativa reconocida.
