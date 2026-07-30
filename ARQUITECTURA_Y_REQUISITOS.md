# Arquitectura y cobertura de requisitos

## Archivos principales

- `app.py`: arranque y pestañas.
- `enaex/data_sources.py`: descarga paralela de Excel y GPS.
- `enaex/aliases.py`: nombres alternativos de columnas.
- `enaex/processing.py`: consolidación, deduplicación, contratos, certificaciones y movimientos.
- `enaex/ai_service.py`: Gemini opcional y una sola llamada por auditoría.
- `enaex/ui/`: componentes visuales independientes.
- `tests/`: pruebas de regresión.

## Decisiones para maximizar rapidez

- Descarga de los Excel en paralelo.
- Consultas GPS concurrentes.
- Un único snapshot cacheado por cinco minutos.
- Índice consolidado de nombre, patente y VIN.
- Datos procesados antes de dibujar las pestañas.
- IA ejecutada solo bajo demanda.

## Cobertura

- Error 404 de Gemini: detección dinámica de modelos.
- Cuota IA: mensaje amarillo, sin detener la app.
- Excel/GPS independientes de IA.
- Logo PNG local con reemplazo textual si falta.
- Fechas `DD/MM/YYYY`.
- Búsqueda múltiple y flexible.
- Unión entre hojas por equipo/patente/VIN.
- Último estado y comentario.
- Movimientos en pestaña separada.
- Destinos de taller y faena.
- Ventana ±15 días configurable.
- Capacidad de seis talleres.
- 22 contratos.
- GPS deduplicado.
- Certificaciones históricas.
- Selector por faena.
- Protección ante columnas GPS faltantes.
- Sin mock data.
- Pruebas automáticas para evitar regresiones.
