# Actualización Lugar vacío = Faena

Esta versión aplica la regla operacional validada: si un equipo tiene una faena válida y la API deja `Lugar` vacío/N/A, la aplicación muestra **Faena**. Los lugares explícitos (SKC, INDUMAR, FullRPM, etc.) se conservan sin cambios.

Archivos modificados:
- app_v2.py
- enaex/processing.py
- enaex/ui/faenas.py
- enaex/ui/common.py
- tests/test_core.py
