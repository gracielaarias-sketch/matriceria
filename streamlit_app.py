import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import tempfile
import os
from fpdf import FPDF

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Calendario Matricería", layout="wide", page_icon="📅")

st.markdown("""
<style>
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-style">📅 Calendario de Horas de Matricería</div>', unsafe_allow_html=True)
st.write("Generador de PDF usando FPDF (Sin dependencias externas)")
st.divider()

# ==========================================
# 2. CARGA DE DATOS DE GOOGLE SHEETS
# ==========================================
SHEETS_CONFIG = [
    {"url": "https://docs.google.com/spreadsheets/d/1sccnOPuosjMSepp0FZoEGteYArIIhB2fGH7TeSRW_7E/export?format=csv", "skiprows": 2},
    {"url": "https://docs.google.com/spreadsheets/d/1bL_tnlSXGO_t9tKnhIHT5pZ3DAxivbiq2tFETVxBaVI/export?format=csv", "skiprows": 2},
    {"url": "https://docs.google.com/spreadsheets/d/1VqsPNhAlT1kPCltbMWsbkZNFBKdwZRFM5RAmnRV0v3c/export?format=csv", "skiprows": 0},
    {"url": "https://docs.google.com/spreadsheets/d/1UNSCxrTy9TUdggNt0ta0TcsEvT3idaRGWcXE_t8J40I/export?format=csv", "skiprows": 0},
    {"url": "https://docs.google.com/spreadsheets/d/1A-0mngZdgvZGbqzWjA_awhrwfvca0K4aGqp5NBAoFAY/export?format=csv", "skiprows": 0},
    {"url": "https://docs.google.com/spreadsheets/d/1MptnOuRfyOAr1EgzNJVygTtNziOSdzXJn-PZDX0pNzc/export?format=csv", "skiprows": 0},
]

@st.cache_data(ttl=300)
def load_data():
    all_data = []
    for config in SHEETS_CONFIG:
        try:
            df = pd.read_csv(config["url"], skiprows=config["skiprows"])
            df.columns = df.columns.astype(str).str.upper().str.strip()
            
            col_fecha = next((c for c in df.columns if 'FECHA' in c), None)
            col_mat = next((c for c in df.columns if 'MATRICERO' in c), None)
            cols_horas = [c for c in df.columns if 'HORAS' in c or 'HS' in c.split()]
            
            if col_fecha and col_mat and cols_horas:
                df_clean = df[[col_fecha, col_mat] + cols_horas].copy()
                for col in cols_horas:
                    df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
                
                df_clean['TOTAL_HORAS'] = df_clean[cols_horas].sum(axis=1)
                df_clean = df_clean.rename(columns={col_fecha: 'FECHA', col_mat: 'MATRICERO'})
                df_clean = df_clean[['FECHA', 'MATRICERO', 'TOTAL_HORAS']]
                all_data.append(df_clean)
        except Exception as e:
            pass # Ignoramos errores individuales para no romper la app
            
    if not all_data:
        return pd.DataFrame()
        
    master_df = pd.concat(all_data, ignore_index=True)
    master_df['FECHA'] = pd.to_datetime(master_df['FECHA'], errors='coerce', dayfirst=True)
    master_df['MATRICERO'] = master_df['MATRICERO'].astype(str).str.strip().str.upper()
    master_df = master_df.dropna(subset=['FECHA'])
    
    # Agrupar
    master_df = master_df.groupby(['FECHA', 'MATRICERO'], as_index=False)['TOTAL_HORAS'].sum()
    return master_df

df_raw = load_data()

# ==========================================
# 3. INTERFAZ Y FILTROS
# ==========================================
col1, col2 = st.columns([1, 3])

with col1:
    st.write("**Seleccione la semana:**")
    today = datetime.now()
    lunes_default = today - timedelta(days=today.weekday())
    start_date = st.date_input("Fecha Inicio (Lunes sugerido)", lunes_default)
    end_date = start_date + timedelta(days=6)
    st.info(f"Rango: {start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}")

if df_raw.empty:
    st.warning("No hay datos cargados en la base principal.")
    st.stop()

# Filtrar y armar el Pivot (Calendario)
mask = (df_raw['FECHA'].dt.date >= start_date) & (df_raw['FECHA'].dt.date <= end_date)
df_filtered = df_raw.loc[mask].copy()

pivot_df = pd.DataFrame()

if not df_filtered.empty:
    dias_espanol = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
    df_filtered['DIA_SEMANA'] = df_filtered['FECHA'].dt.dayofweek.apply(lambda x: dias_espanol[x])
    df_filtered['COLUMNA_FECHA'] = df_filtered['DIA_SEMANA'] + " " + df_filtered['FECHA'].dt.strftime('%d/%m')

    pivot_df = df_filtered.pivot_table(
        index='MATRICERO', 
        columns='COLUMNA_FECHA', 
        values='TOTAL_HORAS', 
        aggfunc='sum',
        fill_value=0
    )
    
    # Ordenar columnas por fecha (basado en el texto 'DD/MM')
    pivot_df = pivot_df[sorted(pivot_df.columns, key=lambda x: datetime.strptime(x.split(' ')[1], '%d/%m'))]
    pivot_df = pivot_df.reset_index()

# ==========================================
# 4. CLASE PDF (FPDF)
# ==========================================
class PDF(FPDF):
    def __init__(self, start_date, end_date):
        super().__init__(orientation='L', unit='mm', format='A4') # L = Landscape (Apaisado)
        self.rango = f"{start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"
        
    def header(self):
        self.set_font("Arial", 'B', 16)
        self.set_text_color(31, 41, 55)
        self.cell(0, 10, "Reporte Semanal de Asistencia - Matriceria", border=0, ln=True, align='C')
        self.set_font("Arial", 'I', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, f"Semana del: {self.rango}", border=0, ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Pagina {self.page_no()}", 0, 0, "C")

def clean_text(text):
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def build_pdf(df_pivot, s_date, e_date):
    pdf = PDF(s_date, e_date)
    pdf.add_page()
    
    if df_pivot.empty:
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, "No hay datos para la semana seleccionada.", ln=True, align='C')
    else:
        # Configurar anchos de columna
        w_mat = 60 # Ancho para el nombre del matricero
        w_day = 30 # Ancho para cada día
        
        # --- ENCABEZADOS DE TABLA ---
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(31, 73, 125) # Azul oscuro
        pdf.set_text_color(255, 255, 255)
        
        pdf.cell(w_mat, 8, "MATRICERO", border=1, align='C', fill=True)
        cols_dias = [c for c in df_pivot.columns if c != 'MATRICERO']
        for col in cols_dias:
            pdf.cell(w_day, 8, clean_text(col), border=1, align='C', fill=True)
        pdf.ln()

        # --- FILAS DE DATOS ---
        pdf.set_font("Arial", 'B', 9)
        for _, row in df_pivot.iterrows():
            # Imprimir Nombre
            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(w_mat, 8, clean_text(str(row['MATRICERO'])[:30]), border=1, fill=True)
            
            # Imprimir Horas con lógica de colores
            for col in cols_dias:
                val = row[col]
                
                # Lógica de colores igual a la imagen
                if val == 0:
                    pdf.set_fill_color(127, 127, 127) # Gris
                    pdf.set_text_color(255, 255, 255)
                elif val == 8:
                    pdf.set_fill_color(198, 239, 206) # Verde
                    pdf.set_text_color(0, 97, 0)
                elif val > 8:
                    pdf.set_fill_color(255, 199, 206) # Rojo
                    pdf.set_text_color(156, 0, 6)
                else:
                    pdf.set_fill_color(255, 235, 156) # Amarillo
                    pdf.set_text_color(156, 101, 0)
                
                # Mostrar sin decimales si es entero
                txt_val = str(int(val)) if val == int(val) else f"{val:.1f}"
                pdf.cell(w_day, 8, txt_val, border=1, align='C', fill=True)
            pdf.ln()

    # Guardar en memoria
    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_pdf.name)
    with open(temp_pdf.name, "rb") as f:
        pdf_bytes = f.read()
    os.remove(temp_pdf.name)
    return pdf_bytes

# ==========================================
# 5. RENDERIZADO Y DESCARGA
# ==========================================
with col2:
    if pivot_df.empty:
        st.info("No hay datos en esta semana. Selecciona otra fecha.")
    else:
        st.write("**Vista previa de los datos:**")
        st.dataframe(pivot_df, use_container_width=True, hide_index=True)
        
        st.write("")
        if st.button("🖨️ Generar PDF", type="primary"):
            with st.spinner("Construyendo documento PDF..."):
                try:
                    pdf_data = build_pdf(pivot_df, start_date, end_date)
                    st.download_button(
                        label="📥 Descargar Calendario PDF", 
                        data=pdf_data, 
                        file_name=f"Calendario_Matriceria_{start_date.strftime('%d%m%Y')}.pdf", 
                        mime="application/pdf", 
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Error generando PDF: {e}")
