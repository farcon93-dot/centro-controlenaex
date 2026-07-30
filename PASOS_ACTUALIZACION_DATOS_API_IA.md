# Actualización: lectura correcta de Estado, Lugar, certificaciones, próxima mantención e historial con IA

## Problemas corregidos

1. `Estado` podía tomar números como 47, 109 o 140 desde campos de certificaciones.
2. No se priorizaba `Estado_Deducido`, que es el estado operativo mostrado por el sistema.
3. `Lugar`, `Condición`, D. RT, D. Sernageomin y D. DGMN podían quedar en N/A por variaciones de nombres en la API.
4. Si el mismo camión llegaba en varias respuestas de la API, se seleccionaba una sola fila y se perdían datos presentes en las otras.
5. La fecha `30-07-2026 (450)` no se interpretaba como próxima mantención.
6. La planificación semanal podía aparecer como si fuera el estado operativo actual.
7. La ficha mostraba la fuente/hoja de los datos.
8. El historial no tenía un resumen específico con IA.

## Nuevo comportamiento

- Estado actual: se prioriza `Estado_Deducido` y se rechazan estados solamente numéricos.
- Lugar actual: reconoce `Lugar`, `nombre_lugar`, `lugar_nombre` y variantes.
- Condición: reconoce `Condicion`, `nombre_condicion`, `condicion_nombre` y variantes.
- Certificaciones: reconoce D. RT, D. Sernageomin y D. DGMN y calcula la fecha de vencimiento.
- Próxima mantención: interpreta fechas aunque vengan con el ciclo entre paréntesis.
- Registros duplicados de API: se unen campo por campo para no perder información.
- Estado operativo y estatus de Mov. equipos quedan separados.
- Si el estado operativo es En proceso, se destaca el comentario de Estado de equipos.
- Ya no aparece la fuente ni la hoja en las consultas.
- Cada ficha incluye un botón para generar con Gemini un punteo de trabajos históricos.

## Archivos que debes subir a GitHub

Sube el contenido de la carpeta de actualización, conservando estas rutas:

- `/enaex/aliases.py`
- `/enaex/normalize.py`
- `/enaex/processing.py`
- `/enaex/ai_service.py`
- `/enaex/ui/common.py`
- `/enaex/ui/equipment.py`
- `/tests/test_core.py`
- `/PASOS_ACTUALIZACION_DATOS_API_IA.md`

## Mensaje recomendado para el commit

`Corrige lectura API, certificaciones e historial con IA`

## Después del commit

1. Espera uno o dos minutos.
2. Abre Streamlit.
3. Entra a **Manage app**.
4. Pulsa **Reboot app**.
5. Cuando cargue, presiona `Ctrl + F5`.
6. En la barra lateral confirma que aparezca `Versión 2026.07.30.3`.

## Prueba recomendada

Busca `Quadra-1060` y comprueba:

- Estado: OK.
- Lugar: Faena.
- D. RT: 17 días.
- D. Sernageomin: 61 días.
- D. DGMN: 67 días.
- Próxima mantención: 30/07/2026.
- Estatus en Mov. equipos: Pendiente, separado del estado operativo.
- No aparece “Fuente de fechas” ni la columna “hoja”.

Después pulsa **Analizar trabajos históricos con IA** para obtener el punteo.
