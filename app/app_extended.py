
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="SmogGuardAI (rozszerzony)", layout="wide")

st.title("AI Prognoza Jakości Powietrza – Słupsk (rozszerzona wersja)")

HIST_PATH = "data/aqicn_slupsk_data.csv"
MERGED_PATH = "data/merged_hourly.csv"
FORECAST_PATH = "data/forecast_pm10.csv"  # obecnie prognoza tylko dla PM10

DEFAULT_THRESHOLD_PM10 = 50  # µg/m3

@st.cache_data(show_spinner=False)
def load_csv(path: str, dt_cols=None):
    try:
        df = pd.read_csv(path)
        if dt_cols:
            for c in dt_cols:
                if c in df.columns:
                    df[c] = pd.to_datetime(df[c], errors='coerce')
        return df
    except FileNotFoundError:
        return pd.DataFrame()

hist = load_csv(HIST_PATH, dt_cols=["timestamp"])      # WAQI – historia
merged = load_csv(MERGED_PATH, dt_cols=["timestamp"])  # Scalona historia (WAQI+IMGW)
fc = load_csv(FORECAST_PATH, dt_cols=["timestamp"])    # Prognoza PM10

# ---------------- Sidebar: filtry i ustawienia ----------------
st.sidebar.header("Ustawienia i filtry")
threshold = st.sidebar.number_input("Próg ostrzegawczy PM10 (µg/m³)", min_value=0, max_value=500, value=DEFAULT_THRESHOLD_PM10, step=5)

# Zakres dat (jeśli mamy dane scalone)
if not merged.empty:
    min_ts = merged["timestamp"].min()
    max_ts = merged["timestamp"].max()
else:
    min_ts = pd.to_datetime("today") - pd.Timedelta(days=1)
    max_ts = pd.to_datetime("today")

start_date = st.sidebar.date_input("Data od", value=min_ts.date())
end_date   = st.sidebar.date_input("Data do", value=max_ts.date())

# Wybór zanieczyszczeń do historii (multiwybór)
pollutants_available = [c for c in ["PM2.5", "PM10", "NO2", "O3"] if c in hist.columns]
selected_pollutants = st.sidebar.multiselect(
    "Zanieczyszczenia (historia)",
    options=pollutants_available,
    default=pollutants_available or []
)

# >>> Wybór zanieczyszczenia do sekcji porównawczej <<<
target_pollutants = ["PM10", "PM2.5", "NO2", "O3"]
target_options = [p for p in target_pollutants if p in (merged.columns if not merged.empty else [])]
if "PM10" not in target_options and (not merged.empty and "PM10" in merged.columns):
    target_options.append("PM10")

selected_target = st.sidebar.selectbox(
    "Zanieczyszczenie (do porównania rzeczywiste vs prognoza)",
    options=target_options if target_options else ["PM10"],
    index=(target_options.index("PM10") if "PM10" in target_options else 0)
)

# Horyzont prognozy
horizon_hours = st.sidebar.selectbox("Horyzont prognozy", options=[6, 24, 48], index=0)

# ---------------- Przygotowanie danych wg zakresu dat ----------------
def filter_by_date(df: pd.DataFrame, col="timestamp"):
    if df.empty or col not in df.columns:
        return df
    mask = (df[col].dt.date >= start_date) & (df[col].dt.date <= end_date)
    return df.loc[mask].copy()

hist_f   = filter_by_date(hist, col="timestamp")
merged_f = filter_by_date(merged, col="timestamp")
fc_f     = fc.copy()

# Dopasowanie horyzontu prognozy
if not fc_f.empty:
    latest_ts = merged_f["timestamp"].max() if not merged_f.empty else hist_f["timestamp"].max() if not hist_f.empty else None
    if latest_ts is not None:
        fc_f = fc_f[fc_f["timestamp"] <= latest_ts + pd.Timedelta(hours=horizon_hours)]

# ---------------- KPI ----------------
col1, col2, col3, col4 = st.columns(4)

