
import streamlit as st
import pandas as pd

st.set_page_config(page_title="SmogGuardAI", layout="wide")

st.title("AI Prognoza Jakości SmogGuardAI – Słupsk")

hist_path = "data/aqicn_slupsk_data.csv"
forecast_path = "data/forecast_pm10.csv"

try:
    hist = pd.read_csv(hist_path, parse_dates=["timestamp"])
    st.subheader("Historia (WAQI)")
    cols = [c for c in ["PM2.5","PM10","NO2","O3"] if c in hist.columns]
    if cols:
        st.line_chart(hist.set_index("timestamp")[cols])
    else:
        st.info("Brak kolumn PM2.5/PM10/NO2/O3 w historii.")
except FileNotFoundError:
    st.warning("Brak danych historycznych – uruchom waqi_fetch.py")

st.markdown("---")
st.subheader("Prognoza PM10 (6h)")
try:
    fc = pd.read_csv(forecast_path, parse_dates=["timestamp"]) 
    st.line_chart(fc.set_index("timestamp")["pm10_pred"]) 
except FileNotFoundError:
    st.info("Brak pliku prognozy – uruchom train_pm10.py i predict.py")
