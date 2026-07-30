import streamlit as st
import pandas as pd
import google.generativeai as genai
import concurrent.futures
import requests
import datetime
import re

st.set_page_config(page_title="Control Flota Enaex", layout="wide", page_icon="🚛")

st.markdown("""
    <div style="display: flex; align-items: center; gap: 20px;">
        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/Enaex_logo.svg/512px-Enaex_logo.svg.png" alt="Enaex" width="160" onerror="this.style.display='none'">
        <h1 style="margin: 0; color: #1E3A8A;">🚛 Centro de Control: Flota y Auditoría</h1>
    </div>
    <hr style="margin-top: 10px; margin-bottom: 20px;">
""", unsafe_allow_html=True)

API_KEY_DASHBOARD = "CX92wBe9wV2NLUMyFE6PzvcyqTWyBPr5"
ENLACES_EXCEL = [
    "https://docs.google.com/spreadsheets/d/1PUlnTUm_CpkvrpVoKJN_3nyD9khxITDV/edit?usp=sharing",
    "https://docs.google.com/spreadsheets/d/1VrDHEb-D7oeypyYdhUpd3_tw_jggTu3K/edit?usp=drive_link&ouid=112672268024787990541&rtpof=true&sd=true"
]

# Basado exactamente en la tabla proporcionada en la imagen
CONTRATOS_OBJETIVO = {
    "Centinela": 13, "Collahuasi": 6, "Los Bronces": 7, "Los Pelambres": 5,
    "Nueva Centinela": 3, "Radomiro Tomic": 5, "Sierra Gorda": 6, "Spence": 5,
    "Andina": 5, "Antucoya": 3, "Chuquicamata": 2, "Lomas Bayas": 5,
    "Los Colorados": 3, "Salvador": 4, "Teniente": 1, "Zaldivar": 2,
    "Cerro Negro": 1, "El Soldado": 2, "Michilla": 1, "Pleito": 1,
    "Romeral": 1, "Salares Norte": 1
}

CAPACIDAD_TALLERES = {
    "SKC ALTO HOSPICIO": 2, "SKC CALAMA": 4, "SKC ANTOFAGASTA": 2,
    "RIO LOA": 2, "SKC COPIAPO": 2, "FULL RPM": 4
}

MODELOS_SEGUROS = ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-1.0-pro', 'gemini-pro']

@st.cache_resource
def configurar_ia(api_key):
    if not api_key: return None
    genai.configure(api_key=api_key)
    for nombre_modelo in MODELOS_SEGUROS:
        try:
            return genai.GenerativeModel(nombre_modelo)
        except Exception:
            continue
    return None

try: API_KEY_GEMINI = st.secrets.get("GEMINI_API_KEY", "")
except: API_KEY_GEMINI = ""
modelo_ia = configurar_ia(API_KEY_GEMINI)

@st.cache_data(ttl=600)
def cargar_excels(urls):
    df_maestro = pd.DataFrame()
    for url in urls:
        try:
            if "/d/" in url:
                id_archivo = url.split('/d/')[1].split('/')[0]
                url_descarga = f"https://drive.google.com/uc?export=download&id={id_archivo}"
                dict_hojas = pd.read_excel(url_descarga, sheet_name=None)
                for nombre_hoja, df_hoja in dict_hojas.items():
                    df_hoja['Origen_Hoja'] = nombre_hoja
                    df_maestro = pd.concat([df_maestro, df_hoja], ignore_index=True)
        except Exception: pass
    return df_maestro

@st.cache_data(ttl=300)
def extraer_api():
    tipos = [27, 26, 24, 21, 23, 41]
    zonas = list(range(1, 14))
    datos = []
    def fetch(t, z):
        try:
            r = requests.get(f"http://40.65.224.42/api/dashboard/estado/{t}/{z}?key={API_KEY_DASHBOARD}", timeout=5)
            if r.status_code == 200: return r.json()
        except: return []
        return []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futuros = [executor.submit(fetch, t, z) for t in tipos for z in zonas]
        for f in concurrent.futures.as_completed(futuros):
            res = f.result()
            if isinstance(res, list) and len(res) > 0: datos.extend(res)
    return pd.DataFrame(datos)

