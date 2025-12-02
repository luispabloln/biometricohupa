import streamlit as st
import pandas as pd
from datetime import datetime, time
import calendar

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Control Biométrico",
    page_icon="⏰",
    layout="wide"
)

# --- FUNCIONES DE UTILIDAD ---

def parse_users(file):
    """Detecta separadores y carga usuarios"""
    try:
        # Intentar leer detectando el motor automáticamente
        df = pd.read_csv(file, sep=None, engine='python', dtype=str)
        
        # Normalizar nombres de columnas a minúsculas
        df.columns = df.columns.str.lower().str.strip()
        
        # Buscar columnas clave
        col_map = {}
        for col in df.columns:
            if 'nombre' in col or 'name' in col:
                col_map['nombre'] = col
            elif 'id' in col or 'codigo' in col or 'user' in col:
                col_map['id'] = col
            elif 'area' in col or 'depto' in col:
                col_map['area'] = col
        
        if 'nombre' in col_map and 'id' in col_map:
            # Renombrar para estandarizar
            df = df.rename(columns={col_map['nombre']: 'Nombre', col_map['id']: 'ID'})
            df['Area'] = df[col_map['area']] if 'area' in col_map else 'GENERAL'
            return df[['ID', 'Nombre', 'Area']]
        else:
            st.error("No se encontraron columnas 'Nombre' o 'ID' en el archivo de usuarios.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer usuarios: {e}")
        return pd.DataFrame()

def parse_logs(file):
    """Detecta separadores y carga registros (logs)"""
    try:
        # Intentar leer detectando el motor automáticamente
        df = pd.read_csv(file, sep=None, engine='python', dtype=str, header=None)
        
        # Si tiene encabezados, pandas a veces los pone como fila 0 si no son obvios
        # Vamos a intentar detectar columnas por contenido (regex)
        
        # Convertir todo a string
        df = df.astype(str)
        
        valid_rows = []
        for index, row in df.iterrows():
            # Unir fila para buscar patrones
            line = " ".join(row.values)
            
            # Buscar fecha (YYYY-MM-DD o DD/MM/YYYY)
            # Regex para fechas
            import re
            date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})', line)
            
            # Buscar hora (HH:MM:SS)
            time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
            
            if date_match and time_match:
                date_str = date_match.group(0)
                time_str = time_match.group(0)
                
                # Buscar ID (número que no esté en la fecha/hora)
                # Limpiamos la fecha y hora de la línea para buscar el ID restante
                clean_line = line.replace(date_str, '').replace(time_str, '')
                # Buscar números restantes de 1 a 10 dígitos
                id_match = re.search(r'\b\d{1,10}\b', clean_line)
                
                if id_match:
                    # Normalizar fecha a YYYY-MM-DD
                    if '/' in date_str:
                        parts = re.split(r'[-/]', date_str)
                        if len(parts[0]) == 4: # YYYY-MM-DD
                            norm_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
                        else: # DD-MM-YYYY
                            norm_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    else:
                        norm_date = date_str

                    valid_rows.append({
                        'ID': id_match.group(0),
                        'Fecha': norm_date,
                        'Hora': time_str
                    })
        
        return pd.DataFrame(valid_rows)

    except Exception as e:
        st.error(f"Error al leer registros: {e}")
        return pd.DataFrame()

def get_workdays(year, month):
    """Devuelve una lista de fechas (strings) que son días laborales (Lun-Vie)"""
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, day) for day in range(1, num_days + 1)]
    # Filtrar solo lunes (0) a viernes (4)
    workdays = [d.strftime('%Y-%m-%d') for d in days if d.weekday() < 5]
    return workdays

def time_to_min(t_str):
    h, m, s = map(int, t_str.split(':'))
    return h * 60 + m

# --- INTERFAZ DE USUARIO ---

st.title("📊 Sistema de Control Biométrico")
st.markdown("Carga tus archivos para analizar asistencia, retrasos y faltas.")

# --- SIDEBAR: CONFIGURACIÓN Y CARGA ---
with st.sidebar:
    st.header("1. Cargar Datos")
    
    file_users = st.file_uploader("📂 Usuarios (CSV/Excel)", type=['csv', 'txt', 'xlsx', 'dat'])
    file_logs = st.file_uploader("📂 Asistencia (Logs)", type=['csv', 'txt', 'dat'])
    
    st.header("2. Configuración")
    entry_time_input = st.time_input("Hora de Entrada Límite", value=time(8, 30))
    entry_limit_mins = entry_time_input.hour * 60 + entry_time_input.minute
    
    st.info("Nota: Los archivos Excel (.xlsx) deben guardarse como CSV antes de subir si dan error.")

# --- LÓGICA PRINCIPAL ---

