# -*- coding: utf-8 -*-
"""
imgw_historical_backfill.py — pobiera PRAWDZIWĄ historię pogodową IMGW z publicznego
archiwum (danepubliczne.imgw.pl, "dane pomiarowo-obserwacyjne / terminowe / synop"),
zamiast syntetycznych danych Open-Meteo (usuniętych w refaktorze licencyjnym 2026-09).

Źródło: pliki ZIP per miesiąc, np.
  https://danepubliczne.imgw.pl/.../terminowe/synop/2026/2026_08_s.zip
Format i mapowanie kolumn zweryfikowane ręcznie (patrz ToDo.md): TEMP->temperatura,
FWR->predkosc_wiatru, WLGW->wilgotnosc_wzgledna, PPPM->cisnienie (ciśnienie na
poziomie morza — dokładnie zgodne z wartościami zwracanymi przez żywe API IMGW),
WO6G->suma_opadu (UWAGA: to opad skumulowany za 6h, nie godzinowy — najlepszy
dostępny w tym archiwum przybliżony odpowiednik).

Stacje: Koszalin, Ustka, Chojnice (te same, które realnie raportuje IMGW blisko
Słupska — sam Słupsk nie ma pełnej stacji synoptycznej, zob. README).

Uruchomienie:
    py src/imgw_historical_backfill.py [--start-year 2025 --start-month 12]

Tryb automatyczny (dla harmonogramu godzinowego — sam pilnuje częstotliwości,
żeby nie ściągać tego samego archiwum co godzinę):
    py src/imgw_historical_backfill.py --auto
    (uruchamia się realnie tylko jeśli minęło >= --auto-days od ostatniego udanego
    przebiegu — zob. znacznik logs/imgw_backfill_last_run.txt; start miesiąca
    wykrywany automatycznie z istniejących danych, żeby nie ściągać całej historii
    od nowa za każdym razem)
"""
from __future__ import annotations
import argparse
import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
OUT = DATA / "imgw_synop_hourly.csv"
MARKER = BASE / "logs" / "imgw_backfill_last_run.txt"

ARCHIVE_URL = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    "dane_meteorologiczne/terminowe/synop/{year}/{year}_{month:02d}_s.zip"
)

STATIONS = {"KOSZALIN": "Koszalin", "USTKA": "Ustka", "CHOJNICE": "Chojnice"}

COLUMNS = (
    "NSP,POST,ROK,MC,DZ,GG,HPOD,WHPOD,HPON,WHPON,HPOW,WHPOW,HTXT,POM1,POM2,WID,WWID,"
    "WIDO,WWIDO,WIDA,WWIDA,NOG,WNOG,KRWR,WKRWR,FWR,WFWR,PORW,WPORW,TEMP,WTEMP,TTZW,"
    "WTTZW,WENT,TWLW,CPW,WCPW,WLGW,WWLGW,TPTR,WTPTR,PPPS,WPPPS,PPPM,WPPPM,TECH,APP,"
    "WAPP,WO6G,WWO6G,ROPT,WROPT,POGB,POGU,CLCM,WCLCM,CHCL,WCHCL,CHLT,CHCM,WCHCM,CHMT,"
    "CHCH,WCHCH,CHHT,SGRN,WSGRN,DEFI,WDEFI,USLN,WUSLN,ROSW,WROSW,PORK,WPORK,GODP,MINP,"
    "TG05,WTG05,TG10,WTG10,TG20,WTG20,TG50,WTG50,TG100,WTG100,TMIN,WTMIN,TMAX,WTMAX,"
    "TGMI,WTGMI,RWSN,WRWSN,PKSN,WPKSN,HSS,WHSS,GRSN,WGRSN,GATS,UKPO,HPRO,WHPRO,CIPR,"
    "WCIPR"
).split(",")


