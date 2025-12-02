import streamlit as st
import pandas as pd
from datetime import datetime, time
import calendar
import os

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Control Biométrico",
    page_icon="⏰",
    layout="wide"
)

# --- CONSTANTES DE ARCHIVOS ---
# Asegúrate de subir tus archivos a GitHub con estos nombres exactos:
FILE_USERS = 'usuarios.csv'
FILE_LOGS = 'registros.csv'

# --- FUNCIONES DE UTILIDAD ---

@st.cache_data
def load_data(users_path, logs_path):
    """Carga los datos una sola vez para mejorar velocidad"""
    
    # 1. CARGAR USUARIOS
    try:
        df_users = pd.read_csv(users_path, sep=None, engine='python', dtype=str)
        # Normalizar columnas
        df_users.columns = df_users.columns.str.lower().str.strip()
        
        # Mapear columnas
        col_map = {}
        for col in df_users.columns:
            if 'nombre' in col or 'name' in col: col_map['nombre'] = col
            elif 'id' in col or 'codigo' in col: col_map['id'] = col
            elif 'area' in col or 'depto' in col: col_map['area'] = col
        
        if 'nombre' in col_map and 'id' in col_map:
            df_users = df_users.rename(columns={col_map['nombre']: 'Nombre', col_map['id']: 'ID'})
            df_users['Area'] = df_users[col_map['area']] if 'area' in col_map else 'GENERAL'
            df_users = df_users[['ID', 'Nombre', 'Area']]
        else:
            return None, None, "Error: No se encontraron columnas Nombre/ID en usuarios.csv"
            
    except Exception as e:
        return None, None, f"Error leyendo usuarios.csv: {e}"

    # 2. CARGAR REGISTROS (LOGS)
    try:
        # Leemos sin header primero para buscar patrones
        df_logs_raw = pd.read_csv(logs_path, sep=None, engine='python', dtype=str, header=None)
        
        valid_rows = []
        import re
        
        # Convertir a string y iterar
        for index, row in df_logs_raw.astype(str).iterrows():
            line = " ".join(row.values)
            
            # Buscar fecha y hora
            date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})', line)
            time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
            
            if date_match and time_match:
                date_str = date_match.group(0)
                time_str = time_match.group(0)
                
                # Buscar ID limpiando la fecha y hora encontradas
                clean_line = line.replace(date_str, '').replace(time_str, '')
                id_match = re.search(r'\b\d{1,10}\b', clean_line)
                
                if id_match:
                    # Normalizar fecha a YYYY-MM-DD
                    norm_date = date_str
                    if '/' in date_str:
                        parts = re.split(r'[-/]', date_str)
                        if len(parts[0]) == 4: # YYYY-MM-DD
                            norm_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
                        else: # DD-MM-YYYY
                            norm_date = f"{parts[2]}-{parts[1]}-{parts[0]}"

                    valid_rows.append({
                        'ID': id_match.group(0),
                        'Fecha': norm_date,
                        'Hora': time_str
                    })
        
        df_logs = pd.DataFrame(valid_rows)
        if df_logs.empty:
            return None, None, "Error: No se detectaron fechas/horas válidas en registros.csv"
            
    except Exception as e:
        return None, None, f"Error leyendo registros.csv: {e}"
        
    return df_users, df_logs, None

def get_workdays(year, month):
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, day) for day in range(1, num_days + 1)]
    return [d.strftime('%Y-%m-%d') for d in days if d.weekday() < 5]

def time_to_min(t_str):
    h, m, s = map(int, t_str.split(':'))
    return h * 60 + m

# --- INTERFAZ DE USUARIO ---

st.title("📊 Sistema de Control Biométrico")

# --- VERIFICACIÓN DE ARCHIVOS ---
if not os.path.exists(FILE_USERS) or not os.path.exists(FILE_LOGS):
    st.error("❌ Archivos de datos no encontrados.")
    st.markdown(f"""
    **Instrucciones para el Administrador:**
    Por favor sube los siguientes archivos a la raíz de tu repositorio en GitHub:
    1. `{FILE_USERS}` (Datos de los empleados)
    2. `{FILE_LOGS}` (Datos del biométrico)
    """)
    st.stop()

# --- CARGA AUTOMÁTICA ---
df_users, df_logs, error_msg = load_data(FILE_USERS, FILE_LOGS)

if error_msg:
    st.error(error_msg)
    st.stop()

