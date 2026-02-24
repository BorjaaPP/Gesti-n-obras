import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import google.generativeai as genai
import json
import tempfile
import os
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="ERP Construcción - Borja", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# 🔴 PEGA AQUÍ LA URL COMPLETA DE TU GOOGLE SHEETS "MAESTRO" 🔴
URL_MAESTRO = "https://docs.google.com/spreadsheets/d/1Ua_8c_VgY_mKN_xN_TX_yXkwhoolkl8KOx3YRndcVdo/edit?gid=0#gid=0"

# --- CONECTAR LA IA ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.sidebar.warning("⚠️ No se ha encontrado la clave de Gemini en los Secrets.")

# --- FUNCIONES DE BASE DE DATOS MULTIOBRA ---
def cargar_datos(hoja, url):
    try:
        return conn.read(spreadsheet=url, worksheet=hoja, ttl=0)
    except Exception as e:
        return pd.DataFrame()

def guardar_datos(hoja, df, url):
    conn.update(spreadsheet=url, worksheet=hoja, data=df)

# --- CORRECCIÓN MATEMÁTICA: SUMAR TARIFAS ---
def calcular_coste_personal(texto_personal, horas, df_tarifas):
    if not texto_personal or horas <= 0 or df_tarifas.empty: return 0.0
    texto_personal = str(texto_personal).lower()
    costes = []
    for _, tarifa in df_tarifas.iterrows():
        nombre_tarifa = str(tarifa['Recurso']).lower()
        if nombre_tarifa and nombre_tarifa != "nan" and nombre_tarifa in texto_personal:
            costes.append(pd.to_numeric(tarifa['Coste_Hora'], errors='coerce'))
    return sum(costes) * float(horas) if costes else 0.0

# --- INICIALIZAR MEMORIA TEMPORAL ---
if 'ia_datos' not in st.session_state:
    st.session_state.ia_datos = {
        "Fecha": datetime.today().strftime("%Y-%m-%d"), "Tarea": "", 
        "Descripción_Tarea": "", "Personal": "", "Maquinaria": ""
    }
if 'mensajes_chat' not in st.session_state:
    st.session_state.mensajes_chat = []

# ==========================================
# 0. LECTURA DEL MAESTRO Y SELECTOR GLOBAL
# ==========================================
if URL_MAESTRO == "PEGAR_AQUI_LA_URL_DEL_MAESTRO":
    st.error("🚨 DETENTE: Debes pegar la URL de tu archivo Maestro en la línea 17 del código.")
    st.stop()

st.sidebar.title("🏗️ ERP Construcción")
st.sidebar.markdown("---")

df_maestro = cargar_datos(0, URL_MAESTRO)

if df_maestro.empty:
    st.sidebar.error("No se pudo conectar con el Archivo Maestro. Revisa los permisos.")
    st.stop()

obras_activas = df_maestro[df_maestro['Estado'] == 'Activa']
if obras_activas.empty:
    st.sidebar.warning("No hay obras activas en el Maestro.")
    st.stop()

st.sidebar.subheader("📍 Selecciona Proyecto")
obra_actual = st.sidebar.selectbox("Proyecto Activo:", obras_activas['Nombre_Proyecto'].tolist())

# Extraemos la URL de la obra seleccionada
url_obra = obras_activas[obras_activas['Nombre_Proyecto'] == obra_actual]['Enlace_Google_Sheet'].values[0]

st.sidebar.markdown("---")
menu = st.sidebar.radio("Ir a Módulo:", [
    "🚧 Gestión de Obras (Diario)",
    "📊 Costes y Rendimientos",
    "📈 Informe Ejecutivo (Finanzas)",
    "📥 Importar Presupuesto (Presto)",
    "👷 Subcontratas", 
    "🧾 Facturas y Precios", 
    "💰 Tarifas (Personal/Maq)"
])

