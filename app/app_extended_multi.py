
# -*- coding: utf-8 -*-
"""
SmogGuardAI — Dashboard PRO
- Historia PM10 (GIOŚ)
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

st.set_page_config(page_title="SmogGuardAI — Prognoza PM10 Słupsk", layout="wide", page_icon="🌫️")

try:
    BASE = Path(__file__).resolve().parents[1]
except Exception:
    BASE = Path.cwd()

DATA = BASE / "data"
OUTPUT = BASE / "outputs"
HIST = DATA / "gios_slupsk.csv"
MERGED = DATA / "merged_hourly.csv"
FORECAST = OUTPUT / "pm10_all_latest.csv"  # KLUCZOWY PLIK dla wykresu prognozy
FORECAST_PM25 = OUTPUT / "pm25_all_latest.csv"
HORIZON_ACC = OUTPUT / "pm10_horizon_accuracy.csv"
PM25_MODEL = BASE / "models" / "pm25_pipeline.pkl"
PM25_BOOTSTRAP_META = BASE / "models" / "pm25_bootstrap_meta.txt"
PM10_FEATURE_IMPORTANCE = BASE / "models" / "pm10_feature_importances.csv"
PM25_FEATURE_IMPORTANCE = BASE / "models" / "pm25_feature_importances.csv"

# Nazwy cech modelu przetłumaczone na język zrozumiały dla człowieka (nie inżyniera ML)
FEATURE_LABELS_PL = {
    "hour": "Godzina",
    "dow": "Dzień tygodnia",
    "month": "Miesiąc",
    "is_weekend": "Weekend",
    "hour_sin": "Pora dnia (cykliczna)",
    "hour_cos": "Pora dnia (cykliczna)",
    "dow_sin": "Dzień tygodnia (cykliczny)",
    "dow_cos": "Dzień tygodnia (cykliczny)",
    "month_sin": "Pora roku (cykliczna)",
    "month_cos": "Pora roku (cykliczna)",
}

def humanize_feature(name: str) -> str:
    if name in FEATURE_LABELS_PL:
        return FEATURE_LABELS_PL[name]
    n = name.lower()
    m = None
    import re as _re
    lag_m = _re.match(r"(pm10|pm2\.?5)_lag(\d+)", n)
    if lag_m:
        return f"Stężenie {lag_m.group(1).upper().replace('PM2.5','PM2.5')} sprzed {lag_m.group(2)}h"
    roll_m = _re.match(r"(pm10|pm2\.?5)_rollmean(\d+)", n)
    if roll_m:
        return f"Średnia {roll_m.group(1).upper()} z ostatnich {roll_m.group(2)}h"
    rollstd_m = _re.match(r"(pm10|pm2\.?5)_rollstd(\d+)", n)
    if rollstd_m:
        return f"Zmienność {rollstd_m.group(1).upper()} z ostatnich {rollstd_m.group(2)}h"
    if "temperatura" in n or n.startswith("temp"):
        return "Temperatura"
    if "wilgotnosc" in n or n.startswith("rh"):
        return "Wilgotność powietrza"
    if "cisnienie" in n or "pressure" in n:
        return "Ciśnienie atmosferyczne"
    if "predkosc_wiatru" in n or "wind" in n:
        base = "Prędkość wiatru (kwadrat)" if n.endswith("_sq") else "Prędkość wiatru"
        return base
    if n == "wg":
        return "Porywy wiatru"
    if "opad" in n:
        return "Opady"
    return name
MIN_ROWS_PM25 = 72  # ta sama reguła co w train_pm10_rf.py

# --- Skala jakości powietrza (progi GIOŚ, µg/m³) — osobne dla PM10 i PM2.5 ---
PM10_BANDS = [
    (20, "Bardzo dobry", "#2ECC71"),
    (50, "Dobry", "#8BC34A"),
    (80, "Umiarkowany", "#FFC107"),
    (110, "Dostateczny", "#FF9800"),
    (150, "Zły", "#E53935"),
    (float("inf"), "Bardzo zły", "#8E24AA"),
]
PM25_BANDS = [
    (13, "Bardzo dobry", "#2ECC71"),
    (35, "Dobry", "#8BC34A"),
    (55, "Umiarkowany", "#FFC107"),
    (75, "Dostateczny", "#FF9800"),
    (110, "Zły", "#E53935"),
    (float("inf"), "Bardzo zły", "#8E24AA"),
]

def air_quality_category(value, bands=PM10_BANDS) -> tuple[str, str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "brak danych", "#9E9E9E"
    for limit, label, color in bands:
        if value <= limit:
            return label, color
    return "Bardzo zły", "#8E24AA"

def pm10_category(value) -> tuple[str, str]:
    return air_quality_category(value, PM10_BANDS)

def pm25_category(value) -> tuple[str, str]:
    return air_quality_category(value, PM25_BANDS)

# --- Rekomendacje zdrowotne wg kategorii jakości powietrza (GIOŚ + wytyczne WHO) ---
# Klucz = etykieta kategorii (wspólna dla PM10 i PM2.5, patrz PM10_BANDS/PM25_BANDS).
HEALTH_ADVICE = {
    "Bardzo dobry": {
        "icon": "🟢",
        "general": "Idealne warunki do aktywności na zewnątrz — bez ograniczeń.",
        "sensitive": "Także dzieci, seniorzy i osoby z astmą czy chorobami serca mogą normalnie przebywać na zewnątrz.",
    },
    "Dobry": {
        "icon": "🟢",
        "general": "Możesz normalnie spędzać czas na zewnątrz, w tym uprawiać sport.",
        "sensitive": "Osoby szczególnie wrażliwe mogą odczuć niewielki dyskomfort przy bardzo długim, intensywnym wysiłku.",
    },
    "Umiarkowany": {
        "icon": "🟡",
        "general": "Możesz wychodzić na zewnątrz, ale rozważ skrócenie długiego, intensywnego wysiłku (np. biegania).",
        "sensitive": "Dzieci, seniorzy, osoby z astmą lub chorobami serca powinny ograniczyć długotrwały wysiłek na zewnątrz.",
    },
    "Dostateczny": {
        "icon": "🟠",
        "general": "Ogranicz długotrwałe przebywanie na zewnątrz, zwłaszcza z wysiłkiem fizycznym.",
        "sensitive": "Dzieci, seniorzy, kobiety w ciąży i osoby z chorobami układu oddechowego/krążenia — unikajcie aktywności na zewnątrz.",
    },
    "Zły": {
        "icon": "🔴",
        "general": "Unikaj aktywności fizycznej na zewnątrz. Rozważ ograniczenie czasu na dworze do niezbędnego minimum.",
        "sensitive": "Grupy wrażliwe powinny pozostać w pomieszczeniach. Rozważ maskę FFP2 przy wyjściu na zewnątrz.",
    },
    "Bardzo zły": {
        "icon": "🟣",
        "general": "Pozostań w pomieszczeniach. Nie wietrz mieszkania w godzinach szczytu zanieczyszczenia.",
        "sensitive": "Osoby z chorobami przewlekłymi (astma, POChP, choroby serca) powinny mieć pod ręką leki i unikać wychodzenia na zewnątrz.",
    },
    "brak danych": {
        "icon": "⚪",
        "general": "Brak danych do wydania rekomendacji.",
        "sensitive": "",
    },
}

_DNI_PL = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

def fmt_dt_pl(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{_DNI_PL[ts.weekday()]}, {ts:%d.%m %H:%M}"

def render_health_advice(label: str, container=st):
    info = HEALTH_ADVICE.get(label, HEALTH_ADVICE["brak danych"])
    container.markdown(
        f"""
        <div style="border-radius:10px;padding:14px 18px;background:#f0f2f6;border:1px solid #d8dce3;">
            <div style="font-size:0.95rem;font-weight:700;margin-bottom:4px;">{info['icon']} Rekomendacja zdrowotna — jakość: {label}</div>
            <div style="font-size:0.9rem;margin-bottom:4px;">{info['general']}</div>
            <div style="font-size:0.85rem;color:#555;">👶🧓🫁 Grupy wrażliwe: {info['sensitive']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def kpi_tile(col, label: str, value_str: str, sub: str = "", color: str = "#31333F"):
    col.markdown(
        f"""
        <div style="border-radius:10px;padding:14px 16px;background:{color}18;
                    border:1px solid {color}55;">
            <div style="font-size:0.82rem;color:#666;font-weight:600;text-transform:uppercase;
                        letter-spacing:.03em;">{label}</div>
            <div style="font-size:1.9rem;font-weight:700;color:{color};line-height:1.15;">{value_str}</div>
            <div style="font-size:0.85rem;color:#666;">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.title("🌫️ SmogGuardAI — prognoza zanieczyszczenia powietrza PM10 dla Słupska")
st.caption(
    "Model AI (Random Forest) przewiduje stężenie pyłu PM10 na podstawie rzeczywistych pomiarów "
    "**GIOŚ** (Główny Inspektorat Ochrony Środowiska) i **IMGW**, uzupełnionych danymi pogodowymi "
    "**IMGW / Open-Meteo**. Linia ciągła = pomiar rzeczywisty, linia przerywana = prognoza modelu."
)

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

NORMS = {
    "PM10": {"who_24h": 45, "pl_24h": 50, "who_annual": 15, "pl_annual": 40},
    "PM2.5": {"who_24h": 15, "pl_24h": None, "who_annual": 5, "pl_annual": 20},
}

@st.cache_data(ttl=300)
def compute_daily_exceedance(df: pd.DataFrame, value_col: str, who_24h: float, pl_24h: float):
    """Dzienne średnie + ile dni przekroczyło normę WHO / polską (24h)."""
    if df.empty or value_col not in df.columns or "timestamp" not in df.columns:
        return None
    s = df.dropna(subset=[value_col]).set_index("timestamp")[value_col]
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s.between(0, 500)]
    if s.empty:
        return None
    daily = s.resample("D").mean().dropna()
    if daily.empty:
        return None
    return {
        "n_days": len(daily),
        "mean": float(daily.mean()),
        "who_exceed_days": int((daily > who_24h).sum()),
        "pl_exceed_days": int((daily > pl_24h).sum()) if pl_24h else None,
        "daily": daily,
    }

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

    # Warstwa bezpieczeństwa: niezależnie od źródła (WAQI, merge, prognoza),
    # fizycznie niemożliwa wartość nie powinna nigdy trafić na dashboard.
    # Znaleziony w produkcji przypadek: przesunięcie kolumn przy dopisywaniu
    # CSV (kolejność pól z API WAQI nie jest gwarantowana) potrafiło wstawić
    # ciśnienie (np. 1010 hPa) w miejsce PM10, pokazując "1010 µg/m³" na
    # dashboardzie. Ucinamy takie wartości u źródła wyświetlania.
    physical_ranges = {
        "pm10": (0, 500), "pm25": (0, 500),
        "pm10_true": (0, 500), "pm10_pred": (0, 500), "pm10_hist": (0, 500),
        "pm25_true": (0, 500), "pm25_pred": (0, 500), "pm25_hist": (0, 500),
        "temp": (-40, 45), "rh": (0, 100), "pressure": (850, 1100), "wind": (0, 60),
    }
    for col, (lo, hi) in physical_ranges.items():
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            df[col] = vals.where(vals.between(lo, hi))

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

# PM2.5 tymczasowo ukryte — tylko PM10.
# NIE włączaj bez ponownej weryfikacji jakości: model PM2.5 (models/pm25_pipeline.pkl) ma
# R² = -22 (2026-09-27) — tylko 15 prawdziwych par pomiarowych Syngeos+GIOŚ na 6419+ wierszy,
# reszta to szacunki sezonowym współczynnikiem PM2.5/PM10 (estimate_pm25_from_pm10.py).
# Pokazanie tego jako "prognozę" klientowi byłoby wprowadzające w błąd — zob. TODO.md.
show_pm25 = False
fc_pollutant = "PM10"

# --- sidebar / filtry ---
with st.sidebar:
    st.header("Filtry")
    days = st.slider("Okres (dni)", 1, 120, 45)
    smooth = st.selectbox("Wygładzanie (rolling h)", [0, 6, 12, 24], index=2)
    meas_src = st.radio("Źródło PM10 (do porównania)", ["historia GIOŚ", "merged GIOŚ+IMGW"], index=0)
    horizon_h = st.number_input("Horyzont prognozy (godziny do przodu)", min_value=1, max_value=72, value=72)
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

# --- wspólne: ostatni PRAWDZIWY pomiar (liczony z pomiaru, nie z prognozy) ---
def compute_last_meas_timestamp() -> pd.Timestamp | None:
    src = hist_f if meas_src == "historia GIOŚ" else merged_f
    if src.empty or "timestamp" not in src.columns or "pm10" not in src.columns:
        return None
    s = src["timestamp"][src["pm10"].notna()]
    return s.max() if not s.empty else None

last_meas_ts = compute_last_meas_timestamp()

def last_meas_value() -> float | None:
    src = hist_f if meas_src == "historia GIOŚ" else merged_f
    if src.empty or "pm10" not in src.columns or last_meas_ts is None:
        return None
    row = src[src["timestamp"] == last_meas_ts]
    if row.empty:
        return None
    return float(row["pm10"].iloc[0])

def pred_at_horizon(h: int) -> float | None:
    if forecast.empty or "pm10_pred" not in forecast.columns or last_meas_ts is None:
        return None
    target_ts = last_meas_ts + pd.Timedelta(hours=h)
    fc = forecast.sort_values("timestamp")
    deltas = (fc["timestamp"] - target_ts).abs()
    if deltas.empty or deltas.min() > pd.Timedelta(hours=1):
        return None
    return float(fc.loc[deltas.idxmin(), "pm10_pred"])

# --- Sekcja nagłówkowa (KPI) — dla szybkiej orientacji, np. dla komisji konkursowej ---
cur_val = last_meas_value()
cur_label, cur_color = pm10_category(cur_val)
pred24 = pred_at_horizon(24)
pred48 = pred_at_horizon(48)
pred72 = pred_at_horizon(72)

k1, k2, k3, k4 = st.columns(4)
kpi_tile(
    k1, "Aktualny PM10 (ostatni pomiar)",
    f"{cur_val:.1f} µg/m³" if cur_val is not None else "brak danych",
    f"Jakość powietrza: {cur_label}" + (f" · {last_meas_ts:%d.%m %H:%M}" if last_meas_ts is not None else ""),
    cur_color,
)
p24_label, p24_color = pm10_category(pred24)
kpi_tile(k2, "Prognoza za 24h", f"{pred24:.1f} µg/m³" if pred24 is not None else "—", p24_label, p24_color)
p48_label, p48_color = pm10_category(pred48)
kpi_tile(k3, "Prognoza za 48h", f"{pred48:.1f} µg/m³" if pred48 is not None else "—", p48_label, p48_color)
p72_label, p72_color = pm10_category(pred72)
kpi_tile(k4, "Prognoza za 72h", f"{pred72:.1f} µg/m³" if pred72 is not None else "—", p72_label, p72_color)

st.markdown("")
render_health_advice(cur_label)

st.markdown("")
badge_col1, badge_col2 = st.columns([2, 1])
with badge_col1:
    st.success(
        "✅ **Dane rzeczywiste i zweryfikowane** — Źródło danych: GIOŚ – EKOINFONET "
        "(stacja Słupsk, ul. Kniaziewicza, [powietrze.gios.gov.pl](https://powietrze.gios.gov.pl)). "
        "Pogoda: IMGW-PIB (stacje synoptyczne, [danepubliczne.imgw.pl](https://danepubliczne.imgw.pl)). "
        "Żadna wartość w bieżącym modelu nie jest danymi syntetycznymi.",
        icon="✅",
    )
with badge_col2:
    if HORIZON_ACC.exists():
        try:
            acc = pd.read_csv(HORIZON_ACC)
            mae24 = acc.loc[acc["horizon_h"] == 24, "mae"]
            mae_txt = f"MAE @24h ≈ {mae24.iloc[0]:.1f} µg/m³" if not mae24.empty else "patrz zakładka Dokładność"
        except Exception:
            mae_txt = "patrz zakładka Dokładność"
    else:
        mae_txt = "uruchom backtest_horizon.py"
    st.info(f"🤖 **Model:** Random Forest, cechy: historia PM10 + pogoda + kalendarz.\n\n{mae_txt}", icon="🤖")

with st.expander("ℹ️ O projekcie — metodologia (dla komisji konkursowej)", expanded=False):
    st.markdown(
        """
**Źródła danych (wszystkie rzeczywiste, publicznie weryfikowalne):**
- **PM10 / NO2 / O3** — Źródło danych: GIOŚ – EKOINFONET ([powietrze.gios.gov.pl](https://powietrze.gios.gov.pl)), archiwum stacji Słupsk ul. Kniaziewicza.
- **PM2.5** — GIOŚ (jeśli stacja raportuje), uzupełniająco prywatne czujniki **Syngeos** w okolicy Słupska. Zbieranie
  danych trwa od niedawna — model PM2.5 uruchomi się automatycznie, gdy uzbiera się min. 72h historii
  (patrz zakładka **"PM2.5"**).
- **Pogoda** — [IMGW](https://danepubliczne.imgw.pl) (stacje synoptyczne) oraz [Open-Meteo](https://open-meteo.com) (archiwum + prognoza godzinowa).

**Model:** Random Forest Regressor (scikit-learn), identyczna architektura dla PM10 i PM2.5 — cechy: opóźnienia
(lag) i średnie kroczące zanieczyszczenia (1–24h), cechy czasowe (godzina, dzień tygodnia, miesiąc, sezon
grzewczy — cyklicznie kodowane), temperatura, wilgotność, ciśnienie, wiatr.

**Prognoza przyszłości** liczona jest **iteracyjnie** (rekurencyjnie) — prognoza z godziny *h* staje się danymi
wejściowymi dla godziny *h+1*, dlatego niepewność rośnie wraz z długością horyzontu (patrz zakładka
**"Dokładność prognozy"**). Pogoda w oknie przyszłości pochodzi z prognozy Open-Meteo (do 72h naprzód).

**Uczciwość danych:** część historii PM10 (styczeń–kwiecień 2026) była tymczasowo uzupełniona wartościami
syntetycznymi w trakcie budowy pipeline'u — zostały one w całości zastąpione realnymi, zweryfikowanymi
pomiarami z archiwum GIOŚ (skrypt `gios_real_backfill.py`).
        """
    )

st.divider()

# --- zakładki ---
tab_hist, tab_compare, tab_future, tab_pm25, tab_accuracy, tab_norms, tab_weather = st.tabs([
    "Historia PM",
    "Rzeczywiste vs prognoza",
    "Predykcja (tylko przyszłość)",
    "PM2.5",
    "Dokładność prognozy",
    "Normy PL vs WHO",
    "Pogoda (IMGW)"
])

# --- Tab 1: Historia PM ---
with tab_hist:
    st.subheader("Historia PM10 (GIOŚ)")

    if hist_f.empty:
        st.info("Brak danych historycznych")
    else:
        hist_plot = hist_f.copy().sort_values("timestamp").reset_index(drop=True)
        add_roll(hist_plot, "pm10", smooth)
        y_col = f"pm10_r{smooth}" if f"pm10_r{smooth}" in hist_plot.columns else "pm10"

        # Segmentacja po przerwach czasowych (>2h) — zapobiega łączeniu odległych punktów
        hist_plot_smoothed = hist_plot[hist_plot[y_col].notna()].copy()
        if hist_plot_smoothed.empty and y_col != "pm10":
            # Okno filtra (np. 1 dzień) jest za krótkie na wygładzanie rolling —
            # zamiast pokazać pusty wykres bez wyjaśnienia, wróć do surowego PM10.
            y_col = "pm10"
            hist_plot_smoothed = hist_plot[hist_plot[y_col].notna()].copy()
        hist_plot = hist_plot_smoothed
        if hist_plot.empty:
            st.info("Za mało danych w wybranym okresie, żeby narysować wykres — zwiększ zakres dni (suwak po lewej).")
            hist_plot = None
        else:
            gaps = hist_plot["timestamp"].diff() > pd.Timedelta(hours=2)
            hist_plot["segment"] = gaps.cumsum()

        if hist_plot is not None and ALT:
            chart = alt.Chart(hist_plot).mark_line(
                color="#e45756", strokeWidth=2
            ).encode(
                x=alt.X("timestamp:T", title="timestamp"),
                y=alt.Y(f"{y_col}:Q", title="PM10 [µg/m³]"),
                detail="segment:N",
                tooltip=["timestamp:T", f"{y_col}:Q"],
            )
            st.altair_chart(chart.properties(height=260), use_container_width=True)
        elif hist_plot is not None:
            st.line_chart(hist_plot.set_index("timestamp")[["pm10"]])

# --- Tab 2: Rzeczywiste vs prognoza ---
with tab_compare:
    st.subheader("Porównanie: pomiar PM10 vs prognoza PM10")

    if forecast_f.empty or "pm10_pred" not in forecast_f.columns:
        st.info("Brak danych prognozy w pm10_all_latest.csv")
    else:
        meas = hist_f if meas_src == "historia GIOŚ" else merged_f
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

        LEGEND_DOMAIN = ["Pomiar rzeczywisty", "Prognoza AI (historia)", "Prognoza AI (przyszłość)"]
        LEGEND_RANGE = ["#e45756", "#1f77b4", "#2ca02c"]

        if ALT:
            meas_plot = meas.assign(seria=LEGEND_DOMAIN[0])
            hist_plot_c = fc.loc[hmask].assign(seria=LEGEND_DOMAIN[1])
            fut_plot_c = fc.loc[fmask].assign(seria=LEGEND_DOMAIN[2])
            color_scale = alt.Scale(domain=LEGEND_DOMAIN, range=LEGEND_RANGE)

            meas_ch = alt.Chart(meas_plot).mark_line(strokeWidth=2)\
                .encode(x="timestamp:T", y=alt.Y("pm10:Q", title="PM10 [µg/m³]"),
                        color=alt.Color("seria:N", scale=color_scale, title="Legenda", legend=alt.Legend(labelLimit=260)))
            hist_ch = alt.Chart(hist_plot_c).mark_line(strokeWidth=1.5, opacity=0.8).encode(
                x="timestamp:T", y="pm10_pred:Q",
                color=alt.Color("seria:N", scale=color_scale, title="Legenda", legend=alt.Legend(labelLimit=260)))
            fut_ch = alt.Chart(fut_plot_c).mark_line(strokeWidth=2.5, strokeDash=[6, 3]).encode(
                x="timestamp:T", y="pm10_pred:Q",
                color=alt.Color("seria:N", scale=color_scale, title="Legenda", legend=alt.Legend(labelLimit=260)))
            norm_rule = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(
                strokeDash=[2, 2], color="#999", strokeWidth=1
            ).encode(y="y:Q")
            norm_label = alt.Chart(pd.DataFrame({"y": [50], "label": ["norma dobowa GIOŚ: 50 µg/m³"]})).mark_text(
                align="left", dx=4, dy=-6, color="#999", fontSize=11
            ).encode(y="y:Q", text="label:N", x=alt.value(2))
            cut_rule = alt.Chart(pd.DataFrame({"timestamp": [last_meas_ts]}))\
                .mark_rule(strokeDash=[4, 4], color="gray").encode(x="timestamp:T")
            final = meas_ch + hist_ch + fut_ch + norm_rule + norm_label + cut_rule
            st.altair_chart(final.resolve_scale(y="shared").properties(height=340), use_container_width=True)
            st.caption(
                "🔴 Ciągła czerwona = rzeczywisty pomiar · 🔵 Niebieska = dopasowanie modelu do przeszłości "
                "(kontrola jakości) · 🟢 Zielona przerywana = prognoza AI na przyszłość · "
                "Szara pionowa kreska = 'teraz' (ostatni realny pomiar)."
            )
        else:
            cols_plot = [c for c in ["pm10_pred"] if c in fc.columns]
            st.line_chart(fc.set_index("timestamp")[cols_plot])

# --- Tab 3: Predykcja (tylko przyszłość) ---
with tab_future:
    st.subheader(f"🔮 Prognoza AI — kolejne {horizon_h} godzin")
    st.caption(
        "Kolor punktów pokazuje kategorię jakości powietrza wg progów GIOŚ dla PM10. "
        "Im dalej w przyszłość, tym większa niepewność prognozy — zobacz zakładkę **Dokładność prognozy**."
    )

    if forecast_f.empty or "pm10_pred" not in forecast_f.columns:
        st.info("Brak danych prognozy w pm10_all_latest.csv")
    elif last_meas_ts is None:
        st.warning("Brak ostatniego pomiaru — nie mogę wyznaczyć przyszłości.")
    else:
        fc = forecast_f.sort_values("timestamp")
        pred_col = "pm10_pred"

        # okno przyszłości: (last_meas_ts, last_meas_ts + h)
        df_future = fc[(fc["timestamp"] > last_meas_ts) &
                       (fc["timestamp"] <= last_meas_ts + pd.Timedelta(hours=horizon_h))].copy()

        if pred_col not in fc.columns:
            st.warning(f"Brak prognozy {fc_pollutant} w pm10_all_latest.csv — uruchom pipeline lub zwiększ horyzont.")
        elif df_future.empty:
            st.warning("Brak prognozy dla wybranego horyzontu — zwiększ horyzont albo odśwież pipeline (predykcja + merge).")
        else:
            df_future["kategoria"] = df_future[pred_col].apply(lambda v: pm10_category(v)[0])
            cat_domain = [b[1] for b in PM10_BANDS]
            cat_range = [b[2] for b in PM10_BANDS]

            k1, k2, k3 = st.columns(3)
            k1.metric("Min w prognozie", f"{df_future[pred_col].min():.1f} µg/m³")
            k2.metric("Średnia w prognozie", f"{df_future[pred_col].mean():.1f} µg/m³")
            k3.metric("Max w prognozie", f"{df_future[pred_col].max():.1f} µg/m³")

            best_row = df_future.loc[df_future[pred_col].idxmin()]
            worst_row = df_future.loc[df_future[pred_col].idxmax()]
            adv_col1, adv_col2 = st.columns(2)
            with adv_col1:
                st.success(
                    f"🟢 **Najlepszy moment na aktywność na zewnątrz:** "
                    f"{fmt_dt_pl(best_row['timestamp'])} "
                    f"({best_row[pred_col]:.1f} µg/m³, {best_row['kategoria']})"
                )
            with adv_col2:
                st.warning(
                    f"🔴 **Najgorszy moment, unikaj wtedy wysiłku:** "
                    f"{fmt_dt_pl(worst_row['timestamp'])} "
                    f"({worst_row[pred_col]:.1f} µg/m³, {worst_row['kategoria']})"
                )
            render_health_advice(worst_row["kategoria"])
            st.markdown("")

            if ALT:
                line = alt.Chart(df_future).mark_line(strokeWidth=2, color="#2ca02c", strokeDash=[6, 3]).encode(
                    x=alt.X("timestamp:T", title="Czas"),
                    y=alt.Y(f"{pred_col}:Q", title="PM10 [µg/m³]"),
                )
                pts = alt.Chart(df_future).mark_circle(size=55).encode(
                    x="timestamp:T", y=f"{pred_col}:Q",
                    color=alt.Color("kategoria:N", scale=alt.Scale(domain=cat_domain, range=cat_range),
                                     title="Jakość powietrza"),
                    tooltip=["timestamp:T", f"{pred_col}:Q", "kategoria:N"],
                )
                norm_rule = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(
                    strokeDash=[2, 2], color="#999", strokeWidth=1
                ).encode(y="y:Q")
                st.altair_chart((line + pts + norm_rule).properties(height=320), use_container_width=True)
            else:
                st.line_chart(df_future.set_index("timestamp")[[pred_col]])

            with st.expander("📋 Szczegółowa tabela prognozy godzina po godzinie"):
                tbl = df_future[["timestamp", pred_col, "kategoria"]].rename(
                    columns={pred_col: "PM10 [µg/m³]", "timestamp": "Data i godzina", "kategoria": "Jakość powietrza"}
                )
                st.dataframe(tbl, use_container_width=True, hide_index=True)

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
                                 file_name=f"prognoza_{horizon_h}h.png", mime="image/png")
            col2.download_button("Pobierz PDF (prognoza)", data=fig_bytes(fig, "pdf"),
                                 file_name=f"prognoza_{horizon_h}h.pdf", mime="application/pdf")

# --- Tab: PM2.5 (ta sama architektura co PM10, osobne źródło danych) ---
with tab_pm25:
    st.subheader("🟣 PM2.5 — pył drobny (ta sama architektura modelu co PM10)")
    st.caption(
        "Źródło: prywatne czujniki **Syngeos** w okolicy Słupska (urządzenia 411/189/623) — "
        "stacja GIOŚ w Słupsku nie zawsze raportuje PM2.5, więc to uzupełniające realne źródło lokalne."
    )

    pm25_forecast = normalize(load_csv(FORECAST_PM25, ["timestamp"]))
    has_pm25_model = PM25_MODEL.exists()
    is_bootstrap = PM25_BOOTSTRAP_META.exists()

    if is_bootstrap:
        st.warning(
            "⚠️ **To NIE są zweryfikowane pomiary.** Za mało realnych danych PM2.5 z czujników "
            "Syngeos (tylko kilkanaście godzin), więc model tymczasowo trenuje się na **szacunku** "
            "PM2.5 = realne PM10 (GIOŚ) × współczynnik sezonowy skalibrowany na garstce realnych "
            "par pomiarowych. Dokładność tego modelu jest wyraźnie niższa niż modelu PM10 — "
            "traktuj wynik jako orientacyjny rząd wielkości, nie precyzyjną prognozę. Model "
            "przetrenuje się automatycznie na w pełni realnych danych, gdy zbierze się "
            f"≥{MIN_ROWS_PM25}h prawdziwych pomiarów.",
            icon="⚠️",
        )
        with st.expander("Metodologia szacowania PM2.5 (pełny opis)"):
            try:
                st.code(PM25_BOOTSTRAP_META.read_text(encoding="utf-8"), language=None)
            except Exception:
                st.write("Brak pliku z opisem metodologii.")

    # Policz realne (nie-metadane, fizycznie możliwe) pomiary PM2.5 w merged_hourly.csv,
    # żeby pokazać uczciwy pasek postępu do progu treningu (72h) — ta sama reguła co
    # w train_pm10_rf.py (MIN_ROWS_TO_TRAIN).
    real_pm25_count = 0
    if not merged.empty:
        for col in ["PM2.5", "pm25_mean", "pm25_median"]:
            if col in merged.columns:
                vals = pd.to_numeric(merged[col], errors="coerce")
                vals = vals[(vals.notna()) & (vals.between(0, 500))]
                real_pm25_count = max(real_pm25_count, len(vals))

    if pm25_forecast.empty or not has_pm25_model:
        st.warning(
            f"**Zbieramy dane.** Model PM2.5 wymaga min. {MIN_ROWS_PM25} godzin realnych pomiarów, "
            f"żeby sensownie się nauczyć — na razie jest ich **{real_pm25_count}/{MIN_ROWS_PM25}**. "
            "Czujniki Syngeos działają i raportują na żywo — dane napłyną automatycznie, gdy "
            "godzinowy pipeline (Harmonogram zadań) będzie uruchomiony. Zero danych syntetycznych — "
            "model po prostu jeszcze czeka na wystarczającą historię."
        )
        st.progress(min(1.0, real_pm25_count / MIN_ROWS_PM25))
    else:
        pm25_f = filtr(pm25_forecast)
        cur25 = None
        if "pm25_true" in pm25_f.columns and pm25_f["pm25_true"].notna().any():
            s = pm25_f.dropna(subset=["pm25_true"]).sort_values("timestamp")
            cur25 = float(s["pm25_true"].iloc[-1])
            cur25_ts = s["timestamp"].iloc[-1]
        cur25_label, cur25_color = pm25_category(cur25)

        def pred25_at(h: int):
            if "pm25_pred" not in pm25_forecast.columns or cur25 is None:
                return None
            target_ts = cur25_ts + pd.Timedelta(hours=h)
            fc = pm25_forecast.sort_values("timestamp")
            deltas = (fc["timestamp"] - target_ts).abs()
            if deltas.empty or deltas.min() > pd.Timedelta(hours=1):
                return None
            return float(fc.loc[deltas.idxmin(), "pm25_pred"])

        tile_prefix = "Szacowany " if is_bootstrap else ""
        k1, k2, k3, k4 = st.columns(4)
        kpi_tile(k1, f"{tile_prefix}Aktualny PM2.5", f"{cur25:.1f} µg/m³" if cur25 is not None else "brak danych",
                 f"Jakość powietrza: {cur25_label}", cur25_color)
        for col, h in zip([k2, k3, k4], [24, 48, 72]):
            v = pred25_at(h)
            lbl, clr = pm25_category(v)
            kpi_tile(col, f"{tile_prefix}Prognoza za {h}h", f"{v:.1f} µg/m³" if v is not None else "—", lbl, clr)

        if ALT and "pm25_pred" in pm25_f.columns:
            fc = pm25_f.sort_values("timestamp")
            last_meas25 = cur25_ts if cur25 is not None else fc["timestamp"].min()
            meas25 = fc.dropna(subset=["pm25_true"])[["timestamp", "pm25_true"]] if "pm25_true" in fc.columns else pd.DataFrame()
            hmask25 = fc["timestamp"] <= last_meas25
            fmask25 = fc["timestamp"] > last_meas25
            meas25_label = "Pomiar (częściowo szacowany)" if is_bootstrap else "Pomiar rzeczywisty"
            LEGEND_DOMAIN25 = [meas25_label, "Prognoza AI (historia)", "Prognoza AI (przyszłość)"]
            color_scale25 = alt.Scale(domain=LEGEND_DOMAIN25, range=["#9c27b0", "#1f77b4", "#2ca02c"])
            layers = []
            if not meas25.empty:
                layers.append(alt.Chart(meas25.assign(seria=LEGEND_DOMAIN25[0])).mark_line(strokeWidth=2).encode(
                    x="timestamp:T", y=alt.Y("pm25_true:Q", title="PM2.5 [µg/m³]"),
                    color=alt.Color("seria:N", scale=color_scale25, title="Legenda")))
            layers.append(alt.Chart(fc.loc[hmask25].assign(seria=LEGEND_DOMAIN25[1])).mark_line(strokeWidth=1.5, opacity=0.8).encode(
                x="timestamp:T", y="pm25_pred:Q", color=alt.Color("seria:N", scale=color_scale25, title="Legenda")))
            layers.append(alt.Chart(fc.loc[fmask25].assign(seria=LEGEND_DOMAIN25[2])).mark_line(strokeWidth=2.5, strokeDash=[6, 3]).encode(
                x="timestamp:T", y="pm25_pred:Q", color=alt.Color("seria:N", scale=color_scale25, title="Legenda")))
            st.altair_chart(alt.layer(*layers).resolve_scale(y="shared").properties(height=320), use_container_width=True)
        else:
            st.info("Brak wystarczających danych do wykresu PM2.5.")

# --- Tab: Dokładność prognozy (audyt błędu w funkcji horyzontu) ---
with tab_accuracy:
    st.subheader("📏 Jak bardzo można ufać prognozie? Błąd modelu w funkcji horyzontu")
    st.caption(
        "Prognoza jest liczona rekurencyjnie: wynik dla godziny *h* staje się danymi wejściowymi dla *h+1*, "
        "więc błąd naturalnie rośnie z odległością w czasie. Ten wykres pokazuje zmierzony (nie szacowany) "
        "błąd modelu na historycznych danych — metodologia w `src/backtest_horizon.py`."
    )
    if not HORIZON_ACC.exists():
        st.warning(
            "Brak pliku `outputs/pm10_horizon_accuracy.csv`. Uruchom audyt:\n\n"
            "`py src/backtest_horizon.py --max-horizon 72 --step-hours 24`"
        )
    else:
        acc = pd.read_csv(HORIZON_ACC)
        has_baseline = "baseline_mae" in acc.columns

        c1, c2, c3 = st.columns(3)
        for col, h in zip([c1, c2, c3], [24, 48, 72]):
            row = acc[acc["horizon_h"] == h]
            if not row.empty:
                r = row.iloc[0]
                delta = f"{r['improvement_pct']:+.0f}% vs 'bez zmian'" if has_baseline and "improvement_pct" in r else None
                # "normal": dodatnia poprawa (model lepszy od baseline) -> zielono,
                # ujemna (model gorszy) -> czerwono. To jest właściwe zachowanie tutaj —
                # "inverse" byłoby błędem: pokazywałoby porażkę modelu na zielono.
                col.metric(f"MAE @ {h}h", f"±{r['mae']:.1f} µg/m³", delta=delta, delta_color="normal")

        if ALT:
            base = alt.Chart(acc).encode(x=alt.X("horizon_h:Q", title="Horyzont prognozy [h]"))
            mae_line = base.mark_line(color="#e45756", strokeWidth=2, point=True).encode(
                y=alt.Y("mae:Q", title="Średni błąd bezwzględny (MAE) [µg/m³]"),
                tooltip=["horizon_h:Q", "mae:Q", "rmse:Q", "n:Q"],
            )
            layers = [mae_line]
            if has_baseline:
                baseline_line = base.mark_line(color="#999", strokeWidth=2, strokeDash=[5, 4], point=True).encode(
                    y="baseline_mae:Q",
                    tooltip=["horizon_h:Q", "baseline_mae:Q"],
                )
                layers.append(baseline_line)
            st.altair_chart(alt.layer(*layers).properties(height=320), use_container_width=True)
            if has_baseline:
                st.caption(
                    "🔴 Model AI · ⚫ Linia przerywana = prognoza naiwna „bez zmian” (baseline) — "
                    "model musi ją wyraźnie pokonywać, inaczej nie ma sensu."
                )
                worse = acc[acc["improvement_pct"] < 0].sort_values("horizon_h")
                if not worse.empty:
                    crossover_h = int(worse.iloc[0]["horizon_h"])
                    best_h = acc.loc[acc["improvement_pct"].idxmax()]
                    st.warning(
                        f"📐 **Uczciwy wniosek z audytu:** model wyraźnie pokonuje prognozę „bez zmian” "
                        f"do ok. **{crossover_h}h** (najlepiej przy h+{int(best_h['horizon_h'])}h: "
                        f"{best_h['improvement_pct']:+.0f}% mniejszy błąd). Powyżej tego progu rekurencyjne "
                        "sumowanie błędu sprawia, że zwykłe „załóż że będzie jak teraz” zaczyna wygrywać z AI. "
                        "To realne ograniczenie modeli autoregresyjnych przy długich horyzontach — pokazujemy "
                        "je wprost zamiast ukrywać. Praktyczny wniosek: prognozie warto ufać najbardziej "
                        f"w oknie 1–{crossover_h}h, dalej traktować ją jako orientacyjny trend, nie liczbę.",
                        icon="📐",
                    )
        st.caption(
            "⚠️ Uwaga metodologiczna: audyt zakłada *idealną* prognozę pogody (używa rzeczywistej, "
            "zarejestrowanej pogody z przeszłości), bo nie da się odtworzyć historycznych prognoz "
            "Open-Meteo sprzed czasu. W realnym działaniu błąd może być nieznacznie wyższy — ten wykres "
            "pokazuje więc dolną granicę błędu, nie górną."
        )
        with st.expander("Pełna tabela wyników audytu"):
            st.dataframe(acc, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🧠 Co wpływa na prognozę? (wyjaśnialność modelu)")
    st.caption(
        "Random Forest nie jest „czarną skrzynką” — po treningu można sprawdzić, których cech "
        "model użył najczęściej do podejmowania decyzji. Poniżej ważność cech (feature importance) "
        "dla modelu PM10."
    )
    if PM10_FEATURE_IMPORTANCE.exists():
        imp = pd.read_csv(PM10_FEATURE_IMPORTANCE).head(10).copy()
        imp["cecha"] = imp["feature"].apply(humanize_feature)
        imp["udział"] = (imp["importance"] * 100).round(1)
        if ALT:
            chart = alt.Chart(imp).mark_bar(color="#4c78a8").encode(
                x=alt.X("importance:Q", title="Ważność cechy", axis=alt.Axis(format="%")),
                y=alt.Y("cecha:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
                tooltip=["cecha:N", alt.Tooltip("udział:Q", title="Udział [%]")],
            )
            st.altair_chart(chart.properties(height=320), use_container_width=True)
        top3 = imp.head(3)["cecha"].tolist()
        st.info(
            f"💡 **W praktyce:** model opiera prognozę PM10 przede wszystkim na: "
            f"**{', '.join(top3)}**. To zgodne z intuicją — zanieczyszczenie zmienia się powoli "
            "z godziny na godzinę, więc niedawna historia jest najsilniejszym sygnałem; pogoda i "
            "pora roku (sezon grzewczy) dopowiadają resztę.",
            icon="💡",
        )
    else:
        st.info("Brak pliku `models/pm10_feature_importances.csv` — uruchom trening (`train_pm10_rf.py`), żeby go wygenerować.")

# --- Tab: Normy PL vs WHO ---
with tab_norms:
    st.subheader("⚖️ Polska norma a zalecenia WHO — czy 'zgodne z normą' znaczy 'bezpieczne'?")
    st.caption(
        "Polskie/unijne normy prawne dla pyłu zawieszonego są wyraźnie bardziej liberalne niż "
        "wytyczne WHO z 2021 roku, oparte na aktualnej wiedzy medycznej o skutkach zdrowotnych "
        "smogu. Poniżej porównanie progów oraz to, jak często Słupsk je przekracza — na bazie "
        "realnych danych zebranych w tym projekcie."
    )

    norm_rows = []
    for pol, n in NORMS.items():
        norm_rows.append({
            "Zanieczyszczenie": pol,
            "Norma 24h — WHO": f"{n['who_24h']} µg/m³",
            "Norma 24h — Polska/UE": f"{n['pl_24h']} µg/m³" if n["pl_24h"] else "brak normy dobowej",
            "Różnica 24h": f"{100*(n['pl_24h']/n['who_24h']-1):+.0f}%" if n["pl_24h"] else "—",
            "Norma roczna — WHO": f"{n['who_annual']} µg/m³",
            "Norma roczna — Polska/UE": f"{n['pl_annual']} µg/m³",
            "Różnica roczna": f"{100*(n['pl_annual']/n['who_annual']-1):+.0f}%",
        })
    st.dataframe(pd.DataFrame(norm_rows), use_container_width=True, hide_index=True)
    st.caption(
        "Źródło norm: WHO Global Air Quality Guidelines (2021); Polska/UE — Dyrektywa 2008/50/WE "
        "i Rozporządzenie Ministra Środowiska (poziomy dopuszczalne)."
    )

    st.info(
        "💡 **Najbardziej uderzający fakt:** polska norma roczna dla PM2.5 (20 µg/m³) jest "
        "**4 razy wyższa** niż zalecenie WHO (5 µg/m³). Powietrze może więc być formalnie "
        "\"zgodne z polską normą\", a jednocześnie znacząco przekraczać poziom uznawany przez "
        "WHO za bezpieczny dla zdrowia.",
        icon="💡",
    )

    st.divider()
    st.subheader("📊 Ile razy Słupsk przekroczył normy? (realne dane)")

    stats10 = compute_daily_exceedance(hist, "pm10", NORMS["PM10"]["who_24h"], NORMS["PM10"]["pl_24h"])
    if stats10 is None:
        st.warning("Za mało danych PM10 do policzenia statystyk dobowych.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Dni z danymi", stats10["n_days"])
        c2.metric("Śr. dobowa PM10", f"{stats10['mean']:.1f} µg/m³")
        who_pct = 100 * stats10["who_exceed_days"] / stats10["n_days"]
        pl_pct = 100 * stats10["pl_exceed_days"] / stats10["n_days"]
        c3.metric("Dni > norma WHO (45)", f"{stats10['who_exceed_days']} ({who_pct:.1f}%)")
        c4.metric("Dni > norma PL (50)", f"{stats10['pl_exceed_days']} ({pl_pct:.1f}%)")

        annual_vs_who = stats10["mean"] - NORMS["PM10"]["who_annual"]
        if annual_vs_who > 0:
            st.warning(
                f"⚠️ Średnia PM10 z dostępnej historii ({stats10['mean']:.1f} µg/m³) **już przekracza** "
                f"roczne zalecenie WHO ({NORMS['PM10']['who_annual']} µg/m³) — mimo że jest daleko od "
                f"polskiej normy rocznej ({NORMS['PM10']['pl_annual']} µg/m³). To dokładnie ta różnica "
                "między 'legalne' a 'zalecane dla zdrowia'.",
                icon="⚠️",
            )
        else:
            st.success(
                f"✅ Średnia PM10 z dostępnej historii ({stats10['mean']:.1f} µg/m³) mieści się "
                f"poniżej rocznego zalecenia WHO ({NORMS['PM10']['who_annual']} µg/m³)."
            )

        if ALT:
            daily_df = stats10["daily"].reset_index()
            daily_df.columns = ["timestamp", "pm10_daily"]

            def _norm_bucket(v):
                if v > NORMS["PM10"]["pl_24h"]:
                    return "Powyżej obu norm"
                if v > NORMS["PM10"]["who_24h"]:
                    return "Powyżej WHO, poniżej PL"
                return "Poniżej normy WHO"

            daily_df["strefa"] = daily_df["pm10_daily"].apply(_norm_bucket)
            zone_domain = ["Poniżej normy WHO", "Powyżej WHO, poniżej PL", "Powyżej obu norm"]
            zone_range = ["#8BC34A", "#FF9800", "#E53935"]

            base = alt.Chart(daily_df).encode(x=alt.X("timestamp:T", title="Dzień"))
            bars = base.mark_bar(size=3).encode(
                y=alt.Y("pm10_daily:Q", title="Średnia dobowa PM10 [µg/m³]"),
                color=alt.Color("strefa:N", scale=alt.Scale(domain=zone_domain, range=zone_range), title="Strefa"),
                tooltip=["timestamp:T", "pm10_daily:Q", "strefa:N"],
            )
            who_line = alt.Chart(pd.DataFrame({"y": [NORMS["PM10"]["who_24h"]]})).mark_rule(
                strokeDash=[4, 4], color="#FF9800", strokeWidth=1.5
            ).encode(y="y:Q")
            pl_line = alt.Chart(pd.DataFrame({"y": [NORMS["PM10"]["pl_24h"]]})).mark_rule(
                strokeDash=[4, 4], color="#E53935", strokeWidth=1.5
            ).encode(y="y:Q")
            st.altair_chart((bars + who_line + pl_line).properties(height=280), use_container_width=True)
            st.caption(
                "🟢 Poniżej normy WHO · 🟠 Powyżej WHO, poniżej normy PL · 🔴 Powyżej obu norm. "
                "Linie przerywane: pomarańczowa = próg WHO (45), czerwona = próg PL (50)."
            )

    st.caption(
        "Uwaga: dostępna historia to obecnie kilka-kilkanaście miesięcy, nie pełny rok kalendarzowy — "
        "porównanie ze średnią roczną ma charakter orientacyjny, nie jest formalnym rozliczeniem normy."
    )

# --- Tab 4: POGODA (IMGW) ---
with tab_weather:
    st.subheader("Pogoda — temperatura / wilgotność / ciśnienie / wiatr")

    # Pogoda pochodzi z IMGW (przez merged_hourly.csv — merge_hourly.py / build_merged_full.py)
    dfw = merged_f
    _weather_src = "IMGW"

    if dfw.empty:
        st.warning("Brak danych pogodowych. Uruchom `run_hourly.bat` (imgw_fetch.py + merge_hourly.py).")
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
