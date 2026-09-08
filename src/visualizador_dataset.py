#!/usr/bin/env python3
"""Visualizador interactivo para revisar las señales del dataset sintético."""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


DEFAULT_DATASET = "data/processed/dataset_definitivo_15d/dataset_bomba_inyeccion.csv"
META_COLUMNS = {
    "Timestamp", "Operating_State", "Failure_Code", "Failure_Name",
    "Fault_Subtype", "Fault_Location", "Severity",
    "Alarm_Active", "Trip_Active", "Event_ID", "Pump_Running",
}


@st.cache_data(show_spinner="Cargando dataset...")
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Timestamp"])
    df = df.sort_values("Timestamp").reset_index(drop=True)
    return df


def event_summary(df: pd.DataFrame) -> pd.DataFrame:
    fault = df[df["Event_ID"] > 0]
    if fault.empty:
        return pd.DataFrame()
    aggregation = {"Inicio": ("Timestamp", "min"), "Fin": ("Timestamp", "max"),
                   "Registros": ("Timestamp", "size"), "Disparo": ("Trip_Active", "max")}
    for column, label in [("Fault_Subtype", "Subtipo"), ("Fault_Location", "Ubicación"),
                          ("Severity", "Severidad")]:
        if column in fault.columns:
            aggregation[label] = (column, "first")
    return fault.groupby(["Event_ID", "Failure_Code", "Failure_Name"], as_index=False).agg(**aggregation)


