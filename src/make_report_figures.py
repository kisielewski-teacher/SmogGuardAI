# -*- coding: utf-8 -*-
"""
make_report_figures.py — rysuje wykres porownujacy metody prognozy (do prezentacji dla komisji).

Czyta wyniki eksperymentow z outputs/ i zapisuje docs/wykres_porownanie_metod.png:
- "bez zmian" (prognoza: jutro = dzis) — punkt odniesienia,
- metoda rekurencyjna (stara), uczona na 1 i 4 latach,
- metoda bezposrednia (nowa), uczona na 4 latach.
Wszystko policzone na tych samych punktach startowych w 2026 roku (dane nieznane modelom przy uczeniu).

Uzycie: py src/make_report_figures.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "outputs"
HOURS = [1, 6, 24, 48, 72]


def fig_wind():
    """PM10 w zaleznosci od kierunku wiatru (8 stron swiata), osobno zima i lato."""
    import numpy as np
    m = pd.read_csv(BASE / "data" / "merged_hourly.csv", parse_dates=["timestamp"])
    m = m[(m["predkosc_wiatru"] > 0) & m["PM10"].notna() & m["kierunek_wiatru"].notna()].copy()
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    m["sektor"] = [names[i] for i in ((m["kierunek_wiatru"] + 22.5) % 360 // 45).astype(int)]
    m["zima"] = m["timestamp"].dt.month.isin([10, 11, 12, 1, 2, 3])
    zima = m[m["zima"]].groupby("sektor")["PM10"].mean().reindex(names)
    lato = m[~m["zima"]].groupby("sektor")["PM10"].mean().reindex(names)
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=150)
    ax.bar(x - 0.2, zima.values, 0.4, color="#3b6ea5", label="Sezon grzewczy (X–III)")
    ax.bar(x + 0.2, lato.values, 0.4, color="#e6ab02", label="Reszta roku (IV–IX)")
    ax.set_xticks(x, ["N\npółnoc", "NE", "E\nwschód", "SE", "S\npołudnie", "SW", "W\nzachód", "NW"])
    ax.set_xlabel("Skąd wieje wiatr")
    ax.set_ylabel("Średnie PM10 (µg/m³)")
    ax.set_title("Smog w Słupsku zależy od kierunku wiatru (dane 2022–2026)\n"
                 "najgorzej, gdy wieje znad lądu (SE, S), najlepiej znad morza i z północy", fontsize=10.5)
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    path = BASE / "docs" / "wykres_pm10_a_kierunek_wiatru.png"
    fig.savefig(path)
    print(f"[OK] Zapisano {path}")


def main():
    fig_wind()
    direct = pd.read_csv(OUT / "experiment_direct_step12_4y_wind.csv")
    rec = pd.read_csv(OUT / "experiment_recursive_step12.csv").set_index("years_of_history")

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    ax.plot(direct["horizon_h"], direct["baseline_mae"], color="#888888", lw=2, ls="--",
            label="Bez zmian (jutro = dziś)")
    for years, color, marker in ((4.0, "#d95f02", "s"), (1.0, "#e6ab02", "^")):
        ys = [rec.loc[years, f"mae_h{h}"] for h in HOURS]
        ax.plot(HOURS, ys, color=color, marker=marker, lw=1.8, ms=7,
                label=f"Stara metoda (pętla), uczona na {int(years)} {'roku' if years == 1 else 'latach'}")
    ax.plot(direct["horizon_h"], direct["mae"], color="#1b9e77", lw=2.6,
            label="Nowa metoda (osobny model na każdą godzinę, z wiatrem), 4 lata")
    ax.set_xlabel("Za ile godzin przewidujemy")
    ax.set_ylabel("Średni błąd (µg/m³) — im niżej, tym lepiej")
    ax.set_title("Dokładność prognozy PM10 w Słupsku — test na danych z 2026 roku,\n"
                 "których modele nigdy nie widziały", fontsize=11)
    ax.set_xlim(0, 73)
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    path = BASE / "docs" / "wykres_porownanie_metod.png"
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path)
    print(f"[OK] Zapisano {path}")


if __name__ == "__main__":
    main()
