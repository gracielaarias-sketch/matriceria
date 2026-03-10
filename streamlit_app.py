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
st.write("<p style='text-align: center;'>Calendarios, Estado de Matrices y Control de Golpes Acumulados.</p>", unsafe_allow_html=True)
st.divider()

# ==========================================
# 2. LISTA MAESTRA DE MATRICES A CONTROLAR (SIN LAS 'N')
# ==========================================
MATRICES_CONTROL = [
    "7431220", "7431230", "7431240",
    "7436620", "7436630", "7436640A", "7436650", "7436660", "7436640B",
    "9369220", "9369230-40", "9369250-60",
    "FAA005213148020", "FAA005213148030", "FAA005213148040", "FAA005213148050", "FAA005213148060",
    "FAA005205484620", "FAA005205484630", "FAA005205484640", "FAA005205484650", "FAA005205484660",
    "FAA005205495220", "FAA005205495230", "FAA005205495240", "FAA005205495250", "FAA005205495260",
    "FAA005205527120", "FAA005205527130", "FAA005205527140", "FAA005205527150", "FAA005205527160",
    "FAA005205527220", "FAA005205527230", "FAA005205527240", "FAA005205527250", "FAA005205527260",
    "RE762338319R/011R20", "RE762338319R/011R30", "RE762338319R/011R40", "RE762338319R/011R50", "RE762338319R/011R60",
    "RE625188951RMP1", "RE625188951RMP2",
    "RE765172097R/032R20", "RE765172097R/032R30", "RE765172097R/032R40", "RE765172097R/032R50",
    "RE765173855R/00720", "RE765173855R/00730", "RE765173855R/00740", "RE765173855R/00750",
    "RE765190257R/517R20", "RE765190257R/517R30", "RE765190257R/517R40", "RE765190257R/517R50",
    "RE764E31359RROLL", "RE764E29624RROLL",
    "RE762193072R20", "RE762193072R30", "RE762193072R40", "RE762193072R50", "RE762193072R60",
    "RE762182738R20", "RE762182738R30", "RE762182738R40", "RE762182738R50", "RE762182738R60",
    "RE762336130R/748R20", "RE762336130R/748R30", "RE762336130R/748R40", "RE762336130R/748R50",
    "RE501334314R20", "RE501334314RMP1", "RE501334314RMP2"
]

# ==========================================
# 3. EXTRACCIÓN INTELIGENTE DE DATOS
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
    {"url": "https://docs.google.com/spreadsheets/d/1VqsPNhAlT1kPCltbMWsbkZNFBKdwZRFM5RAmnRV0v3c/export?format=csv", "skiprows": 0, "tipo": "preventivo"},
    # PRODUCCIÓN
    {"url": "https://docs.google.com/spreadsheets/d/1TdQ3yNxx29SgQ7u8oexxlnL80rAcXQuP118wQVBd9ew/export?format=csv&gid=315437448", "skiprows": 0, "tipo": "produccion"},
]

