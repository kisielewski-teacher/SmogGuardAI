# Jak odczytywać Histogram PM10

## Co to jest histogram?

Histogram pokazuje **jak często** PM10 przyjmowało wartości z danego przedziału.
Oś X = stężenie PM10 w µg/m³, oś Y = liczba godzin z tym stężeniem.

Nie pokazuje KIEDY wartości wystąpiły — tylko jak często i jak duże były.

---

## Elementy wykresu

```
Liczba
godzin
  │
  │  ██
  │  ██ ██
  │  ██ ██ ██
  │  ██ ██ ██ ██
  │  ██ ██ ██ ██ ██
  └──┴──┴──┴──┴──┴──────────────────── µg/m³
     0  10  20  30  40  45  75       150
                        ↑   ↑         ↑
                      WHO  UE    alarm PL
```

### Słupki (bars)
Każdy słupek = jeden przedział stężeń (np. 10–20 µg/m³).
**Wysokość słupka** = liczba godzin w tym przedziale.

### Linie przerywane — normy jakości powietrza
| Kolor | Wartość | Norma | Znaczenie |
|-------|---------|-------|-----------|
| Pomarańczowa | 45 µg/m³ | WHO (dobowy) | Zalecenie Światowej Organizacji Zdrowia |
| Czerwona | 75 µg/m³ | UE × 1,5 | Podwyższone ryzyko zdrowotne |
| Fioletowa | 150 µg/m³ | Alarm smogowy PL | Poziom informowania ludności |

> **Ważne**: normy WHO i UE dotyczą średniej **dobowej**, nie godzinowej.
> Godzinowe wartości mogą przekraczać te linie nawet przy "poprawnej" dobie.

---

## Odczyt konkretnych wartości z wykresu

Na podstawie 1677 godzin danych (ok. 70 dni):

| Przedział PM10 | Liczba godzin | Udział | Interpretacja |
|---------------|---------------|--------|---------------|
| 0 – 10 µg/m³ | 218 h | 13,0% | Bardzo czyste — silny wiatr, deszcz |
| 10 – 20 µg/m³ | 460 h | 27,4% | **Najczęstszy zakres** — dobra jakość powietrza |
| 20 – 30 µg/m³ | 394 h | 23,5% | Umiarkowana jakość — typowy zimowy dzień |
| 30 – 40 µg/m³ | 279 h | 16,6% | Podwyższone — słaby wiatr, chłodno |
| 40 – 45 µg/m³ | 118 h | 7,0% | Zbliżone do normy WHO — uwaga |
| 45 – 50 µg/m³ | 75 h | 4,5% | **Przekroczenie WHO** — ryzyko dla wrażliwych |
| 50 – 60 µg/m³ | 81 h | 4,8% | Wyraźnie podwyższone — ogranicz aktywność na zewn. |
| 60 – 75 µg/m³ | 47 h | 2,8% | Wysokie — epizody smogowe |
| 75 – 100 µg/m³ | 5 h | 0,3% | Bardzo wysokie — szczyt epizodów smogowych |
| powyżej 100 µg/m³ | 0 h | 0,0% | Nie odnotowano w tym okresie |

**Łącznie:**
- Poniżej normy WHO (45 µg/m³): **87,6% godzin** → powietrze jest dopuszczalne przez większość czasu
- Powyżej normy WHO (45 µg/m³): **12,4% godzin** (208 h) → ok. 1 na 8 godzin
- Powyżej 75 µg/m³: **0,3% godzin** (5 h) → rzadkie, silne epizody smogowe

---

## Jak czytać kształt histogramu?

### Kształt tego histogramu — skośny w prawo (right-skewed)

```
Liczba
godzin
240 │      ██
220 │   ██ ██
200 │   ██ ██
180 │   ██ ██
160 │██ ██ ██
140 │██ ██ ██
120 │██ ██ ██ ██           ← norma WHO 45 µg/m³
100 │██ ██ ██ ██
 80 │██ ██ ██ ██ ██ ██ ██
 60 │██ ██ ██ ██ ██ ██ ██
 40 │██ ██ ██ ██ ██ ██ ██
 20 │██ ██ ██ ██ ██ ██ ██ ██ ██
  0 └─────────────────────────────────── µg/m³
     0  10  20  30  40  50  60  70  80
          ↑
      SZCZYT (moda) ~15-20 µg/m³
```

**Co oznacza ten kształt:**
- **Szczyt (moda)** przy ~15–20 µg/m³ → najczęstszy poziom PM10
- **Długi ogon w prawo** → rzadkie, ale możliwe epizody z wysokimi wartościami
- **Gwałtowny spadek** po 45 µg/m³ → większość czasu powietrze jest poniżej normy WHO
- **Brak wartości >100** → w tym okresie nie było ekstremalnych zdarzeń smogowych

### Możliwe kształty histogramów i ich znaczenie

| Kształt | Co oznacza |
|---------|------------|
| Skośny w prawo (jak ten) | Typowo czyste, rzadkie epizody smogowe |
| Skośny w lewo | Częste wysokie stężenia, rzadkie czyste dni |
| Dwugarbny | Dwa wyraźne tryby — np. sezon letni vs zimowy |
| Symetryczny dzwon | Równomierny rozkład wokół średniej |
| Płaski | Brak dominującego poziomu PM10 |

---

## Praktyczna interpretacja dla mieszkańca Słupska

| Jeśli PM10 jest... | Co robić |
|--------------------|----------|
| 0–25 µg/m³ | Powietrze czyste — bieganie, rower, otwarte okna ✓ |
| 25–45 µg/m³ | Umiarkowane — osoby wrażliwe powinny ograniczyć wysiłek na zewn. |
| 45–75 µg/m³ | Przekroczenie WHO — unikaj długiego przebywania na zewnątrz |
| >75 µg/m³ | Wysoka jakość — zostań w domu, zamknij okna, unikaj wysiłku |
| >150 µg/m³ | Alarm smogowy (w tym okresie nie wystąpił) |

---

## Związek histogramu z box plotem

```
Histogram pokazuje:           Box plot pokazuje:
┌────────────────────┐        ┌──────────────┐
│ Jak wygląda cały   │        │ Q1, mediana, │
│ rozkład krok       │   ←→   │ Q3, wąsy,    │
│ po kroku           │        │ outliery     │
└────────────────────┘        └──────────────┘
```

Z histogramu odczytujesz: gdzie leży szczyt (moda) i jak "gruby" jest ogon.
Z box plotu odczytujesz: medianę, percentyle i punkty odstające w jednym miejscu.
Oba wykresy opisują **ten sam zbiór danych** — tylko z różnej perspektywy.
