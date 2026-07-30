# Actualización de búsqueda y ficha técnica

Esta actualización corrige:

- búsquedas que mostraban siempre Quadra-1029;
- lectura exacta de Estado y Condición desde la API del sistema de planificación;
- lectura de Sistema Control;
- lectura de D. RT, D. Sernageomin y D. DGMN;
- cálculo de fechas de vencimiento cuando la API entrega días restantes;
- rechazo de modelos de neumáticos o repuestos como modelo del camión;
- lectura de la columna Estado de equipos del Excel semanal;
- historial de últimos trabajos y bajadas por camión;
- uso del detalle de Estado de equipos cuando el camión está En proceso;
- auditoría IA incluyendo estado, comentarios e historial reciente.

## Archivos que se deben subir a GitHub

Subir el contenido de esta actualización sobre la raíz del repositorio:

- `enaex/aliases.py`
- `enaex/processing.py`
- `enaex/ai_service.py`
- `enaex/ui/common.py`
- `enaex/ui/equipment.py`
- `tests/test_core.py`
- `PASOS_ACTUALIZACION_BUSQUEDA.md`

## Commit recomendado

`Corrige búsqueda, datos técnicos y estado de equipos`

Después del commit, esperar 1 a 3 minutos. En Streamlit abrir **Manage app**, pulsar **Reboot app** y luego recargar con `Ctrl + F5`. Esto es importante para eliminar el índice de búsqueda anterior guardado en caché.
