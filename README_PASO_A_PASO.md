# Centro de Control Enaex — instalación paso a paso

Este proyecto reemplaza el archivo único de 400 líneas por una aplicación modular. Mantiene lo que ya tenías y agrega las correcciones solicitadas: contratos, certificaciones, búsqueda múltiple, consolidación entre hojas, movimientos, capacidad de talleres, vista por faena e IA opcional.

## 1. Qué vas a obtener

La aplicación tiene cuatro pestañas:

1. **Alertas:** cumplimiento de los 22 contratos y certificaciones vencidas o próximas a vencer.
2. **Buscar Equipo:** ficha técnica por nombre, patente o VIN; permite varios equipos separados por comas.
3. **Movimientos de Equipos:** bajadas a taller, subidas a faena y capacidad actual.
4. **Ver por Faena:** selector de faena, objetivo contractual y equipos GPS únicos.

La aplicación funciona aunque Gemini falle, esté sin cuota o no tenga clave. La IA solo se ejecuta al presionar el botón de auditoría.

---

# PARTE A — Reemplazar la aplicación sin perder lo anterior

## Paso 1. Guarda una copia del repositorio

En GitHub Desktop:

1. Abre tu repositorio.
2. Pulsa **Current branch**.
3. Pulsa **New branch**.
4. Escribe `respaldo-app-antigua`.
5. Pulsa **Create branch**.
6. Pulsa **Publish branch**.

Con esto siempre podrás volver a la versión anterior.

## Paso 2. Crea la rama de instalación

1. Vuelve a la rama `main`.
2. Pulsa **Fetch origin** y después **Pull origin**, si aparece.
3. Pulsa **Current branch > New branch**.
4. Escribe `app-nueva-completa`.
5. Pulsa **Create branch**.

Todos los pasos siguientes deben hacerse en `app-nueva-completa`, no en `main`.

## Paso 3. Copia este proyecto al repositorio

1. Descomprime el ZIP entregado por ChatGPT.
2. En GitHub Desktop selecciona **Repository > Show in Explorer**.
3. Abre la carpeta descomprimida y copia todos sus archivos al repositorio.
4. Cuando Windows pregunte si quieres reemplazar archivos con el mismo nombre, acepta.

El proyecto incluye una copia del código antiguo en:

```text
legacy/centro_de_control_enaex_original.py
```

Tu carpeta principal debe verse así:

```text
app.py
centro_de_control_enaex.py
requirements.txt
INSTALAR.bat
EJECUTAR.bat
PROBAR.bat
README_PASO_A_PASO.md

.streamlit/
assets/
enaex/
tests/
legacy/
```

`centro_de_control_enaex.py` se conserva como archivo de compatibilidad. Si tu despliegue actual apunta a ese nombre, seguirá abriendo la aplicación nueva.

---

# PARTE B — Configurar Excel, GPS y Gemini

## Paso 4. Crea el archivo de configuración

Entra a la carpeta `.streamlit`.

Allí verás:

```text
secrets.toml.example
```

Haz una copia y renómbrala exactamente:

```text
secrets.toml
```

Windows puede ocultar las extensiones. Confirma que no quede como `secrets.toml.txt`.

## Paso 5. Configura la clave GPS

Abre `.streamlit/secrets.toml` con Bloc de notas o Visual Studio Code.

Busca:

```toml
GPS_API_KEY = "PEGA_AQUI_LA_CLAVE_GPS_QUE_YA_USAS"
```

Reemplaza solamente el texto entre comillas por la clave que estaba en tu aplicación anterior.

No borres las comillas.

Los dos enlaces Excel que ya usabas vienen escritos en el ejemplo. No necesitas cambiarlos, salvo que hayan sido reemplazados por otros archivos.

## Paso 6. Activa Gemini, si deseas usar IA

Busca:

```toml
GEMINI_API_KEY = "PEGA_AQUI_TU_CLAVE_GEMINI"
```

Pega tu clave Gemini entre comillas.

Puedes dejar:

```toml
GEMINI_MODEL = ""
```

La aplicación consultará los modelos disponibles para tu clave y seleccionará automáticamente uno de texto, priorizando modelos Flash para reducir tiempo y cuota.

Si no agregas una clave Gemini, todo lo demás continuará funcionando.

---

# PARTE C — Instalar y ejecutar en Windows

## Paso 7. Instala Python

Instala Python 3.12 o 3.11. Durante la instalación marca:

```text
Add Python to PATH
```

Después reinicia el computador si Windows no reconoce Python.

## Paso 8. Instala la aplicación

Haz doble clic en:

```text
INSTALAR.bat
```

Este archivo hará automáticamente lo siguiente:

1. Creará un entorno aislado llamado `.venv`.
2. Instalará Streamlit, pandas, openpyxl, requests, RapidFuzz, Google Gen AI y pytest.
3. Creará `secrets.toml` desde el ejemplo si aún no existe.

Es normal que la primera instalación tarde algunos minutos.

## Paso 9. Ejecuta las pruebas

Haz doble clic en:

```text
PROBAR.bat
```

Debes ver:

```text
11 passed
```

Las pruebas revisan:

- fechas de Excel;
- separación entre Centinela y Nueva Centinela;
- consolidación entre hojas mediante patente;
- deduplicación de GPS;
- búsqueda por patente;
- certificaciones históricas;
- capacidad de talleres;
- exclusión de trabajos finalizados.

## Paso 10. Abre la aplicación

Haz doble clic en:

```text
EJECUTAR.bat
```