def downsample(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = int(np.ceil(len(df) / max_points))
    regular = np.arange(0, len(df), step)
    changes = np.flatnonzero(
        df["Failure_Code"].ne(df["Failure_Code"].shift()).to_numpy()
        | df["Operating_State"].ne(df["Operating_State"].shift()).to_numpy()
    )
    indices = np.unique(np.concatenate([regular, changes, np.maximum(changes - 1, 0)]))
    return df.iloc[indices]


def fault_intervals(df: pd.DataFrame):
    summary = event_summary(df)
    for _, row in summary.iterrows():
        yield row["Inicio"], row["Fin"], int(row["Failure_Code"]), row["Failure_Name"]


def state_intervals(df: pd.DataFrame):
    states = df["Operating_State"].astype(str)
    groups = states.ne(states.shift()).cumsum()
    for _, block in df.groupby(groups):
        state = str(block["Operating_State"].iloc[0])
        if state in {"Stopped", "Starting", "Recovering"}:
            yield block["Timestamp"].iloc[0], block["Timestamp"].iloc[-1], state


st.set_page_config(page_title="Bomba de inyección", layout="wide")
st.title("Visualizador del dataset sintético")
st.caption("Selección de señales, zoom temporal, eventos, alarmas y disparos")

with st.sidebar:
    st.header("Dataset")
    path = st.text_input("Ruta del CSV", DEFAULT_DATASET)
    if not Path(path).exists():
        st.error("No se encontró el archivo. Revisa la ruta relativa al proyecto.")
        st.stop()

df = load_data(path)
data_start = df["Timestamp"].min()
data_end = df["Timestamp"].max()
numeric_sensors = [
    c for c in df.select_dtypes(include="number").columns
    if c not in META_COLUMNS
]
events = event_summary(df)

st.info(
    f"Datos disponibles desde **{data_start:%Y-%m-%d %H:%M:%S}** "
    f"hasta **{data_end:%Y-%m-%d %H:%M:%S}**"
)

with st.sidebar:
    st.subheader("Intervalo de análisis")
    st.caption(f"Disponible: {data_start:%Y-%m-%d %H:%M:%S} → {data_end:%Y-%m-%d %H:%M:%S}")
    start_date = st.date_input(
        "Fecha inicial", value=data_start.date(),
        min_value=data_start.date(), max_value=data_end.date(),
    )
    start_time = st.time_input("Hora inicial", value=data_start.time())
    end_date = st.date_input(
        "Fecha final", value=data_end.date(),
        min_value=data_start.date(), max_value=data_end.date(),
    )
    end_time = st.time_input("Hora final", value=data_end.time())

    requested_start = pd.Timestamp.combine(start_date, start_time)
    requested_end = pd.Timestamp.combine(end_date, end_time)
    start = max(data_start, requested_start)
    end = min(data_end, requested_end)
    if start > end:
        st.error("La fecha y hora inicial deben ser anteriores a la fecha y hora final.")
        st.stop()

    defaults = [c for c in ["Suction_Pressure", "Discharge_Pressure", "Suction_Flow",
                            "Motor_Current"] if c in numeric_sensors]
    signals = st.multiselect("Señales", numeric_sensors, default=defaults)
    show_pump_running = st.checkbox("Mostrar bomba encendida/apagada", value=True)
    normalize = st.checkbox("Normalizar para comparar", value=False)
    show_states = st.checkbox("Mostrar estados operativos", value=True)
    max_points = st.slider(
        "Máximo de puntos mostrados", 2_000, 50_000, 15_000, 1_000,
        help="Solo limita los puntos dibujados; no modifica los cálculos ni el dataset.",
    )
    st.caption("Solo afecta el dibujo; las métricas usan todos los registros del intervalo.")
    events_in_range = events[
        (events["Fin"] >= start) & (events["Inicio"] <= end)
    ] if not events.empty else events
    event_options = ["Todos"] + ([str(int(x)) for x in events_in_range["Event_ID"]]
                                  if not events_in_range.empty else [])
    selected_event = st.selectbox("Evento", event_options)

if selected_event != "Todos":
    event_id = int(selected_event)
    event_rows = df[df["Event_ID"] == event_id]
    margin = pd.Timedelta(minutes=5)
    start = max(start, event_rows["Timestamp"].min() - margin)
    end = min(end, event_rows["Timestamp"].max() + margin)

view = df[df["Timestamp"].between(start, end)].copy()
plot_df = downsample(view, max_points)
visible_events = events[(events["Fin"] >= start) & (events["Inicio"] <= end)].copy()
if selected_event != "Todos":
    visible_events = visible_events[visible_events["Event_ID"] == int(selected_event)]

st.caption(f"Intervalo visualizado: **{start:%Y-%m-%d %H:%M:%S}** → **{end:%Y-%m-%d %H:%M:%S}**")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Registros del intervalo", f"{len(view):,}")
c2.metric("Registros con alarma", f"{int(view['Alarm_Active'].sum()):,}")
c3.metric("Registros en disparo", f"{int(view['Trip_Active'].sum()):,}")
c4.metric("Eventos", int(view.loc[view["Event_ID"] > 0, "Event_ID"].nunique()))

if show_pump_running:
    status = plot_df["Pump_Running"].astype(int)
    status_colors = np.where(status.eq(1), "#16a34a", "#dc2626")
    status_fig = go.Figure()
    status_fig.add_trace(go.Scatter(
        x=plot_df["Timestamp"], y=status, mode="lines",
        line={"width": 3, "shape": "hv", "color": "#16a34a"},
        fill="tozeroy", fillcolor="rgba(22,163,74,0.12)",
        customdata=status_colors,
        hovertemplate="%{x}<br>Estado: %{y}<extra></extra>",
    ))
    off = plot_df[status.eq(0)]
    if not off.empty:
        status_fig.add_trace(go.Scatter(
            x=off["Timestamp"], y=np.zeros(len(off)), mode="markers",
            marker={"size": 6, "color": "#dc2626"},
            hovertemplate="%{x}<br>APAGADA (0)<extra></extra>",
        ))
    status_fig.update_layout(
        title="Estado de la bomba — 1: ENCENDIDA · 0: APAGADA",
        height=190, showlegend=False, hovermode="x unified",
        margin={"l": 50, "r": 30, "t": 50, "b": 30},
    )
    status_fig.update_yaxes(tickmode="array", tickvals=[0, 1],
                            ticktext=["APAGADA", "ENCENDIDA"], range=[-0.08, 1.08])
    st.plotly_chart(status_fig, width="stretch", config={"scrollZoom": True})

if not signals:
    st.warning("Selecciona al menos una señal en el panel izquierdo.")
else:
    fig = make_subplots(rows=len(signals), cols=1, shared_xaxes=True,
                        vertical_spacing=min(0.04, 0.20 / len(signals)),
                        subplot_titles=signals)
    for row, signal in enumerate(signals, start=1):
        y = plot_df[signal].astype(float)
        label = signal
        if normalize:
            std = y.std()
            y = (y - y.mean()) / std if std > 0 else y * 0
            label = f"{signal} (z-score)"
        fig.add_trace(
            go.Scattergl(x=plot_df["Timestamp"], y=y, mode="lines", name=label,
                         line={"width": 1.2}), row=row, col=1
        )
        fig.update_yaxes(title_text="z" if normalize else "Valor", row=row, col=1)

    colors = ["rgba(239,68,68,0.13)", "rgba(245,158,11,0.14)",
              "rgba(139,92,246,0.13)", "rgba(14,165,233,0.13)"]
    for i, (fault_start, fault_end, code, name) in enumerate(fault_intervals(view)):
        fig.add_vrect(x0=fault_start, x1=fault_end, fillcolor=colors[i % len(colors)],
                      line_width=0, annotation_text=f"{code}: {name}",
                      annotation_position="top left", row="all", col=1)
    if show_states:
        state_colors = {"Stopped": "rgba(100,116,139,0.12)",
                        "Starting": "rgba(34,197,94,0.10)",
                        "Recovering": "rgba(59,130,246,0.08)"}
        for state_start, state_end, state in state_intervals(view):
            fig.add_vrect(x0=state_start, x1=state_end, fillcolor=state_colors[state],
                          line_width=0, row="all", col=1)
    fig.update_layout(height=max(420, 260 * len(signals)), hovermode="x unified",
                      showlegend=False, margin={"l": 50, "r": 30, "t": 60, "b": 40})
    fig.update_xaxes(rangeslider_visible=(len(signals) == 1), row=len(signals), col=1)
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": True})

st.subheader("Eventos de falla")
if visible_events.empty:
    st.info("El dataset no contiene eventos.")
else:
    st.dataframe(visible_events, width="stretch", hide_index=True)

with st.expander("Distribución de estados y clases"):
    left, right = st.columns(2)
    left.dataframe(view["Operating_State"].value_counts().rename_axis("Estado").reset_index(name="Registros"),
                   width="stretch", hide_index=True)
    right.dataframe(view.groupby(["Failure_Code", "Failure_Name"]).size().reset_index(name="Registros"),
                    width="stretch", hide_index=True)
