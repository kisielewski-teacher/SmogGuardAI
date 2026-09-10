
# -*- coding: utf-8 -*-
import os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="PM10 – Dashboard", layout="wide")
st.title("PM10 – rzeczywiste vs prognoza")

def find_latest(pattern: str) -> str:
    import glob
    files = glob.glob(pattern)
    if not files:
        return ""
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]

# --- Panel boczny: źródło danych (scalone)
st.sidebar.header("Źródło danych")
_script_dir = os.path.dirname(os.path.abspath(__file__))
_outputs_dir = os.path.join(_script_dir, "..", "outputs")
default = os.path.normpath(os.path.join(_outputs_dir, "pm10_all_latest.csv"))
if not os.path.isfile(default):
    fallback = find_latest(os.path.join(_outputs_dir, "pm10_all_*.csv"))
    default = fallback or ""

csv_path = st.sidebar.text_input("Plik CSV", value=default)
auto_refresh = st.sidebar.checkbox("Auto-odśwież co 30 sek", False)
refresh_btn = st.sidebar.button("Odśwież teraz")
st.sidebar.markdown("---")
st.sidebar.header("Filtr danych")

@st.cache_data(ttl=30)
def load_data(path: str) -> pd.DataFrame:
    if not path or not os.path.isfile(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    # czas
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    # unikanie duplikatów
    df = df.drop_duplicates(subset=["timestamp"])
    # typy numeryczne
    for c in ["pm10_true", "pm10_hist", "pm10_pred", "error"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("timestamp")

if refresh_btn:
    st.cache_data.clear()

df = load_data(csv_path)
if df.empty:
    st.error("Brak danych w pliku.")
    st.stop()

# wymagane kolumny
if "pm10_true" not in df.columns or "timestamp" not in df.columns:
    st.error("Brakuje kolumn 'timestamp' i/lub 'pm10_true' w danych.")
    st.stop()

# Filtr zakresu dat
ts_min = df["timestamp"].min().date()
ts_max = df["timestamp"].max().date()
date_range = st.sidebar.date_input(
    "Zakres dat",
    value=(ts_min, ts_max),
    min_value=ts_min,
    max_value=ts_max,
)
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    d_from, d_to = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
    df = df[(df["timestamp"] >= d_from) & (df["timestamp"] < d_to)]

# cutoff historia/przyszłość
last_true = df["timestamp"][df["pm10_true"].notna()].max()
hist_mask = df["timestamp"] <= last_true
fut_mask  = df["timestamp"] >  last_true

# Średnia krocząca 24h
df["pm10_rolling"] = df["pm10_true"].rolling(24, min_periods=1).mean()

has_error = "error" in df.columns and df.loc[hist_mask, "error"].notna().any()

# --- Wykres: subploty (główny + błąd)
if has_error:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.06,
        subplot_titles=("PM10 – rzeczywiste vs prognoza", "Błąd prognozy (prognoza – rzeczywiste)")
    )
    r_main, r_err = 1, 2
else:
    fig = make_subplots(rows=1, cols=1)
    r_main = 1

# Strefy kolorystyczne norm PM10 (tylko na głównym subplocie)
for y0, y1, color, label in [
    (0,   45,  "#2ecc71", "Dobra (< 45)"),
    (45,  75,  "#f39c12", "Umiarkowana (45–75)"),
    (75,  150, "#e74c3c", "Zła (75–150)"),
    (150, 500, "#8e44ad", "Bardzo zła (> 150)"),
]:
    fig.add_hrect(y0=y0, y1=y1, fillcolor=color, opacity=0.07, line_width=0,
                  row=r_main, col=1,
                  annotation_text=label, annotation_position="top left",
                  annotation=dict(font_size=10, font_color=color))

# Rzeczywiste (historia)
fig.add_trace(go.Scatter(
    x=df.loc[hist_mask, "timestamp"],
    y=df.loc[hist_mask, "pm10_true"],
    name="PM10 (rzeczywiste)",
    mode="lines+markers",
    marker=dict(size=4),
    line=dict(color="#d62728"),
    connectgaps=False,
    line_shape='hv'
), row=r_main, col=1)

# Średnia krocząca 24h
fig.add_trace(go.Scatter(
    x=df.loc[hist_mask, "timestamp"],
    y=df.loc[hist_mask, "pm10_rolling"],
    name="Średnia 24h",
    mode="lines",
    line=dict(color="#ff7f0e", width=2, dash="dash"),
    connectgaps=True,
), row=r_main, col=1)

# Prognoza (historia)
if "pm10_hist" in df.columns:
    fig.add_trace(go.Scatter(
        x=df.loc[hist_mask, "timestamp"],
        y=df.loc[hist_mask, "pm10_hist"],
        name="PM10 (prognoza – historia)",
        mode="lines+markers",
        marker=dict(size=4),
        line=dict(color="#1f77b4"),
        connectgaps=False,
        line_shape='hv'
    ), row=r_main, col=1)

# Prognoza (przyszłość) z przedziałem ufności ±15%
if "pm10_pred" in df.columns:
    pred_vals = df.loc[fut_mask, "pm10_pred"]
    if "pm10_pred_lower" in df.columns and "pm10_pred_upper" in df.columns:
        lower = df.loc[fut_mask, "pm10_pred_lower"]
        upper = df.loc[fut_mask, "pm10_pred_upper"]
    else:
        lower = pred_vals * 0.85
        upper = pred_vals * 1.15
    x_fut = df.loc[fut_mask, "timestamp"]
    fig.add_trace(go.Scatter(
        x=x_fut, y=upper,
        mode="lines", line=dict(width=0),
        showlegend=False, name="górna granica", hoverinfo="skip"
    ), row=r_main, col=1)
    fig.add_trace(go.Scatter(
        x=x_fut, y=lower,
        mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(44,160,44,0.15)",
        showlegend=False, name="dolna granica", hoverinfo="skip"
    ), row=r_main, col=1)
    fig.add_trace(go.Scatter(
        x=x_fut, y=pred_vals,
        name="PM10 (prognoza – przyszłość)",
        mode="lines+markers",
        marker=dict(size=4),
        line=dict(color="#2ca02c", dash="dot"),
        connectgaps=False,
        line_shape='hv'
    ), row=r_main, col=1)

# pionowa linia rozdzielająca historia/przyszłość
fig.add_vline(x=last_true, line_color="gray", line_width=1, line_dash="dot")

# Wykres błędu (subplot 2)
if has_error:
    err_data = df.loc[hist_mask].dropna(subset=["error"])
    colors_bar = ["#e74c3c" if v > 0 else "#3498db" for v in err_data["error"]]
    fig.add_trace(go.Bar(
        x=err_data["timestamp"],
        y=err_data["error"],
        name="Błąd (prognoza – rzeczywiste)",
        marker_color=colors_bar,
        showlegend=True,
    ), row=r_err, col=1)
    fig.add_hline(y=0, line_color="gray", line_width=1, row=r_err, col=1)
    fig.update_yaxes(title_text="µg/m³", row=r_err, col=1)

fig.update_layout(
    title="PM10 – rzeczywiste vs prognoza",
    yaxis_title="µg/m³",
    legend=dict(orientation="h", y=-0.12 if has_error else -0.15),
    hovermode="x unified",
    height=650 if has_error else 480,
)
fig.update_xaxes(title_text="timestamp", row=r_main if not has_error else r_err, col=1)

st.plotly_chart(fig, use_container_width=True)

# --- Kafelki: bieżący stan
def aqi_pm10(val: float) -> tuple[str, str]:
    """Zwraca (opis, kolor) dla wartości PM10 µg/m³ wg norm PL/WHO."""
    if val < 20:   return "Bardzo dobra", "🟢"
    if val < 45:   return "Dobra",         "🟡"
    if val < 75:   return "Umiarkowana",   "🟠"
    if val < 150:  return "Zła",           "🔴"
    return "Bardzo zła", "🟣"

last_true_val = df.loc[hist_mask, "pm10_true"].dropna()
next_pred_val = df.loc[fut_mask, "pm10_pred"].dropna() if "pm10_pred" in df.columns else pd.Series([], dtype=float)

st.subheader("Stan powietrza")
kc1, kc2, kc3, kc4 = st.columns(4)

if not last_true_val.empty:
    cur = last_true_val.iloc[-1]
    desc, icon = aqi_pm10(cur)
    kc1.metric("PM10 (ostatni pomiar)", f"{cur:.1f} µg/m³")
    kc2.metric("Jakość powietrza", f"{icon} {desc}")
else:
    kc1.metric("PM10 (ostatni pomiar)", "–")
    kc2.metric("Jakość powietrza", "–")

if not next_pred_val.empty:
    nxt = next_pred_val.iloc[0]
    ndesc, nicon = aqi_pm10(nxt)
    delta_str = f"{nxt - last_true_val.iloc[-1]:+.1f} µg/m³" if not last_true_val.empty else None
    kc3.metric("Prognoza (następna godz.)", f"{nxt:.1f} µg/m³", delta=delta_str)
    kc4.metric("Prognozowana jakość", f"{nicon} {ndesc}")
else:
    kc3.metric("Prognoza (następna godz.)", "–")
    kc4.metric("Prognozowana jakość", "–")

st.write("")

# --- Metryki (tylko historia)
st.subheader("Metryki (historia)")
hist_df = df.loc[hist_mask].copy()
if "pm10_hist" in hist_df.columns and hist_df["pm10_hist"].notna().any():
    h = hist_df.dropna(subset=["pm10_hist", "pm10_true"])
    if not h.empty:
        mae  = (h["pm10_true"] - h["pm10_hist"]).abs().mean()
        rmse = ((h["pm10_true"] - h["pm10_hist"])**2).mean()**0.5
        mape = ((h["pm10_true"] - h["pm10_hist"]).abs() / h["pm10_true"]).mean() * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("MAE", f"{mae:.2f} µg/m³")
        c2.metric("RMSE", f"{rmse:.2f} µg/m³")
        c3.metric("MAPE", f"{mape:.1f} %")
    else:
        st.info("Brak wspólnych punktów do obliczenia metryk.")
else:
    st.info("Brak kolumny 'pm10_hist' lub brak danych w historii.")

# --- Dystrybucja PM10
st.write("---")
st.subheader("Rozkład wartości PM10")
dist_data = df["pm10_true"].dropna()
if not dist_data.empty:
    dc1, dc2 = st.columns(2)
    with dc1:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=dist_data,
            nbinsx=40,
            marker_color="#d62728",
            opacity=0.75,
            name="PM10"
        ))
        # linie norm
        for val, label, color in [(45, "45 µg/m³", "#f39c12"), (75, "75 µg/m³", "#e74c3c"), (150, "150 µg/m³", "#8e44ad")]:
            fig_hist.add_vline(x=val, line_color=color, line_dash="dash",
                               annotation_text=label, annotation_position="top right")
        fig_hist.update_layout(
            title="Histogram PM10",
            xaxis_title="µg/m³", yaxis_title="Liczba godzin",
            showlegend=False, height=350
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with dc2:
        traces_box = [go.Box(y=dist_data, name="PM10 (rzeczywiste)",
                             marker_color="#d62728", boxmean="sd")]
        if "pm10_hist" in df.columns:
            traces_box.append(go.Box(y=df["pm10_hist"].dropna(),
                                     name="PM10 (prognoza – hist.)",
                                     marker_color="#1f77b4", boxmean="sd"))
        fig_box = go.Figure(data=traces_box)
        fig_box.update_layout(
            title="Box plot PM10",
            yaxis_title="µg/m³", height=350
        )
        st.plotly_chart(fig_box, use_container_width=True)

# --- Kolorowana tabela prognozy
st.write("---")
st.subheader("Tabela prognozy PM10")

def color_pm10(val):
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v < 20:   return "background-color:#d5f5e3; color:#1e8449"
    if v < 45:   return "background-color:#fef9e7; color:#b7950b"
    if v < 75:   return "background-color:#fdebd0; color:#ca6f1e"
    if v < 150:  return "background-color:#fadbd8; color:#cb4335"
    return "background-color:#e8daef; color:#7d3c98"

show_cols = ["timestamp"]
for c in ["pm10_true", "pm10_hist", "pm10_pred", "error"]:
    if c in df.columns:
        show_cols.append(c)

tbl = df[show_cols].copy()
tbl["timestamp"] = tbl["timestamp"].dt.strftime("%Y-%m-%d %H:%M")

num_cols = [c for c in show_cols if c != "timestamp"]
styled = (
    tbl.style
    .applymap(color_pm10, subset=num_cols)
    .format({c: "{:.1f}" for c in num_cols}, na_rep="–")
)
st.dataframe(styled, use_container_width=True, height=400)

# --- Informacje o pliku
st.write("---")
st.code(csv_path)
if os.path.isfile(csv_path):
    ts = datetime.fromtimestamp(os.path.getmtime(csv_path))
    st.caption(f"Ostatnia modyfikacja: {ts}")
