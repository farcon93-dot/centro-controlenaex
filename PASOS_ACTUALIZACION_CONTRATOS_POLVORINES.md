# Actualización: contratos solo AUGER/QUADRA + polvorines PMO/PMOCAM

## Qué corrige

1. El cumplimiento contractual se calcula exclusivamente con camiones fábrica cuyo código comienza por `AUGER` o `QUADRA`.
2. Equipos AFI, camionetas, equipos auxiliares, PMO/PMOCAM y otros activos no suman ni restan al objetivo contractual.
3. Los polvorines `PMO` y `PMOCAM` sí permanecen visibles en **Ver por Faena**, identificados como `Polvorín`.
4. La vista por faena separa: camiones fábrica, objetivo contractual, diferencia, polvorines y otros equipos.
5. Se amplía el barrido de tipos de la API GPS desde la lista histórica a los tipos `20` a `30`, más `41`, para recuperar familias de equipos que podían quedar fuera del muestreo anterior.
6. En la barra lateral se muestran los conteos detectados de camiones fábrica y polvorines.

## Cómo subir a GitHub

1. En el repositorio `centro-controlenaex`, pulsa **Add file > Upload files**.
2. Extrae este ZIP en Windows.
3. Arrastra al recuadro de GitHub el contenido de esta carpeta: `enaex`, `tests` y este archivo `.md`.
4. Deben aparecer estas rutas:
   - `/enaex/configuration.py`
   - `/enaex/processing.py`
   - `/enaex/ui/alerts.py`
   - `/enaex/ui/common.py`
   - `/enaex/ui/faenas.py`
   - `/tests/test_core.py`
5. Mensaje de commit sugerido: `Corrige contratos y agrega polvorines por faena`.
6. Confirma directamente en `main`.
7. Espera 1–3 minutos, entra a Streamlit, usa **Manage app > Reboot app** y luego `Ctrl + F5`.

## Qué comprobar

En **Alertas**, las tarjetas deben decir `X de Y camiones fábrica` y solo contar AUGER/QUADRA.

En **Ver por Faena**, por ejemplo Michilla, AFI y PMO/PMOCAM pueden verse en la tabla, pero el indicador contractual solo debe contar AUGER/QUADRA.

En la barra lateral debe aparecer:
- `Camiones fábrica GPS`
- `Polvorines GPS`

Si `Polvorines GPS` sigue en 0 después del reinicio, toma una captura de `Diagnóstico de columnas GPS` y del total `Equipos GPS únicos`: la clasificación ya está preparada, por lo que el siguiente punto a revisar sería el identificador numérico exacto que usa esa API para la familia PMO/PMOCAM.
