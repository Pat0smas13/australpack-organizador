import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# Configuración general de la Web App
st.set_page_config(
    page_title="Austral Pack | Organizador de Planta y Trazabilidad",
    page_icon="📋",
    layout="wide"
)

# ==============================================================================
# 1. BASE DE DATOS EN PYTHON (Unifica Planilla Calidad + Detenciones + Turnos)
# ==============================================================================
def init_db():
    conn = sqlite3.connect("organizador_australpack.db")
    c = conn.cursor()
    
    # Tabla 1: Bitácora de Lotes, Calidad y Notas de Turno
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
    
    # Tabla 2: Organizador de Tareas y Ventanas de Mantenimiento
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
    
    # Datos iniciales del caso para que la app ya tenga historia al abrir el link
    c.execute("SELECT COUNT(*) FROM bitacora_lotes")
    if c.fetchone()[0] == 0:
        lotes_semilla = [
            ("2026-10-28 07:46", "LOTE-FS-480", "Frutos del Sur Export", "Troqueladora-01", "Noche", "Paula Jara (Operadora)", 9.4, 15, "🟡 AMARILLO (Observar)", "Observar sin detener línea; revisar al cierre de formato.", "Excepción de Formato / Ruido", "Cartón con leve humedad por condensación nocturna. Se priorizó continuidad del despacho."),
            ("2026-10-28 15:10", "LOTE-FS-481", "Frutos del Sur Export", "Troqueladora-01", "Día", "Camila Figueroa (Calidad)", 6.8, 0, "🟢 VERDE (Normal)", "Lote liberado a despacho frigorífico.", "Parámetro Validado OK", "Control de calidad normal, sin deformación en prueba de frío."),
            ("2026-10-29 03:20", "LOTE-AP-109", "AgroSur Export", "Troqueladora-01", "Noche", "Óscar Leiva (Mantenimiento)", 11.5, 45, "🔴 ROJO (Detener)", "Detener troqueladora y abrir orden de mantenimiento.", "Falla Real Confirmada", "Desajuste en troquel y exceso de humedad. Se detuvo línea y se reemplazó pieza.")
        ]
        c.executemany('''
            INSERT INTO bitacora_lotes 
            (fecha_hora, id_lote, cliente, maquina, turno, responsable, humedad_pct, minutos_detencion, estado_regla, decision_operativa, validacion_turno, nota_bitacora)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', lotes_semilla)
        
        tareas_semilla = [
            ("2026-10-28 08:00", "LOTE-FS-480", "Troqueladora-01", "Media (Ventana Programada)", "Óscar Leiva (Mantenimiento)", "Sí (En bodega)", "En Proceso", "Calibrar sensor de humedad y revisar cuchillas en cambio de turno sin frenar planta."),
            ("2026-10-29 03:25", "LOTE-AP-109", "Troqueladora-01", "Alta (Detención Inmediata)", "Óscar Leiva (Mantenimiento)", "Sí (En bodega)", "Completada", "Cambio de sello mecánico y validación manual junto a Calidad.")
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
# 2. REGLA DE DECISIÓN EXPLÍCITA Y MANEJO DE ERRORES (Exigencia Sección 9)
# ==============================================================================
def evaluar_lote(humedad, min_detencion, codigo_lote):
    """
    Evalúa los datos ingresados, detecta errores o valores fuera de rango
    y clasifica qué exige detener vs qué permite observar.
    """
    # 1. Manejo de error o dato faltante / fuera de rango
    if not codigo_lote.strip():
        return "⚠️ ERROR: LOTE VACÍO", "Falta identificar el código de lote/pallet. No se puede registrar sin trazabilidad.", "error"
    if humedad <= 0 or humedad > 35 or min_detencion < 0 or min_detencion > 480:
        return (
            "⚠️ ERROR: DATO FUERA DE RANGO (Contingencia Manual)",
            "Valor físicamente inválido o error de lectura. Se bloquea alerta automática y se exige validación manual de Calidad para no degradar la inspección.",
            "error"
        )
    
    # 2. Regla de 3 niveles (Respuesta al turno nocturno y calidad)
    if humedad > 10.0 or min_detencion >= 30:
        return (
            "🔴 ROJO (Detener e Intervenir)",
            "CRÍTICO: Alto riesgo de deformación en frío (>10% humedad) o parada prolongada en troqueladora. Detener línea, retener lote y asignar tarea a Mantenimiento.",
            "rojo"
        )
    elif (8.0 <= humedad <= 10.0) or (10 <= min_detencion < 30):
        return (
            "🟡 AMARILLO (Observar sin Detener)",
            "PRECAUCIÓN: Desviación moderada. NO detener la operación; anotar observación de turno y programar revisión al terminar el formato.",
            "amarillo"
        )
    else:
        return (
            "🟢 VERDE (Operación Normal)",
            "OK: Parámetros dentro de estándar. Lote autorizado para continuar proceso sin restricciones.",
            "verde"
        )

# ==============================================================================
# 3. INTERFAZ WEB DE ORGANIZACIÓN Y ANOTACIÓN
# ==============================================================================
st.title("📋 Austral Pack Circular SpA — Organizador y Bitácora de Trazabilidad")
st.markdown("Sistema centralizado para eliminar planillas aisladas, organizar tareas de mantenimiento y responder auditorías en segundos.")

tab1, tab2, tab3, tab4 = st.tabs([
    "📝 1. Anotar Lote y Turno",
    "🛠️ 2. Organizador de Tareas y Mantenimiento",
    "🔍 3. Buscador de Auditoría (Frutos del Sur)",
    "📊 4. Evaluación Financiera y KPIs"
])

# ------------------------------------------------------------------------------
# PESTAÑA 1: ANOTADOR UNIFICADO (Calidad + Detenciones + Voz del Turno)
# ------------------------------------------------------------------------------
with tab1:
    st.subheader("Bitácora Digital de Producción, Calidad y Turno")
    st.info("💡 **Qué resuelve:** Reemplaza en un solo formulario la planilla de calidad, el registro de paradas y los mensajes sueltos del turno.")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("#### 1. Identificación del Lote y Turno")
        id_lote = st.text_input("Código de Lote / Pallet (Ej: LOTE-FS-482)", value="LOTE-FS-482")
        cliente = st.selectbox("Cliente Asociado", ["Frutos del Sur Export", "AgroSur Export", "Viña Austral", "Mercado Interno"])
        maquina = st.selectbox("Equipo / Línea", ["Troqueladora-01 (Crítica)", "Corrugadora-01", "Pegadora-02", "Bodega Frío"])
        turno = st.radio("Turno", ["Día", "Noche"], horizontal=True)
        responsable = st.selectbox("Persona que realiza la anotación", [
            "Paula Jara (Operadora de Turno)",
            "Camila Figueroa (Jefa de Calidad)",
            "Óscar Leiva (Mantenimiento)",
            "Martín Reyes (Jefe de Producción)"
        ])

    with col_b:
        st.markdown("#### 2. Parámetros del Proceso y Prueba de Errores")
        modo_prueba_error = st.checkbox("🧪 Activar modo de prueba de error (Ingresa valores fuera de rango para demostrar validación)")
        
        if modo_prueba_error:
            humedad = st.number_input("Humedad del Cartón (%) [Rango válido: 1% a 35%]", value=-15.0, step=1.0)
            min_detencion = st.number_input("Minutos de Detención en el Turno [Rango: 0 a 480]", value=600, step=5)
        else:
            humedad = st.number_input("Humedad del Cartón (%) [Meta <= 8.0%]", min_value=-50.0, max_value=100.0, value=7.4, step=0.2)
            min_detencion = st.number_input("Minutos de Detención en Troqueladora", min_value=-10, max_value=600, value=0, step=5)

        estado_regla, decision_texto, color = evaluar_lote(humedad, min_detencion, id_lote)
        
        if color == "error":
            st.error(f"**{estado_regla}**\n\n{decision_texto}")
        elif color == "rojo":
            st.error(f"**{estado_regla}**\n\n{decision_texto}")
        elif color == "amarillo":
            st.warning(f"**{estado_regla}**\n\n{decision_texto}")
        else:
            st.success(f"**{estado_regla}**\n\n{decision_texto}")

    st.divider()
    st.markdown("#### 3. Anotación de Contexto del Trabajador (Resguardo Ético)")
    c1, c2 = st.columns([1, 2])
    with c1:
        validacion_turno = st.selectbox("Contexto de la Alerta / Evento", [
            "Parámetro Validado OK",
            "Falla Real Confirmada (Requiere Intervención)",
            "Excepción de Formato / Ruido Normal de Planta (Falso Positivo)",
            "Registro en Contingencia Manual (Falla de Instrumento)"
        ])
        crear_tarea_auto = st.checkbox("📌 Crear automáticamente tarea pendiente para Mantenimiento/Calidad", value=(color in ["rojo", "amarillo"]))
    with c2:
        nota_bitacora = st.text_area(
            "Anotación detallada del turno (Qué ocurrió y qué se hizo):",
            value="Lote procesado sin novedades. Formato estándar revisado por operador."
        )

    if st.button("💾 Guardar Anotación en Bitácora Oficial", type="primary"):
        if not id_lote.strip():
            st.error("⚠️ No se puede guardar: Debe ingresar un Código de Lote identificable.")
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
            st.success(f"✅ Anotación del lote **{id_lote.upper()}** registrada exitosamente.")

# ------------------------------------------------------------------------------
# PESTAÑA 2: ORGANIZADOR DE TAREAS Y VENTANAS DE MANTENIMIENTO
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("🛠️ Organizador de Intervenciones, Repuestos y Pendientes")
    st.markdown("Responde a la exigencia de **Óscar Leiva (Mantenimiento)**: validar la señal, confirmar repuestos y programar una ventana de intervención.")
    
    with st.expander("➕ Agregar Nueva Tarea o Ventana de Mantenimiento Manualmente"):
        with st.form("nueva_tarea_form"):
            f1, f2, f3 = st.columns(3)
            lote_t = f1.text_input("Lote Asociado", value="LOTE-FS-482")
            maq_t = f2.selectbox("Equipo", ["Troqueladora-01 (Crítica)", "Corrugadora-01", "Sistema Sensores / QR"])
            prio_t = f3.selectbox("Prioridad", ["Media (Ventana Programada)", "Alta (Detención Inmediata)", "Baja (Inspección Rutinaria)"])
            
            f4, f5, f6 = st.columns(3)
            asig_t = f4.selectbox("Responsable", ["Óscar Leiva (Mantenimiento)", "Camila Figueroa (Calidad)", "Martín Reyes (Producción)"])
            rep_t = f5.selectbox("¿Repuesto en Stock?", ["Sí (En bodega)", "No (Solicitar compra)", "No requiere repuesto"])
            est_t = f6.selectbox("Estado Inicial", ["Pendiente", "En Proceso", "Completada"])
            
            desc_t = st.text_input("Descripción del protocolo o acción a realizar:")
            if st.form_submit_button("Guardar Tarea en el Organizador"):
                conn = sqlite3.connect("organizador_australpack.db")
                c = conn.cursor()
                c.execute('''
                    INSERT INTO tareas_planta
                    (fecha_creacion, id_lote_asociado, maquina, prioridad, asignado_a, repuesto_disponible, estado_tarea, descripcion_accion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (datetime.now().strftime("%Y-%m-%d %H:%M"), lote_t.upper(), maq_t, prio_t, asig_t, rep_t, est_t, desc_t))
                conn.commit()
                conn.close()
                st.success("✅ Tarea agregada al organizador.")

    conn = sqlite3.connect("organizador_australpack.db")
    df_tareas = pd.read_sql_query("SELECT * FROM tareas_planta ORDER BY id_tarea DESC", conn)
    conn.close()
    
    filtro_estado = st.radio("Filtrar por estado:", ["Todas", "Pendiente", "En Proceso", "Completada"], horizontal=True)
    if filtro_estado != "Todas":
        df_tareas_vista = df_tareas[df_tareas["estado_tarea"] == filtro_estado]
    else:
        df_tareas_vista = df_tareas
        
    st.dataframe(df_tareas_vista, use_container_width=True)

# ------------------------------------------------------------------------------
# PESTAÑA 3: BUSCADOR DE AUDITORÍA (< 5 SEGUNDOS)
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("🔍 Trazabilidad Instantánea para Auditoría (Frutos del Sur Export)")
    st.markdown("Permite reconstruir **qué ocurrió, quién lo revisó y qué se hizo ante una desviación** en segundos en lugar de 3 horas.")
    
    conn = sqlite3.connect("organizador_australpack.db")
    df_lotes = pd.read_sql_query("SELECT * FROM bitacora_lotes ORDER BY id DESC", conn)
    conn.close()
    
    c_busq1, c_busq2 = st.columns([2, 1])
    texto_buscar = c_busq1.text_input("Buscar por Código de Lote, Cliente o Responsable (Ej: LOTE-FS-480):", "")
    filtro_alerta = c_busq2.selectbox("Filtrar por Nivel de Alerta:", ["Todos", "🟢 VERDE", "🟡 AMARILLO", "🔴 ROJO", "⚠️ ERROR"])
    
    df_resultado = df_lotes.copy()
    if texto_buscar:
        df_resultado = df_resultado[
            df_resultado["id_lote"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["cliente"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["responsable"].str.contains(texto_buscar, case=False, na=False) |
            df_resultado["nota_bitacora"].str.contains(texto_buscar, case=False, na=False)
        ]
    if filtro_alerta != "Todos":
        df_resultado = df_resultado[df_resultado["estado_regla"].str.contains(filtro_alerta[:5], case=False, na=False)]
        
    st.dataframe(df_resultado, use_container_width=True)
    
    csv_auditoria = df_resultado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Historial Verificable del Lote (CSV para Auditoría)",
        data=csv_auditoria,
        file_name="Historial_Trazabilidad_AustralPack.csv",
        mime="text/csv"
    )

# ------------------------------------------------------------------------------
# PESTAÑA 4: RESUMEN EJECUTIVO Y VIABILIDAD (Alternativas A + C)
# ------------------------------------------------------------------------------
with tab4:
    st.subheader("📊 Justificación de la Decisión: Combinación A + C")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Costo Año 1 (A + C)", "$33,2 MM", "Bajo el tope de $48 MM")
    c2.metric("Presupuesto Capacitación/Adopción", "$14,8 MM disponibles", "Financia ambos turnos")
    c3.metric("Disponibilidad Troqueladora", "80% ➔ 88%", "+8 pp (Alternativa A)")
    c4.metric("Trazabilidad y OTIF", "96% Trazab. / 94% OTIF", "+5 pp OTIF (Alternativa C)")
    
    st.markdown("""
    * **Cumplimiento de Restricciones:** Plazo de implementación $\le 12\text{ semanas}$, detención $\le 4\text{ días consecutivos}$ y **cero desvinculaciones** por automatización.
    * **Contingencia Manual:** Si un sensor falla o entrega un valor corrupto, el organizador bloquea alertas falsas y habilita el ingreso manual validado por Calidad.
    """)