# ==========================================
# 1. GESTIÓN DE OBRAS Y DIARIO
# ==========================================
if menu == "🚧 Gestión de Obras (Diario)":
    st.title(f"Gestión de Obra: {obra_actual}")
    st.subheader("📢 Parte de Trabajo y Asistente IA")
    
    tab_parte, tab_chat = st.tabs(["📝 Subir Parte (Audio/Manual)", "💬 Chat del Aparejador"])
    
    with tab_parte:
        archivo_audio = st.file_uploader("🎤 Sube tu audio de WhatsApp aquí", type=['mp3', 'wav', 'ogg', 'm4a', 'opus'])
        
        if archivo_audio and st.button("✨ Procesar Audio con IA"):
            with st.spinner("🧠 Analizando audio y estructurando tareas..."):
                try:
                    df_diario_temp = cargar_datos("Diario", url_obra)
                    tareas_existentes = []
                    if not df_diario_temp.empty and 'Tarea' in df_diario_temp.columns:
                        tareas_existentes = df_diario_temp['Tarea'].dropna().unique().tolist()

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                        tmp.write(archivo_audio.getvalue())
                        tmp_path = tmp.name
                    
                    audio_file = genai.upload_file(path=tmp_path)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = f"""
                    Escucha este audio de un jefe de obra. Extrae la información en formato JSON estricto:
                    {{"Fecha": "YYYY-MM-DD", "Tarea": "tarea general", "Descripción_Tarea": "detalle específico", "Personal": "nombres", "Maquinaria": "maquinaria"}}
                    REGLA VITAL: Tareas generales existentes en esta obra: {tareas_existentes}. 
                    - 'Tarea' debe ser un agrupador general.
                    - 'Descripción_Tarea' es el detalle exacto de lo que han hecho hoy.
                    """
                    respuesta = model.generate_content([prompt, audio_file])
                    texto_json = respuesta.text.replace('```json', '').replace('```', '').strip()
                    st.session_state.ia_datos.update(json.loads(texto_json))
                    st.success("✅ ¡Audio procesado!")
                    os.remove(tmp_path)
                    genai.delete_file(audio_file.name)
                except Exception as e:
                    st.error(f"Error: {e}")

        st.write("**Revisa y completa los datos antes de guardar:**")
        with st.form("form_diario_ia"):
            c1, c2 = st.columns(2)
            fecha_input = c1.text_input("Fecha", value=st.session_state.ia_datos.get("Fecha", datetime.today().strftime("%Y-%m-%d")))
            st.info(f"Guardando en Base de Datos de: **{obra_actual}**")
            
            c_t1, c_t2 = st.columns(2)
            tarea = c_t1.text_input("Tarea General (Agrupador)", value=st.session_state.ia_datos.get("Tarea", ""))
            desc_tarea = c_t2.text_input("Descripción Específica", value=st.session_state.ia_datos.get("Descripción_Tarea", ""))
            
            c3, c4 = st.columns(2)
            personal = c3.text_input("Personal", value=st.session_state.ia_datos.get("Personal", ""))
            h_pers = c4.number_input("Horas Totales Personal", min_value=0.0, step=0.5)
            
            c5, c6 = st.columns(2)
            maq = c5.text_input("Maquinaria", value=st.session_state.ia_datos.get("Maquinaria", ""))
            h_maq = c6.number_input("Horas Maquinaria", min_value=0.0, step=0.5)
            
            c7, c8 = st.columns(2)
            prod = c7.number_input("Producción (Cantidad)", min_value=0.0, step=1.0)
            ud = c8.text_input("Unidad (ej: m2, ml, ud)")
            
            if st.form_submit_button("💾 Guardar en Base de Datos"):
                df_diario = cargar_datos("Diario", url_obra)
                nuevo_parte = pd.DataFrame([{
                    "Fecha": fecha_input, "Proyecto": obra_actual, 
                    "Tipo_Entrada": "Audio" if archivo_audio else "Manual",
                    "Contenido": archivo_audio.name if archivo_audio else "Texto manual", 
                    "Tarea": tarea, "Descripción_Tarea": desc_tarea,
                    "Personal": personal, "Horas_Personal": h_pers, 
                    "Maquinaria": maq, "Horas_Maq": h_maq, "Produccion": prod, "Unidad": ud
                }])
                df_diario = pd.concat([df_diario, nuevo_parte], ignore_index=True)
                guardar_datos("Diario", df_diario, url_obra)
                
                df_tarifas = cargar_datos("Tarifas_Personal_Maquinaria", url_obra)
                coste_p = calcular_coste_personal(personal, h_pers, df_tarifas)
                if coste_p > 0:
                    df_costes = cargar_datos("Costes_Imputados", url_obra)
                    nuevo_coste = pd.DataFrame([{
                        "Fecha": fecha_input, "Proyecto": obra_actual, "Tarea": tarea,
                        "Concepto": f"Mano de obra ({desc_tarea}): {personal}", "Coste_Total": coste_p
                    }])
                    df_costes = pd.concat([df_costes, nuevo_coste], ignore_index=True)
                    guardar_datos("Costes_Imputados", df_costes, url_obra)

                st.session_state.ia_datos = {"Fecha": datetime.today().strftime("%Y-%m-%d"), "Tarea": "", "Descripción_Tarea": "", "Personal": "", "Maquinaria": ""}
                st.success("¡Datos guardados!")

    with tab_chat:
        st.write(f"Habla con la IA. Pídele que calcule rendimientos, impute materiales o registre jornadas.")
        for msg in st.session_state.mensajes_chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        if prompt_usuario := st.chat_input("Ej: Fernando trabajó 8h echando hormigón..."):
            st.session_state.mensajes_chat.append({"role": "user", "content": prompt_usuario})
            with st.chat_message("user"):
                st.markdown(prompt_usuario)
            
            df_d = cargar_datos("Diario", url_obra)
            df_p = cargar_datos("Historico_Precios", url_obra)
            df_t = cargar_datos("Tarifas_Personal_Maquinaria", url_obra)
            
            df_d_obra = df_d.to_csv(index=False) if not df_d.empty else "Sin datos"
                
            contexto = f"""
            Eres un Aparejador experto. Obra actual: '{obra_actual}'.
            REGLAS VITALES DE ACTUACIÓN:
            1. **IMPUTAR MATERIALES:** Si el usuario te manda imputar un material, añade este bloque:
            ```json_imputar
            {{"Tarea": "nombre general", "Concepto": "descripción material", "Coste": numero}}
            ```
            2. **REGISTRAR MANO DE OBRA:** Si el usuario indica horas de personal, OBLIGATORIAMENTE debes crear el registro en el Diario. Separa la Tarea General de la Descripción Específica. Añade este bloque a tu respuesta:
            ```json_diario
            [
              {{"Fecha": "YYYY-MM-DD", "Tarea": "nombre general", "Descripción_Tarea": "detalle", "Personal": "nombres", "Horas_Personal": numero}}
            ]
            ```
            DATOS ACTUALES:
            - Diario: {df_d_obra}
            - Precios: {df_p.to_csv(index=False) if not df_p.empty else "Vacío"}
            - Tarifas: {df_t.to_csv(index=False) if not df_t.empty else "Vacío"}
            """
            
            with st.chat_message("assistant"):
                with st.spinner("🧠 Procesando orden..."):
                    try:
                        modelo_chat = genai.GenerativeModel('gemini-2.5-flash')
                        respuesta_ia = modelo_chat.generate_content(contexto + "\n\nUsuario: " + prompt_usuario)
                        texto_respuesta = respuesta_ia.text
                        
                        if "```json_imputar" in texto_respuesta:
                            match_imp = re.search(r'```json_imputar\n(.*?)\n```', texto_respuesta, re.DOTALL)
                            if match_imp:
                                datos_imputar = json.loads(match_imp.group(1))
                                df_costes = cargar_datos("Costes_Imputados", url_obra)
                                nuevo_coste = pd.DataFrame([{
                                    "Fecha": datetime.today().strftime("%Y-%m-%d"),
                                    "Proyecto": obra_actual, "Tarea": datos_imputar.get("Tarea", "General"),
                                    "Concepto": datos_imputar.get("Concepto", "Material"),
                                    "Coste_Total": float(datos_imputar.get("Coste", 0))
                                }])
                                df_costes = pd.concat([df_costes, nuevo_coste], ignore_index=True)
                                guardar_datos("Costes_Imputados", df_costes, url_obra)
                                st.toast("🛒 Coste de material guardado en Base de Datos")
                            texto_respuesta = re.sub(r'```json_imputar\n.*?\n```', '', texto_respuesta, flags=re.DOTALL)

                        if "```json_diario" in texto_respuesta:
                            match_diario = re.search(r'```json_diario\n(.*?)\n```', texto_respuesta, re.DOTALL)
                            if match_diario:
                                datos_diario = json.loads(match_diario.group(1))
                                if isinstance(datos_diario, dict): datos_diario = [datos_diario]
                                
                                df_diario_act = cargar_datos("Diario", url_obra)
                                df_costes_act = cargar_datos("Costes_Imputados", url_obra)
                                df_tarifas_act = cargar_datos("Tarifas_Personal_Maquinaria", url_obra)
                                
                                nuevos_partes = []
                                nuevos_costes = []
                                
                                for d in datos_diario:
                                    nuevos_partes.append({
                                        "Fecha": d.get("Fecha", datetime.today().strftime("%Y-%m-%d")),
                                        "Proyecto": obra_actual, "Tipo_Entrada": "Chat IA",
                                        "Contenido": "Generado desde conversación",
                                        "Tarea": d.get("Tarea", ""), "Descripción_Tarea": d.get("Descripción_Tarea", ""),
                                        "Personal": d.get("Personal", ""), "Horas_Personal": float(d.get("Horas_Personal", 0)),
                                        "Maquinaria": "", "Horas_Maq": 0, "Produccion": 0, "Unidad": ""
                                    })
                                    coste_p = calcular_coste_personal(d.get("Personal", ""), float(d.get("Horas_Personal", 0)), df_tarifas_act)
                                    if coste_p > 0:
                                        nuevos_costes.append({
                                            "Fecha": d.get("Fecha", datetime.today().strftime("%Y-%m-%d")),
                                            "Proyecto": obra_actual, "Tarea": d.get("Tarea", ""),
                                            "Concepto": f"Mano de obra ({d.get('Descripción_Tarea', '')}): {d.get('Personal', '')}",
                                            "Coste_Total": coste_p
                                        })
                                        
                                df_diario_act = pd.concat([df_diario_act, pd.DataFrame(nuevos_partes)], ignore_index=True)
                                guardar_datos("Diario", df_diario_act, url_obra)
                                if nuevos_costes:
                                    df_costes_act = pd.concat([df_costes_act, pd.DataFrame(nuevos_costes)], ignore_index=True)
                                    guardar_datos("Costes_Imputados", df_costes_act, url_obra)
                                st.toast("👷 Partes guardados y volcados a Costes")
                            texto_respuesta = re.sub(r'```json_diario\n.*?\n```', '', texto_respuesta, flags=re.DOTALL)

                        st.markdown(texto_respuesta)
                        st.session_state.mensajes_chat.append({"role": "assistant", "content": texto_respuesta})
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