def buscar_dato_flexible(df_equipo, palabras_clave):
    """Escanea TODAS las filas de un equipo desde la más nueva a la más antigua para encontrar un dato"""
    if df_equipo is None or df_equipo.empty: return "N/A"
    
    for index, row in df_equipo.iloc[::-1].iterrows():
        for col in df_equipo.columns:
            col_str = str(col).lower().strip()
            for palabra in palabras_clave:
                if palabra in col_str:
                    valor = row[col]
                    if pd.notna(valor) and str(valor).strip().lower() not in ['nan', 'nat', 'none', '']:
                        return str(valor).strip()
    return "N/A"

def formatear_fecha(fecha_str):
    if pd.isna(fecha_str) or fecha_str == "N/A" or str(fecha_str).strip() == "": return "N/A"
    try: return pd.to_datetime(fecha_str, dayfirst=True).strftime('%d/%m/%Y')
    except: return str(fecha_str).split('T')[0].split(' ')[0]

def parsear_fecha_real(fecha_str):
    if pd.isna(fecha_str) or fecha_str == "N/A" or str(fecha_str).strip() == "": return None
    try: return pd.to_datetime(fecha_str, dayfirst=True)
    except: return None

def normalizar_taller(nombre):
    if not nombre or nombre == "N/A": return "N/A"
    n = str(nombre).upper().strip()
    if "HOSPICIO" in n: return "SKC ALTO HOSPICIO"
    if "CALAMA" in n or "MECANICAL" in n: return "SKC CALAMA"
    if "ANTOFAGASTA" in n: return "SKC ANTOFAGASTA"
    if "LOA" in n: return "RIO LOA"
    if "COPIAP" in n: return "SKC COPIAPO"
    if "FULL" in n or "RPM" in n: return "FULL RPM"
    return n

def contar_equipos_faena(faena_obj, conteo_dict):
    """Cuenta equipos evitando que 'Centinela' sume los de 'Nueva Centinela'"""
    total = 0
    for faena_api, cant in conteo_dict.items():
        faena_api_str = str(faena_api).lower()
        if faena_obj.lower() == "centinela":
            if "centinela" in faena_api_str and "nueva" not in faena_api_str: total += cant
        elif faena_obj.lower() in faena_api_str: total += cant
    return total

with st.spinner("Descargando sistemas en vivo y planillas de Excel (Procesamiento Global)..."):
    df_excel_global = cargar_excels(ENLACES_EXCEL)
    df_api_global = extraer_api()
    
    # CRUCIAL: Eliminar duplicados para no inflar los contadores de contratos
    if not df_api_global.empty and 'nombre' in df_api_global.columns:
        # Ordenamos por horas_ult para quedarnos con el registro más reciente del GPS
        df_api_unicos = df_api_global.sort_values('horas_ult', ascending=False, na_position='last').drop_duplicates(subset=['nombre'])
    else:
        df_api_unicos = pd.DataFrame()

tab_alertas, tab_equipos, tab_movimientos, tab_faenas = st.tabs([
    "🚨 Alertas", "🔍 Buscar Equipo", "📅 Movimientos de Equipos", "📍 Ver por Faena"
])

