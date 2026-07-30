# Actualización: capacidad real de talleres desde la API

## Qué corrige

1. La ocupación actual ya no parte en cero.
2. Se lee la columna **Lugar** de la API del sistema de planificación.
3. Los equipos cuyo Lugar sea `Faena` no se cuentan como equipos en taller.
4. Los talleres conocidos se comparan con su capacidad máxima.
5. Lugares no configurados, por ejemplo `Indumar` o `SKC Santiago`, se agrupan en **TALLERES EXTERNOS**.
6. Los movimientos futuros siguen proviniendo únicamente de la hoja **Mov. equipos**.
7. La proyección combina:
   - equipos que están hoy en cada taller según la API;
   - bajadas programadas;
   - subidas programadas;
   - peak y cierre de la semana.
8. Los recuadros se reemplazan por paneles compactos desplegables. Al hacer clic muestran el detalle de equipos actuales y movimientos semanales.
9. Gemini recibe el inventario actual y la proyección calculada para sugerir redistribución sin modificar las cifras.

## Archivos que debes reemplazar en GitHub

Sube el contenido de este paquete a la raíz del repositorio. GitHub debe mostrar estas rutas:

- `/enaex/aliases.py`
- `/enaex/models.py`
- `/enaex/processing.py`
- `/enaex/ai_service.py`
- `/enaex/ui/movements.py`
- `/enaex/ui/common.py`
- `/tests/test_core.py`

No subas la carpeta exterior completa. Arrastra las carpetas `enaex`, `tests` y este archivo directamente a **Add file → Upload files**.

## Mensaje del commit

`Calcula capacidad real desde Lugar API y agrega detalle de talleres`

## Después del commit

1. Espera entre 1 y 3 minutos.
2. Abre la aplicación Streamlit.
3. Presiona `Ctrl + F5`.
4. Si sigue la versión anterior: **Manage app → Reboot app**.
5. En la barra lateral abre **Diagnóstico de columnas GPS**.
6. Confirma que aparezca: `place → Lugar`.

## Comprobación rápida

En **Movimientos de Equipos**:

- El valor **Hoy** debe coincidir con los equipos cuyo `Lugar` sea ese taller.
- Al hacer clic en un taller debe aparecer la lista de equipos actuales.
- `Faena` no debe aparecer como taller.
- `Indumar`, `SKC Santiago` u otros lugares no configurados deben aparecer bajo **TALLERES EXTERNOS**.
- El peak debe sumar las bajadas futuras y descontar las subidas futuras.
