import re
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURACIÓN GENERAL
# ==============================================================================
DB_PATH = "australpack_v2.db"
ZONA_PLANTA = ZoneInfo("America/Santiago")

# Supuestos de demostración, por validar con Calidad y Mantenimiento.
HUMEDAD_VALIDA = (3.0, 35.0)
MINUTOS_VALIDOS = (0, 480)
HUMEDAD_AMARILLO = 8.0
HUMEDAD_ROJO = 10.0
MINUTOS_REVISION = 30
LECTURAS_CONFIRMACION = 3
LIMITES_MAQUINA = {
    "vibracion": (4.5, 7.0),
    "temperatura": (70.0, 85.0),
    "corriente": (32.0, 40.0),
}

ORDEN_NIVEL = {"verde": 0, "amarillo": 1, "rojo": 2}
ETIQUETAS = {
    "verde": "🟢 VERDE (Normal)",
    "amarillo": "🟡 AMARILLO (Observar)",
    "rojo": "🔴 ROJO (Intervenir)",
}

VALIDACION_OK = "Parámetro Validado OK"
VALIDACION_FALLA = "Falla Real Confirmada (Requiere Intervención)"
VALIDACION_DESVIACION = "Desviación Real en Observación"
VALIDACION_RUIDO = "Excepción de Formato / Ruido Normal de Planta (Falso Positivo)"
VALIDACION_MANUAL = "Registro en Contingencia Manual (Falla de Instrumento)"
VALIDACIONES = [
    VALIDACION_OK,
    VALIDACION_FALLA,
    VALIDACION_DESVIACION,
    VALIDACION_RUIDO,
    VALIDACION_MANUAL,
]

PRIORIDAD_ALTA = "Alta (Intervención Prioritaria)"
PRIORIDAD_MEDIA = "Media (Ventana Programada)"
PRIORIDAD_BAJA = "Baja (Inspección Rutinaria)"

CLIENTES = [
    "Frutos del Sur Export",
    "AgroSur Export",
    "Viña Austral",
    "Salmones del Pacífico",
    "Mercado Interno General",
]
EQUIPOS = ["Troqueladora-01 (Crítica)", "Corrugadora-01", "Pegadora-02"]
EQUIPO_SENSORES = "Sistema Sensores / QR"
PERSONAS = [
    "Paula Jara (Operadora de Turno)",
    "Camila Figueroa (Jefa de Calidad)",
    "Óscar Leiva (Mantenimiento)",
    "Martín Reyes (Jefe de Producción)",
]
CAUSAS = [
    "Sin detención",
    "Cambio de formato",
    "Falla mecánica",
    "Falta de material",
    "Espera de información",
    "Otra",
]
ESTADOS_BLOQUEADOS = ("Retenido", "Reprocesar", "Descartar")
ESTADOS_ORDEN = ["Pendiente", "En Proceso", "Completada"]
OPCIONES_REPUESTO = [
    "Por verificar",
    "Sí (En bodega)",
    "No (Solicitar compra)",
    "No requiere repuesto",
]
PATRON_LOTE = re.compile(r"[A-Z0-9-]{6,30}")

COLUMNAS_SEMILLA = (
    "fecha_hora",
    "id_lote",
    "cliente",
    "maquina",
    "turno",
    "responsable",
    "humedad_pct",
    "minutos_detencion",
    "causa_detencion",
    "vibracion",
    "temperatura",
    "corriente",
    "lecturas_seguidas",
    "estado_regla",
    "decision_operativa",
    "validacion_turno",
    "nota_bitacora",
    "estado_lote",
)

st.set_page_config(
    page_title="AustralPack | Terminal Operativo de Planta",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
# ESTILOS
# ==============================================================================
st.markdown(
    """
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
    .sem-verde {
        background-color: #dcfce7;
        color: #166534;
        border-left: 6px solid #22c55e;
    }
    .sem-amarillo {
        background-color: #fef9c3;
        color: #854d0e;
        border-left: 6px solid #eab308;
    }
    .sem-rojo {
        background-color: #fee2e2;
        color: #991b1b;
        border-left: 6px solid #ef4444;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ==============================================================================
# 1. FUNCIONES DE BASE DE DATOS
# ==============================================================================
def ahora_planta():
    return datetime.now(ZONA_PLANTA).strftime("%Y-%m-%d %H:%M:%S")


def conectar():
    return sqlite3.connect(DB_PATH)


def insertar_registro(cursor, registro):
    columnas = ", ".join(registro)
    marcadores = ", ".join("?" for _ in registro)
    cursor.execute(
        f"INSERT INTO bitacora_lotes ({columnas}) VALUES ({marcadores})",
        tuple(registro.values()),
    )


def registrar_evento(cursor, id_lote, evento, detalle, responsable, estado=None):
    cursor.execute(
        """
        INSERT INTO eventos_lote
        (fecha_hora, id_lote, evento, detalle, responsable, estado_nuevo)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ahora_planta(), id_lote, evento, detalle, responsable, estado),
    )


