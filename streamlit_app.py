
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import base64
import pdfkit  # Requiere wkhtmltopdf instalado en el sistema

st.set_page_config(layout="wide", page_title="Calendario de Matricería")

# --- 1. CONFIGURACIÓN DE LOS GOOGLE SHEETS ---
# Convertimos las URLs de 'edit' a 'export?format=csv'
SHEETS_CONFIG = [
    {"url": "https://docs.google.com/spreadsheets/d/1sccnOPuosjMSepp0FZoEGteYArIIhB2fGH7TeSRW_7E/export?format=csv", "skiprows": 2},
    {"url": "https://docs.google.com/spreadsheets/d/1bL_tnlSXGO_t9tKnhIHT5pZ3DAxivbiq2tFETVxBaVI/export?format=csv", "skiprows": 2},
    {"url": "https://docs.google.com/spreadsheets/d/1VqsPNhAlT1kPCltbMWsbkZNFBKdwZRFM5RAmnRV0v3c/export?format=csv", "skiprows": 0},
    {"url": "https://docs.google.com/spreadsheets/d/1UNSCxrTy9TUdggNt0ta0TcsEvT3idaRGWcXE_t8J40I/export?format=csv", "skiprows": 0},
    {"url": "https://docs.google.com/spreadsheets/d/1A-0mngZdgvZGbqzWjA_awhrwfvca0K4aGqp5NBAoFAY/export?format=csv", "skiprows": 0},
    {"url": "https://docs.google.com/spreadsheets/d/1MptnOuRfyOAr1EgzNJVygTtNziOSdzXJn-PZDX0pNzc/export?format=csv", "skiprows": 0},
]

# --- 2. FUNCIÓN DE EXTRACCIÓN Y LIMPIEZA ---
@st.cache_data(ttl=600) # Se actualiza cada 10 minutos
def load_data():
    all_data = []
    
    for config in SHEETS_CONFIG:
        try:
            df = pd.read_csv(config["url"], skiprows=config["skiprows"])
            df.columns = df.columns.astype(str).str.upper().str.strip()
            
            # Buscar columnas clave (Fecha, Matricero, Horas)
            col_fecha = next((c for c in df.columns if 'FECHA' in c), None)
            col_mat = next((c for c in df.columns if 'MATRICERO' in c), None)
            
            # Para las horas, pueden ser múltiples columnas o una (TOTAL HS, HORAS, HS)
            cols_horas = [c for c in df.columns if 'HORAS' in c or 'HS' in c.split()]
            
            if col_fecha and col_mat and cols_horas:
                # Nos quedamos solo con las columnas que importan
                df_clean = df[[col_fecha, col_mat] + cols_horas].copy()
                
                # Convertir a numérico y sumar todas las columnas de horas de esa fila
                for col in cols_horas:
                    df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
                
                df_clean['TOTAL_HORAS'] = df_clean[cols_horas].sum(axis=1)
                
                # Renombrar para unificar
                df_clean = df_clean.rename(columns={col_fecha: 'FECHA', col_mat: 'MATRICERO'})
                df_clean = df_clean[['FECHA', 'MATRICERO', 'TOTAL_HORAS']]
                all_data.append(df_clean)
        except Exception as e:
            st.warning(f"Error cargando un archivo: {e}")
            
    if not all_data:
        return pd.DataFrame()
        
    # Unir todos los datos
    master_df = pd.concat(all_data, ignore_index=True)
    
    # Limpiar formato de Fecha y Matricero
    master_df['FECHA'] = pd.to_datetime(master_df['FECHA'], errors='coerce', dayfirst=True)
    master_df['MATRICERO'] = master_df['MATRICERO'].astype(str).str.strip().str.upper()
    master_df = master_df.dropna(subset=['FECHA']) # Eliminar filas sin fecha
    
    # Agrupar por Fecha y Matricero para sumar horas del mismo día en distintos sheets
    master_df = master_df.groupby(['FECHA', 'MATRICERO'], as_index=False)['TOTAL_HORAS'].sum()
    
    return master_df