with tab_alertas:
    st.header("🚨 Panel de Alertas Tempranas")
    st.subheader("⚖️ Estado de Cumplimiento de Contratos")
    
    if not df_api_unicos.empty and 'nombre_faena' in df_api_unicos.columns:
        conteo_faenas = df_api_unicos['nombre_faena'].value_counts().to_dict()
        cols = st.columns(6)
        
        for idx, (faena_obj, target) in enumerate(CONTRATOS_OBJETIVO.items()):
            actual = contar_equipos_faena(faena_obj, conteo_faenas)
            with cols[idx % 6]:
                if actual < target:
                    st.error(f"**{faena_obj}**\n\n🔴 Faltan: {target - actual}\n\n*{actual} de {target}*")
                elif actual == target:
                    st.warning(f"**{faena_obj}**\n\n🟡 Al límite\n\n*{actual} de {target}*")
                else:
                    st.success(f"**{faena_obj}**\n\n🟢 OK\n\n*{actual} de {target}*")
    else:
        st.info("No hay datos de API disponibles para calcular contratos.")

    st.markdown("---")
    st.subheader("⚠️ Alertas Críticas de Certificaciones (SNGM, RT, DGMN)")
    
    alertas_certificaciones = []
    if not df_excel_global.empty:
        col_equipo = None
        for col in df_excel_global.columns:
            if 'equipo' in str(col).lower().strip(): col_equipo = col; break
                
        if col_equipo:
            equipos_unicos = df_excel_global[col_equipo].dropna().unique()
            hoy = pd.Timestamp.now().normalize()
            limite_30_dias = hoy + pd.Timedelta(days=30)
            
            for eq in equipos_unicos:
                eq_str = str(eq).strip()
                if eq_str.lower() in ['nan', 'none', '']: continue
                
                df_eq = df_excel_global[df_excel_global[col_equipo] == eq]
                
                rt_str = buscar_dato_flexible(df_eq, ['revisión técnica', 'revision tecnica', 'rt'])
                sngm_str = buscar_dato_flexible(df_eq, ['sernageomin', 'sngm'])
                dgmn_str = buscar_dato_flexible(df_eq, ['dgmn'])
                
                docs = [("Revisión Técnica", rt_str), ("Sernageomin", sngm_str), ("DGMN", dgmn_str)]
                
                for nombre_doc, fecha_str in docs:
                    f_parseada = parsear_fecha_real(fecha_str)
                    if f_parseada:
                        if f_parseada < hoy:
                            alertas_certificaciones.append(f"❌ **{eq_str}**: {nombre_doc} VENCIDA ({f_parseada.strftime('%d/%m/%Y')})")
                        elif f_parseada <= limite_30_dias:
                            alertas_certificaciones.append(f"⚠️ **{eq_str}**: {nombre_doc} vence pronto ({f_parseada.strftime('%d/%m/%Y')})")

    if alertas_certificaciones:
        for alerta in alertas_certificaciones:
            st.markdown(alerta)
    else:
        st.success("Toda la flota registra certificaciones al día o con más de 30 días de vigencia en el Excel.")

with tab_equipos:
    st.header("🔍 Búsqueda y Auditoría Individual")
    equipos_input = st.text_input("Ingresa el nombre o código del equipo (Ej: Quadra-70, Auger-165):")
    
    if st.button("Consultar Ficha Técnica") and equipos_input:
        nombres = [eq.strip().upper() for eq in equipos_input.split(",") if eq.strip()]
        
        for nombre in nombres:
            df_historial_equipo = pd.DataFrame()
            if not df_excel_global.empty:
                df_historial_equipo = df_excel_global[df_excel_global.astype(str).apply(lambda x: x.str.upper().str.contains(nombre)).any(axis=1)]

            df_api_equipo = pd.DataFrame()
            if not df_api_unicos.empty and 'nombre' in df_api_unicos.columns:
                df_api_equipo = df_api_unicos[df_api_unicos['nombre'].str.upper().str.contains(nombre, na=False)]
            
            if df_historial_equipo.empty and df_api_equipo.empty:
                st.error(f"❌ No se encontró '{nombre}' ni en Excel ni en API.")
                continue
                
            patente = buscar_dato_flexible(df_historial_equipo, ['patente', 'placa', 'ppu'])
            vin = buscar_dato_flexible(df_historial_equipo, ['vin', 'chasis', 'serie'])
            marca = buscar_dato_flexible(df_historial_equipo, ['marca'])
            modelo = buscar_dato_flexible(df_historial_equipo, ['modelo', 'año', 'year'])
            capacidad = buscar_dato_flexible(df_historial_equipo, ['capacidad', 'tonelaje', 'tons'])
            control = buscar_dato_flexible(df_historial_equipo, ['control', 'sistema'])
            
            rt = formatear_fecha(buscar_dato_flexible(df_historial_equipo, ['revisión técnica', 'revision tecnica']))
            sngm = formatear_fecha(buscar_dato_flexible(df_historial_equipo, ['sernageomin', 'sngm']))
            dgmn = formatear_fecha(buscar_dato_flexible(df_historial_equipo, ['dgmn']))
            
            estatus_taller = buscar_dato_flexible(df_historial_equipo, ['estatus mp', 'status', 'estado'])
            ubicacion_taller = buscar_dato_flexible(df_historial_equipo, ['ubicación', 'taller', 'lugar'])
            comentarios = buscar_dato_flexible(df_historial_equipo, ['motivo', 'comentario', 'trabajos'])
            
            fecha_inicio = formatear_fecha(buscar_dato_flexible(df_historial_equipo, ['fecha inicio', 'inicio planificado', 'inici']))
            fecha_entrega = formatear_fecha(buscar_dato_flexible(df_historial_equipo, ['fecha entrega', 'fin planificado', 'fina']))

            ubicacion_gps = df_api_equipo['nombre_faena'].iloc[0] if not df_api_equipo.empty and 'nombre_faena' in df_api_equipo.columns else "No reporta GPS"
            estado_gps = df_api_equipo['Estado_Deducido'].iloc[0] if not df_api_equipo.empty and 'Estado_Deducido' in df_api_equipo.columns else "N/A"
            horometro = df_api_equipo['horas_ult'].iloc[0] if not df_api_equipo.empty and 'horas_ult' in df_api_equipo.columns else "N/A"

            st.markdown(f"### 🚛 Ficha Técnica: {nombre}")
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 📡 Hardware e Identificación")
                st.info(f"📍 **Ubicación GPS (API):** {ubicacion_gps} | ⚙️ **Estado:** {estado_gps}")
                
                c1, c2 = st.columns(2)
                c1.markdown(f"**Patente:** {patente}")
                c1.markdown(f"**Marca/Modelo:** {marca} {modelo}")
                c1.markdown(f"**VIN/Chasis:** {vin}")
                
                c2.markdown(f"**Capacidad:** {capacidad}")
                c2.markdown(f"**Control:** {control}")
                c2.markdown(f"**Horómetro:** {horometro}")
                
                st.markdown("**🗓️ Certificaciones (Plazos):**")
                st.caption(f"Revisión Técnica: {rt} | Sernageomin: {sngm} | DGMN: {dgmn}")

            with col2:
                st.markdown("#### 🗓️ Planificación de Mantenimiento")
                st.success(f"📋 **Estatus Taller:** {estatus_taller} | **Ubicación:** {ubicacion_taller}")
                
                st.markdown(f"**🗓️ Fechas Planificadas (Excel):**")
                st.markdown(f"- **Bajada a Taller (Inicio):** {fecha_inicio}")
                st.markdown(f"- **Subida a Faena (Entrega):** {fecha_entrega}")
                st.markdown(f"💬 **Trabajos / Motivo:** {comentarios}")
            
            if modelo_ia:
                with st.expander("🤖 Auditoría Automática (IA)"):
                    try:
                        prompt = f"Analiza en 2 líneas. Equipo {nombre}. Bajada: {fecha_inicio}, Subida {fecha_entrega}, estatus {estatus_taller}, ubicado en {ubicacion_taller}. Según GPS está en {ubicacion_gps}. ¿Hay incongruencias?"
                        res = modelo_ia.generate_content(prompt)
                        st.write(res.text)
                    except:
                        st.warning("⚠️ Límite de IA alcanzado (Espera 60 seg). Los datos de la ficha son correctos y operables.")
            st.divider()

