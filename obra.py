import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import google.generativeai as genai
import json
import tempfile
import os

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="ERP Construcción - Borja", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CONECTAR LA IA ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.sidebar.warning("⚠️ No se ha encontrado la clave de Gemini en los Secrets.")

def cargar_datos(hoja):
    try:
        return conn.read(worksheet=hoja, ttl=0)
    except Exception as e:
        st.error(f"Error al cargar la hoja '{hoja}'. ¿Está creada en Google Sheets?")
        return pd.DataFrame()

def guardar_datos(hoja, df):
    conn.update(worksheet=hoja, data=df)

# Inicializar memoria temporal para la IA
if 'ia_datos' not in st.session_state:
    st.session_state.ia_datos = {
        "Fecha": datetime.today().strftime("%Y-%m-%d"), "Proyecto": "", "Tarea": "", 
        "Personal": "", "Maquinaria": ""
    }

# --- MENÚ LATERAL ---
st.sidebar.title("🏗️ Menú Principal")
menu = st.sidebar.radio("Ir a:", [
    "🚧 Gestión de Obras (Diario)", 
    "👷 Subcontratas", 
    "🧾 Facturas y Precios", 
    "💰 Tarifas (Personal/Maq)", 
    "🤖 Asistente IA (Próximamente)"
])

# ==========================================
# 1. GESTIÓN DE OBRAS Y DIARIO (CON IA)
# ==========================================
if menu == "🚧 Gestión de Obras (Diario)":
    st.title("Gestión de Obras y Parte Diario")
    
    df_proyectos = cargar_datos("Proyectos")
    if df_proyectos.empty:
        lista_obras = []
    else:
        lista_obras = df_proyectos[df_proyectos['Estado'] == 'Activa']['Nombre'].tolist()
        
    lista_obras.append("➕ Crear Nueva Obra")
    obra_actual = st.selectbox("Selecciona la obra:", lista_obras)

    if obra_actual == "➕ Crear Nueva Obra":
        with st.form("form_nueva_obra"):
            nombre = st.text_input("Nombre del Proyecto")
            if st.form_submit_button("Guardar Proyecto"):
                nuevo = pd.DataFrame([{"ID_Proyecto": len(df_proyectos)+1, "Nombre": nombre, "Estado": "Activa", "Fecha_Inicio": datetime.today().strftime("%Y-%m-%d")}])
                df_proyectos = pd.concat([df_proyectos, nuevo], ignore_index=True)
                guardar_datos("Proyectos", df_proyectos)
                st.success("Obra creada. Recarga la página.")
                st.rerun()
    else:
        st.subheader("📢 Parte de Trabajo Diario")
        
        # ZONA DE AUDIO E INTELIGENCIA ARTIFICIAL
        st.info("Sube tu audio de WhatsApp y deja que la IA rellene el parte por ti.")
        archivo_audio = st.file_uploader("🎤 Sube tu audio aquí", type=['mp3', 'wav', 'ogg', 'm4a', 'opus'])
        
        if archivo_audio and st.button("✨ Procesar Audio con IA"):
            with st.spinner("🧠 La IA está escuchando y analizando tu audio..."):
                try:
                    # Guardar audio temporalmente para que la IA lo escuche
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                        tmp.write(archivo_audio.getvalue())
                        tmp_path = tmp.name
                    
                    # Subir y procesar con Gemini
                    audio_file = genai.upload_file(path=tmp_path)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = """
                    Escucha este audio de un jefe de obra. Extrae la información en un formato JSON estricto con estas claves:
                    {"Fecha": "YYYY-MM-DD", "Proyecto": "nombre de la obra", "Tarea": "resumen de lo que hacen", "Personal": "nombres de los trabajadores", "Maquinaria": "maquinaria mencionada"}
                    Si dice un día o fecha, conviértela al formato YYYY-MM-DD del año actual. Si no menciona algo, déjalo en blanco "".
                    """
                    respuesta = model.generate_content([prompt, audio_file])
                    
                    # Limpiar la respuesta para sacar solo el JSON
                    texto_json = respuesta.text.replace('```json', '').replace('```', '').strip()
                    datos_extraidos = json.loads(texto_json)
                    
                    # Guardar en la memoria para rellenar las cajas
                    st.session_state.ia_datos.update(datos_extraidos)
                    st.success("✅ ¡Audio procesado! Revisa los datos abajo.")
                    
                    # Borrar archivo temporal y en la nube de Google
                    os.remove(tmp_path)
                    genai.delete_file(audio_file.name)
                except Exception as e:
                    st.error(f"Hubo un error al procesar el audio: {e}")

        st.divider()
        st.write("**Revisa y completa los datos antes de guardar:**")
        
        # FORMULARIO PRE-RELLENADO POR LA IA
        with st.form("form_diario_ia"):
            c1, c2 = st.columns(2)
            fecha_input = c1.text_input("Fecha", value=st.session_state.ia_datos.get("Fecha", datetime.today().strftime("%Y-%m-%d")))
            proyecto_ia = c2.text_input("Proyecto Detectado", value=st.session_state.ia_datos.get("Proyecto", obra_actual))
            
            tarea = st.text_input("Tarea", value=st.session_state.ia_datos.get("Tarea", ""))
            
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
                df_diario = cargar_datos("Diario")
                nuevo_parte = pd.DataFrame([{
                    "Fecha": fecha_input, 
                    "Proyecto": obra_actual, 
                    "Tipo_Entrada": "Audio" if archivo_audio else "Manual",
                    "Contenido": archivo_audio.name if archivo_audio else "Texto manual", 
                    "Tarea": tarea, 
                    "Personal": personal,
                    "Horas_Personal": h_pers, 
                    "Maquinaria": maq, 
                    "Horas_Maq": h_maq,
                    "Produccion": prod, 
                    "Unidad": ud
                }])
                df_diario = pd.concat([df_diario, nuevo_parte], ignore_index=True)
                guardar_datos("Diario", df_diario)
                
                # Limpiar memoria tras guardar
                st.session_state.ia_datos = {
                    "Fecha": datetime.today().strftime("%Y-%m-%d"), "Proyecto": "", "Tarea": "", 
                    "Personal": "", "Maquinaria": ""
                }
                st.success("¡Datos guardados perfectamente en tu Excel!")

# ==========================================
# 2. SUBCONTRATAS
# ==========================================
elif menu == "👷 Subcontratas":
    st.title("Control de Subcontratas y Gremios")
    
    df_proyectos = cargar_datos("Proyectos")
    obras_activas = df_proyectos[df_proyectos['Estado'] == 'Activa']['Nombre'].tolist() if not df_proyectos.empty else ["Sin obras"]
    
    with st.form("form_subcontratas"):
        obra