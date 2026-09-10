# -*- coding: utf-8 -*-
"""
src/syngeos_fetch.py

Prosty fetcher dla publicznego widgetu Syngeos (np. deviceId=623).
- Próbuje wczytać JSON z odpowiedzi; jeżeli to HTML, próbuje wydobyć obiekt JSON
  zawierający klucz `pm2_5` (heurystyka) albo dopasować wartości przez regex.
- Zapisuje wiersz CSV: timestamp, deviceId, pm2_5, pm10, temperature, humidity, air_pressure

Użycie:
  py src/syngeos_fetch.py --url "<widget-url>" --out data/syngeos_623.csv --device 623

"""
from __future__ import annotations
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


def extract_json_block_with_key(text: str, key: str) -> dict | None:
    """Znajdź w tekście pierwszy blok JSON zawierający `key` i zwróć jako dict.
    Heurystyka: znajdź wystąpienie klucza, potem znajdź najbliższy nawias { ... }
    i spróbuj zdeserializować.
    """
    idx = text.find(key)
    if idx == -1:
        return None
    # cofnij do pierwszego '{' przed kluczem
    start = text.rfind('{', 0, idx)
    if start == -1:
        start = 0
    # znajdź odpowiadający '}' - prosta pętla z licznikiem nawiasów
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return None
    snippet = text[start:end]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def find_value_in_obj(obj, candidate_keys):
    """Rekurencyjnie szukaj pierwszego dopasowania klucza w zagnieżdżonym obiekcie."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        for k in candidate_keys:
            if k in obj and obj[k] is not None:
                return obj[k]
        for v in obj.values():
            res = find_value_in_obj(v, candidate_keys)
            if res is not None:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_value_in_obj(item, candidate_keys)
            if res is not None:
                return res
    return None


def regex_extract(text: str, pattern: str):
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    groups = m.groups()
    # wybierz ostatnią przechwyconą grupę, która wygląda jak liczba
    for g in reversed(groups):
        if g is None:
            continue
        try:
            return float(g)
        except Exception:
            continue
    return None


def parse_response_text(text: str) -> dict:
    # Spróbuj JSON bezpośrednio
    try:
        payload = json.loads(text)
    except Exception:
        payload = None

    res = {"pm2_5": None, "pm10": None, "temperature": None, "humidity": None, "air_pressure": None}

    cand_keys = {
        "pm2_5": ["pm2_5", "pm25", "pm2.5", "PM2_5"],
        "pm10": ["pm10", "PM10"],
        "temperature": ["temperature", "temp", "temperatura"],
        "humidity": ["humidity", "rh", "wilgotnosc"],
        "air_pressure": ["air_pressure", "pressure", "cisnienie"],
    }

    if payload is not None:
        for tgt, keys in cand_keys.items():
            v = find_value_in_obj(payload, keys)
            if v is not None:
                try:
                    res[tgt] = float(v)
                except Exception:
                    res[tgt] = None
        return res

    # Jeśli nie JSON — spróbuj wydobyć blok JSON zawierający 'pm2_5'
    block = extract_json_block_with_key(text, "pm2_5")
    if block is not None:
        for tgt, keys in cand_keys.items():
            v = find_value_in_obj(block, keys)
            if v is not None:
                try:
                    res[tgt] = float(v)
                except Exception:
                    res[tgt] = None
        return res

    # Spróbuj sparsować HTML widgetu (bardziej niezawodnie niż proste regexy)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        # Każdy .widget-body może zawierać dwa układy:
        # - wartości w <p class="widget-body__value"> (np. wilgotność, temperatura)
        # - pomiary PM w formacie "(1.86 µg/m³)" w <p class="widget-body__sensor"> przed etykietą "PM2.5"/"PM10"
        for block in soup.find_all(class_=lambda x: x and 'widget-body' in x):
            # 1) spróbuj odnaleźć pomiar zapisany w nawiasie, np. "(1.86 µg/m³)"
            sensor_ps = block.find_all('p', class_=lambda x: x and 'widget-body__sensor' in x)
            measured_p = None
            label_p = None
            for p in sensor_ps:
                txt = p.get_text(strip=True)
                if re.match(r"^\(\s*[0-9]+(?:\.[0-9]+)?", txt):
                    measured_p = p
                    break
            if measured_p:
                # spróbuj odnaleźć etykietę sensora (PM2.5 / PM10 / temp / hum) wśród pozostałych <p>
                for p in sensor_ps:
                    if p is measured_p:
                        continue
                    lbl = p.get_text(strip=True).lower()
                    if any(x in lbl for x in ('pm2', 'pm10', 'temp', 'hum', 'rh', 'press', 'cisn')):
                        label_p = p
                        break
                # gdy brak, spróbuj znaleźć następnika / poprzednika
                if label_p is None:
                    label_p = measured_p.find_next_sibling('p') or measured_p.find_previous_sibling('p')
                # wydobądź liczbę z nawiasu
                m = re.match(r"^\(\s*([0-9]+(?:\.[0-9]+)?)", measured_p.get_text(strip=True))
                if m:
                    value = float(m.group(1))
                    lbl_text = (label_p.get_text(strip=True).lower() if label_p else "")
                    if 'pm2' in lbl_text or 'pm25' in lbl_text:
                        res['pm2_5'] = value
                    elif 'pm10' in lbl_text:
                        res['pm10'] = value
                    elif 'temp' in lbl_text:
                        res['temperature'] = value
                    elif 'hum' in lbl_text or 'rh' in lbl_text:
                        res['humidity'] = value
                    elif 'press' in lbl_text or 'cisn' in lbl_text:
                        res['air_pressure'] = value
                continue

            # 2) spróbuj znaleźć element zawierający wartość (np. wilgotność/temperatura)
            val_tag = block.find(class_=lambda x: x and ('widget-body__value' in x or 'widget-value' in x or 'value' in x))
            if val_tag:
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)", val_tag.get_text())
                if m:
                    value = float(m.group(1))
                    label_tag = block.find(class_=lambda x: x and ('widget-body__sensor' in x or 'widget-body__label' in x or 'widget-body__name' in x))
                    lbl_text = (label_tag.get_text(strip=True).lower() if label_tag else "")
                    if 'temp' in lbl_text:
                        res['temperature'] = value
                    elif 'hum' in lbl_text or 'rh' in lbl_text:
                        res['humidity'] = value
                    elif 'pm2' in lbl_text or 'pm25' in lbl_text:
                        res['pm2_5'] = value
                    elif 'pm10' in lbl_text:
                        res['pm10'] = value
                continue

            # 3) fallback: spróbuj znaleźć wzorzec "(X µg/m³)" wewnątrz bloku i dopasować etykietę
            block_txt = block.get_text(' | ', strip=True)
            m = re.search(r"\(?\s*([0-9]+(?:\.[0-9]+)?)\s*µg/m\u00b3", block_txt)
            if m:
                value = float(m.group(1))
                low = block_txt.lower()
                if 'pm2' in low or 'pm25' in low:
                    res['pm2_5'] = value
                elif 'pm10' in low:
                    res['pm10'] = value
                continue

        # Odrzuć ew. nieprawidłowe dopasowania (rok / timestampy — np. 2026)
        for k in ['pm2_5', 'pm10', 'temperature', 'humidity', 'air_pressure']:
            v = res.get(k)
            if isinstance(v, (int, float)) and v is not None and v > 1000:
                res[k] = None

        if any(res[k] is not None for k in ['pm2_5', 'pm10', 'temperature', 'humidity', 'air_pressure']):
            return res
    except Exception:
        pass

    # Fallback: regex dla najważniejszych miar
    res["pm2_5"] = regex_extract(text, r"pm2[_\-. ]?5[^0-9\-+]*([0-9]+(?:\.[0-9]+)?)")
    res["pm10"] = regex_extract(text, r"pm10[^0-9\-+]*([0-9]+(?:\.[0-9]+)?)")
    res["temperature"] = regex_extract(text, r"(?:temp(?:erature)?)[^0-9\-+]*([0-9]+(?:\.[0-9]+)?)")
    res["humidity"] = regex_extract(text, r"(?:hum|rh|wilgotnosc)[^0-9\-+]*([0-9]+(?:\.[0-9]+)?)")
    res["air_pressure"] = regex_extract(text, r"(?:pressure|cisnienie)[^0-9\-+]*([0-9]+(?:\.[0-9]+)?)")
    return res


def main():
    ap = argparse.ArgumentParser(description="Pobierz dane z publicznego widgetu Syngeos i zapisz CSV")
    ap.add_argument("--url", help="Pojedynczy URL widgetu Syngeos (public) - alternatywa do --devices/--urls")
    ap.add_argument("--urls", help="Lista URLi oddzielona przecinkami (alternatywa do --devices)")
    ap.add_argument("--devices", help="Lista deviceId oddzielona przecinkami (np. 411,189,623)")
    ap.add_argument("--out", default="data/syngeos_all.csv", help="Plik wyjściowy CSV z surowymi odczytami (append)")
    ap.add_argument("--aggregate", default="data/syngeos_agg.csv", help="Zapisz uśrednione pomiary (pm25/pm10) - plik wyjściowy")
    ap.add_argument("--resample", default="h", help="Interwał agregacji (pandas resample), domyślnie 'h' (godzinowo)")
    ap.add_argument("--device", default=None, help="Id urządzenia (opcjonalnie, używane gdy podajesz --url)")
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    # Zbuduj listę URLi do pobrania
    urls = []
    devices_given = []
    if args.devices:
        devices_given = [d.strip() for d in args.devices.split(",") if d.strip()]
        for d in devices_given:
            urls.append(
                f"https://api.syngeos.pl/api/public/widget.html?deviceId={d}&sensorsList%5B%5D=temperature&sensorsList%5B%5D=humidity&sensorsList%5B%5D=air_pressure&sensorsList%5B%5D=pm2_5&sensorsList%5B%5D=pm10&template=horizontal&theme=light"
            )
    if args.urls:
        urls += [u.strip() for u in args.urls.split(",") if u.strip()]
    if args.url:
        urls.append(args.url)

    if not urls:
        raise RuntimeError("Musisz podać co najmniej jeden URL (--url / --urls) lub listę deviceId (--devices).")

    out_path = Path(args.out)
    rows = []

    for u in urls:
        try:
            r = requests.get(u, timeout=args.timeout)
            r.raise_for_status()
            text = r.text
            parsed = parse_response_text(text)
            # spróbuj wydobyć deviceId z URL (jeśli nie podano globalnie)
            m = re.search(r"deviceId=(\d+)", u)
            dev = m.group(1) if m else (args.device or "")
            ts = datetime.now().replace(microsecond=0)
            # Remove redundant columns before saving
            row = {
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "deviceId": dev,
                "pm2_5": parsed.get("pm2_5"),
                "pm10": parsed.get("pm10"),
                "temperature": parsed.get("temperature"),
                "humidity": parsed.get("humidity"),
                "air_pressure": parsed.get("air_pressure"),
            }
            rows.append(row)
            if args.verbose:
                print("[OK] fetched:", dev, "->", row)

        except Exception as e:
            print(f"[WARN] fetch {u} failed:", e)

    # Zapis surowych odczytów (append)
    if rows:
        header = list(rows[0].keys())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not out_path.exists()
        with out_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=header)
            if write_header:
                writer.writeheader()
            for r in rows:
                writer.writerow(r)
        if args.verbose:
            print(f"[OK] Zapisano {len(rows)} wierszy do: {out_path}")

    # Agregacja: uśrednij pomiary PM2.5 / PM10 (godzinowo domyślnie)
    if args.aggregate:
        try:
            # wczytaj cały plik surowy (żeby agregacja obejmowała historię)
            df = pd.read_csv(out_path, parse_dates=["timestamp"]) if out_path.exists() else pd.DataFrame(rows)
            if rows and df.empty:
                df = pd.DataFrame(rows)
            if df.empty:
                raise RuntimeError("Brak danych do agregacji")
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
            # Ujednolicenie nazw: zaakceptuj 'pm25' lub 'pm2_5' (twórz alias 'pm25' gdy potrzeba)
            if "pm25" not in df.columns and "pm2_5" in df.columns:
                df["pm25"] = pd.to_numeric(df["pm2_5"], errors="coerce")
            # zapewnij, że kolumny istnieją (wypełnij NaN jeśli brak)
            if "pm25" not in df.columns:
                df["pm25"] = pd.NA
            if "pm10" not in df.columns:
                df["pm10"] = pd.NA
            # rzutowanie na liczby (bezawaryjnie)
            df["pm25"] = pd.to_numeric(df["pm25"], errors="coerce")
            df["pm10"] = pd.to_numeric(df["pm10"], errors="coerce")
            # grupuj po interwale (użyj tylko pm25/pm10)
            sel = df[["pm25", "pm10"]]
            agg = sel.resample(args.resample).agg(["mean", "median", "std", "count"])
            # spłaszcz kolumny
            agg.columns = ["_".join(col).strip() for col in agg.columns.values]
            agg = agg.reset_index().rename(columns={"pm25_mean": "pm25_mean", "pm10_mean": "pm10_mean"})
            agg_path = Path(args.aggregate)
            agg_path.parent.mkdir(parents=True, exist_ok=True)
            agg.to_csv(agg_path, index=False)
            if args.verbose:
                print(f"[OK] Zapisano agregację do: {agg_path} (wiersze: {len(agg)})")
        except Exception as e:
            print("[WARN] agregacja nie powiodła się:", e)

    if args.verbose and not rows:
        print("[WARN] Nie pobrano żadnych wierszy z podanych URLi.")


if __name__ == "__main__":
    main()