def crear_orden(
    cursor,
    id_lote,
    maquina,
    prioridad,
    asignado_a,
    repuesto,
    estado,
    descripcion,
    registrado_por,
):
    cursor.execute(
        """
        INSERT INTO tareas_planta
        (fecha_creacion, id_lote_asociado, maquina, prioridad, asignado_a,
         repuesto_disponible, estado_tarea, descripcion_accion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ahora_planta(),
            id_lote,
            maquina,
            prioridad,
            asignado_a,
            repuesto,
            estado,
            descripcion,
        ),
    )
    registrar_evento(
        cursor,
        id_lote,
        f"Orden #{cursor.lastrowid} creada",
        f"{prioridad}: {descripcion}",
        registrado_por,
    )


def estado_actual(conn, id_lote):
    fila = conn.execute(
        """
        SELECT estado_nuevo
        FROM eventos_lote
        WHERE id_lote = ? AND estado_nuevo IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (id_lote,),
    ).fetchone()
    if fila:
        return fila[0]

    fila = conn.execute(
        """
        SELECT estado_lote
        FROM bitacora_lotes
        WHERE id_lote = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (id_lote,),
    ).fetchone()
    return fila[0] if fila else None


def init_db():
    conn = conectar()
    c = conn.cursor()

    c.execute(
        """
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
            lectura_humedad_cruda REAL,
            lectura_minutos_cruda INTEGER,
            origen_dato TEXT,
            causa_detencion TEXT,
            vibracion REAL,
            temperatura REAL,
            corriente REAL,
            lecturas_seguidas INTEGER,
            estado_regla TEXT,
            decision_operativa TEXT,
            validacion_turno TEXT,
            nota_bitacora TEXT,
            estado_lote TEXT
        )
        """
    )

    c.execute(
        """
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
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS eventos_lote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            id_lote TEXT NOT NULL,
            evento TEXT NOT NULL,
            detalle TEXT NOT NULL,
            responsable TEXT NOT NULL,
            estado_nuevo TEXT
        )
        """
    )

    c.execute("SELECT COUNT(*) FROM bitacora_lotes")
    if c.fetchone()[0] == 0:
        decision_verde = "Lote apto para continuar a despacho. Máquina dentro de rango."
        decision_amarilla = (
            "Seguir produciendo. Calidad revisa el lote antes del despacho. "
            "Máquina dentro de rango."
        )
        decision_roja = (
            "Retener el lote y avisar a Calidad. Señal crítica confirmada. "
            "Validar en terreno y aplicar protocolo seguro."
        )

        lotes_semilla = [
            (
                "2026-10-27 22:15:00",
                "LOTE-FS-479",
                "Frutos del Sur Export",
                "Troqueladora-01 (Crítica)",
                "Noche",
                "Paula Jara (Operadora de Turno)",
                7.1,
                5,
                "Cambio de formato",
                2.1,
                56.0,
                27.0,
                0,
                ETIQUETAS["verde"],
                decision_verde,
                VALIDACION_OK,
                "Operación fluida en primera mitad del turno nocturno.",
                "Liberado",
            ),
            (
                "2026-10-28 07:46:00",
                "LOTE-FS-480",
                "Frutos del Sur Export",
                "Troqueladora-01 (Crítica)",
                "Noche",
                "Paula Jara (Operadora de Turno)",
                9.4,
                20,
                "Espera de información",
                2.8,
                60.0,
                29.0,
                0,
                ETIQUETAS["amarillo"],
                decision_amarilla,
                VALIDACION_DESVIACION,
                "Humedad sobre el límite de precaución. Se solicitó revisión de Calidad.",
                "En observación",
            ),
            (
                "2026-10-28 15:10:00",
                "LOTE-FS-481",
                "Frutos del Sur Export",
                "Troqueladora-01 (Crítica)",
                "Día",
                "Camila Figueroa (Jefa de Calidad)",
                6.8,
                0,
                "Sin detención",
                2.0,
                54.0,
                27.0,
                0,
                ETIQUETAS["verde"],
                decision_verde,
                VALIDACION_OK,
                "Control de calidad normal, sin deformación en prueba de frío.",
                "Liberado",
            ),
            (
                "2026-10-29 03:20:00",
                "LOTE-AP-109",
                "AgroSur Export",
                "Troqueladora-01 (Crítica)",
                "Noche",
                "Óscar Leiva (Mantenimiento)",
                11.5,
                45,
                "Falla mecánica",
                7.6,
                72.0,
                36.0,
                4,
                ETIQUETAS["rojo"],
                decision_roja,
                VALIDACION_FALLA,
                "Desajuste en troquel y exceso de humedad. Mantenimiento reemplazó la pieza.",
                "Retenido",
            ),
            (
                "2026-10-29 11:30:00",
                "LOTE-VA-204",
                "Viña Austral",
                "Corrugadora-01",
                "Día",
                "Martín Reyes (Jefe de Producción)",
                8.5,
                15,
                "Cambio de formato",
                3.0,
                58.0,
                28.0,
                1,
                ETIQUETAS["amarillo"],
                decision_amarilla,
                VALIDACION_RUIDO,
                "Ajuste menor por cambio de gramaje en caja de exportación.",
                "En observación",
            ),
        ]

        for fila in lotes_semilla:
            registro = dict(zip(COLUMNAS_SEMILLA, fila))
            registro["lectura_humedad_cruda"] = registro["humedad_pct"]
            registro["lectura_minutos_cruda"] = registro["minutos_detencion"]
            registro["origen_dato"] = "Sensor (dato de demostración)"
            insertar_registro(c, registro)

        tareas_semilla = [
            (
                "2026-10-28 08:00:00",
                "LOTE-FS-480",
                "Troqueladora-01 (Crítica)",
                PRIORIDAD_MEDIA,
                "Óscar Leiva (Mantenimiento)",
                "Sí (En bodega)",
                "En Proceso",
                "Revisar cuchillas en cambio de turno sin frenar la planta.",
            ),
            (
                "2026-10-29 03:25:00",
                "LOTE-AP-109",
                "Troqueladora-01 (Crítica)",
                PRIORIDAD_ALTA,
                "Óscar Leiva (Mantenimiento)",
                "Sí (En bodega)",
                "Completada",
                "Cambio de sello mecánico y validación junto a Calidad.",
            ),
            (
                "2026-10-29 11:40:00",
                "LOTE-VA-204",
                "Corrugadora-01",
                PRIORIDAD_MEDIA,
                "Óscar Leiva (Mantenimiento)",
                "Sí (En bodega)",
                "Pendiente",
                "Inspeccionar rodillos al finalizar corrida de Viña Austral.",
            ),
        ]
        c.executemany(
            """
            INSERT INTO tareas_planta
            (fecha_creacion, id_lote_asociado, maquina, prioridad, asignado_a,
             repuesto_disponible, estado_tarea, descripcion_accion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tareas_semilla,
        )

        c.execute(
            """
            INSERT INTO eventos_lote
            (fecha_hora, id_lote, evento, detalle, responsable, estado_nuevo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-10-28 09:10:00",
                "LOTE-FS-480",
                "Decisión de Calidad",
                "Nueva medición y revisión de muestra antes del despacho.",
                "Camila Figueroa (Jefa de Calidad)",
                "Liberado",
            ),
        )

    for tabla in ("bitacora_lotes", "eventos_lote"):
        for accion in ("UPDATE", "DELETE"):
            c.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS bloquear_{accion.lower()}_{tabla}
                BEFORE {accion} ON {tabla}
                BEGIN
                    SELECT RAISE(ABORT, 'Registro protegido: agrega un evento nuevo.');
                END
                """
            )

    conn.commit()
    conn.close()


