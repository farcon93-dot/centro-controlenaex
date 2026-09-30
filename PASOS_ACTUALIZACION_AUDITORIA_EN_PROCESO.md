# Actualización auditoría cruzada — hoja En proceso

Versión objetivo: **2026.09.30.4.5 · AUDITORÍA HOJA EN PROCESO**

Esta actualización modifica únicamente la lógica de auditoría cruzada y sus pruebas/UI asociadas.
No cambia contratos, certificaciones, movimientos, búsqueda ni cálculo de capacidad.

## Regla nueva
La auditoría cruza el sistema de planificación exclusivamente contra la hoja **En proceso** del Excel.

Por equipo se usa el último registro operativo de esa hoja:
- **Estatus MP = Listo / Entregado / Finalizado** → el equipo se considera en **Faena**.
- **Estatus MP = En proceso / En taller** → el equipo se considera en el **Taller** indicado.
- Si el estatus no resuelve el caso y **Fecha Entrega** ya pasó → se considera **Faena**.
- Si la intervención ya inició y **Fecha Entrega** aún no llega → se considera en **Taller**.
- Si el equipo no aparece en **En proceso**, no se genera discrepancia usando Mov. equipos u otras hojas.

La comparación de fechas también usa **Fecha Entrega** de la hoja En proceso.

## Subida a GitHub
Subir el contenido de este paquete sobre el repositorio actual y confirmar directamente en `main`.
Luego reiniciar la app desde Streamlit (`Manage app` → `Reboot app`) y forzar `Ctrl+F5`.
