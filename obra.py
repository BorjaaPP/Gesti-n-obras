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
    st.error("🚨 DETENTE: Debes pegar la URL de tu archivo Maestro en la línea 16 del código.")
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

        resumen_materiales = pd.DataFrame(columns=['Tarea', 'Gasto_Materiales'])
        if not df_imp_obra.empty:
            df_imp_obra['Coste_Total'] = pd.to_numeric(df_imp_obra['Coste_Total'], errors='coerce').fillna(0)
            df_solo_materiales = df_imp_obra[~df_imp_obra['Concepto'].str.contains('Mano de obra', case=False, na=False)]
            resumen_materiales = df_solo_materiales.groupby('Tarea').agg(Gasto_Materiales=('Coste_Total', 'sum')).reset_index()

        if not resumen_personal.empty or not resumen_materiales.empty:
            resumen_final = pd.merge(resumen_personal, resumen_materiales, on='Tarea', how='outer').fillna(0)
            resumen_final['COSTE_TOTAL_PARTIDA'] = resumen_final['Gasto_Personal'] + resumen_final['Gasto_Materiales']
            st.dataframe(resumen_final.style.format({"Gasto_Personal": "{:.2f} €", "Gasto_Materiales": "{:.2f} €", "COSTE_TOTAL_PARTIDA": "{:.2f} €"}), use_container_width=True)

# ==========================================
# 3. INFORME EJECUTIVO (FINANZAS)
# ==========================================
elif menu == "📈 Informe Ejecutivo (Finanzas)":
    st.title(f"📈 Informe Ejecutivo: {obra_actual}")
    
    df_codigos = cargar_datos("Codigos_Control", url_obra)
    df_pto = cargar_datos("Presupuesto_Base", url_obra)
    df_cert = cargar_datos("Certificaciones_Ingresos", url_obra)
    
    if df_codigos.empty:
        st.warning("⚠️ No se ha encontrado la pestaña 'Codigos_Control' o está vacía. Añade tus códigos para ver el resumen.")
    elif df_pto.empty:
        st.info("Aún no has cargado el Presupuesto Base de esta obra.")
    else:
        df_pto_obra = df_pto.copy()
        df_cert_obra = df_cert.copy() if not df_cert.empty else pd.DataFrame()
        
        # 1. Limpiamos los códigos para que coincidan perfectamente (quitamos espacios y forzamos texto)
        df_codigos['Cod_Control'] = df_codigos['Cod_Control'].astype(str).replace(r'\.0$', '', regex=True).str.strip()
        df_pto_obra['Cod_Control'] = df_pto_obra['Cod_Control'].astype(str).replace(r'\.0$', '', regex=True).str.strip()
        
        # 2. Aseguramos que los valores a sumar sean números
        df_pto_obra['Coste'] = pd.to_numeric(df_pto_obra['Coste'], errors='coerce').fillna(0)
        df_pto_obra['Importe_Total_Adjudicado'] = pd.to_numeric(df_pto_obra['Importe_Total_Adjudicado'], errors='coerce').fillna(0)
        
        # 3. Agrupamos el Presupuesto sumando los valores de Coste y Adjudicado por Cod_Control
        resumen_pto = df_pto_obra.groupby('Cod_Control').agg(
            Coste_Presupuestado=('Coste', 'sum'),
            Presupuesto_Adjudicado=('Importe_Total_Adjudicado', 'sum')
        ).reset_index()

        # 4. Preparamos las Certificaciones (Ya dejamos el hueco listo para el futuro)
        resumen_cert = pd.DataFrame(columns=['Cod_Control', 'Total_Certificado'])
        if not df_cert_obra.empty and 'Importe_Certificado_Mes_1' in df_cert_obra.columns:
            df_cert_obra['Cod_Control'] = df_cert_obra['Cod_Control'].astype(str).replace(r'\.0$', '', regex=True).str.strip()
            df_cert_obra['Importe_Certificado_Mes_1'] = pd.to_numeric(df_cert_obra['Importe_Certificado_Mes_1'], errors='coerce').fillna(0)
            resumen_cert = df_cert_obra.groupby('Cod_Control').agg(Total_Certificado=('Importe_Certificado_Mes_1', 'sum')).reset_index()

        # 5. Cruzamos los datos usando "Codigos_Control" como esqueleto principal
        informe_final = df_codigos.merge(resumen_pto, on='Cod_Control', how='left')
        informe_final = informe_final.merge(resumen_cert, on='Cod_Control', how='left')
        
        # Rellenamos los vacíos con 0
        informe_final['Coste_Presupuestado'] = informe_final['Coste_Presupuestado'].fillna(0)
        informe_final['Presupuesto_Adjudicado'] = informe_final['Presupuesto_Adjudicado'].fillna(0)
        informe_final['Total_Certificado'] = informe_final['Total_Certificado'].fillna(0)
        
        # 6. Calculamos el % de Avance de la Certificación respecto al Adjudicado
        informe_final['% Certificado'] = (informe_final['Total_Certificado'] / informe_final['Presupuesto_Adjudicado']) * 100
        informe_final['% Certificado'] = informe_final['% Certificado'].fillna(0).replace([float('inf'), -float('inf')], 0)
        
        # --- INTERFAZ VISUAL ---
        st.subheader("📊 Control de Licitación vs. Certificación (EDT)")
        st.write("Esta tabla se genera en tiempo real cruzando tu lista de códigos con el Presupuesto y las Certificaciones. *Los costes reales (albaranes/nóminas) se analizarán en otro módulo.*")
        
        # Mostramos la tabla con barras de progreso para la certificación
        st.dataframe(
            informe_final.style.format({
                "Coste_Presupuestado": "{:,.2f} €",
                "Presupuesto_Adjudicado": "{:,.2f} €",
                "Total_Certificado": "{:,.2f} €",
                "% Certificado": "{:.2f} %"
            }).bar(subset=['% Certificado'], color='#5fba7d', vmax=100),
            use_container_width=True, hide_index=True
        )
        
        # KPIs Generales Totales
        st.divider()
        c1, c2, c3 = st.columns(3)
        total_adj = informe_final['Presupuesto_Adjudicado'].sum()
        total_cert = informe_final['Total_Certificado'].sum()
        avance_global = (total_cert / total_adj * 100) if total_adj > 0 else 0
        
        c1.metric("Total Presupuesto Adjudicado", f"{total_adj:,.2f} €")
        c2.metric("Total Certificado a Origen", f"{total_cert:,.2f} €")
        c3.metric("% Avance Global Certificado", f"{avance_global:.2f} %")

