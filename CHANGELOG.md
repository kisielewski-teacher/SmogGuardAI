# Historia zmian SmogGuardAI

Numeracja wersji: **GŁÓWNA.NIEWIELKA.POPRAWKA** (np. 1.2.0). Aktualny numer jest w pliku `VERSION`
i w panelu (pasek boczny).

- **GŁÓWNA** (2.0.0): zmiana niezgodna wstecz, np. nowy format plików z danymi, inny sposób uruchamiania
  albo inna zasada działania prognozy, przez którą stare pliki i modele przestają pasować.
- **NIEWIELKA** (1.3.0): nowe funkcje albo nowy model, zgodne ze starszymi danymi i plikami.
- **POPRAWKA** (1.2.1): naprawa błędu bez zmiany sposobu działania.

## Jak wydać nową wersję

1. Uruchom `run_tests.bat` (wszystkie testy mają przejść) i `demo_check.bat`.
2. Zmień numer w pliku `VERSION` i dopisz wpis na górze tego pliku (`## [numer] — data`).
3. Zacommituj: `git commit -m "Wersja X.Y.Z: krótki opis"`. Test `test_versioning.py` sprawdza, czy numer
   w `VERSION` zgadza się z najnowszym wpisem tutaj.
4. Oznacz commit tagiem i wyślij go: `git tag -a vX.Y.Z -m "Wersja X.Y.Z"`, potem `git push origin vX.Y.Z`.

## [1.2.1] — 2026-11-25

### Naprawiono

- Zakładka „Predykcja” pokazywała „Brak prognozy dla wybranego horyzontu”, bo prognoza w repozytorium była
  z 29.10, a pomiary sięgały 25.11. Prognoza jest odświeżona do 28.11.
- `START.bat` sam odświeża prognozę (`odswiez_prognoze.bat`: świeże dane, predykcja 72 h, scalenie wyników),
  gdy plik z prognozą jest starszy niż 6 godzin. Model nie jest trenowany od nowa.

### Dodano

- `Aktualizuj_Edge.bat`: aktualizacja przeglądarki Edge. Zbyt stary Edge pokazuje białą stronę zamiast panelu.
- Panel oznacza stronę jako „nie tłumacz”, żeby automatyczne tłumaczenie przeglądarki nie psuło interfejsu.

## [1.2.0] — 2026-10-29

### Dodano

- Prognoza bezpośrednia: osobny model LightGBM na każdą z 72 godzin (`src/direct_forecast.py`), zamiast pętli.
- Przedział niepewności 80% (kalibrowany metodą conformal) na wykresach prognozy.
- Dane od 2022 roku: PM10 z GIOŚ (prawie 40 tys. godzin) i pogoda IMGW z archiwum rocznych plików stacji.
- Kierunek wiatru w danych i w modelu; zakładka „Róża wiatrów” w panelu.
- Uczciwa ocena poza próbą: `experiment_direct_horizon.py`, `experiment_history_length.py`,
  `compare_experiments.py` (test parowy z losowaniem), zakładka „Dokładność prognozy” liczona poza próbą.
- Pobieranie PM10 z sąsiednich stacji GIOŚ (`gios_neighbors_fetch.py`) do eksperymentów.
- Uruchamianie: `ensure_env.bat` (sprawdza i instaluje Pythona, `.venv` i pakiety), `run_tests.bat` (testy
  równolegle na kopii projektu), `demo_check.bat` (kontrola gotowości przed prezentacją).
- Dokumentacja dla komisji w `docs/` i prezentacja na konkurs (PDF, notatki mówcy, źródła slajdów).

### Zmieniono

- Backtest 1-krokowy w trybie wsadowym (9 minut → 3 sekundy), audyt horyzontu równolegle (25 → 2 minuty).
- Pliki `.bat` zawierają tylko znaki ASCII i mają końce linii CRLF (`.gitattributes`).
- `merge_hourly.py` zawsze bierze pogodę z najbliższej stacji (Ustka), wcześniej wybór był przypadkowy.
- `setup_scheduler.bat` i `remove_scheduler.bat` same proszą o uprawnienia administratora.
- Zakresy wersji bibliotek w `requirements.txt`; opisy w panelu i README zgodne z aktualnym modelem.

### Naprawiono

- Plik dla panelu dopisywał ostatni pomiar na 6 godzin w przyszłość (godziny prognozy wyglądały jak pomiary).
- `gios_real_backfill.py --start` kasował historię sprzed podanej daty.
- Archiwum IMGW z 2024 roku: nazwy stacji z dodatkowymi spacjami powodowały brak całego roku pogody.
- Zgodność z pandas 3 (`day_of_week`, częstotliwość `h`, tablice tylko do odczytu).
- Rzadki wyścig w testach, które podmieniają prawdziwe pliki.

### Sprawdzone i niewdrożone

- Prognoza pogody (nawet idealna), dane z sąsiednich stacji i mieszanie starej i nowej metody nie poprawiły
  wyników poza próbą. Opis: `docs/Jak_poprawilismy_prognoze.md`.

## [1.1.0] — 2026-10-22

- Przejście ze źródeł WAQI i Open-Meteo na dane publiczne GIOŚ i IMGW (kwestie licencyjne).
- Poprawki potoku danych i informacje o licencjach bibliotek (`THIRD_PARTY_LICENSES.md`).

## [1.0.0] — 2026-09-10

- Pierwszy commit kodu źródłowego.
- Naprawa błędów potoku: wyciek danych (leakage), backtest, strefy czasowe, MAPE, kolejność kolumn Open-Meteo.