def month_range(start_year: int, start_month: int):
    today = date.today()
    y, m = start_year, start_month
    while (y, m) <= (today.year, today.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _parse_synop(df: pd.DataFrame) -> pd.DataFrame:
    """Wspolne parsowanie surowych wierszy synop IMGW (plik miesieczny lub roczny stacji)."""
    # w 2024 IMGW zapisuje nazwy stacji dopelnione spacjami ("KOSZALIN      ")
    df = df.assign(POST=df["POST"].astype(str).str.strip())
    df = df[df["POST"].isin(STATIONS)].copy()
    if df.empty:
        return df
    df["stacja"] = df["POST"].map(STATIONS)
    df["timestamp"] = pd.to_datetime(
        dict(year=df["ROK"], month=df["MC"], day=df["DZ"], hour=df["GG"]),
        errors="coerce",
    )
    df["temperatura"] = pd.to_numeric(df["TEMP"], errors="coerce")
    df["predkosc_wiatru"] = pd.to_numeric(df["FWR"], errors="coerce")
    # kierunek wiatru w stopniach (0-360); przy ciszy (predkosc 0) kierunek jest bez znaczenia
    df["kierunek_wiatru"] = pd.to_numeric(df["KRWR"], errors="coerce")
    df["wilgotnosc_wzgledna"] = pd.to_numeric(df["WLGW"], errors="coerce")
    df["suma_opadu"] = pd.to_numeric(df["WO6G"], errors="coerce")
    df["cisnienie"] = pd.to_numeric(df["PPPM"], errors="coerce")
    out = df[["stacja", "timestamp", "temperatura", "predkosc_wiatru", "kierunek_wiatru",
              "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"]].dropna(subset=["timestamp"])
    return out


def fetch_month(year: int, month: int) -> pd.DataFrame:
    url = ARCHIVE_URL.format(year=year, month=month)
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        print(f"[INFO] Brak archiwum dla {year}-{month:02d} (jeszcze nieopublikowane?) — pomijam.")
        return pd.DataFrame()
    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        print(f"[WARN] {year}-{month:02d}: uszkodzone archiwum ZIP — pomijam.")
        return pd.DataFrame()
    name = zf.namelist()[0]
    with zf.open(name) as fh:
        df = pd.read_csv(fh, header=None, names=COLUMNS, encoding="cp1250", low_memory=False)
    out = _parse_synop(df)
    if out.empty:
        return out
    print(f"[OK] {year}-{month:02d}: {len(out)} realnych wierszy ({sorted(out['stacja'].unique())})")
    return out


# Starsze lata IMGW trzyma w ROCZNYCH plikach osobno dla kazdej stacji:
#   .../synop/{rok}/{rok}_{kod}_s.zip  (kod: 105 Koszalin, 115 Ustka, 235 Chojnice)
YEAR_STATION_URL = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    "dane_meteorologiczne/terminowe/synop/{year}/{year}_{code}_s.zip"
)
STATION_CODES = {"Koszalin": 105, "Ustka": 115, "Chojnice": 235}


def fetch_year(year: int) -> pd.DataFrame:
    """Pobiera caly rok dla naszych 3 stacji z rocznych plikow (lata sprzed miesiecznych archiwow)."""
    parts = []
    for name, code in STATION_CODES.items():
        url = YEAR_STATION_URL.format(year=year, code=code)
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            continue
        try:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
        except zipfile.BadZipFile:
            print(f"[WARN] {year} {name}: uszkodzone archiwum ZIP - pomijam.")
            continue
        with zf.open(zf.namelist()[0]) as fh:
            df = pd.read_csv(fh, header=None, names=COLUMNS, encoding="cp1250", low_memory=False)
        out = _parse_synop(df)
        if not out.empty:
            parts.append(out)
    if not parts:
        print(f"[INFO] Brak rocznego archiwum dla {year} - pomijam.")
        return pd.DataFrame()
    res = pd.concat(parts, ignore_index=True)
    print(f"[OK] {year} (roczne pliki): {len(res)} realnych wierszy ({sorted(res['stacja'].unique())})")
    return res


def detect_start_month() -> tuple[int, int]:
    """Wyznacz miesiąc startowy: miesiąc najnowszego realnego wiersza IMGW minus 1
    (żeby domknąć ewentualnie niepełny ostatni miesiąc), albo 2025-12 gdy brak danych."""
    if OUT.exists():
        existing = pd.read_csv(OUT, usecols=["stacja", "timestamp"], parse_dates=["timestamp"])
        real = existing[existing["stacja"].isin(STATIONS.values())]
        if not real.empty:
            last = real["timestamp"].max()
            y, m = last.year, last.month - 1
            if m < 1:
                m, y = 12, y - 1
            return y, m
    return 2025, 12


