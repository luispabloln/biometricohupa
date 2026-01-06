import streamlit as st
import pandas as pd
from datetime import datetime, time
import calendar
import os

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Control Biométrico",
    page_icon="🔐",
    layout="wide"
)

# --- SEGURIDAD Y USUARIOS ---
CREDENCIALES = {
    "admin": "admin123",
    "gerencia": "gerencia2025",
    "rrhh": "rrhh123"
}

def check_password():
    """Retorna True si el usuario está logueado, persistiendo la sesión en URL"""
    if st.query_params.get("logged_in") == "true":
        st.session_state['authenticated'] = True
        if 'user' not in st.session_state:
             st.session_state['user'] = "Usuario"

    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        
    if not st.session_state['authenticated']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("## 🔐 Acceso Restringido")
            with st.form("login_form"):
                username = st.text_input("Usuario")
                password = st.text_input("Contraseña", type="password")
                submit_button = st.form_submit_button("Ingresar")
                
                if submit_button:
                    if username in CREDENCIALES and CREDENCIALES[username] == password:
                        st.session_state['authenticated'] = True
                        st.session_state['user'] = username
                        st.query_params["logged_in"] = "true"
                        st.success("¡Acceso correcto!")
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos")
        return False
    return True

def logout():
    st.session_state['authenticated'] = False
    st.query_params.clear()
    st.rerun()

# --- CONSTANTES ---
FILE_USERS = 'usuarios.csv'
FILE_LOGS = 'registros.csv'
FILE_HOLIDAYS = 'feriados.csv'

# --- FUNCIONES ---

@st.cache_data
def load_data(users_path, logs_path):
    """Carga datos con limpieza de IDs y regex flexible de fechas"""
    
    # 1. USUARIOS
    df_users = None
    encodings = ['utf-8', 'latin-1', 'cp1252']
    
    for enc in encodings:
        try:
            df_users = pd.read_csv(users_path, sep=None, engine='python', dtype=str, encoding=enc)
            break 
        except: continue
            
    if df_users is None: return None, None, "Error leyendo usuarios.csv"

    # Normalizar columnas
    df_users.columns = df_users.columns.str.lower().str.strip()
    col_map = {}
    for col in df_users.columns:
        if 'nombre' in col or 'name' in col: col_map['nombre'] = col
        elif 'id' in col or 'codigo' in col: col_map['id'] = col
        elif 'area' in col or 'depto' in col: col_map['area'] = col
    
    if 'nombre' in col_map and 'id' in col_map:
        df_users = df_users.rename(columns={col_map['nombre']: 'Nombre', col_map['id']: 'ID'})
        df_users['Area'] = df_users[col_map['area']] if 'area' in col_map else 'GENERAL'
        # LIMPIEZA CRÍTICA DE IDS (Quitar espacios)
        df_users['ID'] = df_users['ID'].str.strip()
        df_users = df_users[['ID', 'Nombre', 'Area']]
    else:
        return None, None, "Faltan columnas Nombre/ID en usuarios.csv"

    # 2. REGISTROS
    df_logs_raw = None
    for enc in encodings:
        try:
            df_logs_raw = pd.read_csv(logs_path, sep=None, engine='python', dtype=str, header=None, encoding=enc)
            break
        except: continue
            
    if df_logs_raw is None: return None, None, "Error leyendo registros.csv"

    try:
        valid_rows = []
        import re
        # Regex ajustado para aceptar 1 o 2 dígitos en día/mes (ej: 1/12/2025)
        date_pattern = re.compile(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})|(\d{1,2}[-/]\d{1,2}[-/]\d{4})')
        time_pattern = re.compile(r'(\d{1,2}:\d{2}:\d{2})')
        
        for index, row in df_logs_raw.astype(str).iterrows():
            line = " ".join(row.values)
            
            date_match = date_pattern.search(line)
            time_match = time_pattern.search(line)
            
            if date_match and time_match:
                date_str = date_match.group(0)
                time_str = time_match.group(0)
                
                # Buscar ID en lo que queda de la línea
                clean_line = line.replace(date_str, '').replace(time_str, '')
                id_match = re.search(r'\b\d{1,10}\b', clean_line)
                
                if id_match:
                    user_id = id_match.group(0).strip() # Limpieza de ID
                    
                    # Normalizar fecha
                    norm_date = date_str
                    if '/' in date_str:
                        parts = re.split(r'[-/]', date_str)
                        # Asumir YYYY-MM-DD si el primero es año, sino DD-MM-YYYY
                        if len(parts[0]) == 4: 
                            norm_date = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                        else: 
                            norm_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                    
                    valid_rows.append({
                        'ID': user_id,
                        'Fecha': norm_date,
                        'Hora': time_str
                    })
        
        df_logs = pd.DataFrame(valid_rows)
        if df_logs.empty: return None, None, "No se encontraron fechas válidas en registros.csv"
            
    except Exception as e:
        return None, None, f"Error procesando registros: {e}"
        
    return df_users, df_logs, None

