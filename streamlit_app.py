import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import tempfile
import os
from collections import defaultdict
from fpdf import FPDF

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Calendario Matricería", layout="centered", page_icon="📅")

st.markdown("""
<style>
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-style">📅 Reporte Mensual de Matricería</div>', unsafe_allow_html=True)
st.write("<p style='text-align: center;'>Selecciona el rango de fechas. El sistema organizará automáticamente un mes por hoja, incluyendo Sábados y Domingos en el cálculo de horas extra.</p>", unsafe_allow_html=True)
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
            df = df.loc[:, ~df.columns.duplicated()].copy()
            
            col_fecha = next((c for c in df.columns if 'FECHA' in c), None)
            col_mat = next((c for c in df.columns if 'MATRICERO' in c), None)
            cols_horas = [c for c in df.columns if ('HORAS' in c or 'HS' in c.split() or 'HS' in c) and 'TOTAL' not in c]
            
            if not cols_horas:
                cols_horas = [c for c in df.columns if 'TOTAL' in c and ('HS' in c or 'HORAS' in c)]
            
            if col_fecha and col_mat and cols_horas:
                horas_sum = pd.to_numeric(df[cols_horas[0]], errors='coerce').fillna(0)
                if len(cols_horas) > 1:
                    for col in cols_horas[1:]:
                        horas_sum += pd.to_numeric(df[col], errors='coerce').fillna(0)
                
                df_clean = pd.DataFrame({
                    'FECHA': df[col_fecha],
                    'MATRICERO': df[col_mat],
                    'TOTAL_HORAS': horas_sum
                })
                all_data.append(df_clean)
        except Exception:
            pass
            
    if not all_data:
        return pd.DataFrame()
        
    master_df = pd.concat(all_data, ignore_index=True)
    master_df['FECHA'] = pd.to_datetime(master_df['FECHA'], errors='coerce', dayfirst=True)
    master_df['MATRICERO'] = master_df['MATRICERO'].astype(str).str.strip().str.upper()
    master_df = master_df.dropna(subset=['FECHA'])
    
    # Agrupar las horas
    master_df = master_df.groupby(['FECHA', 'MATRICERO'], as_index=False)['TOTAL_HORAS'].sum()
    
    return master_df

df_raw = load_data()

# ==========================================
# 3. INTERFAZ Y FILTROS
# ==========================================
col1, col2 = st.columns(2)
today = datetime.now()
inicio_mes = today.replace(day=1)

with col1:
    start_date = st.date_input("📅 Fecha de Inicio", inicio_mes)
with col2:
    end_date = st.date_input("📅 Fecha de Fin", today)

if start_date > end_date:
    st.error("La fecha de inicio no puede ser mayor a la fecha de fin.")
    st.stop()

if df_raw.empty:
    st.warning("No hay datos cargados en la base principal. Verifica los enlaces.")
    st.stop()

# ==========================================
# 4. CLASE PDF (FPDF) Y LÓGICA DE DIBUJO
# ==========================================
class PDF(FPDF):
    def __init__(self, start_date, end_date):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.rango = f"{start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"
        
    def header(self):
        self.set_font("Arial", 'B', 16)
        self.set_text_color(31, 41, 55)
        self.cell(0, 8, "Reporte de Asistencia - Matriceria", border=0, ln=True, align='C')
        self.set_font("Arial", 'I', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, f"Periodo seleccionado: {self.rango}", border=0, ln=True, align='C')
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Pagina {self.page_no()}", 0, 0, "C")

def clean_text(text):
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def build_pdf(df_datos, s_date, e_date):
    pdf = PDF(s_date, e_date)
    
    meses_es = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
    dias_espanol = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
    
    delta = e_date - s_date
    all_dates = [s_date + timedelta(days=i) for i in range(delta.days + 1)]
    
    # Agrupar fechas por mes
    months_dict = defaultdict(list)
    for d in all_dates:
        months_dict[(d.year, d.month)].append(d)

    mask_period = (df_datos['FECHA'].dt.date >= s_date) & (df_datos['FECHA'].dt.date <= e_date)
    df_period = df_datos.loc[mask_period]
    all_matriceros = sorted(df_period['MATRICERO'].unique()) if not df_period.empty else []

    if not all_matriceros:
        pdf.add_page()
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, "No hay horas cargadas para el rango de fechas seleccionado.", ln=True, align='C')
        return pdf.output(dest='S').encode('latin-1')

    # === ITERAR POR CADA MES ===
    for (year, month), dates_in_month in months_dict.items():
        pdf.add_page()
        
        # Título del Mes
        pdf.set_font("Arial", 'B', 14)
        pdf.set_text_color(31, 73, 125)
        pdf.cell(0, 8, f"{meses_es[month]} {year}", ln=True, align='L')
        pdf.ln(2)

        # ---------------------------------------------
        # TABLA DE RESUMEN MENSUAL
        # ---------------------------------------------
        working_days = sum(1 for d in dates_in_month if d.weekday() < 5)
        estimated_hs = working_days * 8
        
        pdf.set_font("Arial", 'B', 8)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(196, 6, "RESUMEN", border=1, ln=True, align='C', fill=True)

        pdf.set_fill_color(31, 73, 125)
        pdf.cell(50, 6, "MATRICERO", border=1, align='C', fill=True)
        pdf.cell(26, 6, "AUSENCIAS", border=1, align='C', fill=True)
        pdf.cell(26, 6, "HS EXTRA", border=1, align='C', fill=True)
        pdf.cell(32, 6, "ESTIMADO DE HS", border=1, align='C', fill=True)
        pdf.cell(34, 6, "HS REPORTADAS", border=1, align='C', fill=True)
        pdf.set_fill_color(192, 0, 0)
        pdf.cell(28, 6, "DIFERENCIA", border=1, align='C', ln=True, fill=True)

        pdf.set_font("Arial", 'B', 8)
        for mat in all_matriceros:
            df_mat = df_datos[df_datos['MATRICERO'] == mat]
            
            hs_extra = 0
            ausencias = 0
            reported = 0
            
            # Cálculo de horas exactas día por día
            for d in dates_in_month:
                val_series = df_mat[df_mat['FECHA'].dt.date == d]['TOTAL_HORAS']
                val = val_series.sum() if not val_series.empty else 0
                reported += val
                
                if d.weekday() >= 5: # Sábado o Domingo
                    hs_extra += val
                else: # Lunes a Viernes
                    if val > 8:
                        hs_extra += (val - 8)
                    elif val < 8:
                        ausencias += (8 - val)

            diff = reported - estimated_hs

            # Dibujar Fila
            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(50, 6, clean_text(mat[:25]), border=1, fill=True)

            pdf.set_fill_color(255, 255, 255)
            
            # Ausencias (vacío si es 0)
            t_aus = str(int(ausencias)) if ausencias == int(ausencias) else f"{ausencias:.1f}"
            pdf.cell(26, 6, t_aus if ausencias > 0 else "", border=1, align='C', fill=True)
            
            # Extras (vacío si es 0)
            t_ext = str(int(hs_extra)) if hs_extra == int(hs_extra) else f"{hs_extra:.1f}"
            pdf.cell(26, 6, t_ext if hs_extra > 0 else "", border=1, align='C', fill=True)
            
            # Estimadas y Reportadas
            pdf.cell(32, 6, str(estimated_hs), border=1, align='C', fill=True)
            t_rep = str(int(reported)) if reported == int(reported) else f"{reported:.1f}"
            pdf.cell(34, 6, t_rep, border=1, align='C', fill=True)

            # Diferencia (Color)
            if diff < 0: pdf.set_text_color(192, 0, 0) # Rojo
            elif diff > 0: pdf.set_text_color(0, 128, 0) # Verde
            else: pdf.set_text_color(0, 0, 0)
            
            sign = "+" if diff > 0 else ""
            t_diff = f"{sign}{int(diff)}" if diff == int(diff) else f"{sign}{diff:.1f}"
            pdf.cell(28, 6, t_diff, border=1, align='C', ln=True, fill=True)

        pdf.ln(6) 

        # ---------------------------------------------
        # TABLAS SEMANALES (SIEMPRE LUN-DOM)
        # ---------------------------------------------
        weeks_dict = {}
        for d in dates_in_month:
            w = d.isocalendar()[1]
            if w not in weeks_dict:
                # Construir la semana completa (Lunes a Domingo)
                monday = d - timedelta(days=d.weekday())
                weeks_dict[w] = [monday + timedelta(days=i) for i in range(7)]

        w_mat = 50
        w_day = 30 
        total_w = w_mat + (7 * w_day) # 260mm (Entra perfecto en A4 Apaisado)

        for week_num, full_week in weeks_dict.items():
            if pdf.get_y() > 160: # Salto de página
                pdf.add_page()
                pdf.set_font("Arial", 'B', 10)
                pdf.set_text_color(31, 73, 125)
                pdf.cell(0, 8, f"{meses_es[month]} {year} (Continuación)", ln=True, align='L')
                pdf.ln(2)

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(0, 0, 0)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(total_w, 6, f"SEMANA {week_num}", border=1, ln=True, align='C', fill=True)

            # Cabecera doble (Día y Fecha)
            pdf.set_fill_color(31, 73, 125)
            x_start = pdf.get_x()
            pdf.cell(w_mat, 10, "MATRICERO", border=1, align='C', fill=True)
            x_days = pdf.get_x()
            
            # Fila Superior: Nombres
            for d in full_week:
                pdf.cell(w_day, 5, clean_text(dias_espanol[d.weekday()]), border='LTR', align='C', fill=True)
            pdf.ln()
            
            # Fila Inferior: Fechas
            pdf.set_x(x_days) 
            for d in full_week:
                pdf.cell(w_day, 5, d.strftime('%d/%m/%Y'), border='LBR', align='C', fill=True)
            pdf.ln()

            # Horas Semanales
            pdf.set_font("Arial", 'B', 9)
            for mat in all_matriceros:
                pdf.set_fill_color(240, 240, 240)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(w_mat, 8, clean_text(mat[:25]), border=1, fill=True)
                
                df_mat = df_datos[df_datos['MATRICERO'] == mat]

                for d in full_week:
                    val_series = df_mat[df_mat['FECHA'].dt.date == d]['TOTAL_HORAS']
                    val = val_series.sum() if not val_series.empty else 0

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

                    txt_val = str(int(val)) if val == int(val) else f"{val:.1f}"
                    pdf.cell(w_day, 8, txt_val, border=1, align='C', fill=True)
                pdf.ln()
            pdf.ln(5)

    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_pdf.name)
    with open(temp_pdf.name, "rb") as f:
        pdf_bytes = f.read()
    os.remove(temp_pdf.name)
    return pdf_bytes

# ==========================================
# 5. BOTÓN DE DESCARGA
# ==========================================
st.write("") 
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    if st.button("🖨️ Procesar y Generar PDF", type="primary", use_container_width=True):
        with st.spinner("Construyendo documento PDF, agrupando por meses..."):
            try:
                pdf_data = build_pdf(df_raw, start_date, end_date)
                st.success("¡PDF generado correctamente!")
                st.download_button(
                    label="📥 Clic aquí para descargar PDF", 
                    data=pdf_data, 
                    file_name=f"Reporte_Matriceria_{start_date.strftime('%d%m%Y')}_a_{end_date.strftime('%d%m%Y')}.pdf", 
                    mime="application/pdf", 
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error generando PDF: {e}")
