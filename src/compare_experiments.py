# -*- coding: utf-8 -*-
"""
compare_experiments.py — czy roznica miedzy dwoma wariantami to realna poprawa, czy szum?

Bierze dwa pliki "surowe" z experiment_direct_horizon.py (--out-raw), liczy dla wybranych
horyzontow roznice sredniego bledu (B minus A, ujemna = B lepszy) i przedzial ufnosci 95%
metoda bootstrap parowy: losujemy ze zwracaniem calymi DOBAMI (bloki), bo kolejne punkty startowe
z tej samej doby sa ze soba skorelowane. Jesli przedzial NIE obejmuje zera, poprawa jest wiarygodna.

Uzycie:
    py src/compare_experiments.py A_raw.csv B_raw.csv [--hours 1 6 12 24 48 72] [--label-a bez_wiatru --label-b z_wiatrem]
"""
import argparse

import numpy as np
import pandas as pd


def paired_ci(a: pd.DataFrame, b: pd.DataFrame, hours, n_boot=2000, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for h in hours:
        x = a[a["h"] == h].set_index("origin")
        y = b[b["h"] == h].set_index("origin")
        common = x.index.intersection(y.index)
        ea = (x.loc[common, "pred"] - x.loc[common, "y_true"]).abs()
        eb = (y.loc[common, "pred"] - y.loc[common, "y_true"]).abs()
        day = pd.Series(pd.to_datetime(common).normalize(), index=common)
        groups = [(ea[day == d].to_numpy(), eb[day == d].to_numpy()) for d in day.unique()]
        diff = eb.mean() - ea.mean()
        boots = []
        for _ in range(n_boot):
            idx = rng.integers(0, len(groups), len(groups))
            sa = np.concatenate([groups[i][0] for i in idx])
            sb = np.concatenate([groups[i][1] for i in idx])
            boots.append(sb.mean() - sa.mean())
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out.append({"h": h, "mae_a": ea.mean(), "mae_b": eb.mean(), "diff_b_minus_a": diff,
                    "ci_low": lo, "ci_high": hi, "n": len(common),
                    "wiarygodne": "TAK" if (lo > 0 or hi < 0) else "nie (w granicach szumu)"})
    return pd.DataFrame(out)


def pooled_ci(a: pd.DataFrame, b: pd.DataFrame, n_boot=2000, seed=0):
    """Laczny efekt na WSZYSTKICH horyzontach (1..72) naraz, bootstrap po dobach."""
    rng = np.random.default_rng(seed)
    m = a.merge(b, on=["origin", "h"], suffixes=("_a", "_b"))
    m["ea"] = (m["pred_a"] - m["y_true_a"]).abs()
    m["eb"] = (m["pred_b"] - m["y_true_b"]).abs()
    m["day"] = pd.to_datetime(m["origin"]).dt.normalize()
    per_day = m.groupby("day").agg(sa=("ea", "sum"), sb=("eb", "sum"), n=("ea", "size"))
    diff = (per_day["sb"].sum() - per_day["sa"].sum()) / per_day["n"].sum()
    boots = []
    for _ in range(n_boot):
        pick = per_day.iloc[rng.integers(0, len(per_day), len(per_day))]
        boots.append((pick["sb"].sum() - pick["sa"].sum()) / pick["n"].sum())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"mae_a": per_day["sa"].sum() / per_day["n"].sum(), "mae_b": per_day["sb"].sum() / per_day["n"].sum(),
            "diff_b_minus_a": diff, "ci_low": lo, "ci_high": hi, "n": int(per_day["n"].sum())}


def main():
    ap = argparse.ArgumentParser(description="Parowy bootstrap roznicy bledow dwoch wariantow")
    ap.add_argument("raw_a")
    ap.add_argument("raw_b")
    ap.add_argument("--hours", type=int, nargs="+", default=[1, 6, 12, 24, 48, 72])
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args()
    res = paired_ci(pd.read_csv(args.raw_a, parse_dates=["origin"]), pd.read_csv(args.raw_b, parse_dates=["origin"]),
                    args.hours)
    res = res.rename(columns={"mae_a": f"mae_{args.label_a}", "mae_b": f"mae_{args.label_b}"})
    print(res.round(3).to_string(index=False))
    pooled = pooled_ci(pd.read_csv(args.raw_a, parse_dates=["origin"]), pd.read_csv(args.raw_b, parse_dates=["origin"]))
    verdict = "TAK" if (pooled["ci_low"] > 0 or pooled["ci_high"] < 0) else "nie (w granicach szumu)"
    print(f"\nLacznie dla wszystkich horyzontow: MAE {args.label_a}={pooled['mae_a']:.3f}, {args.label_b}={pooled['mae_b']:.3f}, "
          f"roznica={pooled['diff_b_minus_a']:+.3f} (95% przedzial: {pooled['ci_low']:+.3f} .. {pooled['ci_high']:+.3f}) -> wiarygodne: {verdict}")


if __name__ == "__main__":
    main()
