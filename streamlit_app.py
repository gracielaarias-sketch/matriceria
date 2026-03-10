import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
import tempfile
import os
from collections import defaultdict
from fpdf import FPDF

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Reporte Matricería", layout="centered", page_icon="📅")

st.markdown("""
<style>
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-style">📅 Reporte Gerencial de Matricería</div>', unsafe_allow_html=True)
st.write("<p style='text-align: center;'>Extracción Posicional Estricta desde Google Forms.</p>", unsafe_allow_html=True)
st.divider()

# ==========================================
# 2. ENLACES Y CONSTANTES
# ==========================================
SHEETS_CONFIG = [
    # ASISTENCIA
    {"url": "https://docs.google.com/spreadsheets/d/1sccnOPuosjMSepp0FZoEGteYArIIhB2fGH7TeSRW_7E/export?format=csv&gid=1128388185", "skiprows": 2, "tipo": "asistencia"}, # Fumiscor
    {"url": "https://docs.google.com/spreadsheets/d/1UNSCxrTy9TUdggNt0ta0TcsEvT3idaRGWcXE_t8J40I/export?format=csv&gid=979884533", "skiprows": 0, "tipo": "asistencia"}, # Famma
    # CORRECTIVOS
    {"url": "https://docs.google.com/spreadsheets/d/1bL_tnlSXGO_t9tKnhIHT5pZ3DAxivbiq2tFETVxBaVI/export?format=csv&gid=1507213893", "skiprows": 2, "tipo": "correctivo"}, # Fumiscor
    {"url": "https://docs.google.com/spreadsheets/d/1A-0mngZdgvZGbqzWjA_awhrwfvca0K4aGqp5NBAoFAY/export?format=csv&gid=238711679", "skiprows": 0, "tipo": "correctivo"}, # Famma
    # PREVENTIVOS
    {"url": "https://docs.google.com/spreadsheets/d/1VqsPNhAlT1kPCltbMWsbkZNFBKdwZRFM5RAmnRV0v3c/export?format=csv&gid=1603203990", "skiprows": 2, "tipo": "preventivo"}, # Fumiscor
    {"url": "https://docs.google.com/spreadsheets/d/1MptnOuRfyOAr1EgzNJVygTtNziOSdzXJn-PZDX0pNzc/export?format=csv&gid=324842888", "skiprows": 0, "tipo": "preventivo"} # Famma
]

# Las columnas exactas del formulario donde el matricero elige la pieza
VALID_PIEZA_COLS = [
    'PIEZAS RENAULT', 'PIEZAS FAURECIA', 'PIEZAS FIAT', 'PIEZAS DENSO', 
    'PIEZAS PEUGEOT', 'PIEZA FIAT', 'PIEZA NISSAN', 'PIEZA RENAULT', 'NUMERO DE PIEZA'
]

def clean_matricero(name):
    """Estandariza el nombre del matricero usando su Legajo."""
    name = str(name).upper().strip()
    name = re.sub(r'\s+', ' ', name)
    match = re.match(r'^(\d+)\s*[-_]?\s*(.*)', name)
    if match: return f"{match.group(1)} - {match.group(2).strip()}"
    return name

# ==========================================
# 3. MOTOR DE EXTRACCIÓN POSICIONAL
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    cal_data, mant_data, act_data = [], [], []
    
    for config in SHEETS_CONFIG:
        try:
            df = pd.read_csv(config["url"], skiprows=config["skiprows"])
            
            # Limpieza básica de encabezados
            df.columns = df.columns.astype(str).str.upper().str.strip().str.replace(r'\s+', ' ', regex=True)
            
            # Evitar error de Pandas renombrando duplicados (Pandas agregará .1, .2)
            cols = pd.Series(df.columns)
            for dup in cols[cols.duplicated()].unique():
                cols[cols[cols == dup].index.values.tolist()] = [f"{dup}.{i}" if i != 0 else dup for i in range(sum(cols == dup))]
            df.columns = cols
            df_cols = df.columns.tolist()

            # Buscar índice exacto de Fecha y Matricero
            idx_fecha = next((i for i, c in enumerate(df_cols) if c == 'FECHA'), None)
            idx_mat = next((i for i, c in enumerate(df_cols) if c == 'MATRICERO'), None)
            
            if idx_fecha is None or idx_mat is None: 
                continue

            # --- LECTURA FILA POR FILA POR POSICIÓN ---
            for _, row in df.iterrows():
                fecha = str(row.iloc[idx_fecha]).strip()
                mat = str(row.iloc[idx_mat]).strip()
                
                # Ignorar si no hay datos base
                if fecha in ['NAN', 'NONE', ''] or mat in ['NAN', 'NONE', '']: 
                    continue
                mat = clean_matricero(mat)

                # ====================================================
                # PREVENTIVO / CORRECTIVO
                # ====================================================
                if config['tipo'] in ['preventivo', 'correctivo']:
                    # 1. Extraer Horas
                    idx_hs = next((i for i, c in enumerate(df_cols) if 'HS REALIZADAS' in c and 'TAREA' not in c), None)
                    horas = 0.0
                    if idx_hs is not None and pd.notna(row.iloc[idx_hs]):
                        try:
                            val = float(str(row.iloc[idx_hs]).replace(',', '.'))
                            if val > 0: horas = val
                        except: pass
                    
                    if horas <= 0: continue

                    # 2. Extraer Estado (SÍ/NO)
                    estado = 'NO'
                    idx_term = next((i for i, c in enumerate(df_cols) if 'TERMINADO' in c or 'TERMINO' in c), None)
                    if idx_term is not None and pd.notna(row.iloc[idx_term]):
                        if 'SI' in str(row.iloc[idx_term]).upper() or 'SÍ' in str(row.iloc[idx_term]).upper(): 
                            estado = 'SI'

                    # 3. Barrido Posicional de Piezas y Operación
                    piezas_found = []
                    for i, col_name in enumerate(df_cols):
                        base_col = col_name.split('.')[0].strip() # Quitar el ".1" de Pandas
                        
                        if base_col in VALID_PIEZA_COLS:
                            val_pieza = str(row.iloc[i]).strip()
                            
                            # Si llenaron esta pieza, la operación es SIEMPRE la columna que le sigue (i+1)
                            if val_pieza and val_pieza.upper() not in ['NAN', 'NONE', '-']:
                                op_val = str(row.iloc[i+1]).strip() if (i+1) < len(df_cols) else '-'
                                
                                piezas_found.append({
                                    'matriz': val_pieza, 
                                    'op': op_val
                                })

                    # 4. Guardar Datos
                    if piezas_found:
                        # Si llenaron varias piezas (ej: 2) en el mismo form, se dividen las horas
                        hs_per_piece = horas / len(piezas_found)
                        for p in piezas_found:
                            mant_data.append({
                                'FECHA': fecha, 'MATRICERO': mat, 'MATRIZ': p['matriz'], 
                                'OPERACION': p['op'], 'TIPO': config['tipo'].upper(),
                                'HORAS': hs_per_piece, 'TERMINADO': estado
                            })
                        cal_data.append({'FECHA': fecha, 'MATRICERO': mat, 'TOTAL_HORAS': horas})

                # ====================================================
                # ASISTENCIA (MULTITAREAS)
                # ====================================================
                elif config['tipo'] == 'asistencia':
                    horas_asist_totales = 0.0
                    
                    # Barrer las columnas buscando las tareas.
                    # En Google Forms, la columna de Horas siempre está a la derecha de la de Tarea.
                    for i, col_name in enumerate(df_cols):
                        # Detecta si la columna es "1 - Tarea 1", "1 - Tarea 2", etc.
                        if 'TAREA' in col_name and 'HS' not in col_name and 'OBS' not in col_name and 'DESEA' not in col_name and re.search(r'\d', col_name):
                            t_val = str(row.iloc[i]).strip()
                            
                            # Si completaron la tarea, leer las horas en la celda de la derecha (i+1)
                            if t_val and t_val.upper() not in ['NAN', 'NONE', '-']:
                                try:
                                    h_val = float(str(row.iloc[i+1]).replace(',', '.'))
                                    if h_val > 0:
                                        act_data.append({'FECHA': fecha, 'MATRICERO': mat, 'TAREA': t_val, 'HORAS': h_val})
                                        horas_asist_totales += h_val
                                except: pass

                    if horas_asist_totales > 0:
                        cal_data.append({'FECHA': fecha, 'MATRICERO': mat, 'TOTAL_HORAS': horas_asist_totales})

        except Exception as e:
            print(f"Error procesando {config['url']}: {e}")
            pass
            
    # ==========================
    # AGRUPACIÓN DE DATOS
    # ==========================
    df_calendario = pd.DataFrame(cal_data)
    if not df_calendario.empty:
        df_calendario['FECHA'] = pd.to_datetime(df_calendario['FECHA'], errors='coerce', dayfirst=True)
        df_calendario = df_calendario.dropna(subset=['FECHA'])
        df_calendario = df_calendario.groupby(['FECHA', 'MATRICERO'], as_index=False)['TOTAL_HORAS'].sum()

    df_mantenimiento = pd.DataFrame(mant_data)
    if not df_mantenimiento.empty:
        df_mantenimiento['FECHA'] = pd.to_datetime(df_mantenimiento['FECHA'], errors='coerce', dayfirst=True)
        df_mantenimiento = df_mantenimiento.dropna(subset=['FECHA'])

    df_actividades = pd.DataFrame(act_data)
    if not df_actividades.empty:
        df_actividades['FECHA'] = pd.to_datetime(df_actividades['FECHA'], errors='coerce', dayfirst=True)
        df_actividades = df_actividades.dropna(subset=['FECHA'])

    return df_calendario, df_mantenimiento, df_actividades

df_raw, df_mant_raw, df_act_raw = load_data()

# ==========================================
# 4. INTERFAZ Y FILTROS DE FECHA
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

# ==========================================
# 5. CLASE PDF (FPDF) Y LÓGICA DE DIBUJO
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
        pdf.cell(0, 10, "No hay horas cargadas para el rango seleccionado.", ln=True, align='C')
        return pdf.output(dest='S').encode('latin-1')

    # =========================================================
    # HOJA 1: RESUMEN MENSUAL Y CALENDARIOS
    # =========================================================
    for (year, month), dates_in_month in months_dict.items():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.set_text_color(31, 73, 125)
        pdf.cell(0, 8, f"RESUMEN MENSUAL DE ASISTENCIA: {meses_es[month]} {year}", ln=True, align='L')
        pdf.ln(2)

        working_days = sum(1 for d in dates_in_month if d.weekday() < 5)
        estimated_hs = working_days * 8
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(196, 6, "TABLA GENERAL DE HORAS POR MATRICERO", border=1, ln=True, align='C', fill=True)

        pdf.set_fill_color(31, 73, 125)
        pdf.cell(70, 6, "MATRICERO", border=1, align='C', fill=True)
        pdf.cell(40, 6, "ESTIMADO DE HS", border=1, align='C', fill=True)
        pdf.cell(40, 6, "HS CARGADAS", border=1, align='C', fill=True)
        pdf.set_fill_color(192, 0, 0)
        pdf.cell(46, 6, "FALTANTE / DIFERENCIA", border=1, align='C', ln=True, fill=True)

        pdf.set_font("Arial", 'B', 9)
        for mat in all_matriceros:
            df_mat = df_datos[df_datos['MATRICERO'] == mat]
            reported = sum(df_mat[df_mat['FECHA'].dt.date == d]['TOTAL_HORAS'].sum() for d in dates_in_month)
            diff = reported - estimated_hs

            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(70, 6, clean_text(mat[:35]), border=1, fill=True)
            
            pdf.set_fill_color(255, 255, 255)
            pdf.cell(40, 6, str(estimated_hs), border=1, align='C', fill=True)
            
            t_rep = str(int(reported)) if reported == int(reported) else f"{reported:.1f}"
            pdf.cell(40, 6, t_rep, border=1, align='C', fill=True)

            if diff < 0: pdf.set_text_color(192, 0, 0) 
            elif diff > 0: pdf.set_text_color(0, 128, 0)
            else: pdf.set_text_color(0, 0, 0)
            
            sign = "+" if diff > 0 else ""
            t_diff = f"{sign}{int(diff)}" if diff == int(diff) else f"{sign}{diff:.1f}"
            pdf.cell(46, 6, t_diff, border=1, align='C', ln=True, fill=True)

        # CALENDARIOS SEMANALES
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

        w_mat, w_day = 60, 28 
        total_w = w_mat + (7 * w_day)
        req_h = 16 + (len(all_matriceros) * 8) + 5

        for week_num, full_week in weeks_dict.items():
            if pdf.get_y() + req_h > 185: 
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.set_text_color(31, 73, 125)
                pdf.cell(0, 8, f"CALENDARIO: {meses_es[month]} {year} (Cont.)", ln=True, align='L')
                pdf.ln(2)

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(0, 0, 0)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(total_w, 6, f"SEMANA {week_num}", border=1, ln=True, align='C', fill=True)

            pdf.set_fill_color(31, 73, 125)
            x_s = pdf.get_x()
            pdf.cell(w_mat, 10, "MATRICERO", border=1, align='C', fill=True)
            x_d = pdf.get_x()
            
            for d in full_week: pdf.cell(w_day, 5, clean_text(dias_espanol[d.weekday()]), border='LTR', align='C', fill=True)
            pdf.ln()
            pdf.set_x(x_d) 
            for d in full_week: pdf.cell(w_day, 5, d.strftime('%d/%m/%Y'), border='LBR', align='C', fill=True)
            pdf.ln()

            pdf.set_font("Arial", 'B', 9)
            for mat in all_matriceros:
                pdf.set_fill_color(240, 240, 240)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(w_mat, 8, clean_text(mat[:30]), border=1, fill=True)
                
                df_mat = df_datos[df_datos['MATRICERO'] == mat]
                for d in full_week:
                    val = df_mat[df_mat['FECHA'].dt.date == d]['TOTAL_HORAS'].sum()
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

                    t_val = str(int(val)) if val == int(val) else f"{val:.1f}"
                    pdf.cell(w_day, 8, t_val, border=1, align='C', fill=True)
                pdf.ln()
            pdf.ln(5)

    # =========================================================
    # HOJA 2: MANTENIMIENTO PREVENTIVO Y CORRECTIVO
    # =========================================================
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 1: ESTADO DE MATRICES (MANTENIMIENTO)", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Muestra horas invertidas y estado final en el periodo seleccionado.", ln=True)
    pdf.ln(3)

    def draw_mant_table(df_sub, title):
        pdf.set_font("Arial", 'B', 12)
        pdf.set_text_color(31, 73, 125)
        pdf.cell(0, 8, f"MANTENIMIENTO {title}", ln=True, align='L')
        
        if df_sub.empty:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, f"No se registraron mantenimientos {title.lower()}s en este periodo.", ln=True)
            pdf.ln(5)
            return

        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        
        pdf.cell(100, 7, "MATRIZ / PIEZA", border=1, fill=True)
        pdf.cell(35, 7, "OPERACIÓN", border=1, align='C', fill=True)
        pdf.cell(35, 7, "HS INSUMIDAS", border=1, align='C', fill=True)
        pdf.cell(40, 7, "ESTADO AL CIERRE", border=1, align='C', ln=True, fill=True)

        pdf.set_font("Arial", '', 9)
        total_hs = 0

        for _, row in df_sub.iterrows():
            matriz = str(row['MATRIZ'])
            operacion = str(row['OPERACION'])
            estado = str(row['ULTIMO_ESTADO']).upper()
            total_hs += row['HS_ACUMULADAS']
            
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(100, 7, clean_text(matriz[:55]), border=1)
            pdf.cell(35, 7, clean_text(operacion[:20]), border=1, align='C')
            
            hs_txt = str(int(row['HS_ACUMULADAS'])) if row['HS_ACUMULADAS'] == int(row['HS_ACUMULADAS']) else f"{row['HS_ACUMULADAS']:.1f}"
            pdf.cell(35, 7, hs_txt, border=1, align='C')
            
            if "SI" in estado or "SÍ" in estado:
                pdf.set_text_color(0, 128, 0)
                estado_print = "TERMINADO"
            else:
                pdf.set_text_color(192, 0, 0)
                estado_print = "PENDIENTE"
            
            pdf.cell(40, 7, clean_text(estado_print), border=1, align='C', ln=True)

        # FILA TOTALES
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(220, 220, 220)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(135, 7, f"TOTAL HORAS {title}", border=1, align='R', fill=True)
        
        t_hs_txt = str(int(total_hs)) if total_hs == int(total_hs) else f"{total_hs:.1f}"
        pdf.cell(35, 7, t_hs_txt, border=1, align='C', fill=True)
        pdf.cell(40, 7, "", border=1, align='C', ln=True, fill=True)
        pdf.ln(5)

    if not df_mant.empty:
        df_m_period = df_mant[(df_mant['FECHA'].dt.date >= s_date) & (df_mant['FECHA'].dt.date <= e_date)].copy()
        if not df_m_period.empty:
            df_m_period = df_m_period.sort_values('FECHA')
            resumen_mant = df_m_period.groupby(['MATRIZ', 'OPERACION', 'TIPO']).agg(
                HS_ACUMULADAS=('HORAS', 'sum'),
                ULTIMO_ESTADO=('TERMINADO', 'last')
            ).reset_index()

            df_prev = resumen_mant[resumen_mant['TIPO'] == 'PREVENTIVO'].sort_values('HS_ACUMULADAS', ascending=False)
            df_corr = resumen_mant[resumen_mant['TIPO'] == 'CORRECTIVO'].sort_values('HS_ACUMULADAS', ascending=False)

            draw_mant_table(df_prev, "PREVENTIVO")
            draw_mant_table(df_corr, "CORRECTIVO")
        else:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "No se registraron mantenimientos en este periodo.", ln=True)
    else:
        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 7, "No hubo mantenimiento en este periodo.", ln=True)

    pdf.ln(5)

    # =========================================================
    # HOJA 3: ASISTENCIA
    # =========================================================
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 2: ACTIVIDADES DE ASISTENCIA", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Resumen de horas insumidas por tarea general extraídas del formulario.", ln=True)
    pdf.ln(3)

    if not df_act.empty:
        df_a_period = df_act[(df_act['FECHA'].dt.date >= s_date) & (df_act['FECHA'].dt.date <= e_date)]
        if not df_a_period.empty:
            resumen_act = df_a_period.groupby('TAREA')['HORAS'].sum().reset_index().sort_values('HORAS', ascending=False)
            
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(31, 73, 125)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(140, 7, "ACTIVIDAD / TAREA", border=1, fill=True)
            pdf.cell(35, 7, "HS TOTALES", border=1, align='C', ln=True, fill=True)

            pdf.set_font("Arial", '', 9)
            pdf.set_text_color(0, 0, 0)
            total_hs_act = 0

            for _, row in resumen_act.iterrows():
                total_hs_act += row['HORAS']
                pdf.cell(140, 7, clean_text(str(row['TAREA'])[:80]), border=1)
                hs_txt = str(int(row['HORAS'])) if row['HORAS'] == int(row['HORAS']) else f"{row['HORAS']:.1f}"
                pdf.cell(35, 7, hs_txt, border=1, align='C', ln=True)

            # FILA TOTALES
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(220, 220, 220)
            pdf.cell(140, 7, "TOTAL HORAS ASISTENCIA", border=1, align='R', fill=True)
            
            t_hs_act_txt = str(int(total_hs_act)) if total_hs_act == int(total_hs_act) else f"{total_hs_act:.1f}"
            pdf.cell(35, 7, t_hs_act_txt, border=1, align='C', ln=True, fill=True)

        else:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "No se registraron tareas de asistencia en este periodo.", ln=True)
    else:
        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 7, "No se registraron tareas de asistencia en la base de datos.", ln=True)

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
        with st.spinner("Extrayendo datos posicionalmente desde los formularios originales..."):
            try:
                pdf_data = build_pdf(df_raw, df_mant_raw, df_act_raw, start_date, end_date)
                st.success("¡PDF generado correctamente!")
                st.download_button(
                    label="📥 Descargar Reporte Final", 
                    data=pdf_data, 
                    file_name=f"Reporte_Matriceria_{start_date.strftime('%d%m%Y')}.pdf", 
                    mime="application/pdf", 
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error generando PDF: {e}")