def last_value(df, col):
    if df.empty or col not in df.columns:
        return None
    s = df[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None

last_pm10 = last_value(hist, "PM10")
last_pm25 = last_value(hist, "PM2.5")
last_no2  = last_value(hist, "NO2")
last_o3   = last_value(hist, "O3")

with col1:
    st.metric("PM10 (ostatnia)", f"{last_pm10:.1f}" if last_pm10 is not None else "brak")
with col2:
    st.metric("PM2.5 (ostatnia)", f"{last_pm25:.1f}" if last_pm25 is not None else "brak")
with col3:
    st.metric("NO₂ (ostatnia)", f"{last_no2:.1f}" if last_no2 is not None else "brak")
with col4:
    st.metric("O₃ (ostatnia)", f"{last_o3:.1f}" if last_o3 is not None else "brak")

# ---------------- Historia (WAQI) ----------------
st.subheader("Historia zanieczyszczeń (WAQI)")
if selected_pollutants and not hist_f.empty:
    st.line_chart(hist_f.set_index("timestamp")[selected_pollutants])
else:
    st.info("Brak danych lub brak wybranych kolumn do wyświetlenia.")

st.markdown("---")

# ---------------- Prognoza PM10 ----------------
st.subheader(f"Prognoza PM10 ({horizon_hours}h) z oznaczeniem progu {threshold} µg/m³")
if not fc_f.empty:
    plot_df = fc_f.copy().set_index("timestamp")
    plot_df["status"] = np.where(
        plot_df["pm10_pred"] >= threshold, "powyżej progu",
        np.where(plot_df["pm10_pred"] >= 0.6*threshold, "blisko progu", "poniżej progu")
    )
    st.line_chart(plot_df[["pm10_pred"]])
    st.write("Prognoza (tabela):")
    st.dataframe(plot_df.reset_index()[["timestamp", "pm10_pred", "status"]])
else:
    st.info("Brak pliku prognozy – uruchom train_pm10.py i predict.py.")

st.markdown("---")

# ---------------- Pogoda + korelacje ----------------
st.subheader("Pogoda (IMGW) i korelacje z PM10")
weather_cols = [c for c in ["temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"] if c in merged_f.columns]
if not merged_f.empty and weather_cols:
    c1, c2 = st.columns([2,1])
    with c1:
        st.line_chart(merged_f.set_index("timestamp")[weather_cols])
    with c2:
        show_corr = st.checkbox("Pokaż macierz korelacji (PM10 + pogoda)", value=True)
        if show_corr:
            corr_cols = ["PM10"] + weather_cols
            df_corr = merged_f[corr_cols].corr(method="pearson")
            st.dataframe(df_corr)
else:
    st.info("Brak pogodowych kolumn IMGW lub danych w wybranym zakresie.")

st.markdown("---")

# ---------------- Porównanie: rzeczywiste vs prognoza + błędy ----------------
st.subheader("Porównanie: rzeczywiste vs prognoza + błędy")

# Uwaga: prognoza istnieje tylko dla PM10
if selected_target != "PM10":
    st.info(f"Prognoza jest dostępna tylko dla PM10. Wybrałeś: {selected_target}. Zmień wybór na PM10, aby zobaczyć porównanie.")
else:
    join = pd.DataFrame()
    if not fc_f.empty and not merged_f.empty and "PM10" in merged_f.columns:
        join = pd.merge(fc_f, merged_f[["timestamp", "PM10"]], on="timestamp", how="inner")
        join = join[(join["timestamp"].dt.date >= start_date) & (join["timestamp"].dt.date <= end_date)]
        if not join.empty:
            join["error"] = join["pm10_pred"] - join["PM10"]
            join["abs_error"] = join["error"].abs()

    if join.empty:
        st.info("Na razie brak nakładających się punktów czasu do porównania w wybranym zakresie.")
    else:
        # Overlay
        try:
            import altair as alt
            overlay = (
                alt.Chart(join)
                .transform_fold(["PM10", "pm10_pred"], as_=["Seria", "Wartość"])
                .mark_line(point=True)
                .encode(
                    x="timestamp:T",
                    y=alt.Y("Wartość:Q", title="µg/m³"),
                    color=alt.Color("Seria:N", scale=alt.Scale(scheme="set1")),
                    tooltip=[alt.Tooltip("timestamp:T", title="Czas"),
                             alt.Tooltip("Wartość:Q", title="µg/m³", format=".1f"),
                             alt.Tooltip("Seria:N")]
                )
                .properties(height=300)
            )
            st.altair_chart(overlay, use_container_width=True)
        except Exception:
            st.line_chart(join.set_index("timestamp")[["PM10", "pm10_pred"]])

        # Residua (z domkniętymi nawiasami!)
        try:
            import altair as alt
            resid = (
                alt.Chart(join)
                .mark_bar()
                .encode(
                    x="timestamp:T",
                    y=alt.Y("error:Q", title="Błąd (pred - actual)"),
                    color=alt.condition("datum.error >= 0", alt.value("#d62728"), alt.value("#2ca02c")),
                    tooltip=[alt.Tooltip("timestamp:T", title="Czas"),
                             alt.Tooltip("error:Q", title="Błąd", format=".1f"),
                             alt.Tooltip("PM10:Q", title="PM10", format=".1f"),
                             alt.Tooltip("pm10_pred:Q", title="Pred", format=".1f")]
                )
                .properties(height=200)
            )
            st.altair_chart(resid, use_container_width=True)
        except Exception:
            st.line_chart(join.set_index("timestamp")[["error"]])

        # Scatter + metryki
        c1, c2 = st.columns([2,1])
        with c1:
            try:
                import altair as alt
                scatter = (
                    alt.Chart(join)
                    .mark_circle(size=80)
                    .encode(
                        x=alt.X("PM10:Q", title="Rzeczywiste PM10"),
                        y=alt.Y("pm10_pred:Q", title="Prognoza PM10"),
                        tooltip=[alt.Tooltip("timestamp:T", title="Czas"),
                                 alt.Tooltip("PM10:Q", title="Rzeczywiste", format=".1f"),
                                 alt.Tooltip("pm10_pred:Q", title="Prognoza", format=".1f")]
                    )
                    .properties(height=300)
                )
                mm_min = float(join[["PM10","pm10_pred"]].min().min())
                mm_max = float(join[["PM10","pm10_pred"]].max().max())
                ref = pd.DataFrame({"x":[mm_min, mm_max], "y":[mm_min, mm_max]})
                ref_chart = alt.Chart(ref).mark_line(color="gray", strokeDash=[4,4]).encode(x="x:Q", y="y:Q")
                st.altair_chart(scatter + ref_chart, use_container_width=True)
            except Exception:
                st.write("Wykres punktowy pominięty (Altair niedostępny).")

        with c2:
            mae   = float(join["abs_error"].mean())
            rmse  = float(np.sqrt(((join["error"])**2).mean()))
            nonzero = join["PM10"].replace(0, np.nan)
            mape  = float((join["abs_error"] / nonzero).dropna().mean()*100) if nonzero.notna().any() else float("nan")
            st.metric("MAE",  f"{mae:.2f} µg/m³")
            st.metric("RMSE", f"{rmse:.2f} µg/m³")
            st.metric("MAPE", f"{mape:.1f} %" if not np.isnan(mape) else "—")

        # MAE wg godziny
        join["hour"] = join["timestamp"].dt.hour
        mae_by_hour  = join.groupby("hour")["abs_error"].mean().reset_index()
        try:
            import altair as alt
            bar = (
                alt.Chart(mae_by_hour)
                .mark_bar(color="#1f77b4")
                .encode(x=alt.X("hour:O", title="Godzina"), y=alt.Y("abs_error:Q", title="MAE (µg/m³)"))
                .properties(height=240)
            )
            st.altair_chart(bar, use_container_width=True)
        except Exception:
            st.bar_chart(mae_by_hour.set_index("hour"))

st.markdown("---")

# ---------------- Statystyki 24h / 7d ----------------
st.subheader("Statystyki")
if not merged.empty and "PM10" in merged.columns:
    latest   = merged["timestamp"].max()
    last_24h = merged[(merged["timestamp"] >= latest - pd.Timedelta(hours=24)) & (merged["timestamp"] <= latest)]
    last_7d  = merged[(merged["timestamp"] >= latest - pd.Timedelta(days=7))  & (merged["timestamp"] <= latest)]

    c1, c2 = st.columns(2)
    with c1:
        st.write("**Ostatnie 24h (PM10)**")
        if not last_24h.empty:
            st.write({
                "średnia": round(last_24h["PM10"].mean(), 2),
                "mediana": round(last_24h["PM10"].median(), 2),
                "min":     round(last_24h["PM10"].min(), 2),
                "max":     round(last_24h["PM10"].max(), 2),
                "liczba pomiarów": int(last_24h["PM10"].notna().sum()),
            })
        else:
            st.info("Brak danych z ostatnich 24h.")
    with c2:
        st.write("**Ostatnie 7 dni (PM10)**")
        if not last_7d.empty:
            st.write({
                "średnia": round(last_7d["PM10"].mean(), 2),
                "mediana": round(last_7d["PM10"].median(), 2),
                "min":     round(last_7d["PM10"].min(), 2),
                "max":     round(last_7d["PM10"].max(), 2),
                "liczba pomiarów": int(last_7d["PM10"].notna().sum()),
            })
        else:
            st.info("Brak danych z ostatnich 7 dni.")
else:
    st.info("Brak danych PM10 w pliku merged_hourly.csv.")

st.markdown("---")

st.caption("Wersja rozszerzona: filtry dat, wybór zanieczyszczenia, kolory progów, horyzont prognozy, korelacje, statystyki, porównanie rzeczywiste vs prognoza.")