# --- SIDEBAR: CONFIGURACIÓN ---
with st.sidebar:
    st.header("⚙️ Configuración")
    entry_time_input = st.time_input("Hora de Entrada Límite", value=time(8, 30))
    entry_limit_mins = entry_time_input.hour * 60 + entry_time_input.minute
    
    st.divider()
    st.info(f"Datos cargados desde:\n📄 {FILE_USERS}\n📄 {FILE_LOGS}")

# --- LÓGICA DE NEGOCIO ---

# Preprocesar fechas
df_logs['Fecha_DT'] = pd.to_datetime(df_logs['Fecha'])
df_logs['Mes_Str'] = df_logs['Fecha_DT'].dt.strftime('%Y-%m')

# Filtros
st.markdown("---")
col1, col2, col3 = st.columns(3)

available_months = sorted(df_logs['Mes_Str'].unique(), reverse=True)
with col1:
    selected_month = st.selectbox("📅 Mes", available_months)

available_areas = ["TODOS"] + sorted(df_users['Area'].unique().tolist())
with col2:
    selected_area = st.selectbox("🏢 Departamento", available_areas)
    
with col3:
    search_query = st.text_input("🔍 Buscar Empleado")

show_only_late = st.checkbox("Ver solo con retrasos", value=False)

# Procesamiento principal
current_logs = df_logs[df_logs['Mes_Str'] == selected_month].copy()
daily_logs = current_logs.groupby(['ID', 'Fecha'])['Hora'].min().reset_index()

year, month = map(int, selected_month.split('-'))
workdays = get_workdays(year, month)
today_str = datetime.now().strftime('%Y-%m-%d')

results = []
detail_records = []

for _, user in df_users.iterrows():
    uid = user['ID']
    uname = user['Nombre']
    uarea = user['Area']
    
    # Aplicar filtros
    if selected_area != "TODOS" and uarea != selected_area: continue
    if search_query:
        if search_query.lower() not in uname.lower() and search_query not in uid: continue

    u_logs = daily_logs[daily_logs['ID'] == uid]
    
    delays = 0
    delay_minutes = 0
    attended_dates = set()
    
    # Calcular asistencia
    for _, row in u_logs.iterrows():
        log_date = row['Fecha']
        log_time = row['Hora']
        attended_dates.add(log_date)
        
        mins = time_to_min(log_time)
        is_late = mins > entry_limit_mins
        delay_amt = mins - entry_limit_mins if is_late else 0
        
        if is_late:
            delays += 1
            delay_minutes += delay_amt
        
        detail_records.append({
            "Fecha": log_date, "Empleado": uname, "Area": uarea,
            "Hora": log_time, "Retraso (min)": delay_amt if is_late else 0,
            "Estado": "RETRASO" if is_late else "PUNTUAL"
        })

    # Calcular faltas
    valid_days = [d for d in workdays if d <= today_str or selected_month < today_str[:7]]
    absences = 0
    for d in valid_days:
        if d not in attended_dates:
            absences += 1
            detail_records.append({
                "Fecha": d, "Empleado": uname, "Area": uarea,
                "Hora": "-", "Retraso (min)": 0, "Estado": "AUSENTE"
            })

    if show_only_late and delays == 0: continue

    results.append({
        "ID": uid, "Nombre": uname, "Area": uarea,
        "Retrasos": delays, "Minutos Acumulados": delay_minutes, "Faltas": absences
    })

# --- VISUALIZACIÓN ---

df_resumen = pd.DataFrame(results)
df_detalle = pd.DataFrame(detail_records)

if not df_resumen.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Retrasos", df_resumen['Retrasos'].sum())
    m2.metric("Minutos Perdidos", f"{df_resumen['Minutos Acumulados'].sum()} min")
    m3.metric("Faltas Totales", df_resumen['Faltas'].sum())

    st.subheader("📋 Resumen General")
    st.dataframe(
        df_resumen.style.apply(lambda x: ['color: #d32f2f; font-weight: bold' if v > 0 else '' for v in x], subset=['Retrasos']),
        use_container_width=True, hide_index=True
    )

    if not df_detalle.empty:
        st.subheader("📅 Detalle Diario")
        df_detalle = df_detalle.sort_values(by=['Fecha', 'Empleado'], ascending=[False, True])
        
        def color_status(val):
            if val == 'RETRASO': return 'background-color: #ffcdd2; color: #b71c1c'
            elif val == 'PUNTUAL': return 'background-color: #c8e6c9; color: #1b5e20'
            elif val == 'AUSENTE': return 'background-color: #f5f5f5; color: #616161'
            return ''

        st.dataframe(
            df_detalle.style.applymap(color_status, subset=['Estado']),
            use_container_width=True, hide_index=True
        )
else:
    st.info("No se encontraron registros para mostrar.")
