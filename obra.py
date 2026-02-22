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

# --- CONECTAR LA IA ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.sidebar.warning("⚠️ No se ha encontrado la clave de Gemini en los Secrets.")

def cargar_datos(hoja):
    try:
        return conn.read(worksheet=hoja, ttl=0)
    except Exception as e:
        return pd.DataFrame()

def guardar_datos(hoja, df):
    conn.update(worksheet=hoja, data=df)

# --- CORRECCIÓN MATEMÁTICA: SUMAR TARIFAS ---
def calcular_coste_personal(texto_personal, horas, df_tarifas):
    if not texto_personal or horas <= 0 or df_tarifas.empty: return 0.0
    texto_personal = str(texto_personal).lower()
    costes_encontrados = []
    
    for _, tarifa in df_tarifas.iterrows():
        nombre_tarifa = str(tarifa['Recurso']).lower()
        if nombre_tarifa and nombre_tarifa != "nan" and nombre_tarifa in texto_personal:
            costes_encontrados.append(pd.to_numeric(tarifa['Coste_Hora'], errors='coerce'))
            
    if not costes_encontrados: return 0.0
    
    suma_tarifas = sum(costes_encontrados)
    return suma_tarifas * float(horas)

# --- INICIALIZAR MEMORIA TEMPORAL ---
if 'ia_datos' not in st.session_state:
    st.session_state.ia_datos = {
        "Fecha": datetime.today().strftime("%Y-%m-%d"), "Proyecto": "", "Tarea": "", 
        "Descripción_Tarea": "", "Personal": "", "Maquinaria": ""
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
# 1. GESTIÓN DE OBRAS Y DIARIO (CON CHAT INTELIGENTE)
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
        
        tab_parte, tab_chat = st.tabs(["📝 Subir Parte (Audio/Manual)", "💬 Chat del Aparejador"])
        
        # --- PESTAÑA: SUBIR PARTE ---
        with tab_parte:
            archivo_audio = st.file_uploader("🎤 Sube tu audio de WhatsApp aquí", type=['mp3', 'wav', 'ogg', 'm4a', 'opus'])
            
            if archivo_audio and st.button("✨ Procesar Audio con IA"):
                with st.spinner("🧠 Analizando audio y estructurando tareas..."):
                    try:
                        df_diario_temp = cargar_datos("Diario")
                        tareas_existentes = []
                        if not df_diario_temp.empty and 'Tarea' in df_diario_temp.columns:
                            tareas_existentes = df_diario_temp[df_diario_temp['Proyecto'] == obra_actual]['Tarea'].dropna().unique().tolist()

                        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                            tmp.write(archivo_audio.getvalue())
                            tmp_path = tmp.name
                        
                        audio_file = genai.upload_file(path=tmp_path)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        prompt = f"""
                        Escucha este audio de un jefe de obra. Extrae la información en formato JSON estricto:
                        {{"Fecha": "YYYY-MM-DD", "Proyecto": "nombre de la obra", "Tarea": "tarea general", "Descripción_Tarea": "detalle específico", "Personal": "nombres", "Maquinaria": "maquinaria"}}
                        
                        REGLA VITAL: Tareas generales existentes en esta obra: {tareas_existentes}. 
                        - 'Tarea' debe ser un agrupador general (usa los de la lista si encaja, ej: 'Rampa de acceso'). 
                        - 'Descripción_Tarea' es el detalle exacto de lo que han hecho hoy (ej: 'Colocación de piedra', 'Echar hormigón').
                        """
                        respuesta = model.generate_content([prompt, audio_file])
                        texto_json = respuesta.text.replace('```json', '').replace('```', '').strip()
                        st.session_state.ia_datos.update(json.loads(texto_json))
                        st.success("✅ ¡Audio procesado y separado por nivel de detalle!")
                        os.remove(tmp_path)
                        genai.delete_file(audio_file.name)
                    except Exception as e:
                        st.error(f"Error: {e}")

            st.write("**Revisa y completa los datos antes de guardar:**")
            with st.form("form_diario_ia"):
                c1, c2 = st.columns(2)
                fecha_input = c1.text_input("Fecha", value=st.session_state.ia_datos.get("Fecha", datetime.today().strftime("%Y-%m-%d")))
                proyecto_ia = c2.text_input("Proyecto", value=st.session_state.ia_datos.get("Proyecto", obra_actual))
                
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
                    # 1. GUARDAR EN EL DIARIO
                    df_diario = cargar_datos("Diario")
                    nuevo_parte = pd.DataFrame([{
                        "Fecha": fecha_input, "Proyecto": obra_actual, 
                        "Tipo_Entrada": "Audio" if archivo_audio else "Manual",
                        "Contenido": archivo_audio.name if archivo_audio else "Texto manual", 
                        "Tarea": tarea, "Descripción_Tarea": desc_tarea,
                        "Personal": personal, "Horas_Personal": h_pers, 
                        "Maquinaria": maq, "Horas_Maq": h_maq, "Produccion": prod, "Unidad": ud
                    }])
                    df_diario = pd.concat([df_diario, nuevo_parte], ignore_index=True)
                    guardar_datos("Diario", df_diario)
                    
                    # 2. CALCULAR Y ENVIAR A COSTES_IMPUTADOS AUTOMÁTICAMENTE
                    df_tarifas = cargar_datos("Tarifas_Personal_Maquinaria")
                    coste_p = calcular_coste_personal(personal, h_pers, df_tarifas)
                    if coste_p > 0:
                        df_costes = cargar_datos("Costes_Imputados")
                        nuevo_coste = pd.DataFrame([{
                            "Fecha": fecha_input,
                            "Proyecto": obra_actual,
                            "Tarea": tarea,
                            "Concepto": f"Mano de obra ({desc_tarea}): {personal}",
                            "Coste_Total": coste_p
                        }])
                        df_costes = pd.concat([df_costes, nuevo_coste], ignore_index=True)
                        guardar_datos("Costes_Imputados", df_costes)

                    st.session_state.ia_datos = {
                        "Fecha": datetime.today().strftime("%Y-%m-%d"), "Proyecto": "", "Tarea": "", 
                        "Descripción_Tarea": "", "Personal": "", "Maquinaria": ""
                    }
                    st.success("¡Datos guardados en el Diario y Costes actualizados!")

        # --- PESTAÑA: CHAT DEL PROYECTO ---
        with tab_chat:
            st.write(f"Habla con la IA. Pídele que calcule rendimientos, impute materiales o registre jornadas de trabajo.")
            
            for msg in st.session_state.mensajes_chat:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
            
            if prompt_usuario := st.chat_input("Ej: Fernando y Humberto trabajaron 8h echando hormigón en la rampa..."):
                st.session_state.mensajes_chat.append({"role": "user", "content": prompt_usuario})
                with st.chat_message("user"):
                    st.markdown(prompt_usuario)
                
                df_d = cargar_datos("Diario")
                df_p = cargar_datos("Historico_Precios")
                df_t = cargar_datos("Tarifas_Personal_Maquinaria")
                
                df_d_obra = df_d[df_d['Proyecto'] == obra_actual].to_csv(index=False) if not df_d.empty else "Sin datos"
                    
                contexto = f"""
                Eres un Aparejador experto. Obra actual: '{obra_actual}'.
                
                REGLAS VITALES DE ACTUACIÓN:
                1. **IMPUTAR MATERIALES:** Si el usuario te manda imputar un material, añade este bloque:
                ```json_imputar
                {{"Tarea": "nombre general", "Concepto": "descripción material", "Coste": numero}}
                ```
                2. **REGISTRAR MANO DE OBRA:** Si el usuario indica horas de personal, OBLIGATORIAMENTE debes crear el registro en el Diario. El sistema se encargará solo de calcular los euros. Separa la Tarea General (ej: Rampa de acceso) de la Descripción Específica (ej: Echar hormigón). Añade este bloque a tu respuesta:
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
                            
                            # MATERIALES (Directo a Costes)
                            if "```json_imputar" in texto_respuesta:
                                match_imp = re.search(r'```json_imputar\n(.*?)\n```', texto_respuesta, re.DOTALL)
                                if match_imp:
                                    datos_imputar = json.loads(match_imp.group(1))
                                    df_costes = cargar_datos("Costes_Imputados")
                                    nuevo_coste = pd.DataFrame([{
                                        "Fecha": datetime.today().strftime("%Y-%m-%d"),
                                        "Proyecto": obra_actual,
                                        "Tarea": datos_imputar.get("Tarea", "General"),
                                        "Concepto": datos_imputar.get("Concepto", "Material"),
                                        "Coste_Total": float(datos_imputar.get("Coste", 0))
                                    }])
                                    df_costes = pd.concat([df_costes, nuevo_coste], ignore_index=True)
                                    guardar_datos("Costes_Imputados", df_costes)
                                    st.toast("🛒 Coste de material guardado en Base de Datos")
                                texto_respuesta = re.sub(r'```json_imputar\n.*?\n```', '', texto_respuesta, flags=re.DOTALL)

                            # MANO DE OBRA (Al Diario y automáticamente a Costes)
                            if "```json_diario" in texto_respuesta:
                                match_diario = re.search(r'```json_diario\n(.*?)\n```', texto_respuesta, re.DOTALL)
                                if match_diario:
                                    datos_diario = json.loads(match_diario.group(1))
                                    if isinstance(datos_diario, dict): datos_diario = [datos_diario]
                                    
                                    df_diario_act = cargar_datos("Diario")
                                    df_costes_act = cargar_datos("Costes_Imputados")
                                    df_tarifas_act = cargar_datos("Tarifas_Personal_Maquinaria")
                                    
                                    nuevos_partes = []
                                    nuevos_costes = []
                                    
                                    for d in datos_diario:
                                        # Guardar para el Diario
                                        nuevos_partes.append({
                                            "Fecha": d.get("Fecha", datetime.today().strftime("%Y-%m-%d")),
                                            "Proyecto": obra_actual,
                                            "Tipo_Entrada": "Chat IA",
                                            "Contenido": "Generado desde conversación",
                                            "Tarea": d.get("Tarea", ""),
                                            "Descripción_Tarea": d.get("Descripción_Tarea", ""),
                                            "Personal": d.get("Personal", ""),
                                            "Horas_Personal": float(d.get("Horas_Personal", 0)),
                                            "Maquinaria": "", "Horas_Maq": 0, "Produccion": 0, "Unidad": ""
                                        })
                                        
                                        # Calcular para enviarlo también a Costes
                                        coste_p = calcular_coste_personal(d.get("Personal", ""), float(d.get("Horas_Personal", 0)), df_tarifas_act)
                                        if coste_p > 0:
                                            nuevos_costes.append({
                                                "Fecha": d.get("Fecha", datetime.today().strftime("%Y-%m-%d")),
                                                "Proyecto": obra_actual,
                                                "Tarea": d.get("Tarea", ""),
                                                "Concepto": f"Mano de obra ({d.get('Descripción_Tarea', '')}): {d.get('Personal', '')}",
                                                "Coste_Total": coste_p
                                            })
                                            
                                    df_diario_act = pd.concat([df_diario_act, pd.DataFrame(nuevos_partes)], ignore_index=True)
                                    guardar_datos("Diario", df_diario_act)
                                    
                                    if nuevos_costes:
                                        df_costes_act = pd.concat([df_costes_act, pd.DataFrame(nuevos_costes)], ignore_index=True)
                                        guardar_datos("Costes_Imputados", df_costes_act)
                                        
                                    st.toast("👷 Partes de trabajo guardados y volcados al Libro de Costes")
                                texto_respuesta = re.sub(r'```json_diario\n.*?\n```', '', texto_respuesta, flags=re.DOTALL)

                            st.markdown(texto_respuesta)
                            st.session_state.mensajes_chat.append({"role": "assistant", "content": texto_respuesta})
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
        st.warning("No hay obras activas.")
    else:
        obra_dash = st.selectbox("Selecciona Proyecto a Analizar:", lista_obras)
        st.divider()
        
        df_diario = cargar_datos("Diario")
        df_imputados = cargar_datos("Costes_Imputados")
        df_tarifas = cargar_datos("Tarifas_Personal_Maquinaria")
        
        if df_diario.empty and df_imputados.empty:
            st.info("Aún no hay partes ni costes en esta obra.")
        else:
            df_obra = df_diario[df_diario['Proyecto'] == obra_dash].copy() if not df_diario.empty else pd.DataFrame()
            df_imp_obra = df_imputados[df_imputados['Proyecto'] == obra_dash].copy() if not df_imputados.empty else pd.DataFrame()
            
            st.subheader(f"Resumen de Trabajos: {obra_dash}")
            
            # --- CÁLCULO DE COSTES DE PERSONAL (Agrupando por 'Tarea' general) ---
            resumen_personal = pd.DataFrame(columns=['Tarea', 'Gasto_Personal'])
            if not df_obra.empty and not df_tarifas.empty:
                df_obra['Horas_Personal'] = pd.to_numeric(df_obra['Horas_Personal'], errors='coerce').fillna(0)
                df_obra['Gasto_Personal_Total'] = df_obra.apply(lambda row: calcular_coste_personal(row['Personal'], row['Horas_Personal'], df_tarifas), axis=1)
                resumen_personal = df_obra.groupby('Tarea').agg(Gasto_Personal=('Gasto_Personal_Total', 'sum')).reset_index()

            # --- CÁLCULO DE COSTES IMPUTADOS (Agrupando por 'Tarea' general) ---
            resumen_materiales = pd.DataFrame(columns=['Tarea', 'Gasto_Materiales'])
            if not df_imp_obra.empty:
                df_imp_obra['Coste_Total'] = pd.to_numeric(df_imp_obra['Coste_Total'], errors='coerce').fillna(0)
                df_solo_materiales = df_imp_obra[~df_imp_obra['Concepto'].str.contains('Mano de obra', case=False, na=False)]
                resumen_materiales = df_solo_materiales.groupby('Tarea').agg(Gasto_Materiales=('Coste_Total', 'sum')).reset_index()

            # --- UNIR TODO EN UNA TABLA ---
            if not resumen_personal.empty or not resumen_materiales.empty:
                resumen_final = pd.merge(resumen_personal, resumen_materiales, on='Tarea', how='outer').fillna(0)
                resumen_final['COSTE_TOTAL_PARTIDA'] = resumen_final['Gasto_Personal'] + resumen_final['Gasto_Materiales']
                
                st.dataframe(resumen_final.style.format({
                    "Gasto_Personal": "{:.2f} €", 
                    "Gasto_Materiales": "{:.2f} €", 
                    "COSTE_TOTAL_PARTIDA": "{:.2f} €"
                }), use_container_width=True)
            else:
                st.info("No hay datos suficientes para calcular costes todavía.")

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
            df_tar = cargar_datos("Tarifas_Personal_Maquinaria") 
            nueva_tarifa = pd.DataFrame([{"Recurso": recurso, "Tipo": tipo, "Coste_Hora": coste}])
            df_tar = pd.concat([df_tar, nueva_tarifa], ignore_index=True)
            guardar_datos("Tarifas_Personal_Maquinaria", df_tar)
            st.success("Tarifa registrada con éxito.")