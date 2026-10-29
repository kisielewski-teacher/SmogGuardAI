# SmogGuardAI — System prognozowania jakości powietrza dla Słupska

## Czym jest SmogGuardAI?

SmogGuardAI to program komputerowy, który automatycznie pobiera **rzeczywiste, zweryfikowane** dane o jakości powietrza (GIOŚ) i pogodzie (IMGW), uczy się na podstawie historii pomiarów, a następnie przewiduje stężenia zanieczyszczeń (PM10) na najbliższe **72 godziny**. Wyniki wyświetlane są w czytelnym **panelu wizualizacji** dostępnym w przeglądarce internetowej, wraz z jawnym wskaźnikiem dokładności prognozy w funkcji horyzontu czasowego.

---

## Aktualny stan modelu (aktualizacja 2026-10-29)

- **Główna prognoza** to model **bezpośredni LightGBM**: osobny model na każdą godzinę 1..72 (kod: `src/direct_forecast.py`),
  z **przedziałem niepewności 80%** (kalibrowanym). Uczy się na 4 latach danych GIOŚ i IMGW (w tym kierunek wiatru).
- **Pomocniczo** działa starszy model Random Forest z prognozą w pętli (`train_pm10_rf.py`, `predict_pm10.py`); jego
  wynik daje „dopasowanie do historii” na wykresie, a przyszłe godziny nadpisuje prognoza bezpośrednia.
- **Dokładność** mierzymy **poza próbą** (`src/experiment_direct_horizon.py`): model uczy się na starszych danych, a błąd
  liczymy na późniejszych. Wyniki, wykresy i wyniki negatywne (prognoza pogody, sąsiednie stacje, mieszanie metod):
  [docs/Jak_poprawilismy_prognoze.md](docs/Jak_poprawilismy_prognoze.md). Skrót dla komisji:
  [docs/Streszczenie_dla_komisji.md](docs/Streszczenie_dla_komisji.md).
- **Przydatne polecenia:** `run_full_pipeline.bat` (całość + panel), `run_pipeline_scheduled.bat` (odświeżenie danych),
  `run_tests.bat` (testy na kopii projektu, ok. minuty), `demo_check.bat` (kontrola gotowości przed prezentacją).

> Niektóre opisy kroków poniżej dotyczą starszego modelu rekurencyjnego. Tam, gdzie liczby różnią się od
> dokumentu w `docs/`, obowiązują liczby z dokumentu (ocena poza próbą).

## Słowniczek — co oznaczają używane pojęcia?

| Pojęcie | Wyjaśnienie |
| --- | --- |
| **Pipeline** (potok danych) | Ciąg automatycznych kroków wykonywanych jeden po drugim — jak linia produkcyjna w fabryce. Każdy krok pobiera wyniki poprzedniego i produkuje coś nowego. |
| **Dashboard** (panel wizualizacji) | Strona internetowa otwierana w przeglądarce, która pokazuje wykresy i liczby. Nie wymaga internetu — działa lokalnie na Twoim komputerze. |
| **Model AI / uczenie maszynowe** | Program, który analizuje tysiące historycznych pomiarów i uczy się wzorców — np. że po silnym wietrze smog spada. Dzięki temu potrafi przewidywać przyszłe wartości. |
| **Cechy (features)** | Zmienne wejściowe podawane do modelu AI: temperatura, wilgotność, prędkość wiatru, wartości PM10 z poprzednich godzin itp. |
| **Backtest** (test wsteczny) | Sprawdzenie, jak dobrze model przewidywał jakość powietrza w **przeszłości** — na danych, których model wcześniej nie widział. Pozwala ocenić dokładność. |
| **Wirtualne środowisko (.venv)** | Odizolowany folder z bibliotekami Pythona tylko dla tego projektu — żeby nie mieszać z innymi programami na komputerze. |
| **PM10 / PM2.5** | Pyły zawieszone w powietrzu: PM10 to cząstki do 10 µm, PM2.5 — do 2,5 µm. Im wyższe stężenie, tym gorsze powietrze. |
| **WAQI / GIOŚ / IMGW** | Źródła danych: WAQI = światowy indeks jakości powietrza (aqicn.org), GIOŚ = Główny Inspektorat Ochrony Środowiska, IMGW = Instytut Meteorologii i Gospodarki Wodnej. |
| **AQI** (Air Quality Index) | Indeks jakości powietrza — uproszczona skala słowna (Bardzo dobra / Dobra / Umiarkowana / Zła / Bardzo zła) obliczana na podstawie stężenia PM10. |
| **Rolling mean** (średnia krocząca) | Uśredniona wartość PM10 z ostatnich N godzin (np. 24h), która wygładza krótkotrwałe skoki i pokazuje trend. |

