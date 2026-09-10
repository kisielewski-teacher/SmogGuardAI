# Jak odczytywać Box Plot PM10

## Co to jest box plot (wykres skrzynkowy)?

Box plot to wykres statystyczny pokazujący **rozkład wartości** w zbiorze danych.
Nie pokazuje pojedynczych pomiarów w czasie — pokazuje **podsumowanie całego okresu**
(np. wszystkich godzinowych odczytów PM10 z ostatnich 45 dni).

---

## Elementy wykresu — szczegółowy opis

```
        ┌─── punkt odstający (outlier) — wartość > 1.5 × IQR poza pudełko
        │
  ──────┤  ← górny wąs (whisker) — maksimum bez outlierów (~70 µg/m³ dla czerwonej)
        │
  ┌─────┴─────┐
  │   - - - - │  ← średnia + 1 odchylenie standardowe (linia przerywana górna)
  │           │
  │  ─ ─ ─ ─ │  ← ŚREDNIA arytmetyczna (linia przerywana środkowa)
  │  ━━━━━━━━ │  ← MEDIANA — wartość środkowa (linia ciągła)
  │           │
  │   - - - - │  ← średnia − 1 odchylenie standardowe (linia przerywana dolna)
  └─────┬─────┘
        │
  ──────┤  ← dolny wąs — minimum bez outlierów (~5 µg/m³)
        │
        └─── punkt odstający (outlier)
```

### Pudełko (box)
- **Górna krawędź** = 75. percentyl (Q3) — 75% pomiarów jest PONIŻEJ tej wartości
- **Dolna krawędź** = 25. percentyl (Q1) — 25% pomiarów jest PONIŻEJ tej wartości
- **Wysokość pudełka** = IQR (rozstęp międzykwartylowy = Q3 − Q1) — im wyższe, tym większa zmienność danych
- Pudełko obejmuje **środkowe 50% wszystkich pomiarów**

### Linie wewnątrz pudełka
| Linia | Znaczenie |
| ------- | ----------- |
| Ciągła pozioma | **Mediana** — dokładna połowa pomiarów jest powyżej, połowa poniżej |
| Przerywana górna | Średnia + 1 odchylenie standardowe |
| Przerywana środkowa | **Średnia arytmetyczna** wszystkich wartości |
| Przerywana dolna | Średnia − 1 odchylenie standardowe |

> **Mediana vs Średnia**: jeśli przerywana (średnia) jest wyżej od ciągłej (mediany),
> oznacza to, że kilka wysokich wartości "ciągnie" średnią w górę — dane są skośne w prawo.

### Wąsy (whiskers)
- Sięgają do **1,5 × IQR** powyżej Q3 i poniżej Q1
- Obejmują "normalne" wartości — typowy zakres operacyjny

### Punkty odstające (outliery)
- Pojedyncze kropki **poza wąsami** — wartości wyjątkowo wysokie lub niskie
- Na czerwonej skrzynce widoczna kropka przy ~82 µg/m³ — epizod smogowy z silną inwersją

---

## Odczyt konkretnych wartości z wykresu

### PM10 (rzeczywiste) — czerwona skrzynka

| Statystyka | Wartość | Interpretacja |
| ----------- | --------- | --------------- |
| Minimum (bez outlierów) | ~5 µg/m³ | Czyste powietrze przy silnym wietrze (np. 6 kwi., wiatr 9 m/s) |
| Q1 (25. percentyl) | ~15 µg/m³ | Jedna czwarta godzin miała PM10 poniżej 15 |
| Mediana | ~24 µg/m³ | Typowa godzinowa wartość PM10 — "normalna" jakość powietrza |
| Średnia | ~27 µg/m³ | Nieco wyżej od mediany — kilka epizodów smogowych zawyża wynik |
| Q3 (75. percentyl) | ~37 µg/m³ | Trzy czwarte godzin miało PM10 poniżej 37 |
| Maksimum (bez outlierów) | ~70 µg/m³ | Graniczne wartości podczas epizodów smogowych |
| Outlier | ~82 µg/m³ | Szczyt epizodu smogowego: temp. 2°C, wiatr 1 m/s, wilg. 90% |

### PM10 (prognoza hist.) — niebieska skrzynka

| Statystyka | Wartość | Interpretacja |
| ----------- | --------- | --------------- |
| Q1 | ~16 µg/m³ | Model rzadko przewiduje wartości poniżej 16 |
| Mediana | ~25 µg/m³ | Prognoza "typowej" godziny — zbliżona do rzeczywistości |
| Q3 | ~35 µg/m³ | Model zachowuje podobny rozkład jak dane rzeczywiste |
| Maksimum | ~61 µg/m³ | Model nie przewiduje tak ekstremalnych epizodów jak rzeczywistość |

---

## Porównanie obu skrzynek — co mówi o modelu?

```
                   Czerwona        Niebieska
                  (rzeczywiste)   (prognoza)
Mediana:            ~24              ~25      ✓ zbliżone — model dobrze trafia w środek
Szerokość IQR:      ~22              ~19      ✓ podobna zmienność
Zakres max:         ~70-82           ~61      ⚠ model niedoszacowuje skrajnych epizodów
```

**Wnioski:**

1. **Model jest dobrze skalibrowany** w typowych warunkach — mediany obu skrzynek są bardzo zbliżone (~24–25 µg/m³).

2. **Model "wygładza" ekstrema** — górny wąs prognozy (~61 µg/m³) jest niższy niż rzeczywisty (~70 µg/m³). Oznacza to, że w szczytowych epizodach smogowych model zaniża prognozę o 10–20 µg/m³.

3. **Outlier w danych rzeczywistych** (~82 µg/m³) nie ma odpowiednika w prognozie — model nie przewiduje tak gwałtownych skoków, co jest typową cechą modeli regresji Random Forest.

4. **Dolne zakresy są podobne** — model dobrze przewiduje czyste dni (niskie PM10).

---

## Normy PM10 dla kontekstu

| Poziom | Wartość | Co oznacza |
| -------- | --------- | ------------ |
| WHO (dobowy) | 45 µg/m³ | Zalecenie Światowej Organizacji Zdrowia |
| UE (dobowy) | 50 µg/m³ | Limit prawny UE (nie może być przekroczony >35 razy/rok) |
| Alarm smogowy | 150 µg/m³ | Poziom informowania ludności (PL) |

> **Ważne**: Box plot pokazuje wartości **godzinowe**, nie dobowe.
> Dobowe średnie są zawsze niższe niż godzinowe maksima widoczne na wykresie.
