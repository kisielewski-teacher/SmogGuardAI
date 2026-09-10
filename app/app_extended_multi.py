
# -*- coding: utf-8 -*-
"""
SmogGuardAI — Dashboard PRO
- Historia PM10 (WAQI)
- Prognoza PM10 z outputs/pm10_all_latest.csv (24h horyzont w widoku)
- Twardy cutoff historia/przyszłość liczony z faktycznego ostatniego POMIARU
- Wykresy schodkowe (step-after)
- Eksport PNG/PDF
- Cache + auto-refresh
"""

from pathlib import Path
import os
import io
import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

try:
    import altair as alt
    ALT = True
except Exception:
    ALT = False

st.set_page_config(page_title="SmogGuardAI — Dashboard PRO", layout="wide")
st.title("SmogGuardAI — Dashboard PRO")

try:
    BASE = Path(__file__).resolve().parents[1]
except Exception:
    BASE = Path.cwd()

DATA = BASE / "data"
OUTPUT = BASE / "outputs"
HIST = DATA / "aqicn_slupsk_data.csv"
MERGED = DATA / "merged_hourly.csv"
FORECAST = OUTPUT / "pm10_all_latest.csv"  # KLUCZOWY PLIK dla wykresu prognozy

# --- pomocnicze ---
def detect_sep(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            h = f.readline()
            return ";" if (";" in h and "," not in h) else ","
    except Exception:
        return ","

@st.cache_data(ttl=60)
def load_csv(path: Path, dtcols=None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    sep = detect_sep(path)
    try:
        df = pd.read_csv(path, sep=sep)
    except Exception:
        df = pd.read_csv(path, sep=sep, engine="python", on_bad_lines="skip")
    if dtcols:
        for c in dtcols:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

ALIASES = {
    "timestamp": ["timestamp", "time", "date", "datetime", "DateTime"],
    "pm10": ["pm10", "PM10", "pm_10", "PM_10", "pm10_value"],
    "pm25": ["pm25", "PM25", "pm_25", "PM_25"],
    # prognoza
    "pm10_true": ["pm10_true"],
    "pm10_hist": ["pm10_hist"],
    "pm10_pred": ["pm10_pred"],
    # pogoda (obsługa sufiksów _x/_y z merge_hourly)
    "temp": ["temp", "temperatura", "temperatura_x", "temperatura_y"],
    "rh": ["rh", "wilgotnosc_wzgledna", "wilgotnosc", "humidity",
           "wilgotnosc_wzgledna_x", "wilgotnosc_wzgledna_y"],
    "pressure": ["pressure", "cisnienie", "ciśnienie", "cisnienie_x", "cisnienie_y"],
    "wind": ["wind", "wind_speed", "predkosc_wiatru", "wiatr",
             "predkosc_wiatru_x", "predkosc_wiatru_y"],
}

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    ren = {}
    for tgt, aliases in ALIASES.items():
        for a in aliases:
            if a in df.columns and tgt not in df.columns:
                ren[a] = tgt
                break
    df = df.rename(columns=ren)

    # Dodatkowa normalizacja — obsłużymy przypadki z sufiksami (_x/_y) lub kropkami (PM2.5)
    # jeśli brak canonicalnych kolumn (pm10/pm25), spróbuj odnaleźć podobne nazwy i przypisać
    if "pm10" not in df.columns:
        for col in df.columns:
            col_s = col.lower().replace("_", "").replace("-", "").replace(".", "")
            if col_s.startswith("pm10"):
                df["pm10"] = pd.to_numeric(df[col], errors="coerce")
                break
    if "pm25" not in df.columns:
        for col in df.columns:
            col_s = col.lower().replace("_", "").replace("-", "").replace(".", "")
            # obsłuż warianty: pm25, pm2.5, p m2 5 itp.
            if col_s.startswith("pm25") or col_s.startswith("pm25") or "pm25" in col_s:
                df["pm25"] = pd.to_numeric(df[col], errors="coerce")
                break

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df

def add_roll(df: pd.DataFrame, col: str, w: int) -> None:
    if w > 0 and col in df.columns:
        df[f"{col}_r{w}"] = df[col].rolling(w, min_periods=max(1, w // 4)).mean()

def fig_bytes(fig, fmt: str) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, dpi=150, bbox_inches="tight")
    buf.seek(0)
    return buf.read()

# --- wczytanie ---
hist = normalize(load_csv(HIST, ["timestamp"]))
merged = normalize(load_csv(MERGED, ["timestamp"]))
forecast = normalize(load_csv(FORECAST, ["timestamp"]))

# PM2.5 tymczasowo ukryte — tylko PM10
show_pm25 = False
fc_pollutant = "PM10"

# --- sidebar / filtry ---
with st.sidebar:
    st.header("Filtry")
    days = st.slider("Okres (dni)", 1, 120, 45)
    smooth = st.selectbox("Wygładzanie (rolling h)", [0, 6, 12, 24], index=2)
    meas_src = st.radio("Źródło PM10 (do porównania)", ["historia WAQI", "merged WAQI+IMGW"], index=0)
    horizon_h = st.number_input("Horyzont prognozy (godziny do przodu)", min_value=1, max_value=72, value=24)
    auto_refresh = st.checkbox("Auto-odśwież co 30 sek", False)
    refresh = st.button("Odśwież dane teraz")

cut = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days)

def filtr(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "timestamp" not in df.columns:
        return df
    return df[df["timestamp"] >= cut].copy()

if refresh:
    st.cache_data.clear()

hist_f = filtr(hist)
merged_f = filtr(merged)
forecast_f = filtr(forecast)

# rolling dla historii i merged (w tym pogoda)
for df_ in [hist_f, merged_f]:
    for c in ["pm10", "pm25", "temp", "rh", "pressure", "wind"]:
        add_roll(df_, c, smooth)

# --- zakładki ---
tab_hist, tab_compare, tab_future, tab_weather = st.tabs([
    "Historia PM",
    "Rzeczywiste vs prognoza",
    "Predykcja (tylko przyszłość)",
    "Pogoda (WAQI)"
])

# --- Tab 1: Historia PM ---
with tab_hist:
    st.subheader("Historia PM10 (WAQI)")

    if hist_f.empty:
        st.info("Brak danych historycznych")
    else:
        hist_plot = hist_f.copy().sort_values("timestamp").reset_index(drop=True)
        add_roll(hist_plot, "pm10", smooth)
        y_col = f"pm10_r{smooth}" if f"pm10_r{smooth}" in hist_plot.columns else "pm10"

        # Segmentacja po przerwach czasowych (>2h) — zapobiega łączeniu odległych punktów
        hist_plot = hist_plot[hist_plot[y_col].notna()].copy()
        gaps = hist_plot["timestamp"].diff() > pd.Timedelta(hours=2)
        hist_plot["segment"] = gaps.cumsum()

        if ALT:
            chart = alt.Chart(hist_plot).mark_line(
                color="#e45756", strokeWidth=2
            ).encode(
                x=alt.X("timestamp:T", title="timestamp"),
                y=alt.Y(f"{y_col}:Q", title="PM10 [µg/m³]"),
                detail="segment:N",
                tooltip=["timestamp:T", f"{y_col}:Q"],
            )
            st.altair_chart(chart.properties(height=260), use_container_width=True)
        else:
            st.line_chart(hist_plot.set_index("timestamp")[["pm10"]])

# --- wspólne: pomiar + forecast + last_true (liczony z POMIARU, a nie z fc) ---
def compute_last_meas_timestamp() -> pd.Timestamp | None:
    # zgodnie z przełącznikiem źródła
    src = hist_f if meas_src == "historia WAQI" else merged_f
    if src.empty or "timestamp" not in src.columns or "pm10" not in src.columns:
        return None
    s = src["timestamp"][src["pm10"].notna()]
    return s.max() if not s.empty else None

last_meas_ts = compute_last_meas_timestamp()

# --- Tab 2: Rzeczywiste vs prognoza ---
with tab_compare:
    st.subheader("Porównanie: pomiar PM10 vs prognoza PM10")

    if forecast_f.empty or "pm10_pred" not in forecast_f.columns:
        st.info("Brak danych prognozy w pm10_all_latest.csv")
    else:
        meas = hist_f if meas_src == "historia WAQI" else merged_f
        meas = meas[["timestamp", "pm10"]].dropna().sort_values("timestamp")
        fc = forecast_f.sort_values("timestamp")

        # jeśli brak last_meas_ts, ratunkowo użyj minimum z fc
        if last_meas_ts is None:
            last_meas_ts = fc["timestamp"].min()

        hmask = fc["timestamp"] <= last_meas_ts
        fmask = fc["timestamp"] > last_meas_ts

        with st.expander("Debug — zakresy czasu", expanded=False):
            st.write("last_meas_ts:", last_meas_ts)
            if not fc[hmask].empty:
                st.write("historia prognozy — od:", fc[hmask]["timestamp"].min(), "do:", fc[hmask]["timestamp"].max())
            if not fc[fmask].empty:
                st.write("przyszłość — od:", fc[fmask]["timestamp"].min(), "do:", fc[fmask]["timestamp"].max())

        if ALT:
            meas_ch = alt.Chart(meas).mark_line(color="#e45756", strokeWidth=2)\
                .encode(x="timestamp:T", y=alt.Y("pm10:Q", title="PM10 [µg/m³]"))
            hist_ch = alt.Chart(fc.loc[hmask]).mark_line(
                strokeWidth=1.5, color="#1f77b4", opacity=0.8
            ).encode(x="timestamp:T", y="pm10_pred:Q")
            fut_ch = alt.Chart(fc.loc[fmask]).mark_line(
                strokeWidth=2.5, strokeDash=[6, 3], color="#2ca02c"
            ).encode(x="timestamp:T", y="pm10_pred:Q")
            cut_rule = alt.Chart(pd.DataFrame({"timestamp": [last_meas_ts]}))\
                .mark_rule(strokeDash=[4, 4], color="gray").encode(x="timestamp:T")
            final = meas_ch + hist_ch + fut_ch + cut_rule
            st.altair_chart(final.resolve_scale(y="shared").properties(height=300), use_container_width=True)
        else:
            cols_plot = [c for c in ["pm10_pred"] if c in fc.columns]
            st.line_chart(fc.set_index("timestamp")[cols_plot])

# --- Tab 3: Predykcja (tylko przyszłość) — horyzont 24h ---
with tab_future:
    st.subheader(f"Prognoza PM10 — kolejne {horizon_h} godzin")

    if forecast_f.empty or "pm10_pred" not in forecast_f.columns:
        st.info("Brak danych prognozy w pm10_all_latest.csv")
    elif last_meas_ts is None:
        st.warning("Brak ostatniego pomiaru — nie mogę wyznaczyć przyszłości.")
    else:
        fc = forecast_f.sort_values("timestamp")
        pred_col = "pm10_pred"
        true_col = "pm10_true"

        # okno przyszłości: (last_meas_ts, last_meas_ts + h)
        df_future = fc[(fc["timestamp"] > last_meas_ts) &
                       (fc["timestamp"] <= last_meas_ts + pd.Timedelta(hours=horizon_h))].copy()

        with st.expander("Debug — okno przyszłości (24h)", expanded=False):
            if df_future.empty or pred_col not in df_future.columns:
                st.write("df_future: PUSTE")
            else:
                st.write("Pierwszy punkt:", df_future["timestamp"].min(), "Ostatni punkt:", df_future["timestamp"].max())

        if pred_col not in fc.columns:
            st.warning(f"Brak prognozy {fc_pollutant} w pm10_all_latest.csv — uruchom pipeline lub zwiększ horyzont.")
        elif df_future.empty:
            st.warning("Brak prognozy dla wybranego horyzontu — zwiększ horyzont albo odśwież pipeline (predykcja + merge).")
        else:
            if ALT:
                fut_only = alt.Chart(df_future).mark_line(
                    strokeWidth=2.5, color="#2ca02c"
                ).encode(
                    x=alt.X("timestamp:T", title="Czas"),
                    y=alt.Y(f"{pred_col}:Q", title="PM10 [µg/m³]"),
                    tooltip=["timestamp:T", f"{pred_col}:Q"],
                )
                st.altair_chart(fut_only.properties(height=300), use_container_width=True)
            else:
                st.line_chart(df_future.set_index("timestamp")[[pred_col]])

            # eksport PNG/PDF (matplotlib fallback)
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df_future["timestamp"], df_future[pred_col], color="#2ca02c", linestyle=(0, (4, 3)))
            ax.set_title(f"Prognoza {fc_pollutant} — kolejne {horizon_h}h")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("µg/m³")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            col1, col2 = st.columns(2)
            col1.download_button("Pobierz PNG (prognoza)", data=fig_bytes(fig, "png"),
                                 file_name="prognoza_24h.png", mime="image/png")
            col2.download_button("Pobierz PDF (prognoza)", data=fig_bytes(fig, "pdf"),
                                 file_name="prognoza_24h.pdf", mime="application/pdf")

# --- Tab 4: POGODA (WAQI / Open-Meteo) ---
with tab_weather:
    st.subheader("Pogoda — temperatura / wilgotność / ciśnienie / wiatr")

    # Użyj merged (Open-Meteo) jeśli WAQI ma za mało danych w oknie
    _waqi_weather_ok = (
        not hist_f.empty
        and "temp" in hist_f.columns
        and hist_f["temp"].notna().sum() >= 24
    )
    if _waqi_weather_ok:
        dfw = hist_f
        _weather_src = "WAQI"
    else:
        dfw = merged_f
        _weather_src = "Open-Meteo (merged)"

    if dfw.empty:
        st.warning("Brak danych pogodowych. Uruchom `run_hourly.bat` lub `openmeteo_backfill.py`.")
    else:
        n_pts = len(dfw[dfw["temp"].notna()]) if "temp" in dfw.columns else 0
        if n_pts < 24:
            freshness = dfw["timestamp"].max() if "timestamp" in dfw.columns else None
            st.warning(
                f"Mało danych pogodowych w wybranym okresie ({n_pts} wierszy, źródło: {_weather_src}). "
                f"Ostatni wpis: {freshness}. "
                "Zwiększ zakres dni (suwak po lewej)."
            )
        else:
            st.caption(f"Źródło pogody: {_weather_src} — {n_pts} godzin w oknie")

        def pick_col(df, base_col, smooth_val):
            """Return rolled col if it has any non-NaN values, otherwise raw col."""
            rolled = f"{base_col}_r{smooth_val}"
            if rolled in df.columns and df[rolled].notna().any():
                return rolled
            return base_col

        has_temp = "temp" in dfw.columns and dfw["temp"].notna().any()
        has_rh = "rh" in dfw.columns and dfw["rh"].notna().any()
        has_pr = "pressure" in dfw.columns and dfw["pressure"].notna().any()
        has_wi = "wind" in dfw.columns and dfw["wind"].notna().any()

        if ALT:
            charts = []
            base = alt.Chart(dfw).encode(x="timestamp:T")
            if has_temp:
                y = pick_col(dfw, "temp", smooth)
                charts.append(base.mark_line(color="#ff7f0e").encode(y=alt.Y(f"{y}:Q", title="Temperatura [°C]"))
                              .properties(height=220, title="Temperatura"))
            if has_rh:
                y = pick_col(dfw, "rh", smooth)
                charts.append(base.mark_line(color="#1f77b4").encode(y=alt.Y(f"{y}:Q", title="Wilgotność RH [%]"))
                              .properties(height=220, title="Wilgotność"))
            if has_pr:
                y = pick_col(dfw, "pressure", smooth)
                charts.append(base.mark_line(color="#9467bd").encode(y=alt.Y(f"{y}:Q", title="Ciśnienie [hPa]"))
                              .properties(height=220, title="Ciśnienie"))
            if has_wi:
                y = pick_col(dfw, "wind", smooth)
                charts.append(base.mark_line(color="#2ca02c", strokeDash=[4, 4]).encode(y=alt.Y(f"{y}:Q", title="Wiatr [m/s]"))
                              .properties(height=220, title="Wiatr"))
            if not charts:
                st.info("Brak kolumn pogodowych do pokazania.")
            else:
                st.altair_chart(alt.vconcat(*charts).resolve_scale(x="shared"), use_container_width=True)
        else:
            vars_list = [
                ("temp", "Temperatura [°C]", "#ff7f0e"),
                ("rh", "Wilgotność RH [%]", "#1f77b4"),
                ("pressure", "Ciśnienie [hPa]", "#9467bd"),
                ("wind", "Wiatr [m/s]", "#2ca02c"),
            ]
            available = [(c, t, col) for (c, t, col) in vars_list if c in dfw.columns and dfw[c].notna().any()]
            if not available:
                st.info("Brak kolumn pogodowych do pokazania.")
            else:
                rows, cols = 2, 2
                fig, axes = plt.subplots(rows, cols, figsize=(12, 6), sharex=True)
                axes = axes.flatten()
                for i, (c, title, color) in enumerate(available):
                    y = pick_col(dfw, c, smooth)
                    axes[i].plot(dfw["timestamp"], dfw[y], color=color, marker="o", markersize=4)
                    axes[i].set_title(title)
                    axes[i].grid(True, alpha=0.3)
                for j in range(len(available), rows * cols):
                    fig.delaxes(axes[j])
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)

# --- Export historii PM (tak jak wcześniej) ---
st.markdown("---")
st.subheader("Eksport wykresów PM (historia)")
if not hist_f.empty:
    fig_pm, ax_pm = plt.subplots(figsize=(10, 4))
    y10 = f"pm10_r{smooth}" if f"pm10_r{smooth}" in hist_f.columns else "pm10"
    ax_pm.plot(hist_f["timestamp"], hist_f[y10], color="#e45756", label="PM10")
    if show_pm25 and "pm25" in hist_f.columns:
        y25 = f"pm25_r{smooth}" if f"pm25_r{smooth}" in hist_f.columns else "pm25"
        ax_pm.plot(hist_f["timestamp"], hist_f[y25], color="#4c78a8", linestyle=(0, (3, 3)), label="PM2.5")
    ax_pm.set_title("Historia PM")
    ax_pm.grid(True, alpha=0.3)
    ax_pm.legend()
    fig_pm.tight_layout()
    st.download_button("Pobierz historię PM (PNG)", data=fig_bytes(fig_pm, "png"),
                       file_name="historia_pm.png")
    st.download_button("Pobierz historię PM (PDF)", data=fig_bytes(fig_pm, "pdf"),
                       file_name="historia_pm.pdf")