if file_users and file_logs:
    # 1. Procesar Archivos
    df_users = parse_users(file_users)
    df_logs = parse_logs(file_logs)
    
    if not df_users.empty and not df_logs.empty:
        
        # 2. Filtros
        st.divider()
        col1, col2, col3 = st.columns(3)
        
        # Filtro Mes
        df_logs['Fecha_DT'] = pd.to_datetime(df_logs['Fecha'])
        df_logs['Mes_Str'] = df_logs['Fecha_DT'].dt.strftime('%Y-%m')
        available_months = sorted(df_logs['Mes_Str'].unique(), reverse=True)
        
        with col1:
            selected_month = st.selectbox("📅 Seleccionar Mes", available_months)
        
        # Filtro Area
        available_areas = ["TODOS"] + sorted(df_users['Area'].unique().tolist())
        with col2:
            selected_area = st.selectbox("🏢 Departamento", available_areas)
            
        with col3:
            search_query = st.text_input("🔍 Buscar por Nombre o ID")
        
        show_only_late = st.checkbox("Ver solo con retrasos")

        # 3. Procesamiento de Datos
        
        # Filtrar logs por mes
        current_logs = df_logs[df_logs['Mes_Str'] == selected_month].copy()
        
        # Quedarse con la primera marca del día (Minima hora)
        daily_logs = current_logs.groupby(['ID', 'Fecha'])['Hora'].min().reset_index()
        
        # Obtener días laborales del mes seleccionado
        year, month = map(int, selected_month.split('-'))
        workdays = get_workdays(year, month)
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # Lista para resultados
        results = []
        detail_records = []

        # Procesar por usuario
        for _, user in df_users.iterrows():
            uid = user['ID']
            uname = user['Nombre']
            uarea = user['Area']
            
            # Filtros de búsqueda y área antes de calcular (optimización)
            if selected_area != "TODOS" and uarea != selected_area:
                continue
            if search_query:
                if search_query.lower() not in uname.lower() and search_query not in uid:
                    continue

            # Logs de este usuario
            u_logs = daily_logs[daily_logs['ID'] == uid]
            
            delays = 0
            delay_minutes = 0
            attended_dates = set()
            
            # Calcular Retrasos y llenar detalles
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
                
                status = "RETRASO" if is_late else "PUNTUAL"
                
                detail_records.append({
                    "Fecha": log_date,
                    "Empleado": uname,
                    "ID": uid,
                    "Area": uarea,
                    "Hora": log_time,
                    "Retraso (min)": delay_amt if is_late else 0,
                    "Estado": status
                })

            # Calcular Faltas
            # Días que debió trabajar (hasta hoy si es el mes actual)
            valid_days = [d for d in workdays if d <= today_str or selected_month < today_str[:7]]
            absences = 0
            
            for d in valid_days:
                if d not in attended_dates:
                    absences += 1
                    # Agregar al detalle como Ausente
                    detail_records.append({
                        "Fecha": d,
                        "Empleado": uname,
                        "ID": uid,
                        "Area": uarea,
                        "Hora": "-",
                        "Retraso (min)": 0,
                        "Estado": "AUSENTE"
                    })

            if show_only_late and delays == 0:
                continue

            results.append({
                "ID": uid,
                "Nombre": uname,
                "Area": uarea,
                "Retrasos": delays,
                "Minutos Acumulados": delay_minutes,
                "Faltas": absences
            })

        # Crear DataFrames finales
        df_resumen = pd.DataFrame(results)
        df_detalle = pd.DataFrame(detail_records)

        # 4. Mostrar Métricas
        if not df_resumen.empty:
            total_retrasos = df_resumen['Retrasos'].sum()
            total_minutos = df_resumen['Minutos Acumulados'].sum()
            total_faltas = df_resumen['Faltas'].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Retrasos", total_retrasos)
            m2.metric("Minutos Perdidos", f"{total_minutos} min")
            m3.metric("Faltas Estimadas", total_faltas)

            # 5. Tabla Resumen
            st.subheader("📋 Resumen General")
            st.dataframe(
                df_resumen.style.apply(lambda x: ['color: red' if v > 0 else '' for v in x], subset=['Retrasos', 'Minutos Acumulados']),
                use_container_width=True,
                hide_index=True
            )

            # 6. Tabla Detalle
            if not df_detalle.empty:
                st.subheader("📅 Detalle Diario")
                
                # Ordenar detalle
                df_detalle = df_detalle.sort_values(by=['Fecha', 'Empleado'], ascending=[False, True])
                
                # Colorear estado
                def color_status(val):
                    color = 'gray'
                    if val == 'RETRASO': color = '#ffcccc' # Rojo claro fondo
                    elif val == 'PUNTUAL': color = '#ccffcc' # Verde claro fondo
                    elif val == 'AUSENTE': color = '#eeeeee'
                    return f'background-color: {color}'

                st.dataframe(
                    df_detalle.style.applymap(color_status, subset=['Estado']),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.warning("No se encontraron datos con los filtros seleccionados.")
            
    else:
        st.warning("No se pudieron procesar los archivos. Verifica que el archivo de usuarios tenga columnas Nombre/ID y el de logs tenga fechas/horas.")

else:
    # Pantalla de bienvenida
    st.markdown("""
    ### 👋 ¡Bienvenido!
    
    Sube tus archivos en el menú de la izquierda para comenzar.
    
    **Formatos soportados:**
    * **Usuarios:** Archivo `.csv` con columnas `Nombre`, `ID`, `Area`.
    * **Asistencia:** Archivo `.dat` o `.csv` del biométrico (detecta fechas `DD/MM/YYYY` y `YYYY-MM-DD`).
    """)
