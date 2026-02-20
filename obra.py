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

# --- INICIALIZAR MEMORIA TEMPORAL ---
if 'ia_datos' not in st.session_state:
    st.session_state.ia_datos = {
        "Fecha": datetime.today().strftime("%Y-%m-%d"), "Proyecto": "", "Tarea": "", 
        "Personal": "", "Maquinaria": ""
    }
if 'mensajes_chat' not in st.session_state:
    st.session_state.mensajes_chat = []

# --- MENÚ LATERAL ---
st.sidebar.title("🏗️ Menú Principal")
menu = st.sidebar.radio("Ir a:", [
    "🚧 Gestión de Obras (Diario)",
    "📊 Costes y Rendimientos",
    "👷 Subcontratas", 
    "🧾 Facturas y Precios", 
    "💰 Tarifas (Personal/Maq)"
])

# ==========================================
# 1. GESTIÓN DE OBRAS Y DIARIO (CON CHAT)
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
        st.subheader(f"📢 Parte de Trabajo: {obra_actual}")
        
        # --- PESTAÑAS DENTRO DEL DIARIO ---
        tab_parte, tab_chat = st.tabs(["📝 Subir Parte (Audio/Manual)", "💬 Chat del Proyecto"])
        
        # PESTAÑA: SUBIR PARTE
        with tab_parte:
            st.info("Sube tu audio de WhatsApp y deja que la IA rellene el parte por ti.")
            archivo_audio = st.file_uploader("🎤 Sube tu audio aquí", type=['mp3', 'wav', 'ogg', 'm4a', 'opus'])
            
            if archivo_audio and st.button("✨ Procesar Audio con IA"):
                with st.spinner("🧠 La IA está escuchando y analizando tu audio..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                            tmp.write(archivo_audio.getvalue())
                            tmp_path = tmp.name
                        
                        audio_file = genai.upload_file(path=tmp_path)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        prompt = """
                        Escucha este audio de un jefe de obra. Extrae la información en un formato JSON estricto con estas claves:
                        {"Fecha": "YYYY-MM-DD", "Proyecto": "nombre de la obra", "Tarea": "resumen de lo que hacen", "Personal": "nombres de los trabajadores", "Maquinaria": "maquinaria mencionada"}
                        Si dice un día o fecha, conviértela al formato YYYY-MM-DD del año actual. Si no menciona algo, déjalo en blanco "".
                        """
                        respuesta = model.generate_content([prompt, audio_file])
                        
                        texto_json = respuesta.text.replace('```json', '').replace('```', '').strip()
                        datos_extraidos = json.loads(texto_json)
                        
                        st.session_state.ia_datos.update(datos_extraidos)
                        st.success("✅ ¡Audio procesado! Revisa los datos abajo.")
                        
                        os.remove(tmp_path)
                        genai.delete_file(audio_file.name)
                    except Exception as e:
                        st.error(f"Hubo un error al procesar el audio: {e}")

            st.divider()
            st.write("**Revisa y completa los datos antes de guardar:**")
            
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
                    
                    st.session_state.ia_datos = {
                        "Fecha": datetime.today().strftime("%Y-%m-%d"), "Proyecto": "", "Tarea": "", 
                        "Personal": "", "Maquinaria": ""
                    }
                    st.success("¡Datos guardados perfectamente en tu Excel!")

        # PESTAÑA: CHAT DEL PROYECTO
        with tab_chat:
            st.write(f"Habla con la IA sobre los datos y costes de **{obra_actual}**")
            
            for msg in st.session_state.mensajes_chat:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
            
            if prompt_usuario := st.chat_input("Ej: Calcula el coste de Fernando en la rampa..."):
                st.session_state.mensajes_chat.append({"role": "user", "content": prompt_usuario})
                with st.chat_message("user"):
                    st.markdown(prompt_usuario)
                
                # --- AQUÍ ESTÁ LA MAGIA ARREGLADA ---
                df_d = cargar_datos("Diario")
                df_p = cargar_datos("Historico_Precios")
                df_t = cargar_datos("Tarifas_Personal_Maquinaria") # <-- AHORA LEE LA PESTAÑA CORRECTA
                
                if not df_d.empty:
                    df_d_obra = df_d[df_d['Proyecto'] == obra_actual].to_csv(index=False)
                else:
                    df_d_obra = "Sin datos de diario"
                    
                contexto = f"""
                Eres el asistente inteligente de un Jefe de Obra. Tu tarea es ayudarle a calcular costes, materiales y rendimientos.
                Aquí tienes los datos actuales de la obra '{obra_actual}':
                
                1. Partes Diarios (CSV):
                {df_d_obra}
                
                2. Base de Datos de Precios de Materiales (CSV):
                {df_p.to_csv(index=False) if not df_p.empty else "Sin precios de materiales"}
                
                3. Tarifas de Mano de Obra y Maquinaria (CSV):
                {df_t.to_csv(index=False) if not df_t.empty else "Sin tarifas registradas"}
                
                Responde a la consulta del usuario usando estos datos. Ahora ya tienes acceso a los precios de los materiales y a lo que cuesta la hora de los trabajadores. Haz los cálculos matemáticos multiplicando las horas del parte diario por el coste por hora de las tarifas. No inventes precios.
                """
                
                with st.chat_message("assistant"):
                    with st.spinner("🧠 Consultando la base de datos..."):
                        try:
                            modelo_chat = genai.GenerativeModel('gemini-2.5-flash')
                            respuesta_ia = modelo_chat.generate_content(contexto + "\n\nConsulta del usuario: " + prompt_usuario)
                            st.markdown(respuesta_ia.text)
                            st.session_state.mensajes_chat.append({"role": "assistant", "content": respuesta_ia.text})
                        except Exception as e:
                            st.error(f"Error al conectar con la IA: {e}")

# ==========================================
# 2. COSTES Y RENDIMIENTOS (DASHBOARD)
# ==========================================
elif menu == "📊 Costes y Rendimientos":
    st.title("📊 Análisis de Costes y Rendimientos")
    
    df_proyectos = cargar_datos("Proyectos")
    lista_obras = df_proyectos[df_proyectos['Estado'] == 'Activa']['Nombre'].tolist() if not df_proyectos.empty else []
    
    if not lista_obras:
        st.warning("No hay obras activas. Crea una en la Gestión de Obras.")
    else:
        obra_dash = st.selectbox("Selecciona Proyecto a Analizar:", lista_obras)
        st.divider()
        
        df_diario = cargar_datos("Diario")
        
        if df_diario.empty:
            st.info("Aún no hay partes de trabajo para analizar rendimientos.")
        else:
            df_obra = df_diario[df_diario['Proyecto'] == obra_dash].copy()
            
            if df_obra.empty:
                st.info(f"No hay partes registrados en la obra {obra_dash}.")
            else:
                df_obra['Horas_Personal'] = pd.to_numeric(df_obra['Horas_Personal'], errors='coerce').fillna(0)
                df_obra['Produccion'] = pd.to_numeric(df_obra['Produccion'], errors='coerce').fillna(0)
                
                resumen = df_obra.groupby(['Tarea', 'Unidad']).agg(
                    Total_Horas=('Horas_Personal', 'sum'),
                    Total_Unidades=('Produccion', 'sum')
                ).reset_index()
                
                resumen['Rendimiento (Unidades/Hora)'] = (resumen['Total_Unidades'] / resumen['Total_Horas']).round(2)
                resumen['Rendimiento (Unidades/Hora)'] = resumen['Rendimiento (Unidades/Hora)'].fillna(0)
                
                st.subheader(f"Resumen de Trabajos Activos: {obra_dash}")
                st.dataframe(resumen, use_container_width=True)
                
                st.info("💡 En el futuro, conectaremos los costes de materiales y mano de obra directamente a esta tabla para ver el Coste Total por partida.")

# ==========================================
# 3. SUBCONTRATAS
# ==========================================
elif menu == "👷 Subcontratas":
    st.title("Control de Subcontratas y Gremios")
    
    df_proyectos = cargar_datos("Proyectos")
    obras_activas = df_proyectos[df_proyectos['Estado'] == 'Activa']['Nombre'].tolist() if not df_proyectos.empty else ["Sin obras"]
    
    with st.form("form_subcontratas"):
        obra_sub = st.selectbox("Obra", obras_activas)
        c1, c2 = st.columns(2)
        gremio = c1.text_input("Gremio (ej: Fontanería)")
        empresa = c2.text_input("Empresa Subcontratada")
        
        c3, c4, c5 = st.columns(3)
        f_inicio = c3.date_input("Fecha Inicio")
        f_fin = c4.date_input("Fecha Fin Prevista")
        estado = c5.selectbox("Estado", ["En curso", "Finalizado", "Paralizado"])
        
        notas = st.text_area("Notas / Avance")
        
        if st.form_submit_button("Registrar Subcontrata"):
            df_sub = cargar_datos("Subcontratas")
            nueva_sub = pd.DataFrame([{
                "Proyecto": obra_sub, "Gremio": gremio, "Empresa": empresa,
                "Fecha_Inicio": f_inicio.strftime("%Y-%m-%d"), "Fecha_Fin_Prevista": f_fin.strftime("%Y-%m-%d"),
                "Fecha_Fin_Real": "", "Estado": estado, "Avance_Notas": notas
            }])
            df_sub = pd.concat([df_sub, nueva_sub], ignore_index=True)
            guardar_datos("Subcontratas", df_sub)
            st.success("Subcontrata registrada correctamente.")

# ==========================================
# 4. FACTURAS Y PRECIOS
# ==========================================
elif menu == "🧾 Facturas y Precios":
    st.title("Histórico de Precios y Facturas")
    st.info("💡 Registra aquí los precios de tus materiales para que la IA los utilice en sus cálculos de costes.")
    
    df_proyectos = cargar_datos("Proyectos")
    obras_activas = df_proyectos[df_proyectos['Estado'] == 'Activa']['Nombre'].tolist() if not df_proyectos.empty else ["Sin obras"]
    
    with st.form("form_precios"):
        obra_fac = st.selectbox("Obra a la que imputar", obras_activas)
        c1, c2, c3 = st.columns(3)
        codigo = c1.text_input("Código Material (SKU)")
        desc = c2.text_input("Descripción Material")
        prov = c3.text_input("Proveedor")
        
        c4, c5, c6 = st.columns(3)
        precio = c4.number_input("Precio Unitario (€)", min_value=0.0, format="%.2f")
        dto = c5.number_input("Descuento (%)", min_value=0.0, format="%.2f")
        factura = c6.text_input("Nº Factura / Origen")
        
        if st.form_submit_button("Guardar Precio"):
            df_hist = cargar_datos("Historico_Precios")
            nuevo_precio = pd.DataFrame([{
                "Codigo_Material": codigo, "Material": desc, "Precio_Unitario": precio,
                "Descuento": dto, "Proveedor": prov, "Fecha_Registro": datetime.today().strftime("%Y-%m-%d"),
                "Factura_Origen": factura, "Proyecto": obra_fac
            }])
            df_hist = pd.concat([df_hist, nuevo_precio], ignore_index=True)
            guardar_datos("Historico_Precios", df_hist)
            st.success(f"Precio del artículo '{desc}' guardado en la base de datos.")

# ==========================================
# 5. TARIFAS
# ==========================================
elif menu == "💰 Tarifas (Personal/Maq)":
    st.title("Costes Internos (Personal y Maquinaria)")
    with st.form("form_tarifas"):
        c1, c2, c3 = st.columns(3)
        recurso = c1.text_input("Nombre (ej: Fernando, Retroexcavadora)")
        tipo = c2.selectbox("Tipo", ["Personal", "Maquinaria"])
        coste = c3.number_input("Coste por Hora (€)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Guardar Tarifa"):
            df_tar = cargar_datos("Tarifas_Personal_Maquinaria") # <-- PESTAÑA ACTUALIZADA
            nueva_tarifa = pd.DataFrame([{"Recurso": recurso, "Tipo": tipo, "Coste_Hora": coste}])
            df_tar = pd.concat([df_tar, nueva_tarifa], ignore_index=True)
            guardar_datos("Tarifas_Personal_Maquinaria", df_tar) # <-- PESTAÑA ACTUALIZADA
            st.success("Tarifa registrada con éxito.")