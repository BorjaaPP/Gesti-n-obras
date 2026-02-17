import streamlit as st
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Gestión de Obra", layout="wide")

st.title("🏗️ Sistema de Control de Obra")

# --- BASE DE DATOS TEMPORAL (Esto luego irá a un archivo real) ---
if 'albaranes' not in st.session_state:
    st.session_state.albaranes = []

# --- INTERFAZ DE CARGA ---
st.header("1. Entrada de Documentos")
col1, col2 = st.columns(2)

with col1:
    st.subheader("📸 Albaranes")
    archivo = st.file_uploader("Subir foto de albarán", type=['png', 'jpg', 'jpeg'])
    
    if archivo:
        st.image(archivo, width=300)
        
        # Simulamos que el programa NO conoce al proveedor
        with st.expander("⚠️ Formato no reconocido. Haz clic aquí para 'explicar' el albarán"):
            st.info("Introduce los datos una vez. El programa guardará este formato para la próxima vez.")
            prov = st.text_input("Nombre del Proveedor")
            num = st.text_input("Número de Albarán")
            fecha = st.date_input("Fecha del Albarán")
            material = st.text_input("Material / Concepto")
            cant = st.number_input("Cantidad", min_value=0.0)
            
            if st.button("Guardar y Enseñar al Programa"):
                nuevo_alb = {"Proveedor": prov, "Nº": num, "Fecha": fecha, "Material": material, "Cantidad": cant}
                st.session_state.albaranes.append(nuevo_alb)
                st.success("¡Aprendido! Datos guardados.")

with col2:
    st.subheader("📄 Facturas")
    archivo_pdf = st.file_uploader("Subir factura PDF", type=['pdf'])
    if archivo_pdf:
        st.write("Factura recibida. Esperando cruce de datos...")

# --- VISUALIZACIÓN ---
st.header("2. Registro de Albaranes")
if st.session_state.albaranes:
    df = pd.DataFrame(st.session_state.albaranes)
    st.dataframe(df, use_container_width=True)
else:
    st.write("No hay albaranes cargados todavía.")
