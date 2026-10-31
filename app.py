import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# Configuración general de la Web App
st.set_page_config(
    page_title="Austral Pack | Terminal Operativo de Planta",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# ESTILOS CSS PERSONALIZADOS (Aspecto Industrial Moderno)
# ==============================================================================
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        border-left: 6px solid #38bdf8;
    }
    .main-header h1 {
        color: white !important;
        margin: 0;
        font-size: 1.9rem;
        font-weight: 700;
    }
    .main-header p {
        color: #cbd5e1;
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
    }
    .semaforo-box {
        padding: 1.1rem;
        border-radius: 10px;
        font-weight: 600;
        margin-top: 0.8rem;
        margin-bottom: 0.8rem;
    }
    .sem-verde { background-color: #dcfce7; color: #166534; border-left: 6px solid #22c55e; }
    .sem-amarillo { background-color: #fef9c3; color: #854d0e; border-left: 6px solid #eab308; }
    .sem-rojo { background-color: #fee2e2; color: #991b1b; border-left: 6px solid #ef4444; }
    .sem-error { background-color: #f3e8ff; color: #6b21a8; border-left: 6px solid #a855f7; }
    
    .pasaporte-lote {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-top: 4px solid #0284c7;
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. BASE DE DATOS EN PYTHON (Multicliente y Multiturno)
# ==============================================================================
def init_db(force_reset=False):
    conn = sqlite3.connect("organizador_australpack.db")
    c = conn.cursor()
    
    if force_reset:
        c.execute("DROP TABLE IF EXISTS bitacora_lotes")
        c.execute("DROP TABLE IF EXISTS tareas_planta")
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS bitacora_lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT,
            id_lote TEXT,
            cliente TEXT,
            maquina TEXT,
            turno TEXT,
            responsable TEXT,
            humedad_pct REAL,
            minutos_detencion INTEGER,
            estado_regla TEXT,
            decision_operativa TEXT,
            validacion_turno TEXT,
            nota_bitacora TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS tareas_planta (
            id_tarea INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_creacion TEXT,
            id_lote_asociado TEXT,
            maquina TEXT,
            prioridad TEXT,
            asignado_a TEXT,
            repuesto_disponible TEXT,
            estado_tarea TEXT,
            descripcion_accion TEXT
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM bitacora_lotes")
    if c.fetchone()[0] == 0:
        lotes_semilla = [
            ("2026-10-27 22:15", "LOTE-FS-479", "Frutos del Sur Export", "Troqueladora-01 (Crítica)", "Noche", "Paula Jara (Operadora de Turno)", 7.1, 5, "🟢 VERDE (Normal)", "OK: Parámetros dentro de estándar. Lote autorizado.", "Parámetro Validado OK", "Operación fluida en primera mitad del turno nocturno."),
            ("2026-10-28 07:46", "LOTE-FS-480", "Frutos del Sur Export", "Troqueladora-01 (Crítica)", "Noche", "Paula Jara (Operadora de Turno)", 9.4, 20, "🟡 AMARILLO (Observar)", "Observar sin detener línea; revisar al cierre de formato.", "Excepción de Formato / Ruido Normal de Planta (Falso Positivo)", "Cartón con leve humedad por condensación nocturna. Se priorizó continuidad del despacho."),
            ("2026-10-28 15:10", "LOTE-FS-481", "Frutos del Sur Export", "Troqueladora-01 (Crítica)", "Día", "Camila Figueroa (Jefa de Calidad)", 6.8, 0, "🟢 VERDE (Normal)", "Lote liberado a despacho frigorífico.", "Parámetro Validado OK", "Control de calidad normal, sin deformación en prueba de frío."),
            ("2026-10-29 03:20", "LOTE-AP-109", "AgroSur Export", "Troqueladora-01 (Crítica)", "Noche", "Óscar Leiva (Mantenimiento)", 11.5, 45, "🔴 ROJO (Detener)", "Detener troqueladora y abrir orden de mantenimiento.", "Falla Real Confirmada (Requiere Intervención)", "Desajuste en troquel y exceso de humedad. Se detuvo línea y se reemplazó pieza."),
            ("2026-10-29 11:30", "LOTE-VA-204", "Viña Austral", "Corrugadora-01", "Día", "Martín Reyes (Jefe de Producción)", 8.5, 15, "🟡 AMARILLO (Observar)", "Desviación moderada. Revisar tensión al cambio de turno.", "Excepción de Formato / Ruido Normal de Planta (Falso Positivo)", "Ajuste menor por cambio de gramaje en caja de exportación.")
        ]
        c.executemany('''
            INSERT INTO bitacora_lotes 
            (fecha_hora, id_lote, cliente, maquina, turno, responsable, humedad_pct, minutos_detencion, estado_regla, decision_operativa, validacion_turno, nota_bitacora)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', lotes_semilla)
        
        tareas_semilla = [
            ("2026-10-28 08:00", "LOTE-FS-480", "Troqueladora-01 (Crítica)", "Media (Ventana Programada)", "Óscar Leiva (Mantenimiento)", "Sí (En bodega)", "En Proceso", "Calibrar sensor de humedad y revisar cuchillas en cambio de turno sin frenar planta."),
            ("2026-10-29 03:25", "LOTE-AP-109", "Troqueladora-01 (Crítica)", "Alta (Detención Inmediata)", "Óscar Leiva (Mantenimiento)", "Sí (En bodega)", "Completada", "Cambio de sello mecánico y validación manual junto a Calidad."),
            ("2026-10-29 11:40", "LOTE-VA-204", "Corrugadora-01", "Media (Ventana Programada)", "Óscar Leiva (Mantenimiento)", "Sí (En bodega)", "Pendiente", "Inspeccionar rodillos al finalizar corrida de Viña Austral.")
        ]
        c.executemany('''
            INSERT INTO tareas_planta
            (fecha_creacion, id_lote_asociado, maquina, prioridad, asignado_a, repuesto_disponible, estado_tarea, descripcion_accion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', tareas_semilla)
        conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. REGLA DE DECISIÓN EXPLÍCITA Y MANEJO DE ERRORES
# ==============================================================================
def evaluar_lote(humedad, min_detencion, codigo_lote):
    if not codigo_lote.strip():
        return "⚠️ ERROR: LOTE VACÍO", "Falta identificar el código de lote/pallet. No se puede registrar sin trazabilidad.", "error"
    if humedad <= 0 or humedad > 35 or min_detencion < 0 or min_detencion > 480:
        return (
            "⚠️ ERROR: DATO FUERA DE RANGO (Contingencia Manual)",
            "Valor físicamente inválido o error de lectura del sensor. Se bloquea alerta automática y se exige validación manual de Calidad con higrómetro de respaldo.",
            "error"
        )
    
    if humedad > 10.0 or min_detencion >= 30:
        return (
            "🔴 ROJO (Detener e Intervenir)",
            "CRÍTICO: Alto riesgo de deformación en frío (>10% humedad) o parada prolongada en troqueladora. Detener línea, retener lote y asignar tarea a Mantenimiento.",
            "rojo"
        )
    elif (8.0 <= humedad <= 10.0) or (10 <= min_detencion < 30):
        return (
            "🟡 AMARILLO (Observar sin Detener)",
            "PRECAUCIÓN: Desviación moderada. NO detener la operación; anotar observación de turno y programar revisión al terminar el formato actual.",
            "amarillo"
        )
    else:
        return (
            "🟢 VERDE (Operación Normal)",
            "OK: Parámetros dentro de estándar (<8% humedad y sin detenciones críticas). Lote autorizado para continuar flujo a frigorífico.",
            "verde"
        )

# ==============================================================================
# 3. BARRA LATERAL (Guía Rápida para el Operador en Planta)
# ==============================================================================
with st.sidebar:
    st.markdown("### 🏭 Panel de Control en Piso")
    st.caption("Estado del Sistema: **🟢 Conectado (SQLite Activo)**")
    st.divider()
    
    st.markdown("#### 🚦 Regla Operativa de Turno")
    st.markdown("""
    * **🟢 VERDE:** Humedad `< 8%` y Parada `< 10 min` ➔ *Flujo normal.*
    * **🟡 AMARILLO:** Humedad `8% - 10%` o Parada `10 - 29 min` ➔ *Observar, NO detener máquina.*
    * **🔴 ROJO:** Humedad `> 10%` o Parada `≥ 30 min` ➔ *Detener línea y llamar a Mantenimiento.*
    * **⚠️ ERROR:** Dato `< 0%` o `> 35%` ➔ *Activar Contingencia Manual.*
    """)
    st.divider()
    
    st.markdown("#### 🛡️ Resguardo del Trabajador")
    st.info("Ninguna alerta detiene la planta automáticamente ni genera sanciones. Todo evento requiere validación del operador en terreno.")
    
    if st.button("🔄 Restaurar Datos de Demostración", use_container_width=True):
        init_db(force_reset=True)
        st.toast("Base de datos restaurada con lotes multimarca.", icon="✅")
        st.rerun()

# ==============================================================================
# 4. ENCABEZADO INDUSTRIAL Y RESUMEN OPERATIVO EN VIVO
# ==============================================================================
st.markdown("""
<div class="main-header">
    <h1>🏭 Austral Pack Circular SpA — Terminal de Trazabilidad y Planta</h1>
    <p>Bitácora unificada de Calidad, Producción y Mantenimiento | Control continuo por Lote, Línea y Turno</p>
</div>
""", unsafe_allow_html=True)

conn = sqlite3.connect("organizador_australpack.db")
df_metricas_lotes = pd.read_sql_query("SELECT * FROM bitacora_lotes", conn)
df_metricas_tareas = pd.read_sql_query("SELECT * FROM tareas_planta", conn)
conn.close()

total_lotes = len(df_metricas_lotes)
humedad_prom = df_metricas_lotes["humedad_pct"].mean() if total_lotes > 0 else 0
min_totales_paro = df_metricas_lotes["minutos_detencion"].sum() if total_lotes > 0 else 0
tareas_pend = len(df_metricas_tareas[df_metricas_tareas["estado_tarea"] != "Completada"])

m1, m2, m3, m4 = st.columns(4)
with m1:
    with st.container(border=True):
        st.metric("📦 Lotes Trazados en BD", f"{total_lotes} pallets", "100% con ID único")
with m2:
    with st.container(border=True):
        delta_h = "Dentro de meta (<8%)" if humedad_prom <= 8.0 else "Atención (>8%)"
        st.metric("💧 Humedad Promedio Cartón", f"{humedad_prom:.1f} %", delta_h, delta_color="normal" if humedad_prom <= 8.0 else "inverse")
with m3:
    with st.container(border=True):
        st.metric("⏱️ Tiempo Acumulado Detención", f"{min_totales_paro} min", "Monitoreo de líneas activas", delta_color="off")
with m4:
    with st.container(border=True):
        st.metric("🛠️ Órdenes Mantenimiento Activas", f"{tareas_pend} pendientes", "Con control de repuestos", delta_color="inverse" if tareas_pend > 2 else "normal")

# ==============================================================================
# 5. PESTAÑAS OPERATIVAS GENERALES DE PLANTA
# ==============================================================================
tab1, tab2, tab3 = st.tabs([
    "📝 1. Anotar Lote y Turno (Operación)",
    "📊 2. Mantenimiento y Gráficos de Planta",
    "🔍 3. Historial y Auditoría de Lotes"
])

# ------------------------------------------------------------------------------
# PESTAÑA 1: ANOTADOR UNIFICADO
# ------------------------------------------------------------------------------
with tab1:
    col_a, col_b = st.columns([1, 1])
    
    with col_a:
        with st.container(border=True):
            st.markdown("#### 📦 1. Identificación del Lote y Turno")
            st.caption("Unifica el código QR del pallet con el cliente, el equipo y el turno responsable.")
            
            c_in1, c_in2 = st.columns(2)
            id_lote = c_in1.text_input("Código de Lote / QR Pallet", value="LOTE-AP-501")
            cliente = c_in2.selectbox("Cliente Destino", [
                "Frutos del Sur Export",
                "AgroSur Export",
                "Viña Austral",
                "Salmones del Pacífico",
                "Mercado Interno General"
            ])
            
            c_in3, c_in4 = st.columns(2)
            maquina = c_in3.selectbox("Equipo / Línea", ["Troqueladora-01 (Crítica)", "Corrugadora-01", "Pegadora-02", "Bodega Frío"])
            turno = c_in4.radio("Turno Operativo", ["Día", "Noche"], horizontal=True)
            
            responsable = st.selectbox("Operador / Especialista que registra", [
                "Paula Jara (Operadora de Turno)",
                "Camila Figueroa (Jefa de Calidad)",
                "Óscar Leiva (Mantenimiento)",
                "Martín Reyes (Jefe de Producción)"
            ])

    with col_b:
        with st.container(border=True):
            st.markdown("#### 📡 2. Parámetros del Proceso y Diagnóstico")
            modo_prueba_error = st.toggle("🧪 Simular Falla de Sensor / Dato Fuera de Rango (Prueba de Contingencia)")
            
            p1, p2 = st.columns(2)
            if modo_prueba_error:
                humedad = p1.number_input("Humedad del Cartón (%) [1% a 35%]", value=-15.0, step=1.0)
                min_detencion = p2.number_input("Minutos de Detención [0 a 480]", value=600, step=5)
            else:
                humedad = p1.number_input("Humedad del Cartón (%) [Meta ≤ 8.0%]", min_value=-50.0, max_value=100.0, value=7.4, step=0.2)
                min_detencion = p2.number_input("Minutos Detención en Turno", min_value=-10, max_value=600, value=0, step=5)

            estado_regla, decision_texto, color = evaluar_lote(humedad, min_detencion, id_lote)
            
            clase_css = {
                "verde": "sem-verde",
                "amarillo": "sem-amarillo",
                "rojo": "sem-rojo",
                "error": "sem-error"
            }[color]
            
            st.markdown(f"""
            <div class="semaforo-box {clase_css}">
                <div style="font-size: 1.1rem; margin-bottom: 4px;">{estado_regla}</div>
                <div style="font-weight: 400; font-size: 0.92rem;">{decision_texto}</div>
            </div>
            """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("#### 🛡️ 3. Validación Humana del Turno (Evita sanciones por falsos positivos)")
        c1, c2 = st.columns([1, 2])
        with c1:
            validacion_turno = st.selectbox("Clasificación en Terreno por el Operador", [
                "Parámetro Validado OK",
                "Falla Real Confirmada (Requiere Intervención)",
                "Excepción de Formato / Ruido Normal de Planta (Falso Positivo)",
                "Registro en Contingencia Manual (Falla de Instrumento)"
            ])
            crear_tarea_auto = st.checkbox(
                "📌 Generar orden automática a Mantenimiento", 
                value=(color in ["rojo", "amarillo"])
            )
        with c2:
            nota_bitacora = st.text_area(
                "Anotación de bitácora del turno (Qué ocurrió y qué acción se tomó):",
                value="Lote procesado sin novedades. Formato estándar revisado por operador en línea.",
                height=100
            )

        if st.button("💾 Guardar Registro Oficial en Base de Datos", type="primary", use_container_width=True):
            if not id_lote.strip():
                st.error("⚠️ Error de validación: Debe ingresar un Código de Lote identificable antes de guardar.")
            else:
                ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
                conn = sqlite3.connect("organizador_australpack.db")
                c = conn.cursor()
                c.execute('''
                    INSERT INTO bitacora_lotes
                    (fecha_hora, id_lote, cliente, maquina, turno, responsable, humedad_pct, minutos_detencion, estado_regla, decision_operativa, validacion_turno, nota_bitacora)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ahora, id_lote.strip().upper(), cliente, maquina, turno, responsable, humedad, min_detencion, estado_regla, decision_texto, validacion_turno, nota_bitacora))
                
                if crear_tarea_auto:
                    prioridad_t = "Alta (Detención Inmediata)" if color == "rojo" else "Media (Ventana Programada)"
                    c.execute('''
                        INSERT INTO tareas_planta
                        (fecha_creacion, id_lote_asociado, maquina, prioridad, asignado_a, repuesto_disponible, estado_tarea, descripcion_accion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (ahora, id_lote.strip().upper(), maquina, prioridad_t, "Óscar Leiva (Mantenimiento)", "Por verificar", "Pendiente", nota_bitacora))
                
                conn.commit()
                conn.close()
                st.toast(f"Lote {id_lote.upper()} guardado con éxito", icon="✅")
                st.rerun()

# ------------------------------------------------------------------------------
# PESTAÑA 2: GRÁFICOS DE PLANTA Y ORGANIZADOR DE MANTENIMIENTO
# ------------------------------------------------------------------------------
with tab2:
    st.markdown("#### 📈 Panel Visual de Comportamiento de Planta")
    g1, g2 = st.columns(2)
    
    with g1:
        with st.container(border=True):
            st.markdown("**⏱️ Minutos de Detención por Turno y Máquina**")
            st.caption("Permite comparar dónde se concentran las esperas para programar ventanas de mantenimiento.")
            if not df_metricas_lotes.empty:
                df_paradas = df_metricas_lotes.groupby(["turno", "maquina"])["minutos_detencion"].sum().unstack(fill_value=0)
                st.bar_chart(df_paradas, height=250)
            else:
                st.info("Sin datos para graficar.")

    with g2:
        with st.container(border=True):
            st.markdown("**💧 Curva de Humedad del Cartón (%) por Lote Registrado**")
            st.caption("Monitoreo de tendencia frente al límite de precaución (8%) y crítico (10%) por deformación en frío.")
            if not df_metricas_lotes.empty:
                df_hum = df_metricas_lotes[(df_metricas_lotes["humedad_pct"] > 0) & (df_metricas_lotes["humedad_pct"] <= 35)].copy()
                df_hum = df_hum.set_index("id_lote")[["humedad_pct"]]
                st.area_chart(df_hum, color="#0284c7", height=250)
            else:
                st.info("Sin datos para graficar.")

    st.divider()
    st.markdown("#### 🛠️ Gestión de Órdenes de Mantenimiento y Stock de Repuestos")
    
    col_gest1, col_gest2 = st.columns([1, 1])
    
    with col_gest1:
        with st.expander("➕ Crear Nueva Orden de Mantenimiento Manual", expanded=False):
            with st.form("nueva_tarea_form"):
                f1, f2 = st.columns(2)
                lote_t = f1.text_input("Lote Asociado", value="LOTE-AP-501")
                maq_t = f2.selectbox("Equipo", ["Troqueladora-01 (Crítica)", "Corrugadora-01", "Sistema Sensores / QR"])
                
                f3, f4 = st.columns(2)
                prio_t = f3.selectbox("Prioridad", ["Media (Ventana Programada)", "Alta (Detención Inmediata)", "Baja (Inspección Rutinaria)"])
                asig_t = f4.selectbox("Responsable", ["Óscar Leiva (Mantenimiento)", "Camila Figueroa (Calidad)", "Martín Reyes (Producción)"])
                
                f5, f6 = st.columns(2)
                rep_t = f5.selectbox("¿Repuesto en Stock?", ["Sí (En bodega)", "No (Solicitar compra)", "No requiere repuesto"])
                est_t = f6.selectbox("Estado Inicial", ["Pendiente", "En Proceso", "Completada"])
                
                desc_t = st.text_input("Protocolo o intervención a realizar:")
                if st.form_submit_button("➕ Registrar Orden", use_container_width=True):
                    conn = sqlite3.connect("organizador_australpack.db")
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO tareas_planta
                        (fecha_creacion, id_lote_asociado, maquina, prioridad, asignado_a, repuesto_disponible, estado_tarea, descripcion_accion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (datetime.now().strftime("%Y-%m-%d %H:%M"), lote_t.upper(), maq_t, prio_t, asig_t, rep_t, est_t, desc_t))
                    conn.commit()
                    conn.close()
                    st.toast("Orden agregada correctamente", icon="🛠️")
                    st.rerun()

    with col_gest2:
        with st.expander("⚡ Actualizar Estado o Repuesto de una Orden en Vivo", expanded=False):
            if not df_metricas_tareas.empty:
                opciones_tareas = df_metricas_tareas.apply(
                    lambda r: f"#{r['id_tarea']} | {r['id_lote_asociado']} - {r['maquina']} ({r['estado_tarea']})", axis=1
                ).tolist()
                seleccion = st.selectbox("Seleccionar Orden a actualizar:", opciones_tareas)
                id_sel = int(seleccion.split("|")[0].replace("#", "").strip())
                
                u1, u2 = st.columns(2)
                nuevo_estado = u1.selectbox("Nuevo Estado:", ["Pendiente", "En Proceso", "Completada"])
                nuevo_rep = u2.selectbox("Disponibilidad de Repuesto:", ["Sí (En bodega)", "No (Solicitar compra)", "No requiere repuesto"])
                
                if st.button("🔄 Actualizar Orden Seleccionada", use_container_width=True):
                    conn = sqlite3.connect("organizador_australpack.db")
                    c = conn.cursor()
                    c.execute("UPDATE tareas_planta SET estado_tarea = ?, repuesto_disponible = ? WHERE id_tarea = ?", (nuevo_estado, nuevo_rep, id_sel))
                    conn.commit()
                    conn.close()
                    st.toast(f"Orden #{id_sel} actualizada a {nuevo_estado}", icon="✅")
                    st.rerun()

    filtro_estado = st.radio("Filtrar bandeja de órdenes por estado:", ["Todas", "Pendiente", "En Proceso", "Completada"], horizontal=True)
    df_tareas_vista = df_metricas_tareas if filtro_estado == "Todas" else df_metricas_tareas[df_metricas_tareas["estado_tarea"] == filtro_estado]
        
    st.dataframe(
        df_tareas_vista,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id_tarea": st.column_config.NumberColumn("ID", width="small"),
            "fecha_creacion": "Fecha / Hora",
            "id_lote_asociado": "📦 Lote",
            "maquina": "⚙️ Equipo",
            "prioridad": "🚨 Prioridad",
            "asignado_a": "👷 Responsable",
            "repuesto_disponible": "🔩 Stock Repuesto",
            "estado_tarea": "📌 Estado",
            "descripcion_accion": "Detalle de Intervención"
        }
    )

# ------------------------------------------------------------------------------
# PESTAÑA 3: BUSCADOR GENERAL DE TRAZABILIDAD Y AUDITORÍA (< 5 SEGUNDOS)
# ------------------------------------------------------------------------------
with tab3:
    st.markdown("#### 🔍 Consulta Instantánea de Trazabilidad y Auditoría de Lotes")
    st.caption("Reconstruye la historia verificable de cualquier lote y cliente en menos de 5 segundos: qué ocurrió, quién revisó y cómo se actuó.")
    
    c_busq1, c_busq2 = st.columns([2, 1])
    texto_buscar = c_busq1.text_input("🔎 Buscar por Código de Lote, Cliente, Máquina o Responsable (Ej: LOTE-FS-480, AgroSur, Viña Austral):", "")
    filtro_alerta = c_busq2.selectbox("Filtrar por Nivel de Alerta:", ["Todos", "🟢 VERDE", "🟡 AMARILLO", "🔴 ROJO", "⚠️ ERROR"])
    
    df_resultado = df_metricas_lotes.copy().sort_values(by="id", ascending=False)
    if texto_buscar:
        df_resultado = df_resultado[
            df_resultado["id_lote"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["cliente"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["maquina"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["responsable"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["nota_bitacora"].str.contains(texto_buscar, case=False, na=False)
        ]
    if filtro_alerta != "Todos":
        df_resultado = df_resultado[df_resultado["estado_regla"].str.contains(filtro_alerta[:5], case=False, na=False)]

    if not df_resultado.empty:
        registro_destacado = df_resultado.iloc[0]
        st.markdown(f"""
        <div class="pasaporte-lote">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #cbd5e1; padding-bottom:8px; margin-bottom:10px;">
                <span style="font-size:1.15rem; font-weight:700; color:#0f172a;">📄 Certificado de Trazabilidad — {registro_destacado['id_lote']}</span>
                <span style="background:#e0f2fe; color:#0369a1; padding:4px 10px; border-radius:6px; font-weight:600; font-size:0.85rem;">
                    Fecha Registro: {registro_destacado['fecha_hora']} | Turno: {registro_destacado['turno']}
                </span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; font-size:0.92rem; margin-bottom:10px;">
                <div><b>Cliente:</b><br>{registro_destacado['cliente']}</div>
                <div><b>Equipo / Línea:</b><br>{registro_destacado['maquina']}</div>
                <div><b>Parámetros Medidos:</b><br>Humedad: {registro_destacado['humedad_pct']}% | Parada: {registro_destacado['minutos_detencion']} min</div>
                <div><b>Responsable en Piso:</b><br>{registro_destacado['responsable']}</div>
            </div>
            <div style="background:white; padding:10px; border-radius:6px; border:1px solid #e2e8f0; font-size:0.9rem;">
                <b>Diagnóstico del Sistema:</b> {registro_destacado['estado_regla']} — <i>{registro_destacado['decision_operativa']}</i><br>
                <b>Validación Humana del Turno:</b> {registro_destacado['validacion_turno']}<br>
                <b>Observación Registrada:</b> "{registro_destacado['nota_bitacora']}"
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.dataframe(
        df_resultado,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("N°", width="small"),
            "fecha_hora": "Fecha y Hora",
            "id_lote": "📦 Código Lote",
            "cliente": "🏢 Cliente",
            "maquina": "⚙️ Máquina",
            "turno": "🌙/☀️ Turno",
            "responsable": "👷 Operador / Validador",
            "humedad_pct": st.column_config.NumberColumn("💧 Humedad (%)", format="%.1f %%"),
            "minutos_detencion": st.column_config.NumberColumn("⏱️ Parada (min)", format="%d min"),
            "estado_regla": "🚦 Semáforo",
            "decision_operativa": "Regla Aplicada",
            "validacion_turno": "🛡️ Validación Humana",
            "nota_bitacora": "📝 Nota del Turno"
        }
    )
    
    csv_auditoria = df_resultado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Certificado Oficial de Trazabilidad (CSV / Excel)",
        data=csv_auditoria,
        file_name="Historial_Trazabilidad_AustralPack.csv",
        mime="text/csv",
        use_container_width=True
    )
