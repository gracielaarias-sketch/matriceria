import streamlit as st
import pandas as pd
import numpy as np
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
st.write("<p style='text-align: center;'>Generador de PDF con calendarios, resumen de horas extra, estado de matrices y asistencia.</p>", unsafe_allow_html=True)
st.divider()

# ==========================================
# 2. CARGA Y EXTRACCIÓN AVANZADA DE DATOS
# ==========================================
SHEETS_CONFIG = [
    {"url": "https://docs.google.com/spreadsheets/d/1sccnOPuosjMSepp0FZoEGteYArIIhB2fGH7TeSRW_7E/export?format=csv", "skiprows": 2, "tipo": "asistencia"},
    {"url": "https://docs.google.com/spreadsheets/d/1bL_tnlSXGO_t9tKnhIHT5pZ3DAxivbiq2tFETVxBaVI/export?format=csv", "skiprows": 2, "tipo": "correctivo"},
    {"url": "https://docs.google.com/spreadsheets/d/1VqsPNhAlT1kPCltbMWsbkZNFBKdwZRFM5RAmnRV0v3c/export?format=csv", "skiprows": 0, "tipo": "preventivo"},
    {"url": "https://docs.google.com/spreadsheets/d/1UNSCxrTy9TUdggNt0ta0TcsEvT3idaRGWcXE_t8J40I/export?format=csv", "skiprows": 0, "tipo": "asistencia"},
    {"url": "https://docs.google.com/spreadsheets/d/1A-0mngZdgvZGbqzWjA_awhrwfvca0K4aGqp5NBAoFAY/export?format=csv", "skiprows": 0, "tipo": "correctivo"},
    {"url": "https://docs.google.com/spreadsheets/d/1MptnOuRfyOAr1EgzNJVygTtNziOSdzXJn-PZDX0pNzc/export?format=csv", "skiprows": 0, "tipo": "preventivo"},
]

@st.cache_data(ttl=300)
def load_data():
    cal_data = []  # Para el calendario
    mant_data = [] # Para mantenimiento de matrices
    act_data = []  # Para tareas de asistencia
    
    for config in SHEETS_CONFIG:
        try:
            df = pd.read_csv(config["url"], skiprows=config["skiprows"])
            df.columns = df.columns.astype(str).str.upper().str.strip()
            df = df.loc[:, ~df.columns.duplicated()].copy()
            
            col_fecha = next((c for c in df.columns if 'FECHA' in c), None)
            col_mat = next((c for c in df.columns if 'MATRICERO' in c), None)
            
            # Identificar columnas de horas
            cols_horas = [c for c in df.columns if ('HORAS' in c or 'HS' in c.split() or 'HS' in c) and 'TOTAL' not in c]
            if not cols_horas:
                cols_horas = [c for c in df.columns if 'TOTAL' in c and ('HS' in c or 'HORAS' in c)]
            
            if col_fecha and cols_horas:
                horas_sum = pd.to_numeric(df[cols_horas[0]], errors='coerce').fillna(0)
                if len(cols_horas) > 1:
                    for col in cols_horas[1:]:
                        horas_sum += pd.to_numeric(df[col], errors='coerce').fillna(0)
                
                # --- 1. DATA PARA CALENDARIO ---
                if col_mat:
                    df_cal = pd.DataFrame({'FECHA': df[col_fecha], 'MATRICERO': df[col_mat], 'TOTAL_HORAS': horas_sum})
                    cal_data.append(df_cal)
                
                # --- 2. DATA PARA MANTENIMIENTO ---
                if config["tipo"] in ["preventivo", "correctivo"]:
                    # Buscar columna de pieza/matriz
                    col_pieza = next((c for c in df.columns if c in ['NUMERO DE PIEZA', 'PIEZA', 'MATRIZ']), None)
                    if not col_pieza: 
                        col_pieza = next((c for c in df.columns if 'PIEZA' in c), None)
                    
                    # Buscar columna de terminado
                    col_terminado = next((c for c in df.columns if 'TERMINADO' in c or 'TERMINO' in c), None)
                    
                    if col_pieza and col_terminado:
                        df_m = pd.DataFrame({
                            'FECHA': df[col_fecha],
                            'MATRIZ': df[col_pieza].astype(str),
                            'TIPO': config["tipo"].upper(),
                            'HORAS': horas_sum,
                            'TERMINADO': df[col_terminado].astype(str).str.upper().str.strip()
                        })
                        mant_data.append(df_m)
                        
                # --- 3. DATA PARA ASISTENCIA ---
                if config["tipo"] == "asistencia":
                    cols_tareas = [c for c in df.columns if 'TAREA' in c and 'Desea' not in c and 'HS' not in c and 'HORAS' not in c]
                    if cols_tareas:
                        # Extraemos la primer tarea reportada o combinamos
                        df_act = pd.DataFrame({
                            'FECHA': df[col_fecha],
                            'TAREA': df[cols_tareas[0]].astype(str).str.strip(),
                            'HORAS': horas_sum
                        })
                        act_data.append(df_act)

        except Exception:
            pass
            
    # Unificar y limpiar
    df_calendario = pd.concat(cal_data, ignore_index=True) if cal_data else pd.DataFrame()
    if not df_calendario.empty:
        df_calendario['FECHA'] = pd.to_datetime(df_calendario['FECHA'], errors='coerce', dayfirst=True)
        df_calendario['MATRICERO'] = df_calendario['MATRICERO'].astype(str).str.strip().str.upper()
        df_calendario = df_calendario.dropna(subset=['FECHA'])
        df_calendario = df_calendario.groupby(['FECHA', 'MATRICERO'], as_index=False)['TOTAL_HORAS'].sum()

    df_mantenimiento = pd.concat(mant_data, ignore_index=True) if mant_data else pd.DataFrame()
    if not df_mantenimiento.empty:
        df_mantenimiento['FECHA'] = pd.to_datetime(df_mantenimiento['FECHA'], errors='coerce', dayfirst=True)
        df_mantenimiento = df_mantenimiento.dropna(subset=['FECHA'])
        # Filtrar basuras
        df_mantenimiento = df_mantenimiento[~df_mantenimiento['MATRIZ'].isin(['nan', 'NaN', 'None', ''])]

    df_actividades = pd.concat(act_data, ignore_index=True) if act_data else pd.DataFrame()
    if not df_actividades.empty:
        df_actividades['FECHA'] = pd.to_datetime(df_actividades['FECHA'], errors='coerce', dayfirst=True)
        df_actividades = df_actividades.dropna(subset=['FECHA'])
        df_actividades = df_actividades[~df_actividades['TAREA'].isin(['nan', 'NaN', 'None', ''])]

    return df_calendario, df_mantenimiento, df_actividades

