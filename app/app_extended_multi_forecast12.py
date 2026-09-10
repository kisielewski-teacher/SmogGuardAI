
# -*- coding: utf-8 -*-
"""
app_extended_multi_forecast12.py
Rozszerzona wersja dashboardu PM10 z:
- horyzontem prognozy (1–72h),
- osobną kartą 'Predykcja (tylko przyszłość)',
- eksportem PNG i PDF.

Źródło danych: outputs/pm10_all_latest.csv
"""

import os
import io
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import matplotlib.pyplot as plt

# ---------------------------
# USTAWIENIA STRONY
# ---------------------------
st.set_page_config(
    page_title="PM10 – Dashboard PRO",
    layout="wide"
)

st.title("PM10 – Dashboard PRO z prognozą horyzontową")

# ---------------------------
# FUNKCJE POMOCNICZE
# ---------------------------

def load_data(path: str) -> pd.DataFrame:
    if not path or not os.path.isfile(path):
        return pd.DataFrame()
    df = pd.read_csv(path)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    for c in ["pm10_true", "pm10_hist", "pm10_pred", "error"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

def fig_to_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    buf.seek(0)
    return buf.read()

def fig_to_pdf(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", dpi=160, bbox_inches="tight")
    buf.seek(0)
    return buf.read()

# ---------------------------
# PANEL BOCZNY
# ---------------------------

st.sidebar.header("Źródło danych")

default_path = "outputs/pm10_all_latest.csv"
csv_path = st.sidebar.text_input("Plik CSV", value=default_path)

auto_refresh = st.sidebar.checkbox("Auto-odśwież co 30 sek", False)
refresh = st.sidebar.button("Odśwież teraz")

# Horyzont prognozy — NOWOŚĆ
horizon_h = st.sidebar.number_input(
    "Horyzont prognozy (godziny do przodu)",
    min_value=1,
    max_value=72,
    value=12
)

# ---------------------------
# CACHE ŁADOWANIA
# ---------------------------
@st.cache_data(ttl=30)
def cached_load(path):
    return load_data(path)

if refresh:
    st.cache_data.clear()

df = cached_load(csv_path)

if df.empty:
    st.error("Brak danych w pliku.")
    st.stop()

if "timestamp" not in df.columns or "pm10_true" not in df.columns:
    st.error("Brak kolumn 'timestamp' i/lub 'pm10_true' w pliku.")
    st.stop()

# ---------------------------
# WYZNACZENIE HIST/FUTURE
# ---------------------------

last_true = df["timestamp"][df["pm10_true"].notna()].max()
hist_mask = df["timestamp"] <= last_true
fut_mask = df["timestamp"] > last_true

df_future = df[df["timestamp"] > last_true].copy()
df_future = df_future[
    df_future["timestamp"] <= last_true + pd.Timedelta(hours=horizon_h)
].copy()

# ---------------------------
# ZAKŁADKI
# ---------------------------

tab1, tab2 = st.tabs([
    "Rzeczywiste vs prognoza",
    "Predykcja (tylko przyszłość)"
])

# ---------------------------
# TAB 1 — PEŁNY WYKRES
# ---------------------------

with tab1:
    st.subheader("PM10 – rzeczywiste vs prognoza")

    fig = go.Figure()

    # RZECZYWISTE (czerwone)
    fig.add_trace(go.Scatter(
        x=df.loc[hist_mask, "timestamp"],
        y=df.loc[hist_mask, "pm10_true"],
        name="PM10 (rzeczywiste)",
        mode="lines+markers",
        line=dict(color="#d62728"),
        connectgaps=False,
        line_shape='hv'
    ))

    # HISTORIA PROGNOZY (niebieskie)
    if "pm10_hist" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.loc[hist_mask, "timestamp"],
            y=df.loc[hist_mask, "pm10_hist"],
            name="PM10 (prognoza – historia)",
            mode="lines+markers",
            line=dict(color="#1f77b4"),
            connectgaps=False,
            line_shape='hv'
        ))

    # PRZYSZŁOŚĆ (zielone)
    if "pm10_pred" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.loc[fut_mask, "timestamp"],
            y=df.loc[fut_mask, "pm10_pred"],
            name="PM10 (prognoza – przyszłość)",
            mode="lines+markers",
            line=dict(color="#2ca02c", dash="dot"),
            connectgaps=False,
            line_shape='hv'
        ))

    fig.add_vline(
        x=last_true,
        line_color="gray",
        line_width=1,
        line_dash="dot"
    )

    fig.update_layout(
        xaxis_title="timestamp",
        yaxis_title="µg/m³",
        hovermode="x unified",
        legend=dict(orientation="h")
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# TAB 2 — WYKRES TYLKO PRZYSZŁOŚCI
# ---------------------------

with tab2:
    st.subheader(f"Prognoza PM10 — kolejne {horizon_h} godzin")

    if df_future.empty:
        st.warning("Brak prognozy na wybrany horyzont.")
        st.stop()

    fig2 = go.Figure()

    fig2.add_trace(go.Scatter(
        x=df_future["timestamp"],
        y=df_future["pm10_pred"],
        name=f"Prognoza +{horizon_h}h",
        mode="lines+markers",
        line=dict(color="#2ca02c", dash="dot"),
        connectgaps=False,
        line_shape="hv"
    ))

    fig2.update_layout(
        xaxis_title="timestamp",
        yaxis_title="µg/m³",
        hovermode="x unified",
        legend=dict(orientation="h")
    )

    st.plotly_chart(fig2, use_container_width=True)

    # -----------------------------------
    # Eksport: PNG + PDF — NOWOŚĆ
    # -----------------------------------
    st.markdown("### Eksport wykresu predykcji")

    # Fallback matplotlib do eksportu
    fig_mpl, ax = plt.subplots(figsize=(10, 4))
    ax.plot(
        df_future["timestamp"],
        df_future["pm10_pred"],
        color="#2ca02c"
    )
    ax.set_title(f"Prognoza PM10 — kolejne {horizon_h}h")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("µg/m³")
    ax.grid(True)

    png_bytes = fig_to_png(fig_mpl)
    pdf_bytes = fig_to_pdf(fig_mpl)

    col1, col2 = st.columns(2)

    col1.download_button(
        "Pobierz PNG",
        data=png_bytes,
        file_name="forecast_future.png",
        mime="image/png"
    )

    col2.download_button(
        "Pobierz PDF",
        data=pdf_bytes,
        file_name="forecast_future.pdf",
        mime="application/pdf"
    )