init_db()


# ==============================================================================
# 2. REGLAS DE DECISIÓN Y VALIDACIÓN
# ==============================================================================
def dato_valido(valor, rango):
    return valor is not None and rango[0] <= valor <= rango[1]


def evaluar_calidad(humedad):
    if humedad > HUMEDAD_ROJO:
        return "rojo", "Retenido", "Retener el lote y avisar a Calidad."
    if humedad >= HUMEDAD_AMARILLO:
        return (
            "amarillo",
            "En observación",
            "Seguir produciendo. Calidad revisa el lote antes del despacho.",
        )
    return "verde", "Liberado", "Lote apto para continuar a despacho."


def evaluar_maquina(lecturas, seguidas, minutos):
    nivel = "verde"

    for variable, valor in lecturas.items():
        limite_amarillo, limite_rojo = LIMITES_MAQUINA[variable]
        if valor >= limite_rojo:
            nivel = "rojo"
        elif valor >= limite_amarillo and nivel == "verde":
            nivel = "amarillo"

    confirmada = seguidas >= LECTURAS_CONFIRMACION

    if nivel == "rojo" and confirmada:
        return (
            "rojo",
            PRIORIDAD_ALTA,
            "Señal crítica confirmada. Validar en terreno y aplicar protocolo seguro.",
        )
    if (nivel != "verde" and confirmada) or minutos >= MINUTOS_REVISION:
        return (
            "amarillo",
            PRIORIDAD_MEDIA,
            "Programar revisión de Mantenimiento en la próxima ventana.",
        )
    if nivel != "verde":
        return "amarillo", None, "Señal sin confirmar. Observar; no crea orden."
    return "verde", None, "Máquina dentro de rango."


def evaluar_registro(humedad, minutos, lecturas, seguidas):
    nivel_calidad, estado, accion_calidad = evaluar_calidad(humedad)
    nivel_maquina, prioridad, accion_maquina = evaluar_maquina(
        lecturas, seguidas, minutos
    )
    nivel = max((nivel_calidad, nivel_maquina), key=ORDEN_NIVEL.get)

    return {
        "nivel": nivel,
        "estado_lote": estado,
        "prioridad": prioridad,
        "decision": f"{accion_calidad} {accion_maquina}",
    }


def revisar_formulario(id_lote, resultado, validacion, nota, causa, origen, minutos):
    errores = []
    lote = id_lote.strip().upper()

    if not PATRON_LOTE.fullmatch(lote):
        errores.append(
            "Ingresa un código de lote válido: letras, números y guiones, "
            "entre 6 y 30 caracteres."
        )
    if resultado is None:
        errores.append("Faltan datos válidos de humedad o detención.")
    if validacion is None:
        errores.append("Debes seleccionar la validación del turno.")
    if causa is None:
        errores.append("Debes seleccionar la causa de detención.")
    if causa == "Sin detención" and minutos not in (None, 0):
        errores.append("Si hubo minutos de detención, selecciona una causa.")
    if resultado and resultado["nivel"] != "verde" and len(nota.strip()) < 15:
        errores.append("Describe qué ocurrió y qué acción se tomó.")
    if resultado and resultado["nivel"] == "rojo" and validacion == VALIDACION_OK:
        errores.append("Una alerta roja no puede cerrarse como parámetro OK.")
    if origen == "Contingencia manual" and validacion != VALIDACION_MANUAL:
        errores.append("Marca el registro como contingencia manual.")

    return errores