def load_holidays(path):
    s = set()
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, header=None, dtype=str)
            for val in df[0]:
                try:
                    s.add(pd.to_datetime(val, dayfirst=True).strftime('%Y-%m-%d'))
                except: continue
        except: pass
    return s

def get_workdays(year, month, holidays):
    num_days = calendar.monthrange(year, month)[1]
    days = []
    for day in range(1, num_days + 1):
        d = datetime(year, month, day)
        d_str = d.strftime('%Y-%m-%d')
        if d.weekday() < 5 and d_str not in holidays:
            days.append(d_str)
    return days

def time_to_min(t):
    try:
        h, m, s = map(int, t.split(':'))
        return h * 60 + m
    except: return 0

# --- APP ---

if not check_password(): st.stop()

with st.sidebar:
    st.write(f"👤 **{st.session_state.get('user')}**")
    if st.button("Salir"): logout()
    st.divider()

if not os.path.exists(FILE_USERS) or not os.path.exists(FILE_LOGS):
    st.error("Faltan archivos csv en el repositorio.")
    st.stop()

df_users, df_logs, error_msg = load_data(FILE_USERS, FILE_LOGS)
holidays = load_holidays(FILE_HOLIDAYS)

if error_msg:
    st.error(error_msg)
    st.stop()

with st.sidebar:
    st.header("⚙️ Configuración")
    entry_time = st.time_input("Hora Entrada", value=time(8, 30))
    limit_min = entry_time.hour * 60 + entry_time.minute
    st.divider()

# PROCESAMIENTO
df_logs['Fecha_DT'] = pd.to_datetime(df_logs['Fecha'])
df_logs['Mes_Str'] = df_logs['Fecha_DT'].dt.strftime('%Y-%m')

st.title("📊 Control Biométrico")
col1, col2, col3 = st.columns(3)

months = sorted(df_logs['Mes_Str'].unique(), reverse=True)
with col1: selected_month = st.selectbox("📅 Mes", months)

areas = ["TODOS"] + sorted(df_users['Area'].unique().tolist())
with col2: selected_area = st.selectbox("🏢 Área", areas)

with col3: query = st.text_input("🔍 Buscar")

show_late = st.checkbox("Ver solo con retrasos")

# FILTRADO DE LOGS
logs_month = df_logs[df_logs['Mes_Str'] == selected_month].copy()
daily = logs_month.groupby(['ID', 'Fecha'])['Hora'].min().reset_index()

# DEBUG INFO
with st.sidebar:
    st.info(f"Registros encontrados para {selected_month}: **{len(daily)}**")

year, month = map(int, selected_month.split('-'))
workdays = get_workdays(year, month, holidays)
today = datetime.now().strftime('%Y-%m-%d')

res = []
det = []

for _, u in df_users.iterrows():
    uid, name, area = u['ID'], u['Nombre'], u['Area']
    
    if selected_area != "TODOS" and area != selected_area: continue
    if query and (query.lower() not in name.lower() and query not in uid): continue

    u_logs = daily[daily['ID'] == uid]
    
    delays = 0
    delay_min = 0
    att_dates = set()
    
    for _, row in u_logs.iterrows():
        dt, tm = row['Fecha'], row['Hora']
        att_dates.add(dt)
        
        m = time_to_min(tm)
        is_late = m > limit_min
        diff = m - limit_min if is_late else 0
        
        status = "RETRASO" if is_late else "PUNTUAL"
        if dt in holidays: status += " (FERIADO)"
        
        if is_late:
            delays += 1
            delay_min += diff
            
        det.append({"Fecha": dt, "Nombre": name, "Area": area, "Hora": tm, "Retraso": diff, "Estado": status})

    # Faltas: Solo hasta el día de hoy si es el mes actual
    # Si estamos en 2026 y miramos Dic 2025, cuenta todo el mes.
    valid = [d for d in workdays if d <= today or selected_month < today[:7]]
    
    absences = 0
    for d in valid:
        if d not in att_dates:
            absences += 1
            det.append({"Fecha": d, "Nombre": name, "Area": area, "Hora": "-", "Retraso": 0, "Estado": "AUSENTE"})

    if show_late and delays == 0: continue

    res.append({"ID": uid, "Nombre": name, "Area": area, "Retrasos": delays, "Minutos": delay_min, "Faltas": absences})

df_res = pd.DataFrame(res)
df_det = pd.DataFrame(det)

if not df_res.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Retrasos", df_res['Retrasos'].sum())
    c2.metric("Minutos", f"{df_res['Minutos'].sum()}")
    c3.metric("Faltas", df_res['Faltas'].sum())

    st.dataframe(df_res.style.apply(lambda x: ['color: red' if v > 0 else '' for v in x], subset=['Retrasos']), use_container_width=True, hide_index=True)
    
    if not df_det.empty:
        st.subheader("Detalle Diario")
        st.dataframe(df_det.sort_values(['Fecha', 'Nombre'], ascending=[False, True]), use_container_width=True, hide_index=True)
else:
    st.warning("No hay datos para mostrar.")
