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
    
    # 1. Verificar si hay una sesión activa en los parámetros de la URL (Para sobrevivir al Refresh)
    # Nota: Usamos query_params como un mecanismo simple de persistencia.
    if st.query_params.get("logged_in") == "true":
        st.session_state['authenticated'] = True
        # Intentar recuperar el usuario si es posible, sino default a 'Usuario'
        if 'user' not in st.session_state:
             st.session_state['user'] = "Usuario (Reconectado)"

    # 2. Inicializar estado de sesión si no existe
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        
    # 3. Si no está autenticado, mostrar Login
    if not st.session_state['authenticated']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("## 🔐 Acceso Restringido")
            st.markdown("Por favor ingrese sus credenciales para acceder al sistema biométrico.")
            
            with st.form("login_form"):
                username = st.text_input("Usuario")
                password = st.text_input("Contraseña", type="password")
                submit_button = st.form_submit_button("Ingresar")
                
                if submit_button:
                    if username in CREDENCIALES and CREDENCIALES[username] == password:
                        st.session_state['authenticated'] = True
                        st.session_state['user'] = username
                        
                        # GUARDAR SESIÓN EN URL: Esto permite actualizar la página sin salir
                        st.query_params["logged_in"] = "true"
                        
                        st.success("¡Acceso correcto!")
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos")
        return False
    return True

def logout():
    st.session_state['authenticated'] = False
    # Limpiar la URL al salir
    st.query_params.clear()
    st.rerun()

# --- CONSTANTES DE ARCHIVOS ---
FILE_USERS = 'usuarios.csv'
FILE_LOGS = 'registros.csv'
FILE_HOLIDAYS = 'feriados.csv'

# --- FUNCIONES DE UTILIDAD ---

@st.cache_data
def load_data(users_path, logs_path):
    """Carga los datos manejando errores de codificación (tildes/ñ)"""
    
    # 1. CARGAR USUARIOS
    df_users = None
    encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
    
    for encoding in encodings_to_try:
        try:
            df_users = pd.read_csv(users_path, sep=None, engine='python', dtype=str, encoding=encoding)
            break 
        except UnicodeDecodeError:
            continue 
        except Exception as e:
            return None, None, f"Error leyendo usuarios.csv: {e}"
            
    if df_users is None:
        return None, None, "Error: No se pudo leer el archivo de usuarios con ninguna codificación estándar."

    # Procesar columnas de usuarios
    try:
        df_users.columns = df_users.columns.str.lower().str.strip()
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
        return None, None, f"Error procesando columnas de usuarios: {e}"

    # 2. CARGAR REGISTROS (LOGS)
    df_logs_raw = None
    for encoding in encodings_to_try:
        try:
            df_logs_raw = pd.read_csv(logs_path, sep=None, engine='python', dtype=str, header=None, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return None, None, f"Error leyendo registros.csv: {e}"
            
    if df_logs_raw is None:
        return None, None, "Error: No se pudo leer el archivo de registros."

    try:
        valid_rows = []
        import re
        
        for index, row in df_logs_raw.astype(str).iterrows():
            line = " ".join(row.values)
            
            # Buscar fecha y hora
            date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})', line)
            time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
            
            if date_match and time_match:
                date_str = date_match.group(0)
                time_str = time_match.group(0)
                
                clean_line = line.replace(date_str, '').replace(time_str, '')
                id_match = re.search(r'\b\d{1,10}\b', clean_line)
                
                if id_match:
                    norm_date = date_str
                    if '/' in date_str:
                        parts = re.split(r'[-/]', date_str)
                        if len(parts[0]) == 4: 
                            norm_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
                        else: 
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
        return None, None, f"Error procesando registros.csv: {e}"
        
    return df_users, df_logs, None

def load_holidays(path):
    """Carga lista de feriados desde CSV"""
    holidays = set()
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, header=None, dtype=str)
            for val in df[0]:
                try:
                    dt = pd.to_datetime(val, dayfirst=True)
                    holidays.add(dt.strftime('%Y-%m-%d'))
                except:
                    continue
        except:
            pass
    return holidays

def get_workdays(year, month, holidays_set):
    """Devuelve días laborales excluyendo fines de semana y feriados"""
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, day) for day in range(1, num_days + 1)]
    return [d.strftime('%Y-%m-%d') for d in days if d.weekday() < 5 and d.strftime('%Y-%m-%d') not in holidays_set]