# ==========================================
# 4. MÓDULO NUEVO: IMPORTADOR MÁGICO DE PRESTO
# ==========================================
elif menu == "📥 Importar Presupuesto (Presto)":
    st.title(f"📥 Importador Mágico de Presto: {obra_actual}")
    st.write("Sube el Excel exportado de Presto para volcarlo estructurado a tu Base de Datos.")
    
    archivo_excel = st.file_uploader("📂 Sube tu archivo Excel (.xlsx)", type=['xlsx', 'xls'])
    
    if archivo_excel:
        xls = pd.ExcelFile(archivo_excel)
        hojas_excel = xls.sheet_names
        
        st.divider()
        st.subheader("⚙️ Paso 1: Configuración del Asistente")
        
        with st.form("form_config_importacion"):
            # Simplificamos: ya no pedimos la pestaña de Códigos de Control.
            nombres_hojas_limpios = [h.lower().strip() for h in hojas_excel]
            hojas_sugeridas = [h for h, h_limpio in zip(hojas_excel, nombres_hojas_limpios) if h_limpio in ["viviendas", "elementos comunes", "trasteros"]]
            hojas_pto = st.multiselect("1. ¿Qué pestañas contienen el Presupuesto?", hojas_excel, default=hojas_sugeridas)
            
            c3, c4 = st.columns(2)
            gg_bi = c3.number_input("2. % Gastos Generales y Beneficio Ind. (GG_BI)", value=15.00, step=1.0)
            baja = c4.number_input("3. % Baja de Adjudicación", value=1.20, step=0.1)
            
            letras_excel = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]
            
            st.write("**4. Mapeo de Columnas: Pestañas de Presupuesto**")
            col1, col2, col3 = st.columns(3)
            map_codigo = col1.selectbox("Columna 'Código' de Partida (Ej: A)", letras_excel, index=0) 
            map_unidad = col2.selectbox("Columna 'Unidad' (Ej: C)", letras_excel, index=2) 
            map_texto = col3.selectbox("Columna 'Resumen / Texto' (Ej: D)", letras_excel, index=3) 
            
            col4, col5, col6 = st.columns(3)
            map_cant = col4.selectbox("Columna 'Cantidad' (Ej: E)", letras_excel, index=4) 
            map_precio = col5.selectbox("Columna 'Precio Base' (Ej: H)", letras_excel, index=7) 
            map_coste = col6.selectbox("Columna 'Coste Interno' [Opcional]", ["No disponible"] + letras_excel, index=12) 
            
            st.write("**5. Mapeo de Codigo de Control (El numerito 1, 2, 3...)**")
            map_cod_control = st.selectbox("¿En qué columna de estas pestañas de presupuesto está el 'Cod_Control'?", ["No disponible"] + letras_excel, index=0)
            
            btn_procesar = st.form_submit_button("🚀 Procesar Datos y Ver Tabla")

        if btn_procesar and hojas_pto:
            with st.spinner("Leyendo estructura de Presto y calculando presupuestos..."):
                try:
                    df_resultado = pd.DataFrame()
                    
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
                            
                            # Código de la partida
                            codigo_val = str(row[idx_c]).strip() if pd.notna(row[idx_c]) else ""
                            if codigo_val.endswith('.0'): codigo_val = codigo_val[:-2]

                            texto_val = str(row[idx_t]).strip() if pd.notna(row[idx_t]) else ""
                            
                            precio_raw = str(row[idx_p]).replace(".", "").replace(",", ".") if isinstance(row[idx_p], str) else row[idx_p]
                            precio_val = pd.to_numeric(precio_raw, errors='coerce')
                            
                            if codigo_val.lower() == "nan": codigo_val = ""
                            if texto_val.lower() == "nan": texto_val = ""
                            
                            if "código" in codigo_val.lower() or "codigo" in codigo_val.lower(): continue
                            
                            # Extraemos el Cod_Control de la misma fila (Paso 5)
                            cod_control_asignado = ""
                            if idx_cc != -1 and len(row) > idx_cc:
                                cc_raw = str(row[idx_cc]).strip() if pd.notna(row[idx_cc]) else ""
                                if cc_raw.endswith('.0'): cc_raw = cc_raw[:-2]
                                if cc_raw.lower() != "nan":
                                    cod_control_asignado = cc_raw
                            
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
                                    "Cod_Control": cod_control_asignado,
                                    "Capítulo": capitulo_actual,
                                    "Partida_Codigo": codigo_val,
                                    "Partida_Nombre": texto_val, 
                                    "Partida_Descripcion": texto_val, 
                                    "Unidad": str(row[idx_u]) if pd.notna(row[idx_u]) and str(row[idx_u]) != "nan" else "",
                                    "Cantidad_Proyecto": cantidad,
                                    "PrPres": pr_pres,
                                    "Precio_Licitacion": precio_licitacion,
                                    "Precio_Adjudicado": precio_adjudicado,
                                    "Coste": coste,
                                    "Importe_Total_Adjudicado": importe_total
                                })
                                
                            elif not codigo_val and pd.isna(precio_val) and texto_val:
                                if filas_procesadas: 
                                    filas_procesadas[-1]["Partida_Descripcion"] += "\n" + texto_val
                                
                    df_resultado = pd.DataFrame(filas_procesadas)
                    st.session_state.df_importacion = df_resultado
                    st.success("✅ ¡Datos procesados correctamente!")
                except Exception as e:
                    st.error(f"Error procesando el Excel: {e}")

        if 'df_importacion' in st.session_state and not st.session_state.df_importacion.empty:
            st.subheader("👀 Vista Previa del Presupuesto")
            st.dataframe(st.session_state.df_importacion.head(50), use_container_width=True)
            
            st.warning("⚠️ Al pulsar guardar, los datos sustituirán a los actuales en tu Google Sheets.")
            if st.button("💾 CONFIRMAR Y SUBIR A BASE DE DATOS", type="primary"):
                guardar_datos("Presupuesto_Base", st.session_state.df_importacion, url_obra)
                st.success("🎉 ¡El Presupuesto ha sido importado a Google Sheets!")
                del st.session_state['df_importacion']