def is_due(auto_days: int) -> bool:
    if not MARKER.exists():
        return True
    try:
        last_run = datetime.fromisoformat(MARKER.read_text().strip())
    except Exception:
        return True
    return (datetime.now() - last_run) >= timedelta(days=auto_days)


def main():
    ap = argparse.ArgumentParser(description="Pełny historyczny backfill pogody IMGW (Koszalin/Ustka/Chojnice).")
    ap.add_argument("--start-year", type=int, default=None)
    ap.add_argument("--start-month", type=int, default=None)
    ap.add_argument("--auto", action="store_true",
                     help="Tryb dla harmonogramu: uruchom się tylko jeśli minęło >= --auto-days od ostatniego przebiegu.")
    ap.add_argument("--auto-days", type=int, default=25)
    args = ap.parse_args()

    if args.auto and not is_due(args.auto_days):
        print(f"[INFO] Ostatni backfill był mniej niż {args.auto_days} dni temu — pomijam (tryb --auto).")
        return

    start_year, start_month = args.start_year, args.start_month
    if start_year is None or start_month is None:
        start_year, start_month = detect_start_month()
        print(f"[INFO] Auto-wykryty start: {start_year}-{start_month:02d}")

    chunks = []
    yearly_done = set()
    for y in range(start_year, date.today().year):
        yearly = fetch_year(y)
        if not yearly.empty:
            # tnij do zadanego poczatku (start_month) w pierwszym roku
            if y == start_year:
                yearly = yearly[yearly["timestamp"] >= pd.Timestamp(y, start_month, 1)]
            chunks.append(yearly)
            yearly_done.add(y)
    for y, m in month_range(start_year, start_month):
        if y in yearly_done:
            continue
        chunk = fetch_month(y, m)
        if not chunk.empty:
            chunks.append(chunk)

    if not chunks:
        print("[ERR] Nie udało się pobrać żadnych danych z archiwum IMGW.")
        if args.auto:
            MARKER.parent.mkdir(exist_ok=True)
            MARKER.write_text(datetime.now().isoformat())
        return

    archive = pd.concat(chunks, ignore_index=True)
    archive_min, archive_max = archive["timestamp"].min(), archive["timestamp"].max()
    print(f"\nŁącznie z archiwum: {len(archive)} wierszy ({archive_min} .. {archive_max})")

    existing = pd.read_csv(OUT, parse_dates=["timestamp"]) if OUT.exists() else pd.DataFrame()
    if not existing.empty:
        # Usuń syntetyczne wiersze OpenMeteo-Slupsk w zakresie już pokrytym prawdziwym archiwum —
        # są teraz zbędne i mogłyby kolidować przy scalaniu (merge_asof) z realnymi danymi.
        before = len(existing)
        synthetic_covered = (
            (existing["stacja"] == "OpenMeteo-Slupsk")
            & (existing["timestamp"] >= archive_min)
            & (existing["timestamp"] <= archive_max)
        )
        existing = existing[~synthetic_covered]
        print(f"Usunięto {before - len(existing)} syntetycznych wierszy OpenMeteo-Slupsk pokrytych realnym archiwum.")
        # Usuń też stare, rzadkie realne wiersze z tych samych stacji/godzin (zastępujemy pełnym archiwum)
        existing = existing[~(
            existing["stacja"].isin(STATIONS.values())
            & existing["timestamp"].isin(archive["timestamp"])
        )]

    combined = pd.concat([existing, archive], ignore_index=True)
    combined = combined.drop_duplicates(subset=["stacja", "timestamp"]).sort_values(["timestamp", "stacja"])
    combined.to_csv(OUT, index=False)
    print(f"\nZapisano {len(combined)} wierszy do {OUT}")

    if args.auto:
        MARKER.parent.mkdir(exist_ok=True)
        MARKER.write_text(datetime.now().isoformat())


if __name__ == "__main__":
    main()