def time_to_min(t_str):
    try:
        h, m, s = map(int, t_str.split(':'))
        return h * 60 + m
    except:
        return 0

# --- LÓGICA PRINCIPAL DE LA APP ---

# 1. Verificar Login
if not check_password():
    st.stop() # Si no está logueado, detiene la ejecución aquí

# === A PARTIR DE AQUÍ SOLO SE EJECUTA SI ESTÁ LOGUEADO ===

# 2. Barra Lateral con Logout
with st.sidebar:
    st.write(f"👤 Usuario: **{st.session_state.get('user', 'Conectado')}**")
    if st.button("Cerrar Sesión", type="primary"):
        logout()
    st.markdown("---")

st.title("📊 Sistema de Control Biométrico")

# 3. Verificación de Archivos
if not os.path.exists(FILE_USERS) or not os.path.exists(FILE_LOGS):
    st.error("❌ Archivos de datos no encontrados.")
    st.markdown(f"**Instrucciones:** Sube `usuarios.csv` y `registros.csv` a tu repositorio GitHub.")
    st.stop()

# 4. Carga de Datos
df_users, df_logs, error_msg = load_data(FILE_USERS, FILE_LOGS)
holidays_set = load_holidays(FILE_HOLIDAYS)

if error_msg:
    st.error(error_msg)
    st.stop()

# 5. Configuración en Sidebar (continuación)
with st.sidebar:
    st.header("⚙️ Configuración")
    entry_time_input = st.time_input("Hora de Entrada Límite", value=time(8, 30))
    entry_limit_mins = entry_time_input.hour * 60 + entry_time_input.minute
    
    st.divider()
    st.success(f"✅ Datos cargados correctamente")
    st.caption(f"Empleados: {len(df_users)}")
    st.caption(f"Registros: {len(df_logs)}")
    
    if holidays_set:
        st.info(f"🏖️ {len(holidays_set)} Feriados cargados")
    else:
        st.warning("No se encontró 'feriados.csv'")

# 6. Lógica de Negocio y Visualización
df_logs['Fecha_DT'] = pd.to_datetime(df_logs['Fecha'])
df_logs['Mes_Str'] = df_logs['Fecha_DT'].dt.strftime('%Y-%m')

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

current_logs = df_logs[df_logs['Mes_Str'] == selected_month].copy()
daily_logs = current_logs.groupby(['ID', 'Fecha'])['Hora'].min().reset_index()

year, month = map(int, selected_month.split('-'))
workdays = get_workdays(year, month, holidays_set)
today_str = datetime.now().strftime('%Y-%m-%d')

results = []
detail_records = []

for _, user in df_users.iterrows():
    uid = user['ID']
    uname = user['Nombre']
    uarea = user['Area']
    
    if selected_area != "TODOS" and uarea != selected_area: continue
    if search_query:
        if search_query.lower() not in uname.lower() and search_query not in uid: continue

    u_logs = daily_logs[daily_logs['ID'] == uid]
    
    delays = 0
    delay_minutes = 0
    attended_dates = set()
    
    for _, row in u_logs.iterrows():
        log_date = row['Fecha']
        log_time = row['Hora']
        attended_dates.add(log_date)
        
        mins = time_to_min(log_time)
        is_late = mins > entry_limit_mins
        delay_amt = mins - entry_limit_mins if is_late else 0
        
        status = "RETRASO" if is_late else "PUNTUAL"
        if log_date in holidays_set: status += " (FERIADO)"

        if is_late:
            delays += 1
            delay_minutes += delay_amt
        
        detail_records.append({
            "Fecha": log_date, "Empleado": uname, "Area": uarea,
            "Hora": log_time, "Retraso (min)": delay_amt if is_late else 0,
            "Estado": status
        })

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
            if 'RETRASO' in val: return 'background-color: #ffcdd2; color: #b71c1c'
            elif 'PUNTUAL' in val: return 'background-color: #c8e6c9; color: #1b5e20'
            elif 'AUSENTE' in val: return 'background-color: #f5f5f5; color: #616161'
            return ''

        st.dataframe(
            df_detalle.style.applymap(color_status, subset=['Estado']),
            use_container_width=True, hide_index=True
        )
else:
    st.info("No se encontraron registros para mostrar.")