# ==========================================
# 5. SUBCONTRATAS
# ==========================================
elif menu == "👷 Subcontratas":
    st.title(f"Control de Subcontratas: {obra_actual}")
    with st.form("form_subcontratas"):
        c1, c2 = st.columns(2)
        gremio = c1.text_input("Gremio (ej: Fontanería)")
        empresa = c2.text_input("Empresa Subcontratada")
        c3, c4, c5 = st.columns(3)
        f_inicio = c3.date_input("Fecha Inicio")
        f_fin = c4.date_input("Fecha Fin Prevista")
        estado = c5.selectbox("Estado", ["En curso", "Finalizado", "Paralizado"])
        notas = st.text_area("Notas / Avance")
        
        if st.form_submit_button("Registrar Subcontrata"):
            df_sub = cargar_datos("Subcontratas", url_obra)
            nueva_sub = pd.DataFrame([{
                "Proyecto": obra_actual, "Gremio": gremio, "Empresa": empresa,
                "Fecha_Inicio": f_inicio.strftime("%Y-%m-%d"), "Fecha_Fin_Prevista": f_fin.strftime("%Y-%m-%d"),
                "Fecha_Fin_Real": "", "Estado": estado, "Avance_Notas": notas
            }])
            df_sub = pd.concat([df_sub, nueva_sub], ignore_index=True)
            guardar_datos("Subcontratas", df_sub, url_obra)
            st.success("Subcontrata registrada correctamente.")

