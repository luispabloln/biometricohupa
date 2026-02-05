import streamlit as st
import pandas as pd
from datetime import datetime, time
import calendar
import os
import re

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Control Biométrico",
    page_icon="🔐",
    layout="wide"
)

# --- SEGURIDAD Y USUARIOS ---
CREDENCIALES = {
    "admin": "admin123",
    "joseh": "Jose123",
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
    """Carga datos con limpieza profunda de IDs y Areas"""
    
    # 1. USUARIOS
    df_users = None
    # 'utf-8-sig' ayuda a eliminar caracteres invisibles (BOM) al inicio del archivo
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
    
    for enc in encodings:
        try:
            df_users = pd.read_csv(users_path, sep=None, engine='python', dtype=str, encoding=enc)
            # Validar que tenga columnas
            if len(df_users.columns) > 1:
                break 
        except: continue
            
    if df_users is None: return None, None, "Error leyendo usuarios.csv"

    # Normalizar columnas de usuarios
    df_users.columns = df_users.columns.str.lower().str.strip()
    col_map = {}
    for col in df_users.columns:
        if 'nombre' in col or 'name' in col: col_map['nombre'] = col
        elif 'id' in col or 'codigo' in col: col_map['id'] = col
        elif 'area' in col or 'depto' in col: col_map['area'] = col
    
    if 'nombre' in col_map and 'id' in col_map:
        df_users = df_users.rename(columns={col_map['nombre']: 'Nombre', col_map['id']: 'ID'})
        df_users['Area'] = df_users[col_map['area']] if 'area' in col_map else 'GENERAL'
        
        # --- LIMPIEZA AGRESIVA ---
        # Quitar espacios al principio y final de TODOS los campos clave
        df_users['ID'] = df_users['ID'].astype(str).str.strip()
        df_users['Nombre'] = df_users['Nombre'].astype(str).str.strip()
        df_users['Area'] = df_users['Area'].astype(str).str.strip().str.upper() # Área en mayúsculas para unificar
        
        df_users = df_users[['ID', 'Nombre', 'Area']]
    else:
        return None, None, "Faltan columnas Nombre/ID en usuarios.csv"

    # 2. REGISTROS
    df_logs_raw = None
    for enc in encodings:
        try:
            # Leemos sin header para procesar línea por línea manualmente si es necesario
            df_logs_raw = pd.read_csv(logs_path, sep=None, engine='python', dtype=str, header=None, encoding=enc)
            if not df_logs_raw.empty:
                break
        except: continue
            
    if df_logs_raw is None: return None, None, "Error leyendo registros.csv"

    try:
        valid_rows = []
        # Regex patrones
        date_pattern = re.compile(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})|(\d{1,2}[-/]\d{1,2}[-/]\d{4})')
        time_pattern = re.compile(r'(\d{1,2}:\d{2}:\d{2})')
        
        for index, row in df_logs_raw.astype(str).iterrows():
            # Estrategia 1: Intentar leer columnas estructuradas (ID;Fecha;Hora)
            # Esto evita confundir otros números con el ID
            raw_id, raw_date, raw_time = None, None, None
            
            if len(row) >= 3:
                # Asumimos columna 0=ID, 1=Fecha, 2=Hora (formato estándar)
                c_id, c_date, c_time = str(row[0]), str(row[1]), str(row[2])
                
                # Validamos si parecen datos correctos
                if re.search(r'\d', c_id) and date_pattern.search(c_date) and time_pattern.search(c_time):
                    raw_id = c_id
                    raw_date = date_pattern.search(c_date).group(0)
                    raw_time = time_pattern.search(c_time).group(0)
            
            # Estrategia 2: Si falla la estructura, buscar patrones en toda la línea (backup)
            if not raw_id:
                line = " ".join(row.values)
                date_match = date_pattern.search(line)
                time_match = time_pattern.search(line)
                
                if date_match and time_match:
                    raw_date = date_match.group(0)
                    raw_time = time_match.group(0)
                    # Buscar ID quitando fecha y hora
                    clean_line = line.replace(raw_date, '').replace(raw_time, '')
                    id_match = re.search(r'\b\d{1,10}\b', clean_line)
                    if id_match:
                        raw_id = id_match.group(0)

            # PROCESAR DATOS ENCONTRADOS
            if raw_id and raw_date and raw_time:
                # Normalizar Fecha
                norm_date = raw_date
                if '/' in raw_date:
                    parts = re.split(r'[-/]', raw_date)
                    # Detección inteligente de formato:
                    # Si parte[0] es año (4 chars) -> YYYY-MM-DD
                    if len(parts[0]) == 4: 
                        norm_date = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                    # Si parte[2] es año (4 chars) -> DD-MM-YYYY -> YYYY-MM-DD
                    else: 
                        norm_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                
                valid_rows.append({
                    'ID': raw_id.strip(), # Strip crítico
                    'Fecha': norm_date,
                    'Hora': raw_time
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
        # Lunes=0, Domingo=6. Sábado(5) y Domingo(6) excluidos.
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

# Ordenar meses descendente
months = sorted(df_logs['Mes_Str'].unique(), reverse=True)
with col1: selected_month = st.selectbox("📅 Mes", months)

# Ordenar áreas alfabéticamente
areas = ["TODOS"] + sorted(df_users['Area'].unique().tolist())
with col2: selected_area = st.selectbox("🏢 Área", areas)

with col3: query = st.text_input("🔍 Buscar")

show_late = st.checkbox("Ver solo con retrasos")

# FILTRADO DE LOGS
logs_month = df_logs[df_logs['Mes_Str'] == selected_month].copy()
daily = logs_month.groupby(['ID', 'Fecha'])['Hora'].min().reset_index()

# DEBUG INFO (Muestra cantidad de registros procesados para dar confianza al usuario)
with st.sidebar:
    st.info(f"Registros totales en {selected_month}: **{len(daily)}**")
    if selected_area != "TODOS":
        users_in_area = len(df_users[df_users['Area'] == selected_area])
        st.caption(f"Empleados en {selected_area}: {users_in_area}")

year, month = map(int, selected_month.split('-'))
workdays = get_workdays(year, month, holidays)
today = datetime.now().strftime('%Y-%m-%d')

res = []
det = []

for _, u in df_users.iterrows():
    uid, name, area = u['ID'], u['Nombre'], u['Area']
    
    # Filtros
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

    # Cálculo de faltas inteligente
    # Si el mes seleccionado es PASADO, contar todos los dias.
    # Si es el mes ACTUAL, contar solo hasta HOY.
    # Si es mes FUTURO, 0 faltas.
    
    month_curr = datetime.now().strftime('%Y-%m')
    
    valid_days = []
    if selected_month < month_curr:
        valid_days = workdays # Mes pasado completo
    elif selected_month == month_curr:
        valid_days = [d for d in workdays if d <= today] # Mes actual hasta hoy
    else:
        valid_days = [] # Mes futuro

    absences = 0
    for d in valid_days:
        if d not in att_dates:
            absences += 1
            det.append({"Fecha": d, "Nombre": name, "Area": area, "Hora": "-", "Retraso": 0, "Estado": "AUSENTE"})

    if show_late and delays == 0: continue

    res.append({"ID": uid, "Nombre": name, "Area": area, "Retrasos": delays, "Minutos": delay_min, "Faltas": absences})

df_res = pd.DataFrame(res)
df_det = pd.DataFrame(det)

if not df_res.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Retrasos Totales", df_res['Retrasos'].sum())
    c2.metric("Minutos Totales", f"{df_res['Minutos'].sum()}")
    c3.metric("Faltas Totales", df_res['Faltas'].sum())

    st.dataframe(
        df_res.style.apply(lambda x: ['color: red' if v > 0 else '' for v in x], subset=['Retrasos']), 
        use_container_width=True, 
        hide_index=True
    )
    
    if not df_det.empty:
        st.subheader("Detalle Diario")
        # Colorear filas de Ausente en rojo claro en el detalle si es posible, o dejar simple
        st.dataframe(df_det.sort_values(['Fecha', 'Nombre'], ascending=[False, True]), use_container_width=True, hide_index=True)
else:
    st.warning("No se encontraron coincidencias. Verifica que los IDs en 'usuarios.csv' coincidan exactamente con 'registros.csv'.")