@st.cache_data(ttl=300)
def load_data():
    cal_data, mant_data, act_data, prod_data = [], [], [], []
    
    for config in SHEETS_CONFIG:
        try:
            df = pd.read_csv(config["url"])
            
            # Buscador Inteligente de Encabezados
            cols_upper = df.columns.astype(str).str.upper()
            if not (any('FECHA' in c for c in cols_upper) or any('MATRICERO' in c for c in cols_upper) or any('CÓDIGO' in c for c in cols_upper)):
                for i in range(min(10, len(df))):
                    row_vals = df.iloc[i].astype(str).str.upper().tolist()
                    if any('FECHA' in v for v in row_vals) or any('MATRICERO' in v for v in row_vals) or any('CÓDIGO' in v for v in row_vals):
                        df.columns = df.iloc[i]
                        df = df.iloc[i+1:].reset_index(drop=True)
                        break

            df.columns = df.columns.astype(str).str.upper().str.strip()
            df = df.loc[:, ~df.columns.duplicated()].copy()
            
            col_fecha = next((c for c in df.columns if c in ['1 - FECHA', 'FECHA']), None)
            
            # --- LÓGICA PRODUCCIÓN (GOLPES) ---
            if config["tipo"] == "produccion" and col_fecha:
                col_pieza_prod = next((c for c in df.columns if c in ['CÓDIGO', 'CODIGO', 'PIEZA', 'NUMERO DE PIEZA']), None)
                cols_golpes = [c for c in df.columns if c in ['BUENAS', 'RETRABAJO', 'OBSERVADAS', 'GOLPES']]
                if col_pieza_prod and cols_golpes:
                    df_p = df[[col_fecha, col_pieza_prod] + cols_golpes].copy()
                    df_p['GOLPES_TOTALES'] = 0
                    for c in cols_golpes:
                        df_p['GOLPES_TOTALES'] += pd.to_numeric(df_p[c].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    df_p = df_p.rename(columns={col_fecha: 'FECHA', col_pieza_prod: 'MATRIZ'})
                    df_p = df_p[['FECHA', 'MATRIZ', 'GOLPES_TOTALES']]
                    prod_data.append(df_p)
                continue

            # --- LÓGICA HORAS (Cal, Mant, Act) ---
            col_mat = next((c for c in df.columns if c in ['1 - MATRICERO', 'MATRICERO']), None)
            col_horas_clean = next((c for c in df.columns if c in ['1 - HORAS', 'TOTAL HS', 'HORAS', 'HS']), None)
            
            if col_horas_clean:
                df['HORAS_CALCULADAS'] = pd.to_numeric(df[col_horas_clean], errors='coerce').fillna(0)
            else:
                cols_hs_parciales = [c for c in df.columns if 'HS REALIZADAS' in c or 'HORAS' in c]
                df['HORAS_CALCULADAS'] = 0
                for c in cols_hs_parciales:
                    df['HORAS_CALCULADAS'] += pd.to_numeric(df[c], errors='coerce').fillna(0)

            # Calendario General
            if col_fecha and col_mat:
                df_cal = pd.DataFrame({'FECHA': df[col_fecha], 'MATRICERO': df[col_mat], 'TOTAL_HORAS': df['HORAS_CALCULADAS']})
                cal_data.append(df_cal)

            # Cuadro de Mantenimiento
            if config["tipo"] in ["preventivo", "correctivo"] and col_fecha:
                col_pieza = next((c for c in df.columns if c in ['1 - PIEZA', 'MATRIZ', 'PIEZA', 'NUMERO DE PIEZA']), None)
                col_terminado = next((c for c in df.columns if c in ['1 - TERMINADO?', 'TERMINADO?', 'TERMINADO', 'EL MANTENIMIENTO CORRECTIVO ESTA TERMINADO?', 'SE TERMINO EL MANTENIMIENTO PREVENTIVO?']), None)
                
                if col_pieza and col_terminado:
                    df_m = pd.DataFrame({
                        'FECHA': df[col_fecha],
                        'MATRIZ': df[col_pieza].astype(str).str.strip(),
                        'TIPO': config["tipo"].upper(),
                        'HORAS': df['HORAS_CALCULADAS'],
                        'TERMINADO': df[col_terminado].astype(str).str.upper().str.strip()
                    })
                    mant_data.append(df_m)

            # Tareas de Asistencia
            if config["tipo"] == "asistencia" and col_fecha:
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

    df_actividades = pd.concat(act_data, ignore_index=True) if act_data else pd.DataFrame()
    if not df_actividades.empty:
        df_actividades['FECHA'] = pd.to_datetime(df_actividades['FECHA'], errors='coerce', dayfirst=True)
        df_actividades = df_actividades.dropna(subset=['FECHA'])
        df_actividades = df_actividades[~df_actividades['TAREA'].isin(['nan', 'NaN', 'None', ''])]

    df_produccion = pd.concat(prod_data, ignore_index=True) if prod_data else pd.DataFrame()
    if not df_produccion.empty:
        df_produccion['FECHA'] = pd.to_datetime(df_produccion['FECHA'], errors='coerce', dayfirst=True)
        df_produccion = df_produccion.dropna(subset=['FECHA'])

    return df_calendario, df_mantenimiento, df_actividades, df_produccion

df_raw, df_mant_raw, df_act_raw, df_prod_raw = load_data()

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
# 5. CLASE PDF (FPDF) Y LÓGICA
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

def buscar_matriz_oficial(matriz_sucia, lista_oficial):
    sucia = str(matriz_sucia).upper().replace(" ", "")
    for oficial in lista_oficial:
        if oficial.replace(" ", "") in sucia or sucia in oficial.replace(" ", ""):
            return oficial
    return None

def build_pdf(df_datos, df_mant, df_act, df_prod, s_date, e_date):
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
    # PARTE 1: RESUMEN Y CALENDARIOS
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
    # PARTE 2: MANTENIMIENTO Y GOLPES
    # =========================================================
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(0, 8, "ANEXO 1: ESTADO DE MATRICES Y GOLPES ACUMULADOS", ln=True, align='L')
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Muestra horas invertidas, estado final y produccion realizada desde el ultimo mantenimiento 'Terminado'.", ln=True)
    pdf.ln(3)

    if not df_mant.empty:
        df_m_period = df_mant[(df_mant['FECHA'].dt.date >= s_date) & (df_mant['FECHA'].dt.date <= e_date)].copy()
        if not df_m_period.empty:
            
            df_m_period['MATRIZ_OFICIAL'] = df_m_period['MATRIZ'].apply(lambda x: buscar_matriz_oficial(x, MATRICES_CONTROL))
            df_m_period = df_m_period.dropna(subset=['MATRIZ_OFICIAL']) # Ignorar las que no esten en la lista oficial
            
            if not df_m_period.empty:
                df_m_period = df_m_period.sort_values('FECHA')
                resumen_mant = df_m_period.groupby(['MATRIZ_OFICIAL', 'TIPO']).agg(
                    HS_ACUMULADAS=('HORAS', 'sum'),
                    ULTIMO_ESTADO=('TERMINADO', 'last'),
                    ULTIMA_FECHA=('FECHA', 'last')
                ).reset_index().sort_values('HS_ACUMULADAS', ascending=False)

                pdf.set_font("Arial", 'B', 8)
                pdf.set_fill_color(0, 0, 0)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(65, 7, "MATRIZ / PIEZA", border=1, fill=True)
                pdf.cell(30, 7, "TIPO", border=1, align='C', fill=True)
                pdf.cell(30, 7, "HS INSUMIDAS", border=1, align='C', fill=True)
                pdf.cell(40, 7, "ESTADO AL CIERRE", border=1, align='C', fill=True)
                pdf.set_fill_color(31, 73, 125)
                pdf.cell(35, 7, "GOLPES ACUMULADOS", border=1, align='C', ln=True, fill=True)

                pdf.set_font("Arial", '', 8)
                for _, row in resumen_mant.iterrows():
                    matriz = str(row['MATRIZ_OFICIAL'])
                    estado = str(row['ULTIMO_ESTADO']).upper()
                    fecha_ult = row['ULTIMA_FECHA']
                    
                    pdf.set_fill_color(255, 255, 255)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(65, 7, clean_text(matriz[:40]), border=1)
                    pdf.cell(30, 7, clean_text(row['TIPO']), border=1, align='C')
                    
                    hs_txt = str(int(row['HS_ACUMULADAS'])) if row['HS_ACUMULADAS'] == int(row['HS_ACUMULADAS']) else f"{row['HS_ACUMULADAS']:.1f}"
                    pdf.cell(30, 7, hs_txt, border=1, align='C')
                    
                    if "SI" in estado or "SÍ" in estado:
                        pdf.set_text_color(0, 128, 0)
                        estado_print = "TERMINADO"
                        terminado_bool = True
                    else:
                        pdf.set_text_color(192, 0, 0)
                        estado_print = "PENDIENTE"
                        terminado_bool = False
                    pdf.cell(40, 7, clean_text(estado_print), border=1, align='C')
                    
                    golpes = 0
                    if terminado_bool and not df_prod.empty:
                        df_prod_filter = df_prod[df_prod['FECHA'] >= fecha_ult]
                        mask_matriz = df_prod_filter['MATRIZ'].apply(lambda x: matriz.replace(" ", "") in str(x).upper().replace(" ", ""))
                        golpes = df_prod_filter[mask_matriz]['GOLPES_TOTALES'].sum()

                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", 'B', 8)
                    pdf.cell(35, 7, f"{int(golpes):,}".replace(",", "."), border=1, align='C', ln=True)
                    pdf.set_font("Arial", '', 8)
            else:
                pdf.set_font("Arial", '', 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 7, "No se registraron mantenimientos de la lista oficial de matrices.", ln=True)
        else:
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "No hubo mantenimiento en este periodo.", ln=True)
    else:
        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 7, "No hubo mantenimiento en este periodo.", ln=True)

    pdf.ln(10)

    # =========================================================
    # PARTE 3: ASISTENCIA
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
# 6. BOTÓN DE DESCARGA
# ==========================================
st.write("") 
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    if st.button("🖨️ Procesar y Generar PDF Completo", type="primary", use_container_width=True):
        with st.spinner("Construyendo documento PDF, cruzando datos de producción..."):
            try:
                pdf_data = build_pdf(df_raw, df_mant_raw, df_act_raw, df_prod_raw, start_date, end_date)
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