Se abrirá el navegador. La dirección local normalmente será:

```text
http://localhost:8501
```

No cierres la ventana negra mientras uses la aplicación.

---

# PARTE D — Cómo comprobar cada requerimiento

## 1. Carga independiente de la IA

1. Abre la aplicación sin una clave Gemini.
2. Comprueba que Alertas, Buscar Equipo, Movimientos y Ver por Faena funcionen.
3. La barra lateral debe indicar que la IA está desactivada.

Esto confirma que Gemini no controla los datos crudos.

## 2. Conteo de contratos sin pings repetidos

En Alertas, cada tarjeta debe indicar:

```text
X de Y equipos únicos
```

La aplicación normaliza el nombre del equipo y elimina registros repetidos antes de contar.

Los estados posibles son:

- `Faltan`;
- `Cumplido`;
- `Sobre objetivo`.

## 3. Búsqueda múltiple

Prueba una consulta como:

```text
Quadra-70, Auger-165
```

Después prueba una patente y un VIN.

La ficha debe mostrar:

- patente;
- VIN/chasis;
- marca;
- modelo;
- año;
- capacidad;
- sistema de control;
- horómetro GPS;
- ubicación y estado GPS;
- Revisión Técnica;
- Sernageomin;
- DGMN;
- último estatus de planificación;
- taller;
- bajada;
- subida o entrega;
- comentario.

## 4. Consolidación entre hojas

La app vincula registros mediante tres identificadores:

1. código o nombre del equipo;
2. patente;
3. VIN/chasis.

Ejemplo: si una hoja contiene `Quadra-70 + ABCD12` y otra contiene `ABCD12 + En taller`, ambas filas se unen en la misma ficha.

## 5. Certificaciones

La aplicación escanea todo el historial y utiliza la fecha válida más reciente de cada documento. Esto evita mostrar una renovación antigua como vencida cuando existe otra posterior.

Estados:

- `Vencida`;
- `Vence pronto`, cuando faltan 30 días o menos;
- `Vigente`;
- `Sin fecha`;
- `Fecha inválida`.

## 6. Movimientos

La pestaña Movimientos permite cambiar la ventana, que comienza en ±15 días.

Para cada bajada muestra:

- equipo;
- fecha;
- taller exacto;
- estatus;
- comentario;
- hoja de origen.

Para cada subida muestra:

- equipo;
- fecha;
- faena exacta;
- estatus;
- comentario;
- hoja de origen.

## 7. Capacidad de talleres

Se aplican estos límites:

```text
SKC Alto Hospicio: 2
SKC Calama: 4
SKC Antofagasta: 2
Río Loa: 2
SKC Copiapó: 2
Full RPM: 4
```

Se considera activo un equipo cuando:

- su fecha de inicio ya ocurrió;
- su fecha de entrega todavía no ocurre o está vacía;
- su estatus no indica finalizado, cancelado, cerrado, entregado o liberado.

Un mismo equipo se cuenta solo una vez.

## 8. Vista por faena sin KeyError

La tabla se construye únicamente con campos existentes. Si la API no entrega marca, modelo, estado o timestamp, la aplicación muestra lo disponible y no colapsa.

## 9. Auditoría IA

Busca uno o más equipos y pulsa:

```text
Auditar todos los equipos mostrados con IA
```

Se realiza una sola llamada para el conjunto completo, no una llamada por ficha. Gemini debe responder como máximo dos líneas por equipo y no es responsable de cargar datos.

---

# PARTE E — Diagnóstico cuando una columna no aparece

La barra lateral contiene:

```text
Diagnóstico de columnas Excel
```

Allí verás campos como:

```text
equipment
plate
vin
brand
model
status
workshop
start_date
end_date
faena
revision_tecnica
sernageomin
dgmn
```

Si un campo dice `No detectada`, la planilla usa un encabezado que todavía no está registrado.

Los alias están en:

```text
enaex/aliases.py
```

Ejemplo: si la fecha de bajada se llama `Fecha Programada de Entrada MP`, agrégala dentro de `start_date`:

```python
"start_date": (
    ...,
    "fecha programada de entrada mp",
),
```

Solo debes agregar el nombre. No necesitas modificar la lógica de la aplicación.

---

# PARTE F — Subir a GitHub

Cuando la app funcione localmente:

1. Abre GitHub Desktop.
2. Comprueba que la rama sea `app-nueva-completa`.
3. Confirma que `.streamlit/secrets.toml` no aparezca en la lista de cambios. Está excluido mediante `.gitignore`.
4. Escribe el mensaje:

```text
Instala nueva aplicación modular de control de flota
```

5. Pulsa **Commit to app-nueva-completa**.
6. Pulsa **Publish branch** o **Push origin**.

Después despliega una aplicación de prueba usando:

```text
Branch: app-nueva-completa
Main file path: app.py
```

También puedes mantener el archivo de entrada anterior:

```text
centro_de_control_enaex.py
```

Ambos abren la misma aplicación.

En los secretos del servicio de despliegue pega el mismo contenido de tu `secrets.toml` local.

---

# Qué puede requerir un último ajuste

El código está construido y probado, pero los libros Excel y la API GPS reales no estuvieron disponibles dentro del entorno de desarrollo. Por ello, el único ajuste que podría quedar es agregar uno o más nombres exactos de columnas particulares en `enaex/aliases.py`.

No se usan datos simulados dentro de la aplicación. Cuando una fuente no responde, la app lo informa y sigue utilizando las otras fuentes disponibles.