# ==========================================
# 2. COSTES Y RENDIMIENTOS
# ==========================================
elif menu == "📊 Costes y Rendimientos":
    st.title(f"📊 Análisis de Costes: {obra_actual}")
    
    df_diario = cargar_datos("Diario", url_obra)
    df_imputados = cargar_datos("Costes_Imputados", url_obra)
    df_tarifas = cargar_datos("Tarifas_Personal_Maquinaria", url_obra)
    
    if df_diario.empty and df_imputados.empty:
        st.info("Aún no hay partes ni costes en esta obra.")
    else:
        df_obra = df_diario.copy()
        df_imp_obra = df_imputados.copy()
        
        resumen_personal = pd.DataFrame(columns=['Tarea', 'Gasto_Personal'])
        if not df_obra.empty and not df_tarifas.empty:
            df_obra['Horas_Personal'] = pd.to_numeric(df_obra['Horas_Personal'], errors='coerce').fillna(0)
            df_obra['Gasto_Personal_Total'] = df_obra.apply(lambda row: calcular_coste_personal(row['Personal'], row['Horas_Personal'], df_tarifas), axis=1)
            resumen_personal = df_obra.groupby('Tarea').agg(Gasto_Personal=('Gasto_Personal_Total', 'sum')).reset_index()

        resumen_materiales = pd.DataFrame(