# ==========================================
# 6. FACTURAS Y PRECIOS
# ==========================================
elif menu == "🧾 Facturas y Precios":
    st.title(f"Histórico de Precios: {obra_actual}")
    with st.form("form_precios"):
        c1, c2, c3 = st.columns(3)
        codigo = c1.text_input("Código Material (SKU)")
        desc = c2.text_input("Descripción Material")
        prov = c3.text_input("Proveedor")
        c4, c5, c6 = st.columns(3)
        precio = c4.number_input("Precio Unitario (€)", min_value=0.0, format="%.2f")
        dto = c5.number_input("Descuento (%)", min_value=0.0, format="%.2f")
        factura = c6.text_input("Nº Factura / Origen")
        
        if st.form_submit_button("Guardar Precio"):
            df_hist = cargar_datos("Historico_Precios", url_obra)
            nuevo_precio = pd.DataFrame([{
                "Codigo_Material": codigo, "Material": desc, "Precio_Unitario": precio,
                "Descuento": dto, "Proveedor": prov, "Fecha_Registro": datetime.today().strftime("%Y-%m-%d"),
                "Factura_Origen": factura, "Proyecto": obra_actual
            }])
            df_hist = pd.concat([df_hist, nuevo_precio], ignore_index=True)
            guardar_datos("Historico_Precios", df_hist, url_obra)
            st.success("Precio guardado en la base de datos.")

# ==========================================
# 7. TARIFAS
# ==========================================
elif menu == "💰 Tarifas (Personal/Maq)":
    st.title(f"Costes Internos: {obra_actual}")
    with st.form("form_tarifas"):
        c1, c2, c3 = st.columns(3)
        recurso = c1.text_input("Nombre (ej: Fernando, Retroexcavadora)")
        tipo = c2.selectbox("Tipo", ["Personal", "Maquinaria"])
        coste = c3.number_input("Coste por Hora (€)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Guardar Tarifa"):
            df_tar = cargar_datos("Tarifas_Personal_Maquinaria", url_obra) 
            nueva_tarifa = pd.DataFrame([{"Recurso": recurso, "Tipo": tipo, "Coste_Hora": coste}])
            df_tar = pd.concat([df_tar, nueva_tarifa], ignore_index=True)
            guardar_datos("Tarifas_Personal_Maquinaria", df_tar, url_obra)
            st.success("Tarifa registrada con éxito.")