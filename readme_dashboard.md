# SmogGuardAI — Przewodnik po dashboardzie

> Opisy dla uczniów: co widzisz na ekranie i co to oznacza

---

## Czym jest PM10?

**PM10** (ang. *Particulate Matter 10*) to drobne cząsteczki zawieszone w powietrzu,
których średnica nie przekracza **10 mikrometrów** (µm) — czyli około 7 razy cieńsze
od ludzkiego włosa. Pochodzą głównie z:

- spalania węgla i drewna w piecach domowych (sezon grzewczy)
- ruchu samochodowego (ścieranie opon, hamulców, nawierzchni)
- przemysłu i budów

Gdy stężenie PM10 jest wysokie, wdychamy te cząsteczki głęboko do płuc.
Mogą wywoływać astmę, choroby serca i problemy z oddychaniem.

**Jednostka: µg/m³** — mikrogramy na metr sześcienny powietrza.
Im wyższa wartość, tym bardziej zanieczyszczone powietrze.

---

## Widok 1 — „PM10: rzeczywiste vs prognoza"

Ten wykres pokazuje **dwie rzeczy jednocześnie** na osi czasu (od lewej = przeszłość,
do prawej = przyszłość).

### Górna część — linia PM10 w czasie

| Element | Co oznacza |
|---|---|
| **Niebieska linia ciągła** | Predykcja modelu AI — co model *przewidywał*, że będzie stężenie PM10 |
| **Czerwone punkty / linia** | Rzeczywiste pomiary ze stacji WAQI w Słupsku — co *faktycznie* zmierzono |
| **Przerywana linia pionowa** | Granica między przeszłością (lewa) a przyszłością (prawa) |
| **Zielony punkt** | Ostatnia dostępna predykcja na przyszłość |

### Co widać na wykresie?

Od końca grudnia 2025 do połowy marca 2026 wykres pokazuje typowy zimowy obraz
jakości powietrza w Polsce:

- Większość czasu PM10 utrzymuje się w granicach **10–80 µg/m³** — to normalne
  dla sezonu grzewczego.
- Widać **rytm dobowy**: stężenie rośnie rano (ludzie palą w piecach, by ogrzać
  domy przed pracą) i wieczorem (powroty do domu, gotowanie, ogrzewanie na noc).
- Pod koniec okresu (marzec) wartości są niższe — wiosna, cieplej, mniej ogrzewania.

### Ogromny pik (~1000 µg/m³) około 1–7 lutego

To **anomalia** — wartości sięgające 1000 µg/m³ są fizycznie niemożliwe
w normalnych warunkach dla Słupska. Prawdopodobne przyczyny:

- błąd czujnika (awaria, oblodzenie sensora),
- błędne dane ze źródła API,
- nakładanie się kolumn przy scalaniu danych z różnych źródeł.

Model AI (niebieska linia) **nie przewidział** tego ekstremalnego skoku.
Niebieska linia rośnie, ale zatrzymuje się dużo niżej. To pokazuje ograniczenie
modelu: nie przewiduje ekstremalnych, nieprzewidywalnych zdarzeń (awarii czujnika
czy wyjątkowego epizodu smogowego).

### Dolna część — błąd prognozy

Wykres słupkowy poniżej pokazuje **różnicę** między tym, co model przewidział,
a tym, co faktycznie zmierzono:

- Słupek **w dół** = model przewidział za wysoko (przeszacowanie)
- Słupek **w górę** = model przewidział za nisko (niedoszacowanie)
- Duże niebieskie słupki przy piiku (~-500) to błędy przy anomalii:
  model przewidywał ~50 µg/m³, a zmierzono ~1000 µg/m³.

Na większości okresu błędy są **małe i blisko zera** — model radzi sobie dobrze
w normalnych warunkach.

---

## Widok 2 — „Stan powietrza" (panel bieżący)

Ten panel to **podsumowanie bieżącej sytuacji** — jak tablica informacyjna
na stacji metra.

### Lewa strona — aktualny stan

**PM10 (ostatni pomiar): 31,0 µg/m³**

To ostatnia wartość odczytana ze stacji pomiarowej. Dla porównania:
norma WHO to 45 µg/m³ na dobę, polska norma to 50 µg/m³.
Wartość 31 µg/m³ mieści się bezpiecznie poniżej norm.

**Jakość powietrza: Dobra**

System automatycznie zamienia liczbę µg/m³ na zrozumiałą ocenę słowną:

| Stężenie | Jakość |
|---|---|
| 0–20 µg/m³ | Bardzo dobra |
| 21–40 µg/m³ | Dobra |
| 41–60 µg/m³ | Umiarkowana |
| 61–100 µg/m³ | Zła |
| powyżej 100 µg/m³ | Bardzo zła |

### Prawa strona — prognoza na następną godzinę

**Prognoza (następna godz.): 24,1 µg/m³**

Model AI przewiduje, że za godzinę stężenie PM10 wyniesie 24,1 µg/m³.
Mała etykieta **↓ -6,9 µg/m³** oznacza, że model spodziewa się *spadku*
o 6,9 µg/m³ w stosunku do aktualnego pomiaru. To dobra wiadomość —
powietrze ma być czystsze.

**Prognozowana jakość: Dobra**

Automatyczna ocena jakości dla przewidywanej wartości.

### Metryki historyczne — jak dobry jest model?

Metryki mówią nam, jak bardzo model mylił się **w przeszłości**
(na danych historycznych). To jak ocena szkolna — sprawdzamy, jak dobrze
model zdał egzamin na znanych już odpowiedziach.

| Metryka | Wartość | Co oznacza |
|---|---|---|
| **MAE** (Średni błąd bezwzględny) | 49,31 µg/m³ | Przeciętnie model myli się o ~49 µg/m³. Wysoka wartość wynika z anomalii (~1000 µg/m³) w danych |
| **RMSE** (Pierwiastek błędu średniokwadratowego) | 211,03 µg/m³ | RMSE „karze bardziej" za duże błędy. Wartość 211 jest ogromna właśnie przez kilka ekstremalnych punktów przy awarii czujnika |
| **MAPE** (Średni procentowy błąd bezwzględny) | 18,3% | Model myli się średnio o 18,3% wartości rzeczywistej. Bez anomalii to całkiem dobry wynik |

> **Ważna uwaga:** RMSE jest bardzo czułe na pojedyncze duże błędy. Jeden pomiar
> o wartości 1000 µg/m³, gdy model przewidział 50, wprowadza błąd
> (1000 − 50)² = 902 500 do obliczeń i drastycznie zawyża RMSE.
> Dlatego „prawdziwą" jakość modelu lepiej opisuje MAPE = 18,3%.

---

## Widok 3 — „Rozkład wartości PM10"

Ten wykres odpowiada na pytanie: **jakie wartości PM10 zdarzają się najczęściej?**

### Histogram (lewa strona)

Histogram to wykres słupkowy, gdzie:

- **Oś pozioma (X)** = wartość stężenia PM10 w µg/m³
- **Oś pionowa (Y)** = liczba godzin, w których zaobserwowano takie stężenie

Co widzimy:

- **Ogromny słupek po lewej (0–100 µg/m³)** — przez zdecydowaną większość czasu
  (ponad 800 godzin!) PM10 mieściło się w normalnym zakresie.
- **Małe słupki na prawo (200–1000 µg/m³)** — kilkanaście godzin anomalii
  (prawdopodobnie błędy czujnika).

Pionowe linie przerywane to **progi alarmowe**:

- Żółta: 50 µg/m³ — polska norma dobowa
- Czerwona: 75 µg/m³ — próg ostrzeżeń
- Fioletowa: 150 µg/m³ — próg alarmowy

### Wykres pudełkowy / Box plot (prawa strona)

Box plot to kompaktowy sposób pokazania rozkładu danych.
Czytamy go tak:

```
     ┌───────┐
━━━━━│   │   │━━━━━━━   ←  "wąsy" (zakres bez skrajnych wartości)
     └───────┘
  ↑      ↑   ↑
środek  Q1  Q3
(mediana)   (środkowe 50% danych)
```

- **Czerwone pudełko** (PM10 rzeczywiste): środek pudełka to mediana (~30 µg/m³),
  pudełko obejmuje środkowe 50% pomiarów, czerwone kropki powyżej to anomalie.
- **Niebieskie pudełko** (PM10 prognoza historyczna): pudełko jest węższe i niżej
  — model systematycznie **niedoszacowuje** wartości, bo nigdy nie widział wartości
  ~1000 µg/m³ podczas treningu i nie potrafi ich przewidzieć.

---

## Widok 4 — „Tabela prognozy PM10"

To surowa tabela danych — jak arkusz kalkulacyjny. Zawiera:

| Kolumna | Znaczenie |
|---|---|
| **timestamp** | Data i godzina pomiaru lub predykcji |
| **pm10_true** | Rzeczywisty zmierzony poziom PM10 (µg/m³) — „prawda z czujnika" |
| **pm10_hist** | Historyczna wartość PM10 używana przez model jako punkt odniesienia (średnia krocząca) |
| **pm10_pred** | Predykcja modelu AI — co model przewidywał, że będzie |
| **error** | Błąd = pm10_pred − pm10_true (ujemny = model przewidział za mało, dodatni = za dużo) |

### Kolorowanie komórek

Kolory pomagają szybko ocenić jakość predykcji:

- Zielony = mały błąd, model trafił dobrze
- Żółty / pomarańczowy = większy błąd, model znacznie się pomylił

### Co mówią nam te liczby? — przykłady z tabeli

| Czas | pm10_true | pm10_pred | error | Interpretacja |
|---|---|---|---|---|
| 2025-12-31 15:00 | 21,0 | 12,4 | -8,6 | Model niedoszacował o 8,6 µg/m³ |
| 2025-12-31 18:00 | 28,0 | 10,9 | -17,1 | Duże niedoszacowanie |
| 2025-12-31 22:00 | 10,0 | 10,7 | +0,7 | Prawie idealne trafienie! |

---

## Jak działa model AI w tym systemie?

### Schemat uproszczony

```
Dane wejściowe (cechy):                 Model AI              Wyjście:
────────────────────────────          ────────────          ──────────────
  PM10 sprzed 1 godziny       ──►                   ──►   Predykcja PM10
  PM10 sprzed 3 godzin        ──►    Random                za 1 godzinę
  PM10 sprzed 24 godzin       ──►    Forest
  Temperatura powietrza       ──►    (las losowy)
  Wilgotność względna         ──►
  Ciśnienie atmosferyczne     ──►
  Prędkość wiatru             ──►
  Godzina dnia (sin/cos)      ──►
  Dzień tygodnia              ──►
────────────────────────────          ────────────          ──────────────
```

### Co to jest Random Forest (las losowy)?

**Random Forest** to model składający się z wielu „drzew decyzyjnych".
Każde drzewo to seria pytań, np.:

```
Czy PM10 godzinę temu było > 30?
├─ TAK → Czy temperatura < 5°C?
│        ├─ TAK → Przewiduję PM10 = 38 µg/m³
│        └─ NIE → Przewiduję PM10 = 25 µg/m³
└─ NIE → Czy wiatr > 5 m/s?
         ├─ TAK → Przewiduję PM10 = 8 µg/m³
         └─ NIE → Przewiduję PM10 = 18 µg/m³
```

Odpowiedzi wszystkich drzew (np. 300 drzew) są uśredniane,
żeby dać jedną końcową predykcję.

### Jak model się uczy?

Model uczy się **z historycznych danych** — przegląda tysiące godzin pomiarów
i uczy się, jakie kombinacje cech pogodowych i historycznych PM10 prowadzą
do jakich wartości w przyszłości. To jak nauka z zeszytu z zadaniami:
model widzi pytanie (cechy wejściowe) i odpowiedź (rzeczywiste PM10),
i stopniowo zapamiętuje wzorce.

### Jak model przewiduje przyszłość?

Model przewiduje **krok po kroku**:

1. Zna ostatni zmierzony PM10 (np. 31 µg/m³ o godzinie 10:00).
2. Przewiduje PM10 na godzinę 11:00 używając: last PM10 + prognoza pogody (temperatura,
   wiatr itp. pobrana z serwisu Open-Meteo).
3. Używa tej predykcji (11:00) jako wejścia do przewidzenia PM10 na godzinę 12:00.
4. I tak dalej — każda kolejna godzina buduje na poprzedniej predykcji.

Dlatego im dalej w przyszłość, tym mniej pewna jest prognoza —
błędy kumulują się z każdym krokiem.

### Skąd pochodzi prognoza pogody?

System automatycznie pobiera prognozę temperatury, wilgotności, ciśnienia
i prędkości wiatru z darmowego serwisu **Open-Meteo** (open-meteo.com),
który udostępnia dane dla dowolnych współrzędnych geograficznych bez klucza API.
Dla Słupska używane są współrzędne: 54,463°N / 17,047°E.

### Skąd pochodzą dane historyczne PM10?

Dane historyczne pobierane są ze stacji pomiarowej w Słupsku
przy ul. Kniaziewicza 30, należącej do sieci **GIOŚ**
(Główny Inspektorat Ochrony Środowiska) oraz serwisu **WAQI**
(World Air Quality Index — aqicn.org).

---

## Słowniczek pojęć

| Pojęcie | Wyjaśnienie |
|---|---|
| **µg/m³** | Mikrogram na metr sześcienny — jednostka stężenia zanieczyszczeń w powietrzu |
| **PM10** | Cząsteczki o średnicy do 10 µm zawieszone w powietrzu |
| **Stacja WAQI** | Automatyczna stacja pomiarowa powietrza połączona z internetem |
| **Model AI / ML** | Program komputerowy, który uczy się wzorców z danych historycznych |
| **Random Forest** | Typ modelu AI złożony z wielu drzew decyzyjnych |
| **Predykcja** | Przewidywana (przyszła) wartość obliczona przez model |
| **MAE** | Średnia wartość błędu bez znaku — „o ile średnio model się myli" |
| **RMSE** | Jak MAE, ale duże błędy liczą się znacznie bardziej |
| **MAPE** | Błąd wyrażony w procentach — łatwiejszy do interpretacji |
| **Lag (opóźnienie)** | Wartość zmierzona N godzin wcześniej, używana jako cecha modelu |
| **Rolling mean** | Średnia krocząca — średnia z ostatnich N godzin |
| **Data leakage** | Błąd w budowie modelu: używanie jako cechy tej samej kolumny co cel predykcji |
| **Anomalia** | Wartość skrajnie odbiegająca od normy, często błąd czujnika |
| **Open-Meteo** | Darmowy serwis z prognozami i archiwum pogody dla całego świata |
| **GIOŚ** | Główny Inspektorat Ochrony Środowiska — państwowa sieć pomiarów jakości powietrza |