df_raw, df_mant_raw, df_act_raw = load_data()

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
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        self.set_font("Arial", 'B', 16)
        self.set_text_color(31, 41, 55)
        self.cell(0, 8, "Reporte Gerencial - Area de Matriceria", border=0, ln=True, align='C')
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

def build_pdf(df_datos, df_mant, df_act, s_date, e_date):
    pdf = PDF(s_date, e_date)
    meses_es = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
    dias_espanol = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
    
    delta = e_date - s_date
    all_dates = [s_date + timedelta(days=i) for i in range(delta.days + 1)]
    months_dict = defaultdict(list)
    for d in all_dates: months_dict[(d.year, d.month)].append(d)

    mask_period = (df_datos['FECHA'].dt.date >= s_date) & (df_datos['FECHA'].dt.date <= e_date)
    df_period = df_datos.loc[mask_period]
    all_matriceros = sorted(df_period['MATRICERO'].unique()) if not df_period.empty else []

    if not all_matriceros:
        pdf.add_page()
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, "No hay horas cargadas para el rango de fechas seleccionado.", ln=True, align='C')
        return pdf.output(dest='S').encode('latin-1')

    # =========================================================
    # PARTE 1: RESUMEN Y CALENDARIOS POR MES
    # =========================================================
    for (year, month), dates_in_month in months_dict.items():
        pdf.add_page()
        
        # --- HOJA 1: RESUMEN MENSUAL ---
        pdf.set_font("Arial", 'B', 14)
        pdf.set_text_color(31, 73, 125)
        pdf.cell(0, 8, f"RESUMEN MENSUAL: {meses_es[month]} {year}", ln=True, align='L')
        pdf.ln(2)

        working_days = sum(1 for d in dates_in_month if d.weekday() < 5)
        estimated_hs = working_days * 8
        
        pdf.set_font("Arial", 'B', 8)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(196, 6, "RESUMEN DE ASISTENCIA Y HORAS EXTRAS", border=1, ln=True, align='C', fill=True)

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
            
            for d in dates_in_month:
                val_series = df_mat[df_mat['FECHA'].dt.date == d]['TOTAL_HORAS']
                val = val_series.sum() if not val_series.empty else 0
                reported += val
                
                if d.weekday() >= 5: # Fines de semana = extra puro
                    hs_extra += val
                else:
                    if val > 8: hs_extra += (val - 8)
                    elif val < 8: ausencias += (8 - val)

            diff = reported - estimated_hs

            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(50, 6, clean_text(mat[:25]), border=1, fill=True)
            pdf.set_fill_color(255, 255, 255)
            
            t_aus = str(int(ausencias)) if ausencias == int(ausencias) else f"{ausencias:.1f}"
            pdf.cell(26, 6, t_aus if ausencias > 0 else "", border=1, align='C', fill=True)
            
            t_ext = str(int(hs_extra)) if hs_extra == int(hs_extra) else f"{hs_extra:.1f}"
            pdf.cell(26, 6, t_ext if hs_extra > 0 else "", border=1, align='C', fill=True)
            
            pdf.cell(32, 6, str(estimated_hs), border=1, align='C', fill=True)
            t_rep = str(int(reported)) if reported == int(reported) else f"{reported:.1f}"
            pdf.cell(34, 6, t_rep, border=1, align='C', fill=True)

            if diff < 0: pdf.set_text_color(192, 0, 0) 
            elif diff > 0: pdf.set_text_color(0, 128, 0)
            else: pdf.set_text_color(0, 0, 0)
            
            sign = "+" if diff > 0 else ""
            t_diff = f"{sign}{int(diff)}" if diff == int(diff) else f"{sign}{diff:.1f}"
            pdf.cell(28, 6, t_diff, border=1, align='C', ln=True, fill=True)

        # --- HOJA 2: CALENDARIOS ---
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.set_text_color(31, 73, 125)
        pdf.cell(0, 8, f"CALENDARIO SEMANAL: {meses_es[month]} {year}", ln=True, align='L')
        pdf.ln(2)

        weeks_dict = {}
        for d in dates_in_month:
            w = d.isocalendar()[1]
            if w not in weeks_dict:
                monday = d - timedelta(days=d.weekday())
                weeks_dict[w] = [monday + timedelta(days=i) for i in range(7)]

        w_mat = 50
        w_day = 30 
        total_w = w_mat + (7 * w_day)
        required_height = 6 + 10 + (len(all_matriceros) * 8) + 5

        for week_num, full_week in weeks_dict.items():
            if pdf.get_y() + required_height > 185: 
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.set_text_color(31, 73, 125)
                pdf.cell(0, 8, f"CALENDARIO SEMANAL: {meses_es[month]} {year} (Continuación)", ln=True, align='L')
                pdf.ln(2)

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(0, 0, 0)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(total_w, 6, f"SEMANA {week_num}", border=1, ln=True, align='C', fill=True)

            pdf.set_fill_color(31, 73, 125)
            x_start = pdf.get_x()
            pdf.cell(w_mat, 10, "MATRICERO", border=1, align='C', fill=True)
            x_days = pdf.get_x()
            
            for d in full_week:
                pdf.cell(w_day, 5, clean_text(dias_espanol[d.weekday()]), border='LTR', align='C', fill=True)
            pdf.ln()
            
            pdf.set_x(x_days) 
            for d in full_week:
                pdf.cell(w_day, 5, d.strftime('%d/%m/%Y'), border='LBR', align='C', fill=True)
            pdf.ln()

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
                        pdf.set_fill_color(127, 127, 127) 
                        pdf.set_text_color(255, 255, 255)
                    elif val == 8:
                        pdf.set_fill_color(198, 239, 206) 
                        pdf.set_text_color(0, 97, 0)
                    elif val > 8:
                        pdf.set_fill_color(255, 199, 206) 
                        pdf.set_text_color(156, 0, 6)
                    else:
                        pdf.set_fill_color(255, 235, 156) 
                        pdf.set_text_color(156, 101, 0)

                    txt_val = str(int(val)) if val == int(val) else f"{val:.1f}"
                    pdf.cell(w_day, 8, txt_val, border=1, align='C', fill=True)
                pdf.ln()
            pdf.ln(5)

    # =========================================================
    # PARTE 2: ANEXOS (MATRICES Y ACTIVIDADES)
    # =========================================================
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 1: ESTADO Y MANTENIMIENTO DE MATRICES", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Muestra las horas totales acumuladas en el periodo seleccionado y su ultimo estado reportado.", ln=True)
    pdf.ln(3)

    if not df_mant.empty:
        mask_m = (df_mant['FECHA'].dt.date >= s_date) & (df_mant['FECHA'].dt.date <= e_date)
        df_m_period = df_mant.loc[mask_m]

        if not df_m_period.empty:
            # Agrupar para sumar horas y obtener el último estado
            df_m_period = df_m_period.sort_values('FECHA')
            resumen_mant = df_m_period.groupby(['MATRIZ', 'TIPO']).agg(
                HS_ACUMULADAS=('HORAS', 'sum'),
                ULTIMO_ESTADO=('TERMINADO', 'last')
            ).reset_index().sort_values('HS_ACUMULADAS', ascending=False)

            # Dibujar Tabla Mantenimiento
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(0, 0, 0)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(100, 7, "MATRIZ / PIEZA", border=1, fill=True)
            pdf.cell(35, 7, "TIPO", border=1, align='C', fill=True)
            pdf.cell(30, 7, "HS ACUMULADAS", border=1, align='C', fill=True)
            pdf.cell(40, 7, "ESTADO FINAL", border=1, align='C', ln=True, fill=True)

            pdf.set_font("Arial", '', 9)
            for _, row in resumen_mant.iterrows():
                pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(0, 0, 0)
                
                pdf.cell(100, 7, clean_text(str(row['MATRIZ'])[:55]), border=1)
                
                # Tipo
                pdf.cell(35, 7, clean_text(row['TIPO']), border=1, align='C')
                
                # Horas
                hs_txt = str(int(row['HS_ACUMULADAS'])) if row['HS_ACUMULADAS'] == int(row['HS_ACUMULADAS']) else f"{row['HS_ACUMULADAS']:.1f}"
                pdf.cell(30, 7, hs_txt, border=1, align='C')
                
                # Color Estado
                estado = str(row['ULTIMO_ESTADO']).upper()
                if "SI" in estado or "SÍ" in estado:
                    pdf.set_text_color(0, 128, 0)
                    estado_print = "TERMINADO"
                elif "NO" in estado:
                    pdf.set_text_color(192, 0, 0)
                    estado_print = "PENDIENTE"
                else:
                    estado_print = estado[:15]

                pdf.cell(40, 7, clean_text(estado_print), border=1, align='C', ln=True)
        else:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "No hubo mantenimiento de matrices en este periodo.", ln=True)
    
    pdf.ln(10)

    # --- ANEXO 2: ACTIVIDADES DE ASISTENCIA ---
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 2: ACTIVIDADES DE ASISTENCIA", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Resumen de horas insumidas por tarea general (fuera de mantenimiento de matrices).", ln=True)
    pdf.ln(3)

    if not df_act.empty:
        mask_a = (df_act['FECHA'].dt.date >= s_date) & (df_act['FECHA'].dt.date <= e_date)
        df_a_period = df_act.loc[mask_a]

        if not df_a_period.empty:
            resumen_act = df_a_period.groupby('TAREA')['HORAS'].sum().reset_index().sort_values('HORAS', ascending=False)
            
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(31, 73, 125)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(140, 7, "ACTIVIDAD / TAREA", border=1, fill=True)
            pdf.cell(30, 7, "HS TOTALES", border=1, align='C', ln=True, fill=True)

            pdf.set_font("Arial", '', 9)
            pdf.set_text_color(0, 0, 0)
            for _, row in resumen_act.iterrows():
                pdf.cell(140, 7, clean_text(str(row['TAREA'])[:80]), border=1)
                hs_txt = str(int(row['HORAS'])) if row['HORAS'] == int(row['HORAS']) else f"{row['HORAS']:.1f}"
                pdf.cell(30, 7, hs_txt, border=1, align='C', ln=True)
        else:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "No se registraron tareas de asistencia aisladas en este periodo.", ln=True)
    else:
        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 7, "No se registraron tareas de asistencia en la base de datos.", ln=True)

    # Generar Bytes
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
    if st.button("🖨️ Procesar y Generar PDF Completo", type="primary", use_container_width=True):
        with st.spinner("Construyendo documento PDF con Anexos de Mantenimiento..."):
            try:
                pdf_data = build_pdf(df_raw, df_mant_raw, df_act_raw, start_date, end_date)
                st.success("¡PDF generado correctamente con todos sus anexos!")
                st.download_button(
                    label="📥 Descargar Reporte Final", 
                    data=pdf_data, 
                    file_name=f"Reporte_Gerencial_Matriceria_{start_date.strftime('%d%m%Y')}_a_{end_date.strftime('%d%m%Y')}.pdf", 
                    mime="application/pdf", 
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error generando PDF: {e}")
