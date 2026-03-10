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
st.set_page_config(page_title="Reporte Matricería", layout="centered", page_icon="📅")

st.markdown("""
<style>
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-style">📅 Reporte Gerencial de Matricería</div>', unsafe_allow_html=True)
st.write("<p style='text-align: center;'>Calendarios, Resumen de Horas y Estado de Mantenimiento de Matrices Multi-Cliente.</p>", unsafe_allow_html=True)
st.divider()

# ==========================================
# 2. EXTRACCIÓN INTELIGENTE DE DATOS
# ==========================================
SHEETS_CONFIG = [
    # ASISTENCIA
    {"url": "https://docs.google.com/spreadsheets/d/1sccnOPuosjMSepp0FZoEGteYArIIhB2fGH7TeSRW_7E/export?format=csv&gid=1128388185", "skiprows": 2, "tipo": "asistencia"},
    {"url": "https://docs.google.com/spreadsheets/d/1UNSCxrTy9TUdggNt0ta0TcsEvT3idaRGWcXE_t8J40I/export?format=csv&gid=979884533", "skiprows": 0, "tipo": "asistencia"},
    
    # CORRECTIVOS
    {"url": "https://docs.google.com/spreadsheets/d/1bL_tnlSXGO_t9tKnhIHT5pZ3DAxivbiq2tFETVxBaVI/export?format=csv&gid=1507213893", "skiprows": 2, "tipo": "correctivo"},
    {"url": "https://docs.google.com/spreadsheets/d/1A-0mngZdgvZGbqzWjA_awhrwfvca0K4aGqp5NBAoFAY/export?format=csv&gid=238711679", "skiprows": 0, "tipo": "correctivo"},
    
    # PREVENTIVOS
    {"url": "https://docs.google.com/spreadsheets/d/1MptnOuRfyOAr1EgzNJVygTtNziOSdzXJn-PZDX0pNzc/export?format=csv&gid=324842888", "skiprows": 0, "tipo": "preventivo"},
    {"url": "https://docs.google.com/spreadsheets/d/1VqsPNhAlT1kPCltbMWsbkZNFBKdwZRFM5RAmnRV0v3c/export?format=csv", "skiprows": 0, "tipo": "preventivo"}
]

@st.cache_data(ttl=300)
def load_data():
    cal_data, mant_data, act_data = [], [], []
    
    for config in SHEETS_CONFIG:
        try:
            df = pd.read_csv(config["url"])
            
            # Buscador Inteligente de Encabezados (ignora filas vacías al inicio)
            cols_upper = df.columns.astype(str).str.upper()
            if not (any('FECHA' in c for c in cols_upper) or any('MATRICERO' in c for c in cols_upper)):
                for i in range(min(10, len(df))):
                    row_vals = df.iloc[i].astype(str).str.upper().tolist()
                    if any('FECHA' in v for v in row_vals) or any('MATRICERO' in v for v in row_vals):
                        df.columns = df.iloc[i]
                        df = df.iloc[i+1:].reset_index(drop=True)
                        break

            # Estandarizar y asegurar que no haya columnas con nombres idénticos que rompan Pandas
            raw_cols = df.columns.astype(str).str.upper().str.strip().tolist()
            new_cols, seen = [], {}
            for c in raw_cols:
                if c in seen:
                    seen[c] += 1
                    new_cols.append(f"{c}.{seen[c]}")
                else:
                    seen[c] = 0
                    new_cols.append(c)
            df.columns = new_cols
            
            col_fecha = next((c for c in df.columns if c in ['1 - FECHA', 'FECHA']), None)
            if not col_fecha: continue

            # --- EXTRACCIÓN DE HORAS ---
            col_mat = next((c for c in df.columns if c in ['1 - MATRICERO', 'MATRICERO']), None)
            col_horas_clean = next((c for c in df.columns if c in ['1 - HORAS', 'TOTAL HS', 'HORAS', 'HS']), None)
            
            if col_horas_clean:
                df['HORAS_CALCULADAS'] = pd.to_numeric(df[col_horas_clean], errors='coerce').fillna(0)
            else:
                cols_hs_parciales = [c for c in df.columns if 'HS REALIZADAS' in c or 'HORAS' in c]
                df['HORAS_CALCULADAS'] = 0
                for c in cols_hs_parciales:
                    df['HORAS_CALCULADAS'] += pd.to_numeric(df[c], errors='coerce').fillna(0)

            # 1. Armar Calendario General
            if col_mat:
                df_cal = pd.DataFrame({'FECHA': df[col_fecha], 'MATRICERO': df[col_mat], 'TOTAL_HORAS': df['HORAS_CALCULADAS']})
                cal_data.append(df_cal)

            # 2. Armar Cuadro de Mantenimiento Multi-Cliente
            if config["tipo"] in ["preventivo", "correctivo"]:
                col_terminado = next((c for c in df.columns if c in ['1 - TERMINADO?', 'TERMINADO?', 'TERMINADO', 'EL MANTENIMIENTO CORRECTIVO ESTA TERMINADO?', 'SE TERMINO EL MANTENIMIENTO PREVENTIVO?']), None)
                
                # Buscar TODAS las columnas posibles de piezas (Fiat, Renault, Nissan, etc.), excluyendo preguntas del formulario
                exclusions = ['TIPO', 'LIMPIEZA', 'CERRAMIENTO', '[', '?', 'MANTENIMIENTO']
                cols_pieza_candidatas = [c for c in df.columns if ('PIEZA' in c or 'MATRIZ' in c) and not any(x in c for x in exclusions)]
                
                if col_terminado and cols_pieza_candidatas:
                    mant_rows = []
                    for idx, row in df.iterrows():
                        fecha_val = row[col_fecha]
                        horas_val = row['HORAS_CALCULADAS']
                        terminado_val = str(row[col_terminado]).upper().strip()
                        if terminado_val in ['NAN', 'NONE', '']: terminado_val = "NO"

                        # Si la persona usó las "columnas limpias" al final de la hoja, priorizamos esa
                        usado_limpio = False
                        if '1 - PIEZA' in df.columns and pd.notna(row.get('1 - PIEZA')) and str(row.get('1 - PIEZA')).strip().upper() not in ['', 'NAN', 'NONE', '-']:
                            p = str(row['1 - PIEZA']).strip()
                            o = str(row.get('1 - OPERACION', row.get('OPERACION', '-'))).strip()
                            if o.upper() in ['', 'NAN', 'NONE']: o = "-"
                            mant_rows.append({'FECHA': fecha_val, 'MATRIZ': p, 'OPERACION': o, 'TIPO': config["tipo"].upper(), 'HORAS': horas_val, 'TERMINADO': terminado_val})
                            usado_limpio = True
                            
                        # Si no usaron la limpia, hacemos BARRIDO de todos los clientes en la fila
                        if not usado_limpio:
                            piezas_en_fila = 0
                            for col_idx, col_name in enumerate(df.columns):
                                if col_name in cols_pieza_candidatas:
                                    val = str(row[col_name]).strip()
                                    if val and val.upper() not in ['NAN', 'NONE', '']:
                                        p = val
                                        o = "-"
                                        # Buscar la columna "Operacion" que le sigue a esta pieza
                                        for next_col in df.columns[col_idx+1 : col_idx+4]:
                                            if 'OPERACION' in next_col:
                                                temp_op = str(row[next_col]).strip()
                                                if temp_op and temp_op.upper() not in ['NAN', 'NONE', '']:
                                                    o = temp_op
                                                break
                                        
                                        mant_rows.append({'FECHA': fecha_val, 'MATRIZ': p, 'OPERACION': o, 'TIPO': config["tipo"].upper(), 'HORAS': horas_val, 'TERMINADO': terminado_val})
                                        piezas_en_fila += 1
                            
                            # Si llenaron varias matrices en una misma fila, evitamos duplicar las horas totales dividiéndola equitativamente
                            if piezas_en_fila > 1:
                                for k in range(1, piezas_en_fila + 1):
                                    mant_rows[-k]['HORAS'] = horas_val / piezas_en_fila
                    
                    if mant_rows:
                        mant_data.append(pd.DataFrame(mant_rows))

            # 3. Tareas de Asistencia
            if config["tipo"] == "asistencia":
                col_tarea = next((c for c in df.columns if c in ['TAREAS', 'PRIMER TAREA', '1 - TAREA 1', 'TAREAS REALIZADAS']), None)
                if col_tarea:
                    df_act = pd.DataFrame({
                        'FECHA': df[col_fecha],
                        'TAREA': df[col_tarea].astype(str).str.strip(),
                        'HORAS': df['HORAS_CALCULADAS']
                    })
                    act_data.append(df_act)

        except Exception as e:
            print(f"Error procesando {config['url']}: {e}")
            pass
            
    # ==========================
    # LIMPIEZA FINAL Y AGRUPACIÓN
    # ==========================
    df_calendario = pd.concat(cal_data, ignore_index=True) if cal_data else pd.DataFrame()
    if not df_calendario.empty:
        df_calendario['FECHA'] = pd.to_datetime(df_calendario['FECHA'], errors='coerce', dayfirst=True)
        df_calendario['MATRICERO'] = df_calendario['MATRICERO'].astype(str).str.strip().str.upper()
        df_calendario = df_calendario.dropna(subset=['FECHA'])
        df_calendario = df_calendario[~df_calendario['MATRICERO'].isin(['NAN', 'NONE', ''])]
        df_calendario = df_calendario.groupby(['FECHA', 'MATRICERO'], as_index=False)['TOTAL_HORAS'].sum()

    df_mantenimiento = pd.concat(mant_data, ignore_index=True) if mant_data else pd.DataFrame()
    if not df_mantenimiento.empty:
        df_mantenimiento['FECHA'] = pd.to_datetime(df_mantenimiento['FECHA'], errors='coerce', dayfirst=True)
        df_mantenimiento = df_mantenimiento.dropna(subset=['FECHA'])
        df_mantenimiento = df_mantenimiento[~df_mantenimiento['MATRIZ'].isin(['nan', 'NaN', 'None', ''])]

    df_actividades = pd.concat(act_data, ignore_index=True) if act_data else pd.DataFrame()
    if not df_actividades.empty:
        df_actividades['FECHA'] = pd.to_datetime(df_actividades['FECHA'], errors='coerce', dayfirst=True)
        df_actividades = df_actividades.dropna(subset=['FECHA'])
        df_actividades = df_actividades[~df_actividades['TAREA'].isin(['nan', 'NaN', 'None', ''])]

    return df_calendario, df_mantenimiento, df_actividades

df_raw, df_mant_raw, df_act_raw = load_data()

# ==========================================
# 3. INTERFAZ Y FILTROS DE FECHA
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
# 4. CLASE PDF (FPDF) Y LÓGICA
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
    # PARTE 1: RESUMEN Y CALENDARIOS POR MES
    # =========================================================
    for (year, month), dates_in_month in months_dict.items():
        pdf.add_page()
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
            hs_extra = ausencias = reported = 0
            
            for d in dates_in_month:
                val = df_mat[df_mat['FECHA'].dt.date == d]['TOTAL_HORAS'].sum()
                reported += val
                if d.weekday() >= 5: hs_extra += val
                else:
                    if val > 8: hs_extra += (val - 8)
                    elif val < 8: ausencias += (8 - val)

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

            diff = reported - estimated_hs
            if diff < 0: pdf.set_text_color(192, 0, 0) 
            elif diff > 0: pdf.set_text_color(0, 128, 0)
            else: pdf.set_text_color(0, 0, 0)
            
            sign = "+" if diff > 0 else ""
            t_diff = f"{sign}{int(diff)}" if diff == int(diff) else f"{sign}{diff:.1f}"
            pdf.cell(28, 6, t_diff, border=1, align='C', ln=True, fill=True)

        # CALENDARIOS
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

        w_mat, w_day = 50, 30 
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
                pdf.cell(w_mat, 8, clean_text(mat[:25]), border=1, fill=True)
                
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
    # PARTE 2: MANTENIMIENTO CON OPERACIÓN Y TOTALES
    # =========================================================
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 1: ESTADO DE MATRICES (MANTENIMIENTO)", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Muestra horas invertidas y estado final en el periodo seleccionado.", ln=True)
    pdf.ln(3)

    if not df_mant.empty:
        df_m_period = df_mant[(df_mant['FECHA'].dt.date >= s_date) & (df_mant['FECHA'].dt.date <= e_date)].copy()
        
        if not df_m_period.empty:
            df_m_period = df_m_period.sort_values('FECHA')
            
            resumen_mant = df_m_period.groupby(['MATRIZ', 'OPERACION', 'TIPO']).agg(
                HS_ACUMULADAS=('HORAS', 'sum'),
                ULTIMO_ESTADO=('TERMINADO', 'last')
            ).reset_index().sort_values('HS_ACUMULADAS', ascending=False)

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(0, 0, 0)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(80, 7, "MATRIZ / PIEZA", border=1, fill=True)
            pdf.cell(30, 7, "OPERACIÓN", border=1, align='C', fill=True)
            pdf.cell(35, 7, "TIPO", border=1, align='C', fill=True)
            pdf.cell(35, 7, "HS INSUMIDAS", border=1, align='C', fill=True)
            pdf.cell(40, 7, "ESTADO AL CIERRE", border=1, align='C', ln=True, fill=True)

            pdf.set_font("Arial", '', 9)
            total_hs_mant = 0

            for _, row in resumen_mant.iterrows():
                matriz = str(row['MATRIZ'])
                operacion = str(row['OPERACION'])
                estado = str(row['ULTIMO_ESTADO']).upper()
                total_hs_mant += row['HS_ACUMULADAS']
                
                pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(80, 7, clean_text(matriz[:45]), border=1)
                pdf.cell(30, 7, clean_text(operacion[:15]), border=1, align='C')
                pdf.cell(35, 7, clean_text(row['TIPO']), border=1, align='C')
                
                hs_txt = str(int(row['HS_ACUMULADAS'])) if row['HS_ACUMULADAS'] == int(row['HS_ACUMULADAS']) else f"{row['HS_ACUMULADAS']:.1f}"
                pdf.cell(35, 7, hs_txt, border=1, align='C')
                
                if "SI" in estado or "SÍ" in estado:
                    pdf.set_text_color(0, 128, 0)
                    estado_print = "TERMINADO"
                else:
                    pdf.set_text_color(192, 0, 0)
                    estado_print = "PENDIENTE"
                
                pdf.cell(40, 7, clean_text(estado_print), border=1, align='C', ln=True)

            # FILA DE TOTALES
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(220, 220, 220)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(145, 7, "TOTAL HORAS MANTENIMIENTO", border=1, align='R', fill=True)
            
            t_hs_mant_txt = str(int(total_hs_mant)) if total_hs_mant == int(total_hs_mant) else f"{total_hs_mant:.1f}"
            pdf.cell(35, 7, t_hs_mant_txt, border=1, align='C', fill=True)
            pdf.cell(40, 7, "", border=1, align='C', ln=True, fill=True)

        else:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "No se registraron mantenimientos en este periodo.", ln=True)
    else:
        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 7, "No hubo mantenimiento en este periodo.", ln=True)

    pdf.ln(10)

    # =========================================================
    # PARTE 3: ASISTENCIA CON TOTALES
    # =========================================================
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 2: ACTIVIDADES DE ASISTENCIA", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Resumen de horas insumidas por tarea general.", ln=True)
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

            # FILA DE TOTALES
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
        with st.spinner("Construyendo documento PDF..."):
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
