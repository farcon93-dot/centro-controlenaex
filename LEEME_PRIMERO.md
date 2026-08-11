# HOTFIX CONTRATOS 2026.08.11.2

Esta actualización corrige el cálculo contractual para que SOLO cuenten equipos cuyo código comience por `QUADRA` o `AUGER`.

Ejemplo real de validación en Chuquicamata:
- QUADRA-79 UB -> cuenta
- QUADRA-1003 -> cuenta
- QUADRA-147 AT -> cuenta
- AFI 2815400 -> NO cuenta
- Resultado contractual: 3 camiones fábrica, objetivo 2, diferencia +1.

Además:
- PMO/PMOCAM se muestran como Polvorín pero no cuentan en contrato.
- AFI y otros equipos se muestran como Otro equipo pero no cuentan en contrato.
- Alertas recalcula el contrato directamente desde los nombres actuales del GPS.
- Ver por Faena muestra Tipo y separa el inventario visible del conteo contractual.
- Barra lateral debe mostrar `Versión 2026.08.11.2 · HOTFIX CONTRATOS`.

## Archivos que debes subir reemplazando los existentes
- enaex/processing.py
- enaex/ui/faenas.py
- enaex/ui/alerts.py
- enaex/ui/common.py
- tests/test_core.py

Después del commit, reinicia/reboot la app en Streamlit y usa Ctrl+F5.