with tab_movimientos:
    st.header("📅 Control de Subidas, Bajadas y Capacidad")
    st.write("Análisis logístico de movimientos recientes y próximos (Ventana de ±15 días).")
    
    if st.button("Calcular Movimientos"):
        if df_excel_global.empty:
            st.error("No hay datos en el Excel para procesar.")
        else:
            hoy = pd.Timestamp.now().normalize()
            limite_inferior = hoy - pd.Timedelta(days=15)
            limite_superior = hoy + pd.Timedelta(days=15)
            
            subidas = []
            bajadas = []
            carga_actual = {k: 0 for k in CAPACIDAD_TALLERES.keys()}
            equipos_procesados = set()
            
            col_eq = None
            for col in df_excel_global.columns:
                if 'equipo' in str(col).lower().strip(): col_eq = col; break

            if col_eq:
                for _, row in df_excel_global.iloc[::-1].iterrows():
                    equipo = str(row[col_eq]).strip().upper()
                    if pd.isna(row[col_eq]) or equipo == "NAN" or equipo in equipos_procesados: continue
                    equipos_procesados.add(equipo)
                    
                    df_row = pd.DataFrame([row])
                    f_inicio_str = buscar_dato_flexible(df_row, ['fecha inicio', 'inicio planificado', 'inici'])
                    f_entrega_str = buscar_dato_flexible(df_row, ['fecha entrega', 'fin planificado', 'fina'])
                    faena_obj = buscar_dato_flexible(df_row, ['faena', 'contrato'])
                    taller_raw = buscar_dato_flexible(df_row, ['ubicación', 'taller'])
                    taller_norm = normalizar_taller(taller_raw)
                    
                    f_ini = parsear_fecha_real(f_inicio_str)
                    f_fin = parsear_fecha_real(f_entrega_str)
                    
                    if f_ini and limite_inferior <= f_ini <= limite_superior:
                        bajadas.append(f"🔧 **{equipo}** ➔ Baja a: **{taller_raw}** ({f_ini.strftime('%d/%m')})")
                        
                    if f_fin and limite_inferior <= f_fin <= limite_superior:
                        subidas.append(f"📈 **{equipo}** ➔ Sube a: **{faena_obj}** ({f_fin.strftime('%d/%m')})")
                    
                    # Capacidad: Si inició antes de hoy y aún no lo entregan
                    en_taller = False
                    if f_ini and f_ini <= hoy:
                        if not f_fin or f_fin >= hoy:
                            en_taller = True
                            
                    if en_taller and taller_norm in carga_actual:
                        carga_actual[taller_norm] += 1

                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.warning("### 📉 Bajan a Taller (±15 Días)")
                    if bajadas:
                        for b in bajadas: st.markdown(b)
                    else: st.success("No hay bajadas registradas en esta ventana de tiempo.")
                        
                with col_m2:
                    st.success("### ⛰️ Suben a Faena (±15 Días)")
                    if subidas:
                        for s in subidas: st.markdown(s)
                    else: st.info("No hay subidas registradas en esta ventana de tiempo.")

                st.divider()
                st.subheader("⚖️ Estado de Capacidad por Taller (Ocupados / Límite)")
                cols_talleres = st.columns(3)
                
                for i, (taller, limite) in enumerate(CAPACIDAD_TALLERES.items()):
                    ocupados = carga_actual.get(taller, 0)
                    with cols_talleres[i % 3]:
                        if ocupados > limite: st.error(f"**{taller}**\n\n🔴 SOBREPASADO\n\nEquipos: {ocupados} / {limite}")
                        elif ocupados == limite: st.warning(f"**{taller}**\n\n🟡 AL LÍMITE\n\nEquipos: {ocupados} / {limite}")
                        else: st.success(f"**{taller}**\n\n🟢 CON ESPACIO\n\nEquipos: {ocupados} / {limite}")

