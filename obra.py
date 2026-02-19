import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="ERP Construcción - Borja", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos(hoja):
    try:
        return conn.read(worksheet=hoja, ttl=0)
    except Exception as e:
        st.error(f"Error al cargar la hoja '{hoja}'. ¿Está creada en Google Sheets?")
        return pd.DataFrame()

def guardar_datos(hoja, df):
    conn.update(worksheet=hoja, data=df)

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
# 1. GESTIÓN DE OBRAS Y DIARIO
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
        with st.form("form_diario"):
            fecha = st.date_input("Fecha", datetime.today())
            
            st.write("**1. Resumen General (Audio o Texto)**")
            archivo_audio = st.file_uploader("🎤 Subir Audio", type=['mp3', 'wav', 'ogg', 'm4a'])
            texto_nota = st.text_area("O escribe el parte manual...")
            
            st.write("**2. Rendimientos (Opcional)**")
            c1, c2, c3, c4 = st.columns(4)
            tarea = c1.text_input("Tarea (ej: Zanja)")
            personal = c2.text_input("Personal (ej: Fernando)")
            h_pers = c3.number_input("Horas Personal", min_value=0.0)
            maq = c4.text_input("Maquinaria")
            
            c5, c6, c7, c8 = st.columns(4)
            h_maq = c5.number_input("Horas Maquinaria", min_value=0.0)
            prod = c6.number_input("Producción", min_value=0.0)
            ud = c7.text_input("Unidad (ej: m3)")
            
            if st.form_submit_button("💾 Guardar Parte"):
                contenido_final = f"Audio: {archivo_audio.name}" if archivo_audio else texto_nota
                df_diario = cargar_datos("Diario")
                nuevo_parte = pd.DataFrame([{
                    "Fecha": fecha.strftime("%Y-%m-%d"), "Proyecto": obra_actual, 
                    "Tipo_Entrada": "Audio" if archivo_audio else "Texto",
                    "Contenido": contenido_final, "Tarea": tarea, "Personal": personal,
                    "Horas_Personal": h_pers, "Maquinaria": maq, "Horas_Maq": h_maq,
                    "Produccion": prod, "Unidad": ud
                }])
                df_diario = pd.concat([df_diario, nuevo_parte], ignore_index=True)
                guardar_datos("Diario", df_diario)
                st.success("Parte guardado correctamente.")

# ==========================================
# 2. SUBCONTRATAS
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
            st.success("Subcontrata registrada.")

# ==========================================
# 3. FACTURAS Y PRECIOS
# ==========================================
elif menu == "🧾 Facturas y Precios":
    st.title("Histórico de Precios y Facturas")
    st.info("Módulo de lectura automática (OCR) en mantenimiento. Registro manual activo.")
    
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
            st.success(f"Precio del artículo '{codigo}' guardado en base de datos.")

# ==========================================
# 4. TARIFAS
# ==========================================
elif menu == "💰 Tarifas (Personal/Maq)":
    st.title("Costes Internos (Personal y Maquinaria)")
    with st.form("form_tarifas"):
        c1, c2, c3 = st.columns(3)
        recurso = c1.text_input("Nombre (ej: Fernando, Dumper)")
        tipo = c2.selectbox("Tipo", ["Personal", "Maquinaria"])
        coste = c3.number_input("Coste por Hora (€)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Guardar Tarifa"):
            df_tar = cargar_datos("Tarifas")
            nueva_tarifa = pd.DataFrame([{"Recurso": recurso, "Tipo": tipo, "Coste_Hora": coste}])
            df_tar = pd.concat([df_tar, nueva_tarifa], ignore_index=True)
            guardar_datos("Tarifas", df_tar)
            st.success("Tarifa actualizada.")

# ==========================================
# 5. ASISTENTE IA
# ==========================================
elif menu == "🤖 Asistente IA (Próximamente)":
    st.title("🤖 Tu Asistente de Obra")
    st.write("Aquí podrás preguntarle a la IA cosas como:")
    st.info("💬 *'¿Qué días estuvo Fernando en la obra de Calle Mayor?'*")
    st.info("💬 *'¿Cuál fue el último precio que pagamos por el ladrillo código L-450?'*")
    st.warning("⚠️ Necesitamos rellenar el Excel con datos reales primero para que la IA tenga información que leer. ¡Ve a las otras pestañas y mete un par de datos de prueba!")