# ==============================================================================
# 3. BARRA LATERAL
# ==============================================================================
with st.sidebar:
    st.markdown("### 🏭 Panel de Control en Piso")
    st.caption("Demostrador: los datos pueden reiniciarse si la aplicación se reinicia.")
    st.divider()

    st.markdown("#### 🚦 Regla Operativa")
    st.markdown(
        f"""
**🟢 Verde:** humedad bajo {HUMEDAD_AMARILLO:.0f}% y máquina en rango.

**🟡 Amarillo:** humedad entre {HUMEDAD_AMARILLO:.0f}% y {HUMEDAD_ROJO:.0f}%, señal sin confirmar o parada de {MINUTOS_REVISION} minutos o más. No detener la línea por esta alerta.

**🔴 Rojo:** humedad sobre {HUMEDAD_ROJO:.0f}% o señal crítica confirmada. Validar en terreno y aplicar el protocolo.

**⚠️ Error:** dato fuera de rango. Registrar medición manual.
"""
    )
    st.caption("Umbrales de demostración, sujetos a validación.")
    st.divider()

    st.markdown("#### 🛡️ Resguardo del Trabajador")
    st.info(
        "Ninguna alerta detiene la planta automáticamente. "
        "Cada evento se valida en terreno y conserva su contexto."
    )

# ==============================================================================
# 4. ENCABEZADO Y RESUMEN
# ==============================================================================
st.markdown(
    """
<div class="main-header">
    <h1>🏭 AustralPack Circular SpA — Terminal de Trazabilidad y Planta</h1>
    <p>Bitácora unificada de Calidad, Producción y Mantenimiento | Control por lote, equipo y turno</p>
</div>
""",
    unsafe_allow_html=True,
)

conn = conectar()
df_lotes = pd.read_sql_query("SELECT * FROM bitacora_lotes ORDER BY id", conn)
df_tareas = pd.read_sql_query("SELECT * FROM tareas_planta ORDER BY id_tarea", conn)
conn.close()

total_registros = len(df_lotes)
lotes_unicos = df_lotes["id_lote"].nunique()
humedades = df_lotes["humedad_pct"].dropna()
humedad_prom = humedades.mean() if not humedades.empty else 0
min_totales_paro = int(df_lotes["minutos_detencion"].sum())
tareas_pend = len(df_tareas[df_tareas["estado_tarea"] != "Completada"])

m1, m2, m3, m4 = st.columns(4)
with m1:
    with st.container(border=True):
        st.metric(
            "📦 Lotes trazados",
            f"{lotes_unicos} lotes",
            f"{total_registros} registros",
            delta_color="off",
        )
with m2:
    with st.container(border=True):
        en_rango = humedad_prom < HUMEDAD_AMARILLO
        st.metric(
            "💧 Humedad promedio",
            f"{humedad_prom:.1f} %",
            "Bajo precaución" if en_rango else "Atención",
            delta_color="normal" if en_rango else "inverse",
        )
with m3:
    with st.container(border=True):
        st.metric(
            "⏱️ Detención registrada",
            f"{min_totales_paro} min",
            "Validada en registros",
            delta_color="off",
        )
with m4:
    with st.container(border=True):
        st.metric(
            "🛠️ Órdenes activas",
            f"{tareas_pend} pendientes",
            "Repuesto informado por orden",
            delta_color="off",
        )

# ==============================================================================
# 5. PESTAÑAS
# ==============================================================================
tab1, tab2, tab3 = st.tabs(
    [
        "📝 1. Anotar Lote y Turno",
        "📊 2. Mantenimiento y Gráficos",
        "🔍 3. Historial y Auditoría",
    ]
)