with tab_faenas:
    st.header("📍 Vista Global de Faenas")
    if not df_api_unicos.empty and 'nombre_faena' in df_api_unicos.columns:
        faenas_activas = sorted([str(f) for f in df_api_unicos['nombre_faena'].dropna().unique() if str(f).strip() != ""])
        
        # Combinar las faenas reales del GPS con las del diccionario por si alguna falta
        todas_las_opciones = sorted(list(set(faenas_activas + list(CONTRATOS_OBJETIVO.keys()))))
        
        faena_seleccionada = st.selectbox("Selecciona la Faena / Contrato:", ["(Elige una Faena)"] + todas_las_opciones)
        
        if faena_seleccionada != "(Elige una Faena)":
            # Filtrado inteligente (incluye variaciones de nombre en GPS)
            df_filtrado = df_api_unicos[df_api_unicos['nombre_faena'].astype(str).str.contains(faena_seleccionada, case=False, na=False)]
            
            equipos_actuales = len(df_filtrado)
            target = CONTRATOS_OBJETIVO.get(faena_seleccionada, 0)
            
            st.markdown(f"### Análisis de Contrato: {faena_seleccionada}")
            
            if target > 0:
                if equipos_actuales < target: st.error(f"**Objetivo:** {target} equipos | **Actual en Faena:** {equipos_actuales} equipos ➔ FALTAN {target - equipos_actuales}")
                else: st.success(f"**Objetivo:** {target} equipos | **Actual en Faena:** {equipos_actuales} equipos ➔ CUMPLIDO")
            else:
                st.info(f"**Actual en Faena:** {equipos_actuales} equipos (Sin cuota objetivo registrada)")
            
            columnas_deseadas = ['nombre', 'marca_nombre', 'horas_ult', 'Estado_Deducido']
            columnas_existentes = [col for col in columnas_deseadas if col in df_filtrado.columns]
            
            if not df_filtrado.empty:
                st.dataframe(df_filtrado[columnas_existentes].reset_index(drop=True), use_container_width=True)
            else:
                st.write(f"No hay camiones reportando señal GPS en {faena_seleccionada} en este momento.")
    else:
        st.write("Conectando con GPS / Sin datos en vivo disponibles.")