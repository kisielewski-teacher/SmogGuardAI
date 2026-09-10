# SmogGuardAI — System prognozowania jakości powietrza dla Słupska

## Czym jest SmogGuardAI?

SmogGuardAI to program komputerowy, który automatycznie pobiera dane o jakości powietrza i pogodzie, uczy się na podstawie historii pomiarów, a następnie przewiduje stężenia zanieczyszczeń (PM10) na najbliższe 24 godziny. Wyniki wyświetlane są w czytelnym **panelu wizualizacji** dostępnym w przeglądarce internetowej.

---

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

## KROK 3 — Konfiguracja klucza API (wymagane tylko raz)

Program pobiera dane z internetu i potrzebuje darmowego klucza dostępu (tokenu API) do serwisu WAQI (aqicn.org).

### Jak uzyskać klucz API WAQI?

1. Wejdź na: **<https://aqicn.org/data-platform/token/>**
2. Wpisz swój adres e-mail i kliknij „Submit".
3. Odbierz e-mail i skopiuj otrzymany token (ciąg liter i cyfr).

### Jak skonfigurować plik .env?

1. W folderze projektu `C:\Programy\Powietrze\SmogGuardAI` znajdź plik `.env.example`.
2. Skopiuj go i zmień nazwę kopii na `.env` (bez słowa „example").
3. Otwórz plik `.env` w Notatniku (kliknij prawym przyciskiem → Otwórz za pomocą → Notatnik).
4. Zastąp tekst `WKLEJ_TUTAJ_SWOJ_TOKEN` swoim tokenem WAQI:

```env
WAQI_TOKEN=abc123twój_token_tutaj
CITY=Slupsk
OUTPUT_FILE=aqicn_slupsk_data.csv
IMGW_STATIONS=Slupsk,Koszalin,Chojnice,Ustka,Leba
TZ=Europe/Warsaw
```

1. Zapisz plik (`Ctrl+S`) i zamknij Notatnik.

---

## KROK 4 — Uruchomienie projektu (pełny potok danych)

Masz dwie opcje uruchomienia:

### Opcja A — Pełny potok danych (zalecane przy pierwszym uruchomieniu)

Pełny potok wykonuje wszystkie 10 kroków: pobieranie danych, scalanie, budowę cech, trening modelu AI, prognozowanie, backtest i przygotowanie wyników dla panelu wizualizacji.

Otwórz **Eksplorator plików**, przejdź do folderu `C:\Programy\Powietrze\SmogGuardAI`, a następnie **dwukrotnie kliknij** plik:

```bat
run_full_pipeline.bat
```

Pojawi się czarne okno konsoli — to normalne. Pierwsze uruchomienie może zająć kilka minut, bo program pobiera i instaluje potrzebne biblioteki.

### Opcja B — Szybki potok godzinowy (do automatyzacji)

Wykonuje uproszczone kroki: pobieranie → scalanie → trening → prognozowanie. Przeznaczony do cyklicznego uruchamiania co godzinę.

```bat
run_hourly.bat
```

---

## Co dokładnie robi program? — Opis wszystkich kroków

### Krok 1/10 — Pobieranie danych z 5 źródeł (`fetch`)

Program łączy się z internetem i pobiera dane z pięciu różnych źródeł:

- **WAQI** (`waqi_fetch.py`) — dane o jakości powietrza z sieci aqicn.org dla Słupska (PM10, PM2.5, NO2, O3, temperatura, wilgotność, ciśnienie, prędkość wiatru)
- **IMGW** (`imgw_fetch.py`) — dane pogodowe z synoptycznych stacji meteorologicznych IMGW (Słupsk, Koszalin, Ustka i inne)
- **GIOŚ** (`gios_fetch.py`) — oficjalne pomiary jakości powietrza z sieci Inspekcji Ochrony Środowiska
- **Airly** (`airly_fetch.py`) — dane z czujników sieci Airly
- **Sensor.Community** (`sensor_community_fetch.py`) — dane z obywatelskich czujników jakości powietrza

Każde źródło zapisuje swoje dane do osobnego pliku CSV w folderze `data/`.

> **CSV** (Comma-Separated Values) to prosty format pliku tekstowego, w którym dane ułożone są w kolumny rozdzielone przecinkami — można go otworzyć w Excelu.

### Krok 2/10 — Scalanie danych godzinowych (`merge_hourly`)

Skrypt `merge_hourly.py` łączy dane ze wszystkich pobranych plików w jeden wspólny plik `data/merged_hourly.csv`. Wyrównuje wszystkie pomiary do wspólnej osi czasu (co godzinę) i wypełnia ewentualne luki.

### Krok 3/10 — Budowa cech dla modelu AI (`features`)

Skrypt `features.py` przetwarza scalone dane i tworzy plik `data/features_pm10.csv` zawierający zmienne wejściowe (cechy) dla modelu AI:

- **Lagi czasowe** — wartości PM10 sprzed 1, 3, 6, 12 i 24 godzin (model „patrzy" w przeszłość)
- **Średnie kroczące** — uśrednione wartości PM10 z ostatnich 3, 6, 12 i 24 godzin
- **Dane pogodowe** — temperatura, wilgotność, ciśnienie, prędkość i kierunek wiatru, opady deszczu

### Krok 4/10 — Trening modelu AI dla PM10 (`train_pm10_rf`)

Skrypt `train_pm10_rf.py` uczy model **Random Forest** (las losowy — rodzaj algorytmu uczenia maszynowego opartego na wielu drzewach decyzyjnych). Model analizuje historyczne dane i uczy się zależności między warunkami pogodowymi a stężeniem PM10.

Wytrenowany model zapisywany jest do pliku `models/pm10_pipeline.pkl`.

> **Random Forest** buduje setki lub tysiące małych „drzewek decyzyjnych" i uśrednia ich odpowiedzi, co daje znacznie lepszą dokładność niż jedno drzewo.

### Krok 5/10 — (Opcjonalnie) Trening modelu dla PM2.5

W bieżącej wersji ten krok jest wyłączony — projekt skupia się na PM10. Skrypt `train_pm25.py` istnieje i można go uruchomić ręcznie.

### Krok 6/10 — Prognozowanie PM10 na 24 godziny (`predict_pm10`)

Skrypt `predict_pm10.py` używa wytrenowanego modelu do wygenerowania prognozy stężeń PM10 na kolejne 24 godziny. Wyniki zapisywane są do pliku `outputs/pm10_pred_latest.csv`.

### Krok 7/10 — (Opcjonalnie) Prognozowanie PM2.5

Wyłączone w bieżącej wersji. Skrypt `predict_pm25.py` istnieje do ręcznego użycia.

### Krok 8/10 — Backtest historyczny (`backtest_pm10`)

Skrypt `backtest_pm10.py` sprawdza wstecznie, jak dobrze model przewidywał wartości PM10 na danych historycznych. Wynik (plik `outputs/pm10_backtest_YYYYMMDD_HHMMSS.csv`) zawiera kolumny `y_true` (prawdziwe pomiary) i `y_pred` (prognozy modelu).

Osiągane metryki dokładności:

- MAE (średni błąd bezwzględny): **ok. 0.47 µg/m³**
- RMSE (pierwiastek błędu średniokwadratowego): **ok. 1.26 µg/m³**
- R² (współczynnik dopasowania, max 1.0): **ok. 0.97**

### Krok 9/10 — (Opcjonalnie) Backtest PM2.5

Wyłączony w bieżącej wersji.

### Krok 10/10 — Scalanie wyników do panelu (`merge_pm10_results`)

Skrypt `merge_pm10_results.py` łączy w jeden plik `outputs/pm10_all_latest.csv`:

- wyniki backtestów (historia porównawcza)
- prognozy na kolejne 24 godziny
- prawdziwe pomiary z serwisu WAQI

Ten plik jest następnie odczytywany przez panel wizualizacji.

---

## KROK 5 — Uruchomienie panelu wizualizacji (Dashboard)

**Panel wizualizacji** (dashboard) to strona internetowa, która otwiera się w Twojej przeglądarce i pokazuje wykresy z historią pomiarów, prognozą oraz metrykami modelu.

### Panel PM10 (główny — zalecany)

Otwórz wiersz poleceń (`Win+R` → `cmd` → Enter), przejdź do folderu projektu i uruchom:

```bat
cd C:\Programy\Powietrze\SmogGuardAI
py -m streamlit run src/streamlit_pm10_dashboard.py
```

### Panel rozszerzony (wielozanieczyszczeniowy)

```bat
cd C:\Programy\Powietrze\SmogGuardAI
py -m streamlit run app/app_extended_multi.py
```

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

Skrypt automatycznie utworzy zadanie o nazwie `Powietrze_Slupsk_Hourly`, które będzie uruchamiać `run_hourly.bat` co godzinę.

### Ręczna konfiguracja przez Harmonogram zadań

1. Naciśnij `Win`, wpisz `Harmonogram zadań` i otwórz go.
2. Kliknij „Utwórz zadanie podstawowe..." w prawym panelu.
3. Nazwa: `Powietrze_Slupsk_Hourly`
4. Wyzwalacz: Co godzinę
5. Akcja: Uruchom program → wskaż plik `C:\Programy\Powietrze\SmogGuardAI\run_hourly.bat`
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
 │   ├─ aqicn_slupsk_data.csv    ← dane WAQI
 │   ├─ imgw_slupsk_hourly.csv   ← dane IMGW
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
 ├─ run_full_pipeline.bat    ← pełny potok (wszystkie 10 kroków)
 ├─ run_hourly.bat           ← szybki potok godzinowy
 ├─ setup_scheduler.bat      ← konfiguracja automatyzacji (uruchom jako admin)
 └─ remove_scheduler.bat     ← usunięcie automatyzacji
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

### „WAQI token error" lub brak danych

Sprawdź plik `.env` — token WAQI musi być wpisany bez cudzysłowów i spacji.

### Jak sprawdzić czy wszystko działa poprawnie?

Sprawdź logi w folderze `logs/` — każdy krok potoku zapisuje tam swój raport. Jeśli krok zakończył się błędem, w konsoli pojawi się `[WARN]`.

---

## Dane techniczne modelu AI

| Parametr | Wartość |
| --- | --- |
| Algorytm | Random Forest (scikit-learn) |
| Liczba drzew | 300 |
| Horyzont prognozy | 24 godziny |
| Częstotliwość aktualizacji | Co godzinę |
| MAE | ~0.47 µg/m³ |
| R² | ~0.97 |
| Minimalna liczba wierszy do treningu | 72 godziny (3 doby) |

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
