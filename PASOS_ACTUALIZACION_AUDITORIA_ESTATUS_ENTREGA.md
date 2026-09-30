# Actualización auditoría cruzada — Estatus y Fecha Entrega

Esta actualización modifica únicamente la lógica de discrepancias Planificación vs Excel.

Reglas implementadas:

1. `Listo` / entregado / finalizado en **Mov. equipos** significa que el equipo ya fue entregado y se considera en **Faena**.
2. `En proceso` / en taller significa que el equipo sigue en el taller informado por el Excel.
3. Si no hay un estado concluyente, se revisa la **última Fecha Entrega** registrada para el equipo. Si es anterior al día actual, se considera en **Faena**.
4. Solo para estados pendientes o sin definición se usa la ventana de fechas para determinar si el equipo debería seguir en taller.

Esto evita falsos positivos como `QUADRA-1021`, que aparece en Faena en el sistema y `Listo` en Excel.

## Archivos modificados

- `app_v2.py` (solo etiqueta de build)
- `enaex/processing.py` (lógica de auditoría)
- `enaex/ui/common.py` (solo etiqueta de versión)
- `tests/test_core.py` (pruebas de regresión)

## Instalación

Subir el contenido de este paquete a la raíz del repositorio GitHub y reemplazar los archivos existentes. Hacer commit directo a `main`, esperar el redeploy de Streamlit y luego usar **Manage app > Reboot app**.

Versión esperada: `2026.09.30.4.4 · AUDITORÍA ESTATUS/ENTREGA`.