# ------------------------------------------------------------------------------
# PESTAÑA 1: REGISTRO
# ------------------------------------------------------------------------------
with tab1:
    mensaje_ok = st.session_state.pop("mensaje_ok", None)
    if mensaje_ok:
        st.success(mensaje_ok)

    if "form_id" not in st.session_state:
        st.session_state.form_id = 0
    fid = st.session_state.form_id

    col_a, col_b = st.columns([1, 1])

    with col_a:
        with st.container(border=True):
            st.markdown("#### 📦 1. Identificación del Lote y Turno")
            st.caption("Une el código del lote con su cliente, equipo y turno.")

            c_in1, c_in2 = st.columns(2)
            id_lote = c_in1.text_input(
                "Código de Lote / QR Pallet",
                placeholder="Ej: LOTE-AP-501",
                key=f"lote_{fid}",
            )
            cliente = c_in2.selectbox(
                "Cliente destino",
                CLIENTES,
                index=None,
                placeholder="Selecciona un cliente",
                key=f"cliente_{fid}",
            )

            c_in3, c_in4 = st.columns(2)
            maquina = c_in3.selectbox(
                "Equipo / Línea",
                EQUIPOS,
                index=None,
                placeholder="Selecciona un equipo",
                key=f"maquina_{fid}",
            )
            turno = c_in4.radio(
                "Turno",
                ["Día", "Noche"],
                index=None,
                horizontal=True,
                key=f"turno_{fid}",
            )

            responsable = st.selectbox(
                "Persona que registra",
                PERSONAS,
                index=None,
                placeholder="Selecciona una persona",
                key=f"responsable_{fid}",
            )

            lote_normalizado = id_lote.strip().upper()
            if lote_normalizado:
                registros_previos = int((df_lotes["id_lote"] == lote_normalizado).sum())
                if registros_previos:
                    st.caption(
                        f"Este lote ya tiene {registros_previos} registro(s). "
                        "El nuevo dato se agregará a su historial."
                    )

    with col_b:
        with st.container(border=True):
            st.markdown("#### 📡 2. Parámetros del Proceso y Diagnóstico")
            simular_falla = st.toggle(
                "🧪 Simular falla de sensor",
                key=f"falla_{fid}",
            )

            p1, p2 = st.columns(2)
            if simular_falla:
                lectura_humedad = p1.number_input(
                    "Humedad del cartón (%)",
                    value=-15.0,
                    step=1.0,
                    key=f"humedad_error_{fid}",
                )
                lectura_minutos = p2.number_input(
                    "Minutos de detención",
                    value=600,
                    step=5,
                    key=f"minutos_error_{fid}",
                )
            else:
                lectura_humedad = p1.number_input(
                    "Humedad del cartón (%)",
                    value=None,
                    step=0.1,
                    placeholder="Ingresa la lectura",
                    key=f"humedad_{fid}",
                )
                lectura_minutos = p2.number_input(
                    "Minutos de detención",
                    value=None,
                    step=5,
                    placeholder="Ingresa los minutos",
                    key=f"minutos_{fid}",
                )

            st.caption("Señales IoT simuladas de la Alternativa A")
            s1, s2, s3 = st.columns(3)
            vibracion = s1.number_input(
                "Vibración (mm/s)",
                value=2.0,
                step=0.1,
                key=f"vibracion_{fid}",
            )
            temperatura = s2.number_input(
                "Temperatura (°C)",
                value=55.0,
                step=1.0,
                key=f"temperatura_{fid}",
            )
            corriente = s3.number_input(
                "Corriente (A)",
                value=28.0,
                step=0.5,
                key=f"corriente_{fid}",
            )
            lecturas_seguidas = st.number_input(
                "Lecturas seguidas fuera de rango",
                min_value=0,
                value=0,
                step=1,
                key=f"seguidas_{fid}",
            )

            humedad = lectura_humedad
            minutos = lectura_minutos
            origen = "Sensor"

            sensor_con_error = (
                lectura_humedad is not None
                and not dato_valido(lectura_humedad, HUMEDAD_VALIDA)
            ) or (
                lectura_minutos is not None
                and not dato_valido(lectura_minutos, MINUTOS_VALIDOS)
            )

            if sensor_con_error:
                st.error(
                    "⚠️ Dato fuera de rango. Se bloquea la alerta automática "
                    "y se requiere verificación manual."
                )
                h1, h2 = st.columns(2)
                humedad = h1.number_input(
                    "Humedad con higrómetro (%)",
                    value=None,
                    step=0.1,
                    key=f"humedad_manual_{fid}",
                )
                minutos = h2.number_input(
                    "Minutos verificados",
                    value=None,
                    step=5,
                    key=f"minutos_manual_{fid}",
                )
                origen = "Contingencia manual"

            lecturas = {
                "vibracion": vibracion,
                "temperatura": temperatura,
                "corriente": corriente,
            }
            resultado = None

            if dato_valido(humedad, HUMEDAD_VALIDA) and dato_valido(
                minutos, MINUTOS_VALIDOS
            ):
                resultado = evaluar_registro(
                    humedad,
                    minutos,
                    lecturas,
                    lecturas_seguidas,
                )
                st.markdown(
                    f"""
                    <div class="semaforo-box sem-{resultado['nivel']}">
                        <div style="font-size: 1.1rem; margin-bottom: 4px;">
                            {ETIQUETAS[resultado['nivel']]}
                        </div>
                        <div style="font-weight: 400; font-size: 0.92rem;">
                            {resultado['decision']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.info("Ingresa datos válidos para evaluar el lote.")

    with st.container(border=True):
        st.markdown("#### 🛡️ 3. Validación Humana del Turno")
        c1, c2 = st.columns([1, 2])

        with c1:
            validacion_turno = st.selectbox(
                "Clasificación en terreno",
                VALIDACIONES,
                index=None,
                placeholder="Selecciona una opción",
                key=f"validacion_{fid}",
            )
            causa_detencion = st.selectbox(
                "Causa de detención",
                CAUSAS,
                index=None,
                placeholder="Selecciona una causa",
                key=f"causa_{fid}",
            )

        with c2:
            nota_bitacora = st.text_area(
                "Qué ocurrió y qué acción se tomó",
                placeholder="Describe la situación observada en terreno",
                height=100,
                key=f"nota_{fid}",
            )

        if st.button(
            "💾 Guardar Registro Oficial",
            type="primary",
            use_container_width=True,
        ):
            errores = revisar_formulario(
                id_lote,
                resultado,
                validacion_turno,
                nota_bitacora,
                causa_detencion,
                origen,
                minutos,
            )

            if cliente is None:
                errores.append("Debes seleccionar el cliente.")
            if maquina is None:
                errores.append("Debes seleccionar el equipo.")
            if turno is None:
                errores.append("Debes seleccionar el turno.")
            if responsable is None:
                errores.append("Debes seleccionar quién registra.")

            if errores:
                for error in errores:
                    st.error(error)
            else:
                lote = id_lote.strip().upper()
                prefijo = "⚠️ ERROR DE SENSOR → " if origen != "Sensor" else ""

                conn = conectar()
                c = conn.cursor()

                estado_previo = estado_actual(conn, lote)
                estado_final = (
                    estado_previo
                    if estado_previo in ESTADOS_BLOQUEADOS
                    else resultado["estado_lote"]
                )

                registro = {
                    "fecha_hora": ahora_planta(),
                    "id_lote": lote,
                    "cliente": cliente,
                    "maquina": maquina,
                    "turno": turno,
                    "responsable": responsable,
                    "humedad_pct": humedad,
                    "minutos_detencion": minutos,
                    "lectura_humedad_cruda": lectura_humedad,
                    "lectura_minutos_cruda": lectura_minutos,
                    "origen_dato": origen,
                    "causa_detencion": causa_detencion,
                    "vibracion": vibracion,
                    "temperatura": temperatura,
                    "corriente": corriente,
                    "lecturas_seguidas": lecturas_seguidas,
                    "estado_regla": prefijo + ETIQUETAS[resultado["nivel"]],
                    "decision_operativa": resultado["decision"],
                    "validacion_turno": validacion_turno,
                    "nota_bitacora": nota_bitacora.strip(),
                    "estado_lote": estado_final,
                }
                insertar_registro(c, registro)

                registrar_evento(
                    c,
                    lote,
                    "Registro de turno",
                    validacion_turno,
                    responsable,
                    estado_final,
                )

                ordenes_creadas = 0
                nota_orden = nota_bitacora.strip() or "Revisión solicitada desde el turno."

                if validacion_turno == VALIDACION_FALLA or (
                    validacion_turno == VALIDACION_MANUAL and resultado["prioridad"]
                ):
                    crear_orden(
                        c,
                        lote,
                        maquina,
                        resultado["prioridad"] or PRIORIDAD_MEDIA,
                        "Óscar Leiva (Mantenimiento)",
                        "Por verificar",
                        "Pendiente",
                        nota_orden,
                        responsable,
                    )
                    ordenes_creadas += 1

                if origen == "Contingencia manual":
                    crear_orden(
                        c,
                        lote,
                        EQUIPO_SENSORES,
                        PRIORIDAD_MEDIA,
                        "Óscar Leiva (Mantenimiento)",
                        "Por verificar",
                        "Pendiente",
                        "Revisar instrumento: "
                        f"humedad {lectura_humedad}, minutos {lectura_minutos}.",
                        responsable,
                    )
                    ordenes_creadas += 1

                conn.commit()
                conn.close()

                st.session_state.mensaje_ok = (
                    f"Lote {lote} guardado. Estado: {estado_final}. "
                    f"Órdenes creadas: {ordenes_creadas}."
                )
                st.session_state.form_id += 1
                st.rerun()

# ------------------------------------------------------------------------------
# PESTAÑA 2: MANTENIMIENTO Y GRÁFICOS
# ------------------------------------------------------------------------------
with tab2:
    st.markdown("#### 📈 Comportamiento de Planta")
    g1, g2 = st.columns(2)

    with g1:
        with st.container(border=True):
            st.markdown("**⏱️ Minutos de detención por equipo y causa**")
            st.caption("Ayuda a priorizar causas sin comparar personas o turnos.")

            if not df_lotes.empty:
                df_paradas = (
                    df_lotes.assign(
                        causa=df_lotes["causa_detencion"].fillna("Sin clasificar")
                    )
                    .groupby(["maquina", "causa"])["minutos_detencion"]
                    .sum()
                    .unstack(fill_value=0)
                )
                st.bar_chart(df_paradas, height=250)
            else:
                st.info("Sin datos para graficar.")

    with g2:
        with st.container(border=True):
            st.markdown("**💧 Humedad registrada (%)**")
            st.caption(
                f"Precaución: {HUMEDAD_AMARILLO:.0f}% | "
                f"Crítico: {HUMEDAD_ROJO:.0f}% | Umbrales por validar."
            )

            df_hum = df_lotes[["fecha_hora", "humedad_pct"]].dropna()
            if not df_hum.empty:
                st.line_chart(
                    df_hum.set_index("fecha_hora"),
                    color="#0284c7",
                    height=250,
                )
            else:
                st.info("Sin datos para graficar.")

    st.divider()
    st.markdown("#### 🛠️ Órdenes de Mantenimiento y Repuestos")
    col_gest1, col_gest2 = st.columns([1, 1])

    with col_gest1:
        with st.expander("➕ Crear orden manual", expanded=False):
            with st.form("nueva_tarea_form", clear_on_submit=True):
                f1, f2 = st.columns(2)
                lote_t = f1.text_input("Lote asociado", placeholder="Ej: LOTE-AP-501")
                maq_t = f2.selectbox("Equipo", EQUIPOS + [EQUIPO_SENSORES])

                f3, f4 = st.columns(2)
                prio_t = f3.selectbox(
                    "Prioridad",
                    [PRIORIDAD_MEDIA, PRIORIDAD_ALTA, PRIORIDAD_BAJA],
                )
                asig_t = f4.selectbox(
                    "Responsable",
                    [
                        "Óscar Leiva (Mantenimiento)",
                        "Camila Figueroa (Jefa de Calidad)",
                        "Martín Reyes (Jefe de Producción)",
                    ],
                )

                f5, f6 = st.columns(2)
                rep_t = f5.selectbox("Repuesto", OPCIONES_REPUESTO)
                est_t = f6.selectbox("Estado inicial", ESTADOS_ORDEN)

                registrado_por = st.selectbox("Registrado por", PERSONAS)
                desc_t = st.text_input("Intervención a realizar")

                if st.form_submit_button("➕ Registrar orden", use_container_width=True):
                    lote_orden = lote_t.strip().upper()

                    if not PATRON_LOTE.fullmatch(lote_orden):
                        st.error("Ingresa un código de lote válido.")
                    elif len(desc_t.strip()) < 10:
                        st.error("Describe la intervención.")
                    else:
                        conn = conectar()
                        c = conn.cursor()
                        crear_orden(
                            c,
                            lote_orden,
                            maq_t,
                            prio_t,
                            asig_t,
                            rep_t,
                            est_t,
                            desc_t.strip(),
                            registrado_por,
                        )
                        conn.commit()
                        conn.close()
                        st.rerun()

    with col_gest2:
        with st.expander("⚡ Actualizar orden", expanded=False):
            if not df_tareas.empty:
                etiquetas_orden = {
                    int(f.id_tarea): (
                        f"#{f.id_tarea} | {f.id_lote_asociado} - "
                        f"{f.maquina} ({f.estado_tarea})"
                    )
                    for f in df_tareas.itertuples()
                }
                id_sel = st.selectbox(
                    "Orden",
                    list(etiquetas_orden),
                    format_func=etiquetas_orden.get,
                )

                u1, u2 = st.columns(2)
                nuevo_estado = u1.selectbox("Nuevo estado", ESTADOS_ORDEN)
                nuevo_rep = u2.selectbox("Repuesto", OPCIONES_REPUESTO)
                responsable_cambio = st.selectbox("Registrado por", PERSONAS)

                if st.button("🔄 Actualizar orden", use_container_width=True):
                    fila = df_tareas[df_tareas["id_tarea"] == id_sel].iloc[0]

                    conn = conectar()
                    c = conn.cursor()
                    c.execute(
                        """
                        UPDATE tareas_planta
                        SET estado_tarea = ?, repuesto_disponible = ?
                        WHERE id_tarea = ?
                        """,
                        (nuevo_estado, nuevo_rep, id_sel),
                    )
                    registrar_evento(
                        c,
                        fila["id_lote_asociado"],
                        f"Orden #{id_sel} actualizada",
                        f"{fila['estado_tarea']} → {nuevo_estado}; repuesto: {nuevo_rep}",
                        responsable_cambio,
                    )
                    conn.commit()
                    conn.close()
                    st.rerun()
            else:
                st.info("No hay órdenes registradas.")

    filtro_estado = st.radio(
        "Filtrar órdenes",
        ["Todas"] + ESTADOS_ORDEN,
        horizontal=True,
    )
    df_tareas_vista = (
        df_tareas
        if filtro_estado == "Todas"
        else df_tareas[df_tareas["estado_tarea"] == filtro_estado]
    )

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
            "repuesto_disponible": "🔩 Repuesto",
            "estado_tarea": "📌 Estado",
            "descripcion_accion": "Detalle",
        },
    )

# ------------------------------------------------------------------------------
# PESTAÑA 3: HISTORIAL Y AUDITORÍA
# ------------------------------------------------------------------------------
with tab3:
    st.markdown("#### 🔍 Consulta de Trazabilidad")
    st.caption("Muestra qué ocurrió, quién lo revisó y qué acción quedó registrada.")

    c_busq1, c_busq2 = st.columns([2, 1])
    texto_buscar = c_busq1.text_input(
        "Buscar por lote, cliente, equipo, responsable o nota",
        placeholder="Ej: LOTE-FS-480",
    )
    filtro_alerta = c_busq2.selectbox(
        "Nivel de alerta",
        ["Todos", "🟢 VERDE", "🟡 AMARILLO", "🔴 ROJO", "⚠️ ERROR"],
    )

    inicio_consulta = time.perf_counter()
    df_resultado = df_lotes.sort_values(by="id", ascending=False)
    busqueda = texto_buscar.strip()

    if busqueda:
        coincide = pd.Series(False, index=df_resultado.index)
        for columna in (
            "id_lote",
            "cliente",
            "maquina",
            "responsable",
            "nota_bitacora",
        ):
            coincide = coincide | df_resultado[columna].str.contains(
                busqueda,
                case=False,
                na=False,
                regex=False,
            )
        df_resultado = df_resultado[coincide]

    if filtro_alerta != "Todos":
        df_resultado = df_resultado[
            df_resultado["estado_regla"].str.contains(
                filtro_alerta,
                case=False,
                na=False,
                regex=False,
            )
        ]

    if df_resultado.empty:
        st.warning("No se encontraron registros con esos filtros.")
    else:
        lote_elegido = st.selectbox(
            "Lote a revisar",
            df_resultado["id_lote"].unique().tolist(),
        )
        historia = df_lotes[df_lotes["id_lote"] == lote_elegido].sort_values("id")

        conn = conectar()
        eventos = pd.read_sql_query(
            """
            SELECT fecha_hora, evento, detalle, responsable, estado_nuevo
            FROM eventos_lote
            WHERE id_lote = ?
            ORDER BY id
            """,
            conn,
            params=(lote_elegido,),
        )
        estado = estado_actual(conn, lote_elegido)
        conn.close()

        duracion_consulta = time.perf_counter() - inicio_consulta
        st.caption(
            f"Consulta resuelta en {duracion_consulta:.3f} s "
            f"sobre {total_registros} registros de demostración."
        )

        with st.container(border=True):
            st.markdown(f"### 📄 Reporte de trazabilidad: {lote_elegido}")
            r1, r2, r3, r4 = st.columns(4)
            r1.markdown(f"**Estado actual**  \n{estado}")
            r2.markdown(f"**Cliente**  \n{historia.iloc[-1]['cliente']}")
            r3.markdown(f"**Equipos**  \n{', '.join(historia['maquina'].unique())}")
            r4.markdown(f"**Registros**  \n{len(historia)}")

        st.markdown("**Registros de proceso**")
        st.dataframe(
            historia[
                [
                    "fecha_hora",
                    "maquina",
                    "turno",
                    "responsable",
                    "humedad_pct",
                    "lectura_humedad_cruda",
                    "minutos_detencion",
                    "origen_dato",
                    "causa_detencion",
                    "vibracion",
                    "temperatura",
                    "corriente",
                    "estado_regla",
                    "validacion_turno",
                    "nota_bitacora",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "fecha_hora": "Fecha y hora",
                "maquina": "Equipo",
                "turno": "Turno",
                "responsable": "Responsable",
                "humedad_pct": st.column_config.NumberColumn(
                    "Humedad usada (%)",
                    format="%.1f",
                ),
                "lectura_humedad_cruda": st.column_config.NumberColumn(
                    "Lectura original (%)",
                    format="%.1f",
                ),
                "minutos_detencion": "Detención (min)",
                "origen_dato": "Origen",
                "causa_detencion": "Causa",
                "vibracion": "Vibración",
                "temperatura": "Temperatura",
                "corriente": "Corriente",
                "estado_regla": "Semáforo",
                "validacion_turno": "Validación",
                "nota_bitacora": "Nota",
            },
        )

        st.markdown("**Eventos y decisiones**")
        if eventos.empty:
            st.info("Este lote no tiene eventos adicionales.")
        else:
            st.dataframe(
                eventos,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "fecha_hora": "Fecha y hora",
                    "evento": "Evento",
                    "detalle": "Detalle",
                    "responsable": "Responsable",
                    "estado_nuevo": "Estado",
                },
            )

        with st.expander("Registrar decisión de Calidad"):
            q1, q2 = st.columns(2)
            estado_nuevo = q1.selectbox(
                "Decisión",
                ["Liberado", "Retenido", "Reprocesar", "Descartar"],
            )
            responsable_calidad = q2.selectbox(
                "Responsable",
                ["Camila Figueroa (Jefa de Calidad)"],
            )
            motivo = st.text_input("Motivo de la decisión")

            if st.button("Guardar decisión de Calidad"):
                if len(motivo.strip()) < 10:
                    st.error("Escribe un motivo más claro.")
                else:
                    conn = conectar()
                    c = conn.cursor()
                    registrar_evento(
                        c,
                        lote_elegido,
                        "Decisión de Calidad",
                        motivo.strip(),
                        responsable_calidad,
                        estado_nuevo,
                    )
                    conn.commit()
                    conn.close()
                    st.rerun()

        partes_reporte = [historia.assign(tipo_fila="Registro de proceso")]
        if not eventos.empty:
            partes_reporte.append(eventos.assign(tipo_fila="Evento"))

        reporte = pd.concat(partes_reporte, ignore_index=True).sort_values("fecha_hora")
        csv_auditoria = reporte.to_csv(index=False, sep=";").encode("utf-8-sig")

        st.download_button(
            "📥 Descargar reporte del lote (CSV)",
            data=csv_auditoria,
            file_name=f"Trazabilidad_{lote_elegido}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    st.markdown("#### Registros encontrados")
    st.dataframe(
        df_resultado[
            [
                "id",
                "fecha_hora",
                "id_lote",
                "cliente",
                "maquina",
                "turno",
                "responsable",
                "humedad_pct",
                "minutos_detencion",
                "estado_regla",
                "validacion_turno",
                "nota_bitacora",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("N°", width="small"),
            "fecha_hora": "Fecha y hora",
            "id_lote": "Lote",
            "cliente": "Cliente",
            "maquina": "Equipo",
            "turno": "Turno",
            "responsable": "Responsable",
            "humedad_pct": st.column_config.NumberColumn(
                "Humedad (%)",
                format="%.1f",
            ),
            "minutos_detencion": "Detención (min)",
            "estado_regla": "Semáforo",
            "validacion_turno": "Validación",
            "nota_bitacora": "Nota",
        },
    )