# --- 3. INTERFAZ DE USUARIO ---
st.title("📅 Calendario de Horas de Matricería")

# Selector de fechas en la barra lateral
st.sidebar.header("Filtros")
today = datetime.now()
start_date = st.sidebar.date_input("Fecha Inicio", today - timedelta(days=today.weekday())) # Lunes de esta semana
end_date = st.sidebar.date_input("Fecha Fin", start_date + timedelta(days=6)) # Domingo

# Cargar datos
df = load_data()

if df.empty:
    st.error("No se pudieron extraer datos. Verifica los links o el formato de los Sheets.")
else:
    # Filtrar por fechas
    mask = (df['FECHA'].dt.date >= start_date) & (df['FECHA'].dt.date <= end_date)
    df_filtered = df.loc[mask].copy()

    if df_filtered.empty:
        st.info("No hay horas registradas en el rango seleccionado.")
    else:
        # Formatear la fecha para que se vea como columna (Ej: LUNES 6/10)
        dias_espanol = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
        df_filtered['DIA_SEMANA'] = df_filtered['FECHA'].dt.dayofweek.apply(lambda x: dias_espanol[x])
        df_filtered['COLUMNA_FECHA'] = df_filtered['DIA_SEMANA'] + " " + df_filtered['FECHA'].dt.strftime('%d/%m/%Y')

        # Pivotear tabla (Matricero en filas, Fechas en columnas)
        pivot_df = df_filtered.pivot_table(
            index='MATRICERO', 
            columns='COLUMNA_FECHA', 
            values='TOTAL_HORAS', 
            aggfunc='sum',
            fill_value=0
        )
        
        # Ordenar columnas cronológicamente (basado en la fecha oculta en el string)
        pivot_df = pivot_df[sorted(pivot_df.columns, key=lambda x: datetime.strptime(x.split(' ')[1], '%d/%m/%Y'))]

        # --- 4. ESTILIZACIÓN (Colores como en Excel) ---
        def color_cells(val):
            if val == 0:
                color = '#7f7f7f' # Gris oscuro (como en la imagen para el 0)
                text = 'white'
            elif val == 8:
                color = '#c6efce' # Verde suave
                text = '#006100'
            elif val > 8:
                color = '#ffc7ce' # Rojo/Rosa para horas extras
                text = '#9c0006'
            else:
                color = '#ffeb9c' # Amarillo para menos de 8
                text = '#9c6500'
            return f'background-color: {color}; color: {text}; text-align: center;'

        styled_df = pivot_df.style.applymap(color_cells)
        
        # Mostrar en pantalla
        st.subheader(f"SEMANA DEL {start_date.strftime('%d/%m')} AL {end_date.strftime('%d/%m')}")
        st.dataframe(styled_df, use_container_width=True)

        # --- 5. EXPORTACIÓN A PDF Y EXCEL ---
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        # Botón para descargar Excel (Siempre funciona, sin instalar nada extra)
        # buffer = io.BytesIO() (Omitido por brevedad, Streamlit maneja esto nativamente si se prefiere)
        # Pero exportar el HTML es excelente para imprimir a PDF desde el navegador:
        html_table = styled_df.to_html()
        
        with col1:
            st.download_button(
                label="📥 Descargar Tabla (HTML para Imprimir)",
                data=html_table,
                file_name=f"Asistencia_{start_date}.html",
                mime="text/html"
            )
            st.caption("Abre el HTML descargado y presiona Ctrl+P para guardar como PDF exacto con colores.")

        # Botón PDF (Solo funciona si tu servidor tiene wkhtmltopdf)
        with col2:
            if st.button("🖨️ Generar PDF Directo"):
                try:
                    pdf = pdfkit.from_string(html_table, False)
                    b64 = base64.b64encode(pdf).decode()
                    href = f'<a href="data:application/pdf;base64,{b64}" download="calendario_{start_date}.pdf" target="_blank">Haz clic aquí para descargar tu PDF</a>'
                    st.markdown(href, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error generando PDF: ¿Tienes wkhtmltopdf instalado? Error: {e}")

