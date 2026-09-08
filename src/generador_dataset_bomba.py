#!/usr/bin/env python3
"""Generador físico-informado de datos sintéticos para una bomba de inyección.

El Excel de rangos es la fuente de verdad para valores normales, alarmas,
disparos y clases. La simulación genera operación normal, transitorios,
fallas progresivas/súbitas/oscilatorias, alarmas y disparos.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RANGE_SHEET = "Rangos y protecciones"
CLASS_SHEET = "Clases de falla"

HYDRAULIC = [
    "Suction_Filter_DP", "Suction_Pressure", "Discharge_Pressure",
    "Suction_Flow", "Wellhead_Pressure",
]
VIBRATIONS = [
    "Pump_Vibration_Free_End", "Pump_Vibration_Coupling_End",
    "Motor_Vibration_Free_End", "Motor_Vibration_Coupling_End",
]
BEARING_TEMPS = [
    "Pump_Bearing_Temp_Free_End", "Pump_Bearing_Temp_Coupling_End",
    "Motor_Bearing_Temp_Free_End", "Motor_Bearing_Temp_Coupling_End",
]
WINDING_TEMPS = [
    "Motor_Winding_Temp_1A", "Motor_Winding_Temp_1B",
    "Motor_Winding_Temp_2A", "Motor_Winding_Temp_2B",
    "Motor_Winding_Temp_3A", "Motor_Winding_Temp_3B",
]
NUMERIC_VARIABLES = (
    HYDRAULIC + ["VFD_Frequency_Actual", "Motor_Current", "Pump_Running"]
    + VIBRATIONS + BEARING_TEMPS + WINDING_TEMPS
    + ["Injection_Valve_Position"]
)

FAULT_NAMES = {
    0: "Operación normal",
    1: "Filtro de succión obstruido",
    2: "Baja presión de succión",
    3: "Alta presión de descarga",
    4: "Cavitación",
    5: "Sobrecarga del motor",
    6: "Falla de rodamiento",
    7: "Baja presión de descarga",
    8: "Alta temperatura de devanados",
    9: "Alta temperatura de rodamientos",
    10: "Alta vibración en bomba o motor",
    11: "Bajo caudal de succión",
    12: "Alta corriente del motor",
    13: "Alta presión en el cabezal del pozo",
    14: "Baja presión del cabezal / posible ruptura de tubería",
    15: "Alto caudal de succión",
}

TRIP_PROBABILITY = {2: 1.0, 3: 1.0, 4: 0.30, 5: 1.0, 6: 0.55,
                    8: 0.85, 9: 0.80, 10: 0.80, 11: 1.0, 12: 1.0,
                    13: 1.0, 14: 1.0, 15: 1.0}


@dataclass
class Event:
    event_id: int
    code: int
    start: int
    end: int
    trip_start: int | None
    severity: float = 1.0
    subtype: str = ""
    location: str = ""
    trigger_variable: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True,
                        help="Excel Rangos_y_protecciones_bomba_inyeccion.xlsx")
    parser.add_argument("--output-dir", type=Path, default=Path("salidas_generador"))
    parser.add_argument("--start", default="2026-01-01 00:00:00")
    parser.add_argument("--days", type=float, default=7.0)
    parser.add_argument("--sample-seconds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=74145)
    parser.add_argument("--fault-codes", default="all",
                        help="all o lista separada por comas, por ejemplo 1,2,4")
    parser.add_argument("--events-per-class", type=int, default=1,
                        help="Número de eventos por clase solicitada")
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args()


def _number(value):
    if pd.isna(value) or str(value).strip().upper() == "NA":
        return np.nan
    return float(value)


def read_configuration(path: Path) -> tuple[pd.DataFrame, dict[int, str]]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el Excel: {path}")

    ranges = pd.read_excel(path, sheet_name=RANGE_SHEET, header=3)
    ranges = ranges[ranges["Variable"].isin(NUMERIC_VARIABLES)].copy()
    ranges = ranges.set_index("Variable")
    for col in ["Mín. observado", "Máx. observado", "Valor normal", "Mín. normal",
                "Máx. normal", "Alarma baja", "Disparo baja", "Alarma alta",
                "Disparo alta"]:
        ranges[col] = ranges[col].map(_number)

    missing = sorted(set(NUMERIC_VARIABLES) - set(ranges.index))
    if missing:
        raise ValueError(f"Faltan variables en el Excel: {missing}")

    classes = pd.read_excel(path, sheet_name=CLASS_SHEET, header=3)
    classes = classes.dropna(subset=["Código", "Failure_Name"])
    class_names = {int(row["Código"]): str(row["Failure_Name"]) for _, row in classes.iterrows()}
    if set(class_names) != set(FAULT_NAMES):
        raise ValueError("Las clases del Excel no coinciden con los códigos 0–15 esperados.")
    return ranges, class_names


def smooth_noise(rng: np.random.Generator, n: int, scale: float, span: int) -> np.ndarray:
    raw = pd.Series(rng.normal(0, scale, n))
    return raw.ewm(span=max(2, span), adjust=False).mean().to_numpy()


def clip_to_normal(x: np.ndarray, ranges: pd.DataFrame, variable: str, margin: float = 0.02):
    row = ranges.loc[variable]
    lo, hi = row["Mín. normal"], row["Máx. normal"]
    if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
        pad = (hi - lo) * margin
        return np.clip(x, lo + pad, hi - pad)
    return x


def build_normal_operation(n: int, dt: int, ranges: pd.DataFrame,
                           rng: np.random.Generator) -> pd.DataFrame:
    t = np.arange(n) * dt
    day_wave = np.sin(2 * np.pi * t / 86400.0)
    slow = smooth_noise(rng, n, 1.0, max(30, 900 // dt))

    freq = 50 + 2.2 * day_wave + 1.1 * slow
    valve = 50 + 7 * np.sin(2 * np.pi * t / 43200.0 + 0.8) + 2.0 * slow
    freq = clip_to_normal(freq, ranges, "VFD_Frequency_Actual")
    valve = clip_to_normal(valve, ranges, "Injection_Valve_Position")

    flow = 6000 * (freq / 50) * (0.85 + 0.003 * valve)
    flow += smooth_noise(rng, n, 80, max(5, 30 // dt))
    flow = clip_to_normal(flow, ranges, "Suction_Flow")

    wellhead = 1250 + 0.065 * (flow - 6000) + smooth_noise(rng, n, 7, max(10, 60 // dt))
    wellhead = clip_to_normal(wellhead, ranges, "Wellhead_Pressure")
    discharge = wellhead + 45 + 0.025 * (flow - 6000)
    discharge += smooth_noise(rng, n, 4, max(10, 45 // dt))
    discharge = clip_to_normal(discharge, ranges, "Discharge_Pressure")

    suction = 40 - 0.004 * (flow - 6000) + smooth_noise(rng, n, 1.1, max(10, 60 // dt))
    suction = clip_to_normal(suction, ranges, "Suction_Pressure")
    dp = 1.0 + 0.00010 * (flow - 6000) + smooth_noise(rng, n, 0.035, max(5, 30 // dt))
    dp = clip_to_normal(dp, ranges, "Suction_Filter_DP")

    current = 200 * (freq / 50) * (0.72 + 0.28 * discharge / 1250)
    current += smooth_noise(rng, n, 2.5, max(5, 20 // dt))
    current = clip_to_normal(current, ranges, "Motor_Current")

    data = {
        "Suction_Filter_DP": dp,
        "Suction_Pressure": suction,
        "Discharge_Pressure": discharge,
        "Suction_Flow": flow,
        "Wellhead_Pressure": wellhead,
        "VFD_Frequency_Actual": freq,
        "Motor_Current": current,
        "Pump_Running": np.ones(n, dtype=np.int8),
        "Injection_Valve_Position": valve,
    }

    vibration_load = (current - 200) / 1000
    for i, name in enumerate(VIBRATIONS):
        data[name] = np.clip(
            0.030 + vibration_load + smooth_noise(rng, n, 0.003, max(2, 5 // dt))
            + rng.normal(0, 0.0015, n) + i * 0.0006,
            0, 0.095,
        )

    bearing_target = 90 + 0.10 * (current - 200)
    winding_target = 95 + 0.15 * (current - 200)
    for i, name in enumerate(BEARING_TEMPS):
        data[name] = np.clip(bearing_target + i * 0.5 + smooth_noise(rng, n, 1.0, max(60, 600 // dt)), 60, 109)
    for i, name in enumerate(WINDING_TEMPS):
        data[name] = np.clip(winding_target + (i % 2) * 0.7 + smooth_noise(rng, n, 1.2, max(60, 600 // dt)), 70, 119)

    return pd.DataFrame(data)


def schedule_events(n: int, dt: int, codes: list[int], rng: np.random.Generator) -> list[Event]:
    if not codes:
        return []
    reserve = max(300 // dt, 1)
    available = n - 2 * reserve
    if available <= 0:
        raise ValueError("La simulación es demasiado corta para insertar eventos.")

    # En simulaciones cortas reduce automáticamente la cantidad de fallas.
    min_block = max(8 * 60 // dt, 30)
    max_events = max(1, available // (min_block + reserve))
    if len(codes) > max_events:
        chosen = rng.choice(len(codes), size=max_events, replace=False)
        codes = [codes[i] for i in chosen]

    segment = available // len(codes)
    events = []
    for idx, code in enumerate(rng.permutation(codes), start=1):
        seg_start = reserve + (idx - 1) * segment
        seg_end = reserve + idx * segment
        max_duration = max(min_block, min(40 * 60 // dt, segment // 2))
        min_duration = min(min_block, max_duration)
        duration = int(rng.integers(min_duration, max_duration + 1))
        latest = max(seg_start, seg_end - duration - reserve // 2)
        start = int(rng.integers(seg_start, latest + 1)) if latest > seg_start else seg_start
        end = min(n, start + duration)
        trip_start = None
        if duration >= 60 and rng.random() < TRIP_PROBABILITY.get(int(code), 0.0):
            trip_start = start + int(duration * rng.uniform(0.75, 0.90))
        events.append(Event(idx, int(code), start, end, trip_start,
                            severity=float(rng.uniform(0.80, 1.20))))
    return sorted(events, key=lambda e: e.start)


def profile(length: int, mode: str, rng: np.random.Generator) -> np.ndarray:
    x = np.linspace(0, 1, length)
    if mode == "sudden":
        return np.clip((x - 0.08) / 0.08, 0, 1)
    if mode == "oscillatory":
        return np.clip(x + 0.20 * x * np.sin(np.linspace(0, 30 * np.pi, length))
                       + rng.normal(0, 0.035, length), 0, 1.25)
    if mode == "thermal":
        return 1 - np.exp(-4 * x)
    return x ** 1.25


def add(df: pd.DataFrame, sl: slice, variable: str, amount: float, p: np.ndarray):
    df.loc[sl, variable] = df.loc[sl, variable].to_numpy() + amount * p


def set_toward(df: pd.DataFrame, sl: slice, variable: str, target: float, p: np.ndarray):
    base = df.loc[sl, variable].to_numpy()
    df.loc[sl, variable] = base + (target - base) * p


def apply_fault(df: pd.DataFrame, event: Event, ranges: pd.DataFrame,
                rng: np.random.Generator, dt: int):
    idx = np.arange(event.start, event.end)
    sl = slice(event.start, event.end - 1)
    m = len(idx)
    p = profile(m, "progressive", rng)
    ps = profile(m, "sudden", rng)
    po = profile(m, "oscillatory", rng)
    pt = profile(m, "thermal", rng)
    code = event.code

    def alarm_hi(v): return ranges.loc[v, "Alarma alta"]
    def trip_hi(v): return ranges.loc[v, "Disparo alta"]
    def alarm_lo(v): return ranges.loc[v, "Alarma baja"]
    def trip_lo(v): return ranges.loc[v, "Disparo baja"]

    if code == 1:
        set_toward(df, sl, "Suction_Filter_DP", alarm_hi("Suction_Filter_DP") + 0.5, p)
        add(df, sl, "Suction_Pressure", -12, p); add(df, sl, "Suction_Flow", -1500, p)
        add(df, sl, "Discharge_Pressure", -70, p); add(df, sl, "Motor_Current", -18, p)
        add(df, sl, "Injection_Valve_Position", 10, p)
        for v in VIBRATIONS[:2]: add(df, sl, v, 0.035, p)
    elif code == 2:
        set_toward(df, sl, "Suction_Pressure", trip_lo("Suction_Pressure") - 3, ps)
        set_toward(df, sl, "Suction_Flow", trip_lo("Suction_Flow") - 250, p)
        add(df, sl, "Discharge_Pressure", -260, p); add(df, sl, "Wellhead_Pressure", -90, p)
        add(df, sl, "Motor_Current", -55, p); add(df, sl, "Injection_Valve_Position", 22, p)
        for v in VIBRATIONS[:2]: add(df, sl, v, 0.12 * po, np.ones(m))
        for v in BEARING_TEMPS[:2]: add(df, sl, v, 18, pt)
    elif code == 3:
        set_toward(df, sl, "Discharge_Pressure", trip_hi("Discharge_Pressure") + 30, ps)
        add(df, sl, "Wellhead_Pressure", 160, p); add(df, sl, "Suction_Pressure", 8, p)
        add(df, sl, "Suction_Flow", -1300, p); add(df, sl, "Motor_Current", 75, p)
        add(df, sl, "Injection_Valve_Position", -22, p)
        for v in WINDING_TEMPS: add(df, sl, v, 25, pt)
    elif code == 4:
        event.subtype = "Cavitación oscilatoria"; event.location = "Succión de la bomba"
        event.trigger_variable = "Suction_Pressure"
        oscillation = np.sin(np.linspace(0, 55 * np.pi, m)) + rng.normal(0, 0.35, m)
        add(df, sl, "Suction_Pressure", -15 * event.severity, po); add(df, sl, "Suction_Flow", -1300, po)
        add(df, sl, "Discharge_Pressure", -180, po); add(df, sl, "Motor_Current", -25, po)
        for v in VIBRATIONS[:2]: df.loc[sl, v] += 0.08 * po + 0.035 * po * oscillation
        for v in VIBRATIONS[2:]: df.loc[sl, v] += 0.025 * po
        for v in BEARING_TEMPS[:2]: add(df, sl, v, 35, pt)
        if event.trip_start is None:
            df.loc[sl, "Suction_Pressure"] = df.loc[sl, "Suction_Pressure"].clip(lower=21.5)
    elif code == 5:
        event.subtype = "Sobrecarga eléctrica"; event.location = "Motor"
        event.trigger_variable = "Motor_Current"
        set_toward(df, sl, "Motor_Current", trip_hi("Motor_Current") + 15, p)
        add(df, sl, "Discharge_Pressure", 80, p); add(df, sl, "Suction_Flow", -450, p)
        for v in VIBRATIONS[2:]: add(df, sl, v, 0.045, p)
        for v, delta in zip(BEARING_TEMPS[2:], rng.uniform(35, 55, 2)):
            add(df, sl, v, float(delta), pt)
        for v, target in zip(WINDING_TEMPS, rng.permutation(np.linspace(170, 208, 6))):
            set_toward(df, sl, v, float(target), pt)
    elif code == 6:
        pairs = dict(zip(BEARING_TEMPS, VIBRATIONS))
        primary_temp = str(rng.choice(BEARING_TEMPS)); primary_vib = pairs[primary_temp]
        prefix = primary_temp.split("_")[0]
        companion_temp = next(v for v in BEARING_TEMPS if v.startswith(prefix) and v != primary_temp)
        companion_vib = pairs[companion_temp]
        event.subtype = "Rodamiento localizado"; event.location = primary_temp
        event.trigger_variable = primary_vib
        vib_target = trip_hi(primary_vib) + 0.02 if event.trip_start is not None else 0.18
        set_toward(df, sl, primary_vib, vib_target, po)
        set_toward(df, sl, primary_temp, 170 if event.trip_start is not None else 150, pt)
        add(df, sl, companion_vib, 0.04, p); add(df, sl, companion_temp, 25, pt)
        for v in VIBRATIONS:
            if v not in (primary_vib, companion_vib): add(df, sl, v, 0.008, p)
        for v in BEARING_TEMPS:
            if v not in (primary_temp, companion_temp): add(df, sl, v, 6, pt)
        add(df, sl, "Motor_Current", 15 if prefix == "Motor" else 8, p)
    elif code == 7:
        set_toward(df, sl, "Discharge_Pressure", 720, ps)
        add(df, sl, "Wellhead_Pressure", -360, p); add(df, sl, "Suction_Flow", -1100, p)
        add(df, sl, "Suction_Pressure", -7, p); add(df, sl, "VFD_Frequency_Actual", -12, p)
        add(df, sl, "Motor_Current", -50, p); add(df, sl, "Injection_Valve_Position", 20, p)
    elif code == 8:
        phase = int(rng.integers(1, 4))
        hot = [f"Motor_Winding_Temp_{phase}A", f"Motor_Winding_Temp_{phase}B"]
        event.subtype = "Sobretemperatura de fase"; event.location = f"Fase {phase}"
        event.trigger_variable = hot[int(rng.integers(0, 2))]
        for i, v in enumerate(hot):
            target = trip_hi(v) + 3 + 3 * i if event.trip_start is not None else 195 + 8 * i
            set_toward(df, sl, v, target, pt)
        for v in WINDING_TEMPS:
            if v not in hot: add(df, sl, v, float(rng.uniform(8, 20)), pt)
        for v in BEARING_TEMPS[2:]: add(df, sl, v, 28, pt)
        add(df, sl, "Motor_Current", 45, p)
    elif code == 9:
        primary = str(rng.choice(BEARING_TEMPS)); prefix = primary.split("_")[0]
        companion = next(v for v in BEARING_TEMPS if v.startswith(prefix) and v != primary)
        event.subtype = "Sobretemperatura localizada"; event.location = primary
        event.trigger_variable = primary
        target = trip_hi(primary) + 5 if event.trip_start is not None else 170
        set_toward(df, sl, primary, target, pt); add(df, sl, companion, 28, pt)
        for v in BEARING_TEMPS:
            if v not in (primary, companion): add(df, sl, v, 5, pt)
        for v in VIBRATIONS: add(df, sl, v, 0.018 if v.startswith(prefix) else 0.006, p)
        add(df, sl, "Motor_Current", 15, p)
    elif code == 10:
        subtype = str(rng.choice(["Localizada", "Desbalance", "Desalineación", "Holgura"]))
        if subtype == "Localizada": selected = [str(rng.choice(VIBRATIONS))]
        elif subtype == "Desbalance":
            prefix = str(rng.choice(["Pump", "Motor"])); selected = [v for v in VIBRATIONS if v.startswith(prefix)]
        elif subtype == "Desalineación": selected = [VIBRATIONS[1], VIBRATIONS[3]]
        else: selected = list(VIBRATIONS)
        event.subtype = subtype; event.location = ", ".join(selected)
        event.trigger_variable = selected[0]
        for i, v in enumerate(selected):
            target = trip_hi(v) + 0.012 + 0.008 * i if event.trip_start is not None else 0.17 + 0.008 * i
            set_toward(df, sl, v, target, po)
        for v in VIBRATIONS:
            if v not in selected: add(df, sl, v, 0.012, p)
        for v in BEARING_TEMPS: add(df, sl, v, float(rng.uniform(8, 20)), pt)
        add(df, sl, "Motor_Current", 15, po)
    elif code == 11:
        set_toward(df, sl, "Suction_Flow", trip_lo("Suction_Flow") - 250, ps)
        add(df, sl, "Suction_Pressure", -13, p); add(df, sl, "Discharge_Pressure", -130, p)
        add(df, sl, "Motor_Current", -45, p); add(df, sl, "Injection_Valve_Position", 22, p)
        add(df, sl, "Suction_Filter_DP", 1.1, p)
    elif code == 12:
        set_toward(df, sl, "Motor_Current", trip_hi("Motor_Current") + 15, ps)
        add(df, sl, "Discharge_Pressure", 80, p)
        for v in BEARING_TEMPS[2:]: add(df, sl, v, 28, pt)
        for v in WINDING_TEMPS: add(df, sl, v, 55, pt)
    elif code == 13:
        set_toward(df, sl, "Wellhead_Pressure", trip_hi("Wellhead_Pressure") + 25, ps)
        set_toward(df, sl, "Discharge_Pressure", trip_hi("Discharge_Pressure") + 35, p)
        add(df, sl, "Suction_Flow", -1450, p); add(df, sl, "Motor_Current", 75, p)
        add(df, sl, "Suction_Pressure", 7, p); add(df, sl, "Injection_Valve_Position", 20, p)
    elif code == 14:
        set_toward(df, sl, "Wellhead_Pressure", trip_lo("Wellhead_Pressure") - 80, ps)
        set_toward(df, sl, "Discharge_Pressure", 420, ps)
        set_toward(df, sl, "Suction_Flow", trip_hi("Suction_Flow") + 350, ps)
        add(df, sl, "Motor_Current", 80, ps); add(df, sl, "Suction_Pressure", -7, ps)
        add(df, sl, "Injection_Valve_Position", -25, pt)
    elif code == 15:
        set_toward(df, sl, "Suction_Flow", trip_hi("Suction_Flow") + 300, ps)
        add(df, sl, "Wellhead_Pressure", -260, p); add(df, sl, "Discharge_Pressure", -120, p)
        add(df, sl, "Suction_Pressure", -7, p); add(df, sl, "Motor_Current", 80, p)
        set_toward(df, sl, "Injection_Valve_Position", 96, p)

    force_trip_threshold(df, event, ranges, dt)
    if event.trip_start is not None:
        trip = slice(event.trip_start, event.end - 1)
        k = event.end - event.trip_start
        decay = np.exp(-np.linspace(0, 7, k))
        df.loc[trip, "Pump_Running"] = 0
        for v in ["VFD_Frequency_Actual", "Motor_Current", "Suction_Flow"]:
            df.loc[trip, v] = df.loc[trip, v].to_numpy() * decay
        df.loc[trip, "Discharge_Pressure"] = (
            df.loc[trip, "Wellhead_Pressure"].to_numpy()
            + (df.loc[trip, "Discharge_Pressure"].to_numpy()
               - df.loc[trip, "Wellhead_Pressure"].to_numpy()) * decay
        )
        for v in VIBRATIONS:
            df.loc[trip, v] = df.loc[trip, v].to_numpy() * decay


def add_normal_transients(df: pd.DataFrame, dt: int,
                          rng: np.random.Generator) -> list[tuple[int, int, int, int]]:
    """Inserta paradas normales completas: bajada, espera y arranque suave."""
    n = len(df)
    count = int((n * dt) // (3 * 86400))
    if count == 0:
        return []
    blocks = []
    ramp_down = max(90 // dt, 10)
    stopped = max(180 // dt, 20)
    ramp_up = max(120 // dt, 10)
    total = ramp_down + stopped + ramp_up
    for k in range(count):
        center = int((k + 1) * n / (count + 1))
        start = int(np.clip(center + rng.integers(-1800 // dt, 1800 // dt + 1), 0, n - total))
        stop_start = start + ramp_down
        restart_start = stop_start + stopped
        end = restart_start + ramp_up
        down_sl = slice(start, stop_start - 1)
        stop_sl = slice(stop_start, restart_start - 1)
        up_sl = slice(restart_start, end - 1)
        down = np.linspace(1, 0, ramp_down)
        up = np.linspace(0, 1, ramp_up) ** 1.25
        dynamic = ["VFD_Frequency_Actual", "Motor_Current", "Suction_Flow", *VIBRATIONS]
        for v in dynamic:
            df.loc[down_sl, v] = df.loc[down_sl, v].to_numpy() * down
            df.loc[stop_sl, v] = 0.0
            df.loc[up_sl, v] = df.loc[up_sl, v].to_numpy() * up
        df.loc[stop_sl, "Pump_Running"] = 0
        df.loc[up_sl, "Pump_Running"] = 1
        df.loc[stop_sl, "Discharge_Pressure"] = df.loc[stop_sl, "Wellhead_Pressure"].to_numpy()
        blocks.append((start, stop_start, restart_start, end))
    return blocks


def force_trip_threshold(df: pd.DataFrame, event: Event, ranges: pd.DataFrame, dt: int):
    """Garantiza evidencia física del umbral antes de ordenar el disparo."""
    if event.trip_start is None:
        return
    mapping = {
        4: ("Suction_Pressure", "Disparo baja", -2.0),
        2: ("Suction_Pressure", "Disparo baja", -2.0),
        3: ("Discharge_Pressure", "Disparo alta", 20.0),
        5: ("Motor_Current", "Disparo alta", 10.0),
        8: ("Motor_Winding_Temp_1A", "Disparo alta", 3.0),
        9: ("Pump_Bearing_Temp_Free_End", "Disparo alta", 3.0),
        10: ("Pump_Vibration_Free_End", "Disparo alta", 0.01),
        11: ("Suction_Flow", "Disparo baja", -150.0),
        12: ("Motor_Current", "Disparo alta", 10.0),
        13: ("Wellhead_Pressure", "Disparo alta", 20.0),
        14: ("Wellhead_Pressure", "Disparo baja", -30.0),
        15: ("Suction_Flow", "Disparo alta", 200.0),
    }
    if event.trigger_variable:
        variable = event.trigger_variable
        column = "Disparo baja" if event.code in {2, 4, 11, 14} else "Disparo alta"
        offset = {2: -2.0, 4: -2.0, 11: -150.0, 14: -30.0}.get(event.code, 0.01)
        if variable in BEARING_TEMPS or variable in WINDING_TEMPS:
            offset = 3.0
    elif event.code in mapping:
        variable, column, offset = mapping[event.code]
    else:
        return
    threshold = ranges.loc[variable, column]
    if not np.isfinite(threshold):
        return
    width = min(max(12 // dt, 3), event.trip_start - event.start)
    start = event.trip_start - width
    sl = slice(start, event.trip_start - 1)
    current = df.loc[sl, variable].to_numpy()
    target = threshold + offset
    df.loc[sl, variable] = current + (target - current) * np.linspace(0.45, 1.0, width)


def apply_post_event_recovery(df: pd.DataFrame, event: Event, next_start: int,
                              dt: int) -> tuple[int, int]:
    """Conserva parada/enfriamiento y reinicia sin saltos verticales."""
    available = max(0, next_start - event.end)
    if available < 10:
        return event.end, event.end
    if event.trip_start is not None:
        hold = min(max(180 // dt, 20), available // 2)
        restart = min(max(150 // dt, 20), available - hold)
    else:
        hold = 0
        restart = min(max(180 // dt, 20), available)
    hold_end = event.end + hold
    recovery_end = hold_end + restart
    continuous = [v for v in NUMERIC_VARIABLES if v != "Pump_Running"]
    previous = max(event.start, event.end - 1)
    start_values = df.loc[previous, continuous].to_numpy(dtype=float)

    if hold:
        hold_sl = slice(event.end, hold_end - 1)
        hold_len = hold_end - event.end
        base = df.loc[hold_sl, continuous].to_numpy(dtype=float)
        thermal_decay = np.exp(-np.linspace(0, 1.6, hold_len))
        recovered = base.copy()
        for j, v in enumerate(continuous):
            if v in BEARING_TEMPS or v in WINDING_TEMPS:
                recovered[:, j] = base[:, j] + (start_values[j] - base[:, j]) * thermal_decay
        df.loc[hold_sl, continuous] = recovered
        zero_vars = ["VFD_Frequency_Actual", "Motor_Current", "Suction_Flow", *VIBRATIONS]
        df.loc[hold_sl, zero_vars] = 0.0
        df.loc[hold_sl, "Pump_Running"] = 0
        df.loc[hold_sl, "Discharge_Pressure"] = df.loc[hold_sl, "Wellhead_Pressure"].to_numpy()

    if restart:
        restart_sl = slice(hold_end, recovery_end - 1)
        base = df.loc[restart_sl, continuous].to_numpy(dtype=float)
        blend = (np.linspace(0, 1, restart) ** 1.35)[:, None]
        restart_values = (
            df.loc[hold_end - 1, continuous].to_numpy(dtype=float)
            if hold else start_values
        )
        recovered = base + (restart_values - base) * (1 - blend)
        if event.trip_start is not None:
            ramp_vars = ["VFD_Frequency_Actual", "Motor_Current", "Suction_Flow", *VIBRATIONS]
            for v in ramp_vars:
                j = continuous.index(v)
                recovered[:, j] = base[:, j] * blend[:, 0]
            df.loc[restart_sl, "Pump_Running"] = 1
        df.loc[restart_sl, continuous] = recovered
    return hold_end, recovery_end


def apply_limits(df: pd.DataFrame, ranges: pd.DataFrame):
    # Límites físicos amplios: permiten superar alarmas/disparos sin valores imposibles.
    nonnegative = ["Suction_Filter_DP", "Suction_Flow", "VFD_Frequency_Actual",
                   "Motor_Current", *VIBRATIONS, *BEARING_TEMPS, *WINDING_TEMPS,
                   "Injection_Valve_Position"]
    for v in nonnegative:
        df[v] = df[v].clip(lower=0)
    df["Injection_Valve_Position"] = df["Injection_Valve_Position"].clip(0, 100)
    df["Pump_Running"] = df["Pump_Running"].round().clip(0, 1).astype(np.int8)


def threshold_flags(df: pd.DataFrame, ranges: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    alarm = np.zeros(len(df), dtype=bool)
    threshold_trip = np.zeros(len(df), dtype=bool)
    for v in NUMERIC_VARIABLES:
        if v == "Pump_Running":
            continue
        row = ranges.loc[v]
        values = df[v].to_numpy()
        valid = (np.ones(len(df), dtype=bool) if v in BEARING_TEMPS + WINDING_TEMPS
                 else df["Pump_Running"].to_numpy() == 1)
        if np.isfinite(row["Alarma baja"]): alarm |= valid & (values <= row["Alarma baja"])
        if np.isfinite(row["Alarma alta"]): alarm |= valid & (values >= row["Alarma alta"])
        if np.isfinite(row["Disparo baja"]): threshold_trip |= valid & (values <= row["Disparo baja"])
        if np.isfinite(row["Disparo alta"]): threshold_trip |= valid & (values >= row["Disparo alta"])
    return alarm, threshold_trip


def validate(df: pd.DataFrame, ranges: pd.DataFrame, events: list[Event]) -> dict:
    alarm, threshold_trip = threshold_flags(df, ranges)
    numeric = df[NUMERIC_VARIABLES]
    report = {
        "rows": int(len(df)),
        "start": str(df["Timestamp"].min()),
        "end": str(df["Timestamp"].max()),
        "duplicate_timestamps": int(df["Timestamp"].duplicated().sum()),
        "missing_values": int(df.isna().sum().sum()),
        "chronological": bool(df["Timestamp"].is_monotonic_increasing),
        "events": len(events),
        "alarm_rows": int(alarm.sum()),
        "threshold_trip_rows": int(threshold_trip.sum()),
        "simulated_trip_rows": int(df["Trip_Active"].sum()),
        "normal_rows_pct": round(float((df["Failure_Code"] == 0).mean() * 100), 3),
        "min_by_variable": {k: round(float(v), 5) for k, v in numeric.min().items()},
        "max_by_variable": {k: round(float(v), 5) for k, v in numeric.max().items()},
        "rows_by_failure": {str(int(k)): int(v) for k, v in df["Failure_Code"].value_counts().sort_index().items()},
    }
    return report


def create_plots(df: pd.DataFrame, output_dir: Path):
    plot_vars = ["Suction_Pressure", "Discharge_Pressure", "Suction_Flow",
                 "Motor_Current", "Pump_Vibration_Free_End", "Motor_Winding_Temp_1A"]
    step = max(1, len(df) // 20000)
    sample = df.iloc[::step]
    fig, axes = plt.subplots(3, 2, figsize=(16, 10), sharex=True)
    for ax, variable in zip(axes.flat, plot_vars):
        ax.plot(sample["Timestamp"], sample[variable], lw=0.8)
        ax.set_title(variable)
        ax.grid(alpha=0.2)
    fig.suptitle("Validación visual del dataset sintético", fontsize=14)
    fig.tight_layout()
    fig.savefig(output_dir / "series_principales.png", dpi=150)
    plt.close(fig)

    counts = df["Failure_Code"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.bar(counts.index.astype(str), counts.values)
    ax.set(title="Registros por clase", xlabel="Failure_Code", ylabel="Registros")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_dir / "distribucion_clases.png", dpi=150)
    plt.close(fig)


def generate(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    if args.days <= 0 or args.sample_seconds <= 0 or args.events_per_class <= 0:
        raise ValueError("days, sample-seconds y events-per-class deben ser mayores que cero.")
    ranges, class_names = read_configuration(args.config)
    rng = np.random.default_rng(args.seed)
    n = int(round(args.days * 86400 / args.sample_seconds))
    if n < 60:
        raise ValueError("Se requieren al menos 60 registros.")

    if args.fault_codes.strip().lower() == "all":
        codes = list(range(1, 16))
    else:
        codes = sorted({int(x.strip()) for x in args.fault_codes.split(",") if x.strip()})
        invalid = sorted(set(codes) - set(range(1, 16)))
        if invalid:
            raise ValueError(f"Códigos de falla inválidos: {invalid}")

    codes = [code for code in codes for _ in range(args.events_per_class)]
    df = build_normal_operation(n, args.sample_seconds, ranges, rng)
    normal_stops = add_normal_transients(df, args.sample_seconds, rng)
    events = schedule_events(n, args.sample_seconds, codes, rng)

    failure_code = np.zeros(n, dtype=np.int16)
    event_id = np.zeros(n, dtype=np.int16)
    trip_active = np.zeros(n, dtype=np.int8)
    operating_state = np.full(n, "Normal", dtype=object)
    fault_subtype = np.full(n, "No aplica", dtype=object)
    fault_location = np.full(n, "No aplica", dtype=object)
    severity = np.zeros(n, dtype=float)

    for position, event in enumerate(events):
        apply_fault(df, event, ranges, rng, args.sample_seconds)
        if not event.subtype:
            event.subtype = "Patrón estándar"
        if not event.location:
            event.location = "Sistema de bombeo"
        failure_code[event.start:event.end] = event.code
        event_id[event.start:event.end] = event.event_id
        fault_subtype[event.start:event.end] = event.subtype
        fault_location[event.start:event.end] = event.location
        severity[event.start:event.end] = event.severity
        progress_end = event.start + int((event.end - event.start) * 0.35)
        operating_state[event.start:progress_end] = "Degrading"
        operating_state[progress_end:event.end] = "Fault"
        if event.trip_start is not None:
            trip_active[event.trip_start:event.end] = 1
            operating_state[event.trip_start:event.end] = "Tripped"

        next_start = events[position + 1].start if position + 1 < len(events) else n
        hold_end, recovery_end = apply_post_event_recovery(
            df, event, next_start, args.sample_seconds
        )
        if event.trip_start is not None:
            operating_state[event.end:hold_end] = "Stopped"
            operating_state[hold_end:recovery_end] = "Starting"
        else:
            operating_state[event.end:recovery_end] = "Recovering"

    for down_start, stop_start, restart_start, stop_end in normal_stops:
        positions = np.arange(stop_end - down_start)
        normal_mask = failure_code[down_start:stop_end] == 0
        local = operating_state[down_start:stop_end]
        local[(positions < stop_start - down_start) & normal_mask] = "Stopping"
        local[(positions >= stop_start - down_start)
              & (positions < restart_start - down_start) & normal_mask] = "Stopped"
        local[(positions >= restart_start - down_start) & normal_mask] = "Starting"
        operating_state[down_start:stop_end] = local

    apply_limits(df, ranges)
    alarm_active, _ = threshold_flags(df, ranges)
    timestamps = pd.date_range(args.start, periods=n, freq=f"{args.sample_seconds}s")
    df.insert(0, "Timestamp", timestamps)
    df["Operating_State"] = operating_state
    stopped_normal = (df["Pump_Running"] == 0) & (failure_code == 0)
    df.loc[stopped_normal, "Operating_State"] = "Stopped"
    df["Failure_Code"] = failure_code
    df["Failure_Name"] = pd.Series(failure_code).map(class_names).to_numpy()
    df["Alarm_Active"] = alarm_active.astype(np.int8)
    df["Trip_Active"] = trip_active
    df["Event_ID"] = event_id
    df["Fault_Subtype"] = fault_subtype
    df["Fault_Location"] = fault_location
    df["Severity"] = severity

    ordered = ["Timestamp", *NUMERIC_VARIABLES, "Operating_State", "Failure_Code",
               "Failure_Name", "Fault_Subtype", "Fault_Location", "Severity",
               "Alarm_Active", "Trip_Active", "Event_ID"]
    df = df[ordered]
    report = validate(df, ranges, events)
    report["event_schedule"] = [
        {
            "event_id": e.event_id,
            "failure_code": e.code,
            "failure_name": class_names[e.code],
            "start": str(timestamps[e.start]),
            "end": str(timestamps[e.end - 1]),
            "trip_start": str(timestamps[e.trip_start]) if e.trip_start is not None else None,
            "severity": round(e.severity, 3),
            "subtype": e.subtype,
            "location": e.location,
            "trigger_variable": e.trigger_variable,
        }
        for e in events
    ]
    return df, report


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df, report = generate(args)
    dataset_path = args.output_dir / "dataset_bomba_inyeccion.csv"
    df.to_csv(dataset_path, index=False, float_format="%.5f")
    (args.output_dir / "informe_validacion.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if not args.no_plots:
        create_plots(df, args.output_dir)

    print(f"Dataset generado: {dataset_path}")
    print(f"Registros: {len(df):,}")
    print(f"Eventos: {report['events']}")
    print(f"Operación normal: {report['normal_rows_pct']:.3f}%")
    print(f"Valores faltantes: {report['missing_values']}")


if __name__ == "__main__":
    main()
