import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import google.generativeai as genai
import json
import os
import re
import unicodedata

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="ERP Construcción", layout="wide", initial_sidebar_state="expanded")

# --- ESTÉTICA VERDE CLARO PROFESIONAL (INYECCIÓN DE CSS) ---
st.markdown("""
    <style>
    /* Fondo principal y color de texto (Tonos claros y legibles) */
    .stApp {
        background-color: #f4f9f5;
        color: #1a3324;
    }
    
    /* Barra lateral */
    [data-testid="stSidebar"] {
        background-color: #e6f0ea !important;
        border-right: 1px solid #cce0d5;
    }
    
    /* Quitar el padding gigante superior de la barra lateral */
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem !important;
    }
    
    /* Compactar botones de radio (el menú) */
    .stRadio [role="radiogroup"] {
        gap: 0.1rem !important;
    }
    .stRadio label {
        padding: 2px 0px !important;
        font-size: 0.85rem !important;
        color: #2d4d3a !important;
    }
    
    /* Diseño de los selectores y campos de entrada */
    .stSelectbox div[data-baseweb="select"], .stTextInput input, .stNumberInput input, .stTextArea textarea {
        background-color: #ffffff !important;
        border: 1px solid #b3ccbe !important;
        border-radius: 4px !important;
        color: #1a3324 !important;
        font-size: 0.85rem !important;
        min-height: 32px !important;
    }
    
    /* Líneas separadoras más sutiles */
    hr {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
        border-color: #cce0d5 !important;
    }
    
    /* Textos descriptivos pequeños */
    .small-text {
        font-size: 0.75rem;
        color: #557c65;
        margin-bottom: 2px;
        margin-top: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Título superior de la app */
    .app-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #122b1c;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# 🔴 PEGA AQUÍ LA URL COMPLETA DE TU GOOGLE SHEETS "MAESTRO" 🔴
URL_MAESTRO = "https://docs.google.com/spreadsheets/d/1Ua_8c_VgY_mKN_xN_TX_yXkwhoolkl8KOx3YRndcVdo/edit?gid=1271955705#gid=1271955705"

# --- CONEXIÓN IA ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.sidebar.warning("Aviso: Clave de Gemini no encontrada en Secrets.")

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_datos(hoja, url):
    try:
        return conn.read(spreadsheet=url, worksheet=hoja, ttl=0)
    except Exception:
        return pd.DataFrame()

def guardar_datos(hoja, df, url):
    conn.update(spreadsheet=url, worksheet=hoja, data=df)

def calcular_coste_personal(texto_personal, horas, df_tarifas):
    if not texto_personal or horas <= 0 or df_tarifas.empty: return 0.0
    texto_personal = str(texto_personal).lower()
    costes = []
    for _, tarifa in df_tarifas.iterrows():
        nombre_tarifa = str(tarifa['Recurso']).lower()
        if nombre_tarifa and nombre_tarifa != "nan" and nombre_tarifa in texto_personal:
            costes.append(pd.to_numeric(tarifa['Coste_Hora'], errors='coerce'))
    return sum(costes) * float(horas) if costes else 0.0

# --- ASISTENTE IA GENÉRICO ---
def modulo_chat_ia(nombre_modulo, dicc_dataframes):
    chat_key = f"chat_{nombre_modulo.replace(' ', '_')}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []
        
    st.markdown(f"**Asistente de Datos: {nombre_modulo}**")
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input(f"Consultar datos de {nombre_modulo}..."):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        contexto = f"Eres un analista de datos para un ERP de construcción. Módulo: '{nombre_modulo}'.\nDATOS:\n"
        for nombre_tabla, df in dicc_dataframes.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                contexto += f"--- {nombre_tabla} ---\n{df.to_csv(index=False)}\n\n"
            else:
                contexto += f"--- {nombre_tabla} ---\n(Sin datos)\n\n"
                
        contexto += """Instrucciones: Responde de forma profesional, clara y concisa. Basa tus cálculos estrictamente en los datos adjuntos.\n\nUsuario: """ + prompt
        with st.chat_message("assistant"):
            with st.spinner("Procesando consulta..."):
                try:
                    modelo = genai.GenerativeModel('gemini-2.5-flash')
                    respuesta = modelo.generate_content(contexto)
                    st.markdown(respuesta.text)
                    st.session_state[chat_key].append({"role": "assistant", "content": respuesta.text})
                except Exception as e:
                    st.error(f"Error de IA: {e}")

# --- MEMORIA TEMPORAL ---
if 'ia_datos' not in st.session_state:
    st.session_state.ia_datos = {"Fecha": datetime.today().strftime("%Y-%m-%d"), "Tarea": "", "Descripción_Tarea": "", "Personal": "", "Maquinaria": ""}

# ==========================================
# 0. NAVEGACIÓN Y SELECTOR GLOBAL (COMPACTO)
# ==========================================
if URL_MAESTRO == "PEGAR_AQUI_LA_URL_DEL_MAESTRO":
    st.error("Sistema bloqueado: URL del Maestro no configurada en el código fuente.")
    st.stop()

# Estructura compacta de la barra lateral
st.sidebar.markdown('<p class="app-title">ERP Construcción</p>', unsafe_allow_html=True)

df_maestro = cargar_datos(0, URL_MAESTRO)
if df_maestro.empty:
    st.sidebar.error("Error BD Maestra.")
    st.stop()

obras_activas = df_maestro[df_maestro['Estado'] == 'Activa']
if obras_activas.empty:
    st.sidebar.warning("No hay proyectos.")
    st.stop()

st.sidebar.markdown('<p class="small-text" style="margin-top: 5px;">PROYECTO ACTIVO</p>', unsafe_allow_html=True)
obra_actual = st.sidebar.selectbox("", obras_activas['Nombre_Proyecto'].tolist(), label_visibility="collapsed")
url_obra = obras_activas[obras_activas['Nombre_Proyecto'] == obra_actual]['Enlace_Google_Sheet'].values[0]

st.sidebar.markdown('<hr>', unsafe_allow_html=True)

# --- LÓGICA DE NAVEGACIÓN INSTANTÁNEA ---
if 'vista_activa' not in st.session_state:
    st.session_state.vista_activa = "Gestión de Obras (Diario)"

def cambiar_vista_proyecto():
    st.session_state.vista_activa = st.session_state.rad_proj

def cambiar_vista_global():
    st.session_state.vista_activa = st.session_state.rad_glob

st.sidebar.markdown('<p class="small-text">MÓDULOS DEL PROYECTO</p>', unsafe_allow_html=True)
st.sidebar.radio("", [
    "Gestión de Obras (Diario)",
    "Costes y Rendimientos",
    "Informe Ejecutivo (Finanzas)",
    "Importar Presupuesto",
    "Importar Certificación",
    "Subcontratas"
], key="rad_proj", label_visibility="collapsed", on_change=cambiar_vista_proyecto)

st.sidebar.markdown('<hr>', unsafe_allow_html=True)

st.sidebar.markdown('<p class="small-text">BASES DE DATOS GLOBALES</p>', unsafe_allow_html=True)
st.sidebar.radio("", [
    "Base de Precios",
    "Tarifas (Personal/Maquinaria)"
], key="rad_glob", label_visibility="collapsed", on_change=cambiar_vista_global)

vista_activa = st.session_state.vista_activa

# ==========================================
# 1. GESTIÓN DE OBRAS Y DIARIO
# ==========================================
if vista_activa == "Gestión de Obras (Diario)":
    st.title(f"Gestión de Obra: {obra_actual}")
    
    tab_parte, tab_chat = st.tabs(["Registro de Producción", "Asistente Virtual de Obra"])
    
    with tab_parte:
        st.markdown("### Registro de Jornada")
        with st.form("form_diario"):
            c1, c2 = st.columns(2)
            fecha_input = c1.text_input("Fecha", value=datetime.today().strftime("%Y-%m-%d"))
            
            c_t1, c_t2 = st.columns(2)
            tarea = c_t1.text_input("Tarea General (Agrupador)")
            desc_tarea = c_t2.text_input("Descripción Específica")
            
            c3, c4 = st.columns(2)
            personal = c3.text_input("Personal Asignado")
            h_pers = c4.number_input("Horas Totales Personal", min_value=0.0, step=0.5)
            
            c5, c6 = st.columns(2)
            maq = c5.text_input("Maquinaria Utilizada")
            h_maq = c6.number_input("Horas Maquinaria", min_value=0.0, step=0.5)
            
            c7, c8 = st.columns(2)
            prod = c7.number_input("Producción (Cantidad)", min_value=0.0, step=1.0)
            ud = c8.text_input("Unidad (ej: m2, ml, ud)")
            
            if st.form_submit_button("Guardar Registro"):
                df_diario = cargar_datos("Diario", url_obra)
                nuevo_parte = pd.DataFrame([{
                    "Fecha": fecha_input, "Proyecto": obra_actual, "Tipo_Entrada": "Manual",
                    "Contenido": "Texto manual", "Tarea": tarea, "Descripción_Tarea": desc_tarea,
                    "Personal": personal, "Horas_Personal": h_pers, 
                    "Maquinaria": maq, "Horas_Maq": h_maq, "Produccion": prod, "Unidad": ud
                }])
                df_diario = pd.concat([df_diario, nuevo_parte], ignore_index=True)
                guardar_datos("Diario", df_diario, url_obra)
                
                df_tarifas = cargar_datos("Tarifas_Personal_Maquinaria", URL_MAESTRO)
                coste_p = calcular_coste_personal(personal, h_pers, df_tarifas)
                if coste_p > 0:
                    df_costes = cargar_datos("Costes_Imputados", url_obra)
                    nuevo_coste = pd.DataFrame([{
                        "Fecha": fecha_input, "Proyecto": obra_actual, "Tarea": tarea,
                        "Concepto": f"Mano de obra ({desc_tarea}): {personal}", "Coste_Total": coste_p
                    }])
                    df_costes = pd.concat([df_costes, nuevo_coste], ignore_index=True)
                    guardar_datos("Costes_Imputados", df_costes, url_obra)
                st.success("Registro guardado correctamente.")
    with tab_chat:
        st.info("El Asistente Virtual para creación de partes por IA está inactivo en esta versión.")

# ==========================================
# 2. COSTES Y RENDIMIENTOS
# ==========================================
elif vista_activa == "Costes y Rendimientos":
    st.title("Análisis de Costes Imputados")
    
    df_diario = cargar_datos("Diario", url_obra)
    df_imputados = cargar_datos("Costes_Imputados", url_obra)
    df_tarifas = cargar_datos("Tarifas_Personal_Maquinaria", URL_MAESTRO)
    
    if df_diario.empty and df_imputados.empty:
        st.info("Sin registros de costes en este proyecto.")
    else:
        df_obra = df_diario.copy()
        resumen_personal = pd.DataFrame(columns=['Tarea', 'Gasto_Personal'])
        if not df_obra.empty and not df_tarifas.empty:
            df_obra['Horas_Personal'] = pd.to_numeric(df_obra['Horas_Personal'], errors='coerce').fillna(0)
            df_obra['Gasto_Personal_Total'] = df_obra.apply(lambda row: calcular_coste_personal(row['Personal'], row['Horas_Personal'], df_tarifas), axis=1)
            resumen_personal = df_obra.groupby('Tarea').agg(Gasto_Personal=('Gasto_Personal_Total', 'sum')).reset_index()

        df_solo_materiales = df_imputados[~df_imputados['Concepto'].str.contains('Mano de obra', case=False, na=False)] if not df_imputados.empty else pd.DataFrame()
        resumen_materiales = df_solo_materiales.groupby('Tarea').agg(Gasto_Materiales=('Coste_Total', 'sum')).reset_index() if not df_solo_materiales.empty else pd.DataFrame()

        if not resumen_personal.empty or not resumen_materiales.empty:
            resumen_final = pd.merge(resumen_personal, resumen_materiales, on='Tarea', how='outer').fillna(0)
            resumen_final['Coste_Total_Partida'] = resumen_final['Gasto_Personal'] + resumen_final['Gasto_Materiales']
            st.dataframe(resumen_final.style.format({"Gasto_Personal": "{:.2f} €", "Gasto_Materiales": "{:.2f} €", "Coste_Total_Partida": "{:.2f} €"}), use_container_width=True)

# ==========================================
# 3. INFORME EJECUTIVO (FINANZAS)
# ==========================================
elif vista_activa == "Informe Ejecutivo (Finanzas)":
    st.title("Informe Ejecutivo y Curva de Evolución")
    
    df_codigos = cargar_datos("Codigos_Control", url_obra)
    df_pto = cargar_datos("Presupuesto_Base", url_obra)
    df_cert = cargar_datos("Certificaciones_Ingresos", url_obra)
    
    if df_codigos.empty or df_pto.empty:
        st.warning("Estructura de presupuesto o códigos incompleta.")
    else:
        df_pto_obra = df_pto.copy()
        df_cert_obra = df_cert.copy() if not df_cert.empty else pd.DataFrame()
        
        df_codigos['Cod_Control'] = df_codigos['Cod_Control'].astype(str).replace(r'\.0$', '', regex=True).str.strip()
        df_pto_obra['Cod_Control'] = df_pto_obra['Cod_Control'].astype(str).replace(r'\.0$', '', regex=True).str.strip()
        
        df_pto_obra['Coste'] = pd.to_numeric(df_pto_obra['Coste'], errors='coerce').fillna(0)
        df_pto_obra['Cantidad_Proyecto'] = pd.to_numeric(df_pto_obra['Cantidad_Proyecto'], errors='coerce').fillna(0)
        df_pto_obra['Importe_Total_Adjudicado'] = pd.to_numeric(df_pto_obra['Importe_Total_Adjudicado'], errors='coerce').fillna(0)
        df_pto_obra['Coste_Total_Fila'] = df_pto_obra['Coste'] * df_pto_obra['Cantidad_Proyecto']
        
        resumen_pto = df_pto_obra.groupby('Cod_Control').agg(
            Coste_Presupuestado=('Coste_Total_Fila', 'sum'),
            Presupuesto_Adjudicado=('Importe_Total_Adjudicado', 'sum')
        ).reset_index()

        meses_certificados = [col for col in df_cert_obra.columns if col.startswith("Importe_Mes_")]
        
        resumen_cert = pd.DataFrame(columns=['Cod_Control', 'Total_Certificado'])
        if not df_cert_obra.empty and meses_certificados:
            df_cert_obra['Cod_Control'] = df_cert_obra['Cod_Control'].astype(str).replace(r'\.0$', '', regex=True).str.strip()
            df_cert_obra['Total_Certificado_Calculado'] = df_cert_obra[meses_certificados].apply(pd.to_numeric, errors='coerce').sum(axis=1)
            resumen_cert = df_cert_obra.groupby('Cod_Control').agg(Total_Certificado=('Total_Certificado_Calculado', 'sum')).reset_index()

        informe_final = df_codigos.merge(resumen_pto, on='Cod_Control', how='left').merge(resumen_cert, on='Cod_Control', how='left').fillna(0)
        informe_final['% Certificado'] = (informe_final['Total_Certificado'] / informe_final['Presupuesto_Adjudicado']) * 100
        informe_final['% Certificado'] = informe_final['% Certificado'].replace([float('inf'), -float('inf')], 0)
        
        st.markdown("### Estado General EDT")
        st.dataframe(
            informe_final.style.format({
                "Coste_Presupuestado": "{:,.2f} €",
                "Presupuesto_Adjudicado": "{:,.2f} €",
                "Total_Certificado": "{:,.2f} €",
                "% Certificado": "{:.2f} %"
            }).bar(subset=['% Certificado'], color='#5fba7d', vmax=100),
            use_container_width=True, hide_index=True
        )
        
        st.markdown("---")
        total_coste_pto = informe_final['Coste_Presupuestado'].sum()
        total_adj = informe_final['Presupuesto_Adjudicado'].sum()
        total_cert = informe_final['Total_Certificado'].sum()
        avance_global = (total_cert / total_adj * 100) if total_adj > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Licitación (Coste Base)", f"{total_coste_pto:,.2f} €")
        c2.metric("Adjudicación Total", f"{total_adj:,.2f} €")
        c3.metric("Certificado a Origen", f"{total_cert:,.2f} €", f"{avance_global:.2f}% Avance")

        st.markdown("---")
        st.markdown("### Evolución de Certificaciones")
        if not df_cert_obra.empty and meses_certificados:
            datos_grafica = {}
            acumulado = 0
            for mes_col in sorted(meses_certificados, key=lambda x: int(x.split('_')[2])):
                nombre_mes = mes_col.replace("Importe_", "").replace("_", " ")
                total_mes = pd.to_numeric(df_cert_obra[mes_col], errors='coerce').sum()
                acumulado += total_mes
                datos_grafica[nombre_mes] = acumulado
                
            df_evolucion = pd.DataFrame(list(datos_grafica.items()), columns=['Mes', 'Certificado Acumulado']).set_index('Mes')
            st.line_chart(df_evolucion, y='Certificado Acumulado')
        else:
            st.info("No hay datos de certificaciones para generar la gráfica.")

# ==========================================
# 4. IMPORTAR PRESUPUESTO
# ==========================================
elif vista_activa == "Importar Presupuesto":
    st.title("Importación de Presupuesto Base")
    archivo_excel = st.file_uploader("Subir Archivo de Presupuesto (.xlsx)", type=['xlsx', 'xls'])
    if archivo_excel:
        xls = pd.ExcelFile(archivo_excel)
        hojas_excel = xls.sheet_names
        
        with st.form("form_config_importacion"):
            nombres_hojas_limpios = [h.lower().strip() for h in hojas_excel]
            hojas_sugeridas = [h for h, h_limpio in zip(hojas_excel, nombres_hojas_limpios) if h_limpio in ["viviendas", "elementos comunes", "trasteros"]]
            hojas_pto = st.multiselect("Pestañas con Presupuesto", hojas_excel, default=hojas_sugeridas)
            
            c3, c4 = st.columns(2)
            gg_bi = c3.number_input("% GG y BI", value=15.00, step=1.0)
            baja = c4.number_input("% Baja", value=1.20, step=0.1)
            
            letras_excel = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]
            col1, col2, col3 = st.columns(3)
            map_codigo = col1.selectbox("Col. Código", letras_excel, index=0) 
            map_unidad = col2.selectbox("Col. Unidad", letras_excel, index=2) 
            map_texto = col3.selectbox("Col. Texto", letras_excel, index=3) 
            col4, col5, col6 = st.columns(3)
            map_cant = col4.selectbox("Col. Cantidad", letras_excel, index=4) 
            map_precio = col5.selectbox("Col. Precio Base", letras_excel, index=7) 
            map_coste = col6.selectbox("Col. Coste Interno", ["No disponible"] + letras_excel, index=12) 
            
            map_cod_control = st.selectbox("Col. 'Cod_Control' (El numérico)", ["No disponible"] + letras_excel, index=0)
            
            if st.form_submit_button("Procesar Datos"):
                try:
                    def letra_idx(letra): return ord(letra) - 65
                    filas_procesadas = []
                    for hoja in hojas_pto:
                        df_h = pd.read_excel(xls, sheet_name=hoja, header=None)
                        capitulo_actual = "Sin Capítulo"
                        
                        idx_c = letra_idx(map_codigo)
                        idx_u = letra_idx(map_unidad)
                        idx_t = letra_idx(map_texto)
                        idx_can = letra_idx(map_cant)
                        idx_p = letra_idx(map_precio)
                        idx_cost = letra_idx(map_coste) if map_coste != "No disponible" else -1
                        idx_cc = letra_idx(map_cod_control) if map_cod_control != "No disponible" else -1
                        
                        for index, row in df_h.iterrows():
                            if len(row) <= max(idx_c, idx_u, idx_t, idx_can, idx_p): continue
                            
                            codigo_val = str(row[idx_c]).strip() if pd.notna(row[idx_c]) else ""
                            if codigo_val.endswith('.0'): codigo_val = codigo_val[:-2]

                            texto_val = str(row[idx_t]).strip() if pd.notna(row[idx_t]) else ""
                            precio_raw = str(row[idx_p]).replace(".", "").replace(",", ".") if isinstance(row[idx_p], str) else row[idx_p]
                            precio_val = pd.to_numeric(precio_raw, errors='coerce')
                            
                            if codigo_val.lower() == "nan": codigo_val = ""
                            if texto_val.lower() == "nan": texto_val = ""
                            if "código" in codigo_val.lower() or "codigo" in codigo_val.lower(): continue
                            
                            cod_control_asignado = ""
                            if idx_cc != -1 and len(row) > idx_cc:
                                cc_raw = str(row[idx_cc]).strip() if pd.notna(row[idx_cc]) else ""
                                if cc_raw.endswith('.0'): cc_raw = cc_raw[:-2]
                                if cc_raw.lower() != "nan": cod_control_asignado = cc_raw
                            
                            if codigo_val and texto_val and pd.isna(precio_val):
                                capitulo_actual = texto_val
                            elif codigo_val and pd.notna(precio_val):
                                cantidad = pd.to_numeric(row[idx_can], errors='coerce')
                                if pd.isna(cantidad): cantidad = 0.0
                                
                                coste = 0.0
                                if idx_cost != -1 and len(row) > idx_cost:
                                    coste_val = pd.to_numeric(row[idx_cost], errors='coerce')
                                    if pd.notna(coste_val): coste = coste_val
                                
                                pr_pres = float(precio_val)
                                precio_licitacion = pr_pres * (1 + (gg_bi / 100.0))
                                precio_adjudicado = precio_licitacion * (1 - (baja / 100.0))
                                importe_total = cantidad * precio_adjudicado
                                
                                filas_procesadas.append({
                                    "Cod_Control": cod_control_asignado, "Capítulo": capitulo_actual,
                                    "Partida_Codigo": codigo_val, "Partida_Nombre": texto_val, 
                                    "Partida_Descripcion": texto_val, "Unidad": str(row[idx_u]) if pd.notna(row[idx_u]) and str(row[idx_u]) != "nan" else "",
                                    "Cantidad_Proyecto": cantidad, "PrPres": pr_pres,
                                    "Precio_Licitacion": precio_licitacion, "Precio_Adjudicado": precio_adjudicado,
                                    "Coste": coste, "Importe_Total_Adjudicado": importe_total
                                })
                            elif not codigo_val and pd.isna(precio_val) and texto_val:
                                if filas_procesadas: filas_procesadas[-1]["Partida_Descripcion"] += "\n" + texto_val
                                
                    st.session_state.df_importacion = pd.DataFrame(filas_procesadas)
                    st.success("Datos procesados correctamente.")
                except Exception as e:
                    st.error(f"Error procesando: {e}")

        if 'df_importacion' in st.session_state and not st.session_state.df_importacion.empty:
            st.dataframe(st.session_state.df_importacion.head(50), use_container_width=True)
            if st.button("Confirmar y Subir a BD", type="primary"):
                guardar_datos("Presupuesto_Base", st.session_state.df_importacion, url_obra)
                st.success("Presupuesto guardado con éxito.")
                del st.session_state['df_importacion']

# ==========================================
# 4.1 IMPORTAR CERTIFICACIÓN (ESTRICTA PERO FLEXIBLE)
# ==========================================
elif vista_activa == "Importar Certificación":
    st.title("Importación de Certificación de Producción")
    st.markdown("Macheo contra Presupuesto Base. (Filtro inteligente de limpieza y separadores activado).")
    
    archivo_cert = st.file_uploader("Subir Archivo de Certificación (.xlsx o .csv)", type=['xlsx', 'xls', 'csv'])
    if archivo_cert:
        if archivo_cert.name.endswith('.csv'):
            xls_cert = None
            hojas_cert = ["Hoja CSV"]
        else:
            xls_cert = pd.ExcelFile(archivo_cert)
            hojas_cert = xls_cert.sheet_names

        with st.form("form_certificacion"):
            c1, c2 = st.columns(2)
            mes_cert = c1.number_input("Mes de Certificación (Ej: 1, 2...)", min_value=1, step=1)
            hoja_cert = c2.selectbox("Pestaña del documento", hojas_cert, index=0)
            
            letras_excel = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]
            
            col1, col2, col3, col4 = st.columns(4)
            map_cod = col1.selectbox("Col. 'Código'", letras_excel, index=0) # Por defecto A
            map_nat = col2.selectbox("Col. 'Naturaleza'", ["Omitir"] + letras_excel, index=1) # Por defecto B
            map_nom = col3.selectbox("Col. 'Nombre'", letras_excel, index=3) # Por defecto D
            map_can = col4.selectbox("Col. 'Cantidad'", letras_excel, index=4) # Por defecto E
            
            if st.form_submit_button("Validar Certificación"):
                df_pto = cargar_datos("Presupuesto_Base", url_obra)
                df_cert_db = cargar_datos("Certificaciones_Ingresos", url_obra)

                if df_pto.empty:
                    st.error("Presupuesto Base no encontrado. Importación abortada.")
                else:
                    def letra_idx(letra): return ord(letra) - 65
                    
                    # --- LECTOR INTELIGENTE DE ARCHIVOS ---
                    try:
                        if xls_cert is None:
                            # Detecta automáticamente si usa comas o puntos y comas
                            df_excel = pd.read_csv(archivo_cert, header=None, sep=None, engine='python', encoding='utf-8')
                        else:
                            df_excel = pd.read_excel(xls_cert, sheet_name=hoja_cert, header=None)
                    except Exception:
                        # Si el utf-8 falla por ser un Excel antiguo de Windows
                        archivo_cert.seek(0)
                        df_excel = pd.read_csv(archivo_cert, header=None, sep=None, engine='python', encoding='latin1')

                    if df_cert_db.empty or 'Partida_Codigo' not in df_cert_db.columns:
                        df_base = df_pto[['Cod_Control', 'Capítulo', 'Partida_Codigo', 'Partida_Nombre', 'Unidad', 'Precio_Adjudicado']].copy()
                    else:
                        df_base = df_cert_db.copy()
                        if 'Precio_Adjudicado' not in df_base.columns:
                            dict_precios = dict(zip(df_pto['Partida_Codigo'], df_pto['Precio_Adjudicado']))
                            df_base['Precio_Adjudicado'] = df_base['Partida_Codigo'].map(dict_precios).fillna(0.0)

                    col_cant_mes = f"Cantidad_Mes_{mes_cert}"
                    col_imp_mes = f"Importe_Mes_{mes_cert}"
                    df_base[col_cant_mes] = 0.0
                    df_base[col_imp_mes] = 0.0

                    pto_codigos = df_base['Partida_Codigo'].astype(str).replace(r'\.0$', '', regex=True).str.strip().tolist()
                    
                    # --- FUNCIÓN LIMPIEZA EXTREMA ---
                    def limpiar_texto(texto):
                        if pd.isna(texto): return ""
                        t = str(texto).lower().replace("\n", " ").replace("\r", " ")
                        t = unicodedata.normalize('NFKD', t).encode('ASCII', 'ignore').decode('utf-8')
                        t = re.sub(r'[.,;:_\-]', ' ', t)
                        return " ".join(t.split())
                        
                    pto_nombres = df_base['Partida_Nombre'].apply(limpiar_texto).tolist()

                    huerfanas = []
                    encontradas = 0

                    for index, row in df_excel.iterrows():
                        if len(row) <= max(letra_idx(map_cod), letra_idx(map_nom), letra_idx(map_can)): continue

                        # Filtro Naturaleza (Capítulos)
                        if map_nat != "Omitir":
                            idx_nat = letra_idx(map_nat)
                            if len(row) > idx_nat and pd.notna(row[idx_nat]):
                                nat_val = str(row[idx_nat]).strip().lower()
                                if "capítulo" in nat_val or "capitulo" in nat_val:
                                    continue 

                        cod_val = str(row[letra_idx(map_cod)]).strip() if pd.notna(row[letra_idx(map_cod)]) else ""
                        if cod_val.endswith('.0'): cod_val = cod_val[:-2]
                        
                        nom_val = str(row[letra_idx(map_nom)]).strip() if pd.notna(row[letra_idx(map_nom)]) else ""
                        
                        can_raw = str(row[letra_idx(map_can)]).replace(".", "").replace(",", ".") if isinstance(row[letra_idx(map_can)], str) else row[letra_idx(map_can)]
                        can_val = pd.to_numeric(can_raw, errors='coerce')

                        # --- FILTROS DE IGNORAR (CERO, CABECERAS, PPTOAGRUPADO Y FANTASMAS) ---
                        if pd.isna(can_val) or can_val == 0: continue
                        if "código" in cod_val.lower() or "codigo" in cod_val.lower() or "cancert" in cod_val.lower(): continue
                        
                        # ¡El bloqueador definitivo de PPTOAGRUPADO!
                        if "pptoagrupado" in cod_val.lower() or "pptoagrupado" in nom_val.lower(): continue
                        
                        if cod_val == "" and (nom_val == "" or nom_val.replace(".", "").replace(",", "").isnumeric()): continue

                        # --- NORMALIZACIÓN DEL EXCEL ---
                        nom_val_norm = limpiar_texto(nom_val)

                        match_idx = -1
                        # 1. Búsqueda exacta por Código
                        if cod_val and cod_val in pto_codigos:
                            match_idx = pto_codigos.index(cod_val)
                            
                        # 2. Búsqueda exacta por Nombre
                        elif nom_val_norm and nom_val_norm in pto_nombres:
                            match_idx = pto_nombres.index(nom_val_norm)
                            
                        # 3. Novedad: Búsqueda PARCIAL (Si uno contiene al otro)
                        elif nom_val_norm:
                            for i, p_nom in enumerate(pto_nombres):
                                if p_nom and (nom_val_norm in p_nom or p_nom in nom_val_norm):
                                    match_idx = i
                                    break

                        if match_idx != -1:
                            precio = pd.to_numeric(df_base.at[match_idx, 'Precio_Adjudicado'], errors='coerce')
                            cant_mes_actual = can_val
                            # A Origen: restamos los meses anteriores
                            for m in range(1, mes_cert):
                                col_ant = f"Cantidad_Mes_{m}"
                                if col_ant in df_base.columns:
                                    cant_mes_actual -= pd.to_numeric(df_base.at[match_idx, col_ant], errors='coerce')
                                    
                            df_base.at[match_idx, col_cant_mes] = cant_mes_actual
                            df_base.at[match_idx, col_imp_mes] = cant_mes_actual * precio
                            encontradas += 1
                        else:
                            huerfanas.append({"Código": cod_val, "Nombre Original": nom_val, "Cantidad": can_val})

                    if huerfanas:
                        st.error(f"Validación Fallida: {len(huerfanas)} partidas no registradas en el Presupuesto Base.")
                        st.markdown("Revisa la lista. Si son correctas, debes añadirlas a tu Presupuesto Base antes de certificar.")
                        st.dataframe(pd.DataFrame(huerfanas), use_container_width=True)
                        if 'df_cert_importacion' in st.session_state: del st.session_state['df_cert_importacion']
                    else:
                        st.success(f"Validación Exitosa. {encontradas} partidas mapeadas correctamente.")
                        st.session_state.df_cert_importacion = df_base

        if 'df_cert_importacion' in st.session_state and not st.session_state.df_cert_importacion.empty:
            if st.button("Confirmar y Guardar Certificación", type="primary"):
                guardar_datos("Certificaciones_Ingresos", st.session_state.df_cert_importacion, url_obra)
                st.success("Certificación registrada y volcada al Informe Ejecutivo.")
                del st.session_state['df_cert_importacion']


# ==========================================
# 5. SUBCONTRATAS
# ==========================================
elif vista_activa == "Subcontratas":
    st.title("Gestión de Subcontratas")
    with st.form("form_subcontratas"):
        c1, c2 = st.columns(2)
        gremio = c1.text_input("Gremio")
        empresa = c2.text_input("Empresa")
        c3, c4, c5 = st.columns(3)
        f_inicio = c3.date_input("Fecha Inicio")
        f_fin = c4.date_input("Fecha Fin")
        estado = c5.selectbox("Estado", ["En curso", "Finalizado", "Paralizado"])
        notas = st.text_area("Notas / Avance")
        if st.form_submit_button("Registrar"):
            df_sub = cargar_datos("Subcontratas", url_obra)
            nueva_sub = pd.DataFrame([{
                "Proyecto": obra_actual, "Gremio": gremio, "Empresa": empresa,
                "Fecha_Inicio": f_inicio.strftime("%Y-%m-%d"), "Fecha_Fin_Prevista": f_fin.strftime("%Y-%m-%d"),
                "Fecha_Fin_Real": "", "Estado": estado, "Avance_Notas": notas
            }])
            df_sub = pd.concat([df_sub, nueva_sub], ignore_index=True)
            guardar_datos("Subcontratas", df_sub, url_obra)
            st.success("Registrado.")

# ==========================================
# 6. BASES GLOBALES
# ==========================================
elif vista_activa == "Base de Precios":
    st.title("Base de Datos Global: Histórico de Precios")
    st.markdown("Los registros introducidos aquí estarán disponibles para **todos los proyectos**.")
    
    with st.form("form_precios_global"):
        c1, c2, c3 = st.columns(3)
        codigo = c1.text_input("Código (SKU)")
        desc = c2.text_input("Descripción")
        prov = c3.text_input("Proveedor")
        c4, c5 = st.columns(2)
        precio = c4.number_input("Precio (€)", min_value=0.0, format="%.2f")
        dto = c5.number_input("Dto (%)", min_value=0.0, format="%.2f")
        if st.form_submit_button("Guardar en Global"):
            df_hist = cargar_datos("Historico_Precios", URL_MAESTRO)
            nuevo_precio = pd.DataFrame([{
                "Codigo_Material": codigo, "Material": desc, "Precio_Unitario": precio,
                "Descuento": dto, "Proveedor": prov, "Fecha_Actualizacion": datetime.today().strftime("%Y-%m-%d")
            }])
            df_hist = pd.concat([df_hist, nuevo_precio], ignore_index=True)
            guardar_datos("Historico_Precios", df_hist, URL_MAESTRO)
            st.success("Registrado.")
    df_ver = cargar_datos("Historico_Precios", URL_MAESTRO)
    if not df_ver.empty: st.dataframe(df_ver, use_container_width=True)

elif vista_activa == "Tarifas (Personal/Maquinaria)":
    st.title("Base de Datos Global: Costes Internos")
    st.markdown("Estas tarifas se aplicarán al cálculo de costes de **todas las obras**.")
    
    with st.form("form_tarifas_global"):
        c1, c2, c3 = st.columns(3)
        recurso = c1.text_input("Identificador")
        tipo = c2.selectbox("Clasificación", ["Personal", "Maquinaria"])
        coste = c3.number_input("Coste (€/h)", min_value=0.0, format="%.2f")
        if st.form_submit_button("Guardar Tarifa"):
            df_tar = cargar_datos("Tarifas_Personal_Maquinaria", URL_MAESTRO) 
            nueva_tarifa = pd.DataFrame([{"Recurso": recurso, "Tipo": tipo, "Coste_Hora": coste}])
            df_tar = pd.concat([df_tar, nueva_tarifa], ignore_index=True)
            guardar_datos("Tarifas_Personal_Maquinaria", df_tar, URL_MAESTRO)
            st.success("Registrado.")
    df_ver_t = cargar_datos("Tarifas_Personal_Maquinaria", URL_MAESTRO)
    if not df_ver_t.empty: st.dataframe(df_ver_t, use_container_width=True)