---

## Wymagania — co musisz mieć na komputerze?

- System **Windows 10 lub Windows 11** (64-bit)
- Dostęp do **internetu** (do pobrania danych i bibliotek)
- Wolne miejsce na dysku: ok. **500 MB**

---

## KROK 1 — Instalacja Pythona

Python to język programowania, w którym napisany jest SmogGuardAI.

1. Wejdź na stronę: **<https://www.python.org/downloads/>**
2. Kliknij duży żółty przycisk **„Download Python 3.x.x"** (wybierz wersję 3.10 lub nowszą).
3. Uruchom pobrany instalator.
4. **WAŻNE**: Zanim klikniesz „Install Now", zaznacz checkbox **„Add Python to PATH"** na dole okna instalatora.
5. Kliknij „Install Now" i poczekaj na zakończenie instalacji.

**Sprawdzenie instalacji** — otwórz wiersz poleceń (naciśnij `Win+R`, wpisz `cmd`, naciśnij Enter) i wpisz:

```bat
py --version
```

Powinieneś zobaczyć np. `Python 3.11.x`. Jeśli pojawia się błąd, powtórz instalację i upewnij się, że zaznaczyłeś „Add Python to PATH".

---

## KROK 2 — Pobranie projektu

Jeśli masz już pliki projektu w folderze `C:\Programy\Powietrze\SmogGuardAI` — pomiń ten krok.

W przeciwnym razie pobierz i rozpakuj archiwum projektu do folderu `C:\Programy\Powietrze\SmogGuardAI`.

---

## KROK 3 — Konfiguracja (wymagane tylko raz)

Program korzysta wyłącznie z darmowych, publicznych API GIOŚ i IMGW — **nie
potrzebujesz żadnego klucza/tokenu API**, żeby go uruchomić.

1. W folderze projektu `C:\Programy\Powietrze\SmogGuardAI` znajdź plik `.env.example`.
2. Skopiuj go i zmień nazwę kopii na `.env` (bez słowa „example").
3. Domyślna zawartość działa od razu — nic nie musisz zmieniać:

```env
CITY=Slupsk
OUTPUT_FILE=aqicn_slupsk_data.csv
IMGW_STATIONS=Slupsk,Koszalin,Chojnice,Ustka,Leba
TZ=Europe/Warsaw
```

> Plik `.env` zawiera też zakomentowaną linię `WAQI_TOKEN` — to pozostałość po
> starszej, zdeprecjonowanej integracji z WAQI (aqicn.org), której darmowy
> token nie pozwala na użycie komercyjne. Możesz ją zignorować.

---

## KROK 4 — Uruchomienie projektu (pełny potok danych)

Masz dwie opcje uruchomienia:

### Opcja A — Cały projekt jednym plikiem (zalecane przy pierwszym uruchomieniu)

Ten jeden plik uruchamia **cały projekt od początku do końca**: pobieranie
danych, scalanie, budowę cech, trening modelu AI, prognozowanie, backtest,
przygotowanie wyników — a na końcu **sam otwiera panel wizualizacji**
w przeglądarce. Nie trzeba nic więcej klikać.

Otwórz **Eksplorator plików**, przejdź do folderu `C:\Programy\Powietrze\SmogGuardAI`, a następnie **dwukrotnie kliknij** plik:

```bat
run_full_pipeline.bat
```

Pojawi się czarne okno konsoli — to normalne. Pierwsze uruchomienie może
zająć kilka minut, bo program pobiera i instaluje potrzebne biblioteki
oraz trenuje model. Gdy potok danych się zakończy, w tym samym oknie
automatycznie wystartuje panel (Streamlit) i otworzy się przeglądarka
pod adresem `http://localhost:8501`. Żeby zamknąć panel, wróć do tego
czarnego okna i naciśnij `Ctrl+C`.

### Opcja B — Potok do automatyzacji (bez otwierania panelu)

Wykonuje te same kroki co Opcja A (pobieranie → scalanie → trening → prognoza 72h → backtest → scalanie wyników), ale **nie** uruchamia na końcu dashboardu — dashboard trzymamy włączony osobno cały czas, żeby Harmonogram zadań mógł odpalać ten skrypt co godzinę bez konfliktu portu. Właśnie ten plik wskazuje `setup_scheduler.bat` (patrz [KROK 6](#krok-6--automatyzacja-uruchamianie-co-godzinę)).

```bat
run_pipeline_scheduled.bat
```

---

## Co dokładnie robi program? — Opis wszystkich kroków

Pełny pipeline (`run_full_pipeline.bat`) ma 14 kroków — PM10 i PM2.5 przechodzą przez
**identyczną architekturę modelu** (ten sam kod `train_pm10_rf.py`/`predict_pm10.py`/`backtest_pm10.py`,
tylko inny `--target`). Różnica jest tylko w **danych wejściowych do treningu PM2.5**
(zobacz Krok 5) — patrz też uwaga „Skąd PM2.5, skoro WAQI go nie ma?" niżej.

### Krok 1/14 — Pobieranie danych na żywo (`fetch`)

Program łączy się z internetem i pobiera dane z trzech źródeł:

- **GIOŚ** (`gios_fetch.py`) — oficjalne, publiczne pomiary zanieczyszczeń (PM10, PM2.5, NO2, O3) ze stacji Słupsk, ul. Kniaziewicza — to główne i jedyne wymagane komercyjnie źródło pomiarów w programie
- **IMGW** (`imgw_fetch.py`) — dane pogodowe z synoptycznych stacji meteorologicznych IMGW (Słupsk, Koszalin, Ustka i inne)
- **Syngeos** (`syngeos_fetch.py`) — bieżące odczyty z prywatnych czujników PM2.5 koło Słupska (patrz Krok 5 — dlaczego tylko bieżące, nie archiwalne)

Każde źródło zapisuje swoje dane do osobnego pliku CSV w folderze `data/`.

> Pełną historię GIOŚ (nie tylko bieżącą godzinę) buduje/uzupełnia osobno
> `src/gios_real_backfill.py` → `data/gios_slupsk.csv`; `gios_fetch.py` dopisuje
> tylko bieżącą godzinę przy każdym uruchomieniu pipeline'u. `merge_hourly.py`
> łączy te dane z pogodą IMGW (patrz Krok 2) — GIOŚ jest kanonicznym źródłem
> prawdy dla PM10/PM2.5/NO2/O3 (patrz Krok 4). Skrypty `waqi_fetch.py` i
> `openmeteo_backfill.py` istnieją w `src/` wyłącznie dla zgodności z testami —
> są zdeprecjonowane (darmowe API WAQI/Open-Meteo zabraniają użycia
> komercyjnego, zob. `ToDo.md`) i nie są już częścią żadnego pipeline'u.
> Podobnie `airly_fetch.py` i `sensor_community_fetch.py` istnieją w `src/`, ale
> nie są obecnie częścią `run_full_pipeline.bat`/`run_pipeline_scheduled.bat` —
> są używane tylko przez starszy, nieużywany już `run_hourly.bat`.
>
> **CSV** (Comma-Separated Values) to prosty format pliku tekstowego, w którym dane ułożone są w kolumny rozdzielone przecinkami — można go otworzyć w Excelu.

### Krok 2/14 — Scalanie danych godzinowych (`merge_hourly`)

Skrypt `merge_hourly.py` łączy dane ze wszystkich pobranych plików w jeden wspólny plik `data/merged_hourly.csv`. Wyrównuje wszystkie pomiary do wspólnej osi czasu (co godzinę) i wypełnia ewentualne luki.

### Krok 3/14 — Budowa cech dla modelu AI (`features`)

Skrypt `features.py` przetwarza scalone dane i tworzy plik `data/features_pm10.csv` zawierający zmienne wejściowe (cechy) dla modelu AI:

- **Lagi czasowe** — wartości PM10 sprzed 1, 3, 6, 12 i 24 godzin (model „patrzy" w przeszłość)
- **Średnie kroczące** — uśrednione wartości PM10 z ostatnich 3, 6, 12 i 24 godzin
- **Dane pogodowe** — temperatura, wilgotność, ciśnienie, prędkość i kierunek wiatru, opady deszczu

### Krok 4/14 — Trening modelu AI dla PM10 (`train_pm10_rf`)

Skrypt `train_pm10_rf.py` uczy model **Random Forest** (las losowy — rodzaj algorytmu uczenia maszynowego opartego na wielu drzewach decyzyjnych). Model analizuje historyczne dane i uczy się zależności między warunkami pogodowymi a stężeniem PM10.

Wytrenowany model zapisywany jest do pliku `models/pm10_pipeline.pkl`.

> **Random Forest** buduje setki lub tysiące małych „drzewek decyzyjnych" i uśrednia ich odpowiedzi, co daje znacznie lepszą dokładność niż jedno drzewo.

Skrypt sam wykrywa i naprawia typowy problem po scalaniu: jeśli kanoniczna kolumna celu (np. `PM10`)
ma mniej danych niż jej alias po `merge_asof` (`PM10_x`/`PM10_y`/`pm10_mean`), automatycznie
przełącza się na alias z największą liczbą realnych wartości (`utils_features.resolve_best_target_alias`).
Jeśli w ogóle brakuje min. 72 realnych pomiarów, trening jest bezpiecznie pomijany z czytelnym
ostrzeżeniem zamiast produkować bezwartościowy model.

### Krok 5/14 — Przygotowanie danych PM2.5 (`estimate_pm25_from_pm10`)

**To jest jedyna nietypowa część pipeline'u.** Lokalne źródło PM2.5 (prywatne czujniki
**Syngeos** koło Słupska — WAQI dla Słupska go nie raportuje) nie ma API archiwalnego,
tylko bieżący odczyt, więc realnej historii jest bardzo mało (kilkanaście godzin). Skrypt
`estimate_pm25_from_pm10.py`:

1. **Sprawdza, ile jest realnych pomiarów PM2.5** w `merged_hourly.csv`.
2. **Jeśli >= 72h (próg treningu)** — kopiuje dane bez zmian. Model uczy się wyłącznie na
   realnych danych, dokładnie jak PM10. To docelowy, w pełni wiarygodny stan.
3. **Jeśli mniej** — szacuje PM2.5 dla całej historii jako `PM10_realne × współczynnik(sezon)`.
   Współczynnik (mediana PM2.5/PM10) jest liczony osobno dla sezonu grzewczego i pozostałego
   okresu, skalibrowany na garstce realnych, równoległych pomiarów PM2.5+PM10 z Syngeos.
   Wynik zapisywany jest do `data/merged_hourly_pm25_bootstrap.csv` z jawną kolumną
   `PM2.5_is_estimated` i opisem metodologii w `models/pm25_bootstrap_meta.txt`.

**To są dane szacowane, nie pomiar** — dashboard (zakładka „PM2.5") pokazuje to wyraźnie
pomarańczowym ostrzeżeniem, dopóki trwa ten tryb. Krok uruchamia się automatycznie za
każdym razem — sam „awansuje" do czystych danych rzeczywistych, gdy tylko zbierze się
wystarczająco dużo prawdziwych pomiarów (nie trzeba nic ręcznie przełączać).

### Krok 6/14 — Trening modelu AI dla PM2.5 (`train_pm10_rf --target PM2.5`)

Ten sam skrypt i ta sama architektura co dla PM10 — jedyna różnica to `--target PM2.5`,
`--csv-path data/merged_hourly_pm25_bootstrap.csv` (wynik Kroku 5) i inna ścieżka zapisu
(`models/pm25_pipeline.pkl`).

### Krok 7/14 — Prognozowanie PM10 na 72 godziny (`predict_pm10`)

Skrypt `predict_pm10.py` generuje starszą prognozę **rekurencyjną** (wynik godziny *h* wraca jako dane dla *h+1*) i zapisuje ją, razem z dopasowaniem do historii, do `outputs/pm10_pred_latest.csv`. Zaraz po nim `direct_forecast.py train` (raz na dobę) i `direct_forecast.py predict` nadpisują **przyszłe godziny** prognozą bezpośrednią z przedziałem niepewności (kolumny `pm10_pred_low`, `pm10_pred_high`). Historia zostaje bez zmian.

### Krok 8/14 — Prognozowanie PM2.5 na 72 godziny (`predict_pm10 --model pm25_pipeline.pkl`)

Ten sam skrypt `predict_pm10.py`, tylko wskazuje na model PM2.5 — wynik trafia do `outputs/pm25_pred_latest.csv`. Pomijany (z ostrzeżeniem w logu), dopóki model PM2.5 nie istnieje.

### Krok 9/14 — Backtest historyczny PM10 (`backtest_pm10` + `backtest_horizon`)

Skrypt `backtest_pm10.py` sprawdza wstecznie błąd **1-krokowy** (h+1) — jak dobrze model przewidywał wartość PM10 mając dostęp do prawdziwych opóźnień z poprzednich godzin. Wynik (plik `outputs/pm10_backtest_YYYYMMDD_HHMMSS.csv`) zawiera kolumny `y_true` (prawdziwe pomiary) i `y_pred` (prognozy modelu).

Osiągane metryki walidacyjne modelu (na zbiorze wydzielonym chronologicznie): MAE ≈ 1.8–3.2 µg/m³, R² ≈ 0.88 (dokładne wartości z ostatniego treningu — plik `logs/train_pm10_rf.log`).

**Uwaga o uczciwości liczb.** `backtest_pm10.py` ocenia model także na danych, na których się uczył, więc jego
MAE jest optymistyczne. Do oceny dokładności służy **`src/experiment_direct_horizon.py`** (ocena poza próbą), który
wypełnia zakładkę **„Dokładność prognozy”** (`outputs/pm10_horizon_accuracy.csv`). Przykład (test na 2026 roku):

| Horyzont | Zgadywanie „bez zmian” | Model | Poprawa |
| --- | --- | --- | --- |
| 24 h | 7,05 µg/m³ | 5,58 | o 21% |
| 72 h | 7,96 µg/m³ | 5,87 | o 26% |

Starszy `backtest_horizon.py` (rekurencyjny, w próbie) zostaje w repozytorium wyłącznie do porównań historycznych.

Dla PM2.5 (dane szacowane, patrz Krok 5) walidacyjne MAE ≈ 2.7 µg/m³, ale R² wychodzi
**ujemny** (ok. -10) — nie dlatego, że model jest bezużyteczny, tylko dlatego, że sam cel
(wartości rzędu 1-4 µg/m³ latem) ma bardzo małą wariancję, więc R² jest tu mylącą miarą.
Liczby te są pokazane w dashboardzie bez upiększania — to element uczciwości danych w tym
projekcie.

### Krok 10/14 — Backtest historyczny PM2.5 (`backtest_pm10 --target PM2.5`)

Analogicznie do Kroku 9, ale dla PM2.5 — pomijany, dopóki nie ma jeszcze modelu PM2.5.

### Krok 11/14 — Scalanie wyników PM10 do panelu (`merge_pm10_results --pollutant pm10`)

Skrypt `merge_pm10_results.py` łączy w jeden plik `outputs/pm10_all_latest.csv`:

- wyniki backtestów (historia porównawcza)
- prognozy na kolejne 72 godziny
- prawdziwe pomiary z serwisu WAQI/GIOŚ

Ten plik jest następnie odczytywany przez panel wizualizacji.

### Krok 12/14 — Scalanie wyników PM2.5 do panelu (`merge_pm10_results --pollutant pm25`)

Ten sam skrypt, flaga `--pollutant pm25` zamienia nazwy kolumn na `pm25_true`/`pm25_pred`/`pm25_hist`
i pomija fallback z WAQI (bo WAQI nie ma PM2.5 dla Słupska). Wynik: `outputs/pm25_all_latest.csv`,
odczytywany przez zakładkę **„PM2.5"** w panelu. Pomijany, dopóki nie ma jeszcze backtestu/predykcji PM2.5.

### Krok 13/14 — Audyt dokładności PM10 poza próbą (`experiment_direct_horizon`)

Patrz opis w Kroku 9. Model uczy się na starszych danych, a błąd liczony jest na ostatnich 300 dniach (ok. 1 minuty).

### Krok 14/14 — Uruchomienie panelu wizualizacji (`streamlit run`)

Ostatni krok uruchamia panel (dashboard) `app/app_extended_multi.py` i
otwiera go w domyślnej przeglądarce pod adresem `http://localhost:8501`.
To ten sam panel opisany niżej w sekcji [„Uruchomienie panelu wizualizacji
(Dashboard)"](#krok-5--uruchomienie-panelu-wizualizacji-dashboard) — przy
uruchomieniu przez `run_full_pipeline.bat` nie trzeba go już uruchamiać
ręcznie.

---

## KROK 5 — Uruchomienie panelu wizualizacji (Dashboard)

**Panel wizualizacji** (dashboard) to strona internetowa, która otwiera się w Twojej przeglądarce i pokazuje wykresy z historią pomiarów, prognozą oraz metrykami modelu.

### Panel PM10 (główny — zalecany)

Otwórz wiersz poleceń (`Win+R` → `cmd` → Enter), przejdź do folderu projektu i uruchom:

```bat
cd C:\Programy\Powietrze\SmogGuardAI
py -m streamlit run src/streamlit_pm10_dashboard.py
```

### Panel rozszerzony — `app/app_extended_multi.py` (zalecany, używany przez `run_full_pipeline.bat`)

```bat
cd C:\Programy\Powietrze\SmogGuardAI
py -m streamlit run app/app_extended_multi.py
```

Ten panel jest tym, który otwiera się automatycznie po `run_full_pipeline.bat`, i zawiera:

- **Pasek KPI na górze** — aktualny PM10, prognoza za 24h/48h/72h, każda wartość z kategorią jakości powietrza wg progów GIOŚ (kolor tła: zielony → fioletowy).
- **Plakietkę wiarygodności danych** — jawna informacja, że PM10 pochodzi z oficjalnego archiwum GIOŚ, a pogoda z IMGW (nie z danych syntetycznych).
- **Rozwijane „O projekcie"** — metodologia w skrócie, przeznaczona do prezentacji (np. komisji konkursowej).
- **Zakładkę „Dokładność prognozy"** — wykres błędu (MAE/RMSE) w funkcji horyzontu h=1..72h, **porównanie z prognozą naiwną „bez zmian"** (model musi ją pokonywać, żeby mieć sens — powyżej ok. 22h przestaje), oraz **wyjaśnialność modelu**: wykres ważności cech (feature importance) z prostym tłumaczeniem "na czym model się opiera" zamiast czarnej skrzynki.
- Zakładki: Historia PM, Rzeczywiste vs prognoza (z czytelną legendą kolorów), Predykcja (z tabelą godzina-po-godzinie i kolorami kategorii), **PM2.5** (ta sama architektura co PM10 — pokazuje pasek postępu zbierania danych, dopóki nie ma jeszcze 72h historii), Dokładność prognozy, Pogoda.

Po chwili w konsoli pojawią się adresy:

```text
Local URL: http://localhost:8501
```

**Otwórz przeglądarkę internetową** (Chrome, Firefox, Edge) i wpisz ten adres w pasku adresu. Panel wyświetli się automatycznie.

> Żeby zamknąć panel, wróć do okna konsoli i naciśnij `Ctrl+C`.

---

## Panel PM10 — funkcje i elementy

Panel (`src/streamlit_pm10_dashboard.py`) zawiera następujące sekcje:

### Wykres główny (PM10 rzeczywiste vs prognoza)

| Element | Opis |
| --- | --- |
| **Linia czerwona** | Rzeczywiste pomiary PM10 (historia) |
| **Linia pomarańczowa przerywana** | Średnia krocząca 24h — wygładza krótkotrwałe skoki |
| **Linia niebieska** | Prognoza historyczna (model vs rzeczywistość) |
| **Linia zielona przerywana** | Prognoza przyszłości (następne 24h) |
| **Zielony obszar** | Przedział ufności prognozy (±15% od wartości prognozy) |
| **Linia pionowa szara** | Granica historia/przyszłość |
| **Strefy kolorystyczne** | Zielona < 45, żółta 45–75, czerwona 75–150, fioletowa > 150 µg/m³ |

### Wykres błędu (subplot pod głównym)

Widoczny gdy dane zawierają kolumnę `error`. Słupki czerwone oznaczają prognozę wyższą niż rzeczywistość, niebieskie — niższą.

### Kafelki stanu powietrza

Cztery kafelki pokazujące na bieżąco:

- **PM10 (ostatni pomiar)** — aktualne stężenie
- **Jakość powietrza** — słowny opis + ikona koloru (🟢🟡🟠🔴🟣)
- **Prognoza następna godzina** — wartość + zmiana względem teraz
- **Prognozowana jakość** — słowny opis prognozy

### Metryki modelu (historia)

- **MAE** — średni błąd bezwzględny w µg/m³
- **RMSE** — pierwiastek błędu średniokwadratowego
- **MAPE** — procentowy błąd prognozy

### Rozkład wartości PM10

- **Histogram** — rozkład częstości wartości PM10 z pionowymi liniami norm
- **Box plot** — wykres pudełkowy z medianą, kwartylamiemi odchyleniem standardowym (porównanie pomiarów i prognozy)

### Kolorowana tabela danych

Tabela wszystkich wartości z kolorowaniem komórek wg norm:

| Kolor | Zakres | Jakość |
| --- | --- | --- |
| Zielony | < 20 µg/m³ | Bardzo dobra |
| Żółty | 20–45 µg/m³ | Dobra |
| Pomarańczowy | 45–75 µg/m³ | Umiarkowana |
| Czerwony | 75–150 µg/m³ | Zła |
| Fioletowy | > 150 µg/m³ | Bardzo zła |

### Panel boczny (sidebar)

- **Plik CSV** — ścieżka do pliku danych (domyślnie `outputs/pm10_all_latest.csv`)
- **Auto-odśwież co 30 sek** — automatyczne odświeżanie danych
- **Odśwież teraz** — ręczne odświeżenie
- **Zakres dat** — filtrowanie wszystkich wykresów do wybranego okresu

---

## KROK 6 — Automatyzacja (uruchamianie co godzinę)

Żeby program automatycznie aktualizował dane co godzinę bez Twojego udziału, możesz dodać go do **Harmonogramu zadań Windows** (wbudowane narzędzie Windows do planowania zadań).

### Automatyczna konfiguracja (zalecane)

Uruchom jako administrator — kliknij prawym przyciskiem myszy na plik, wybierz „Uruchom jako administrator":

```bat
setup_scheduler.bat
```

> **Wymagane uprawnienia administratora.** Tworzenie zadań w Harmonogramie zadań Windows wymaga podniesionych
> uprawnień — uruchomienie bez „Uruchom jako administrator" zakończy się błędem „Odmowa dostępu".

Skrypt utworzy zadanie o nazwie `Powietrze_Slupsk_Hourly`, które będzie uruchamiać `run_pipeline_scheduled.bat`
co godzinę (pobieranie danych, trening, prognoza 72h — **bez** otwierania dashboardu). Dashboard uruchom
osobno i zostaw włączony (`py -m streamlit run app/app_extended_multi.py`) — sam odświeży dane co minutę
(cache TTL) i po każdym przebiegu Harmonogramu pokaże świeżą prognozę.

> **Uwaga:** wcześniejsza wersja tego skryptu wskazywała na nieaktualną ścieżkę projektu (`air3\run_hourly.bat`)
> sprzed przeniesienia/przemianowania folderu na `SmogGuardAI` — przez to automatyczne odświeżanie danych
> faktycznie nie działało od kilku miesięcy. Zostało to naprawione.

### Ręczna konfiguracja przez Harmonogram zadań

1. Naciśnij `Win`, wpisz `Harmonogram zadań` i otwórz go.
2. Kliknij „Utwórz zadanie podstawowe..." w prawym panelu.
3. Nazwa: `Powietrze_Slupsk_Hourly`
4. Wyzwalacz: Co godzinę
5. Akcja: Uruchom program → wskaż plik `C:\Programy\Powietrze\SmogGuardAI\run_pipeline_scheduled.bat`
6. Kliknij Zakończ.

### Usunięcie zaplanowanego zadania

```bat
remove_scheduler.bat
```

---

## Struktura folderów projektu

```text
SmogGuardAI/
 ├─ data/                    ← dane źródłowe i scalone (CSV)
 │   ├─ gios_slupsk.csv          ← dane GIOŚ (główne źródło zanieczyszczeń)
 │   ├─ imgw_synop_hourly.csv    ← dane IMGW (pogoda)
 │   └─ merged_hourly.csv        ← dane scalone (główne źródło)
 ├─ models/                  ← wytrenowane modele AI (pliki .pkl)
 │   └─ pm10_pipeline.pkl        ← model PM10
 ├─ outputs/                 ← wyniki: prognozy, backtest, dane dla panelu
 │   └─ pm10_all_latest.csv      ← plik źródłowy dla panelu
 ├─ logs/                    ← logi z każdego kroku (do diagnostyki błędów)
 ├─ src/                     ← skrypty potoku danych (Python)
 │   └─ streamlit_pm10_dashboard.py  ← panel PM10 (główny)
 ├─ app/                     ← panel rozszerzony (wielozanieczyszczeniowy)
 │   └─ app_extended_multi.py    ← panel rozszerzony
 ├─ .env                     ← Twoja konfiguracja (token API, stacje)
 ├─ .env.example             ← wzór pliku .env
 ├─ requirements.txt         ← lista bibliotek Python
 ├─ run_full_pipeline.bat       ← pełny potok + dashboard (pierwsze uruchomienie ręczne)
 ├─ run_pipeline_scheduled.bat  ← ten sam potok BEZ dashboardu (do Harmonogramu zadań)
 ├─ setup_scheduler.bat         ← konfiguracja automatyzacji (uruchom jako admin)
 ├─ remove_scheduler.bat        ← usunięcie automatyzacji
 └─ src/experiment_direct_horizon.py ← audyt dokładności poza próbą (h=1..72h); src/direct_forecast.py ← główna prognoza
```

---

## Rozwiązywanie problemów

### „py nie jest rozpoznawane jako polecenie"

Python nie jest zainstalowany lub nie został dodany do PATH. Zainstaluj Pythona ponownie i upewnij się, że zaznaczyłeś **„Add Python to PATH"** podczas instalacji.

### „Brak wirtualnego środowiska w .venv"

Pliki `.bat` tworzą środowisko automatycznie. Jeśli błąd się powtarza, otwórz wiersz poleceń w folderze projektu i wpisz:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### „ModuleNotFoundError: No module named 'plotly'"

Biblioteka Plotly nie jest zainstalowana. Uruchom:

```bat
py -m pip install plotly
```

### Panel nie otwiera się w przeglądarce

Upewnij się, że wpisałeś poprawnie adres `http://localhost:8501` w pasku adresu przeglądarki (nie w pasku wyszukiwania).

### Brak danych / błąd pobierania GIOŚ lub IMGW

Sprawdź, czy masz połączenie z internetem i czy `data/gios_slupsk.csv` /
`data/imgw_synop_hourly.csv` w ogóle istnieją — jeśli nie, uruchom ręcznie
`py src\gios_real_backfill.py` (jednorazowo, buduje pełną historię) oraz
`py src\imgw_fetch.py`.

### Jak sprawdzić czy wszystko działa poprawnie?

Sprawdź logi w folderze `logs/` — każdy krok potoku zapisuje tam swój raport. Jeśli krok zakończył się błędem, w konsoli pojawi się `[WARN]`.

---

## Dane techniczne modelu AI

| Parametr | Wartość |
| --- | --- |
| Algorytm (główna prognoza) | LightGBM, osobny model na każdą godzinę 1..72 (prognoza bezpośrednia) + przedział 80% |
| Algorytm pomocniczy | Random Forest (scikit-learn) — dopasowanie do historii |
| Liczba drzew | 300 |
| `min_samples_leaf` | 10 (patrz niżej — dobrane empirycznie) |
| Rozmiar pliku modelu | ~3,5 MB (PM10), ~3,8 MB (PM2.5) — kompresja joblib `compress=6` |
| Horyzont prognozy | 72 godziny (prognoza bezpośrednia) |
| Częstotliwość aktualizacji | Co godzinę |
| MAE (walidacja, chronologiczny podział 80/20) | ~2,94 µg/m³ (PM10) |
| R² (walidacja, chronologiczny podział 80/20) | ~0,59 (PM10) |
| Błąd w funkcji horyzontu (h=1..72h) | zobacz `outputs/pm10_horizon_accuracy.csv` / zakładka „Dokładność prognozy" |
| Minimalna liczba wierszy do treningu | 72 godziny (3 doby) |

**Dlaczego `min_samples_leaf=10`, a nie domyślne 1?** Bez ograniczenia (domyślne ustawienie
scikit-learn) drzewa rosną aż każdy liść ma pojedynczą próbkę — dopasowują się do szumu
pojedynczych pomiarów, a plik modelu waży **~130 MB**. Sprawdziłem empirycznie kilkanaście
wartości `min_samples_leaf` (1–50) na tych samych danych walidacyjnych: okazało się, że
**większe liście jednocześnie poprawiają dokładność i zmniejszają plik** — bo pojedyncze
liście to przeuczenie, nie sygnał. Przy `min_samples_leaf=10` MAE spada z 3,04 do **2,94**,
R² rośnie z 0,57 do **0,59**, a plik z 130 MB do **3,5 MB** (37x mniej). To nie jest kompromis
jakość-za-rozmiar — obie strony wygrywają. Dodatkowo `joblib.dump(..., compress=6)` daje
bezstratną kompresję na dysku (ten sam model, mniejszy plik) bez zauważalnego wpływu na czas
wczytywania (+0,2 s).

## Szybki start — podsumowanie

Będąc w folderze projektu (`C:\Programy\Powietrze\SmogGuardAI`), uruchamiamy w kolejności:

**1. Pełny potok danych** (pobieranie, trening, prognoza):

```powershell
.\run_full_pipeline.bat
```

> W PowerShell **zawsze** trzeba dodać `.\` przed nazwą pliku `.bat` — inaczej PowerShell nie wie, że chodzi o plik w bieżącym folderze.

**2. Panel wizualizacji PM10** (po zakończeniu potoku):

```powershell
py -m streamlit run src/streamlit_pm10_dashboard.py
```

widok ogólny:

```powershell
py -m streamlit run app/app_extended_multi.py
```

Następnie otwórz przeglądarkę i wejdź na: **<http://localhost:8501>**
