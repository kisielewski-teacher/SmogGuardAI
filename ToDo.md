# ToDo

## Funkcje

- Biała strona panelu u ucznia (Edge, `http://localhost:8501`): serwer i aplikacja działają (czysty Edge 157 bez okna pokazuje pełny panel). Poprawka `translate="no"` nie pomogła (strona dalej ma `lang=en`, więc skrypt się nie wykonał). Gmail na tym komputerze pokazuje baner "Ta wersja przeglądarki nie jest już obsługiwana", więc podejrzenie: za stary Edge nie uruchamia frontendu Streamlit 1.66. Sprawdzić `edge://version` i konsolę (F12) ucznia. Jeśli to stara przeglądarka: wymóg aktualnej przeglądarki w `README.md`, kontrola wersji w `START.bat` albo przypięcie starszego Streamlita w `requirements.txt`. Gdy `translate="no"` okaże się zbędne, usunąć je z aplikacji.
- Prognoza w repo się starzeje: `START.bat` odświeża ją teraz sam (`odswiez_prognoze.bat`, gdy plik ma więcej niż 6 godzin), ale bez treningu. Model `pm10_pipeline.pkl` jest z 29.10.2026, więc co kilka tygodni trzeba uruchomić `run_full_pipeline.bat` i wydać nową wersję. Rozważyć też komunikat w panelu, gdy prognoza jest starsza niż 24 godziny, zamiast ogólnego "zwiększ horyzont".
- Komunikat "Brak prognozy dla wybranego horyzontu — zwiększ horyzont" w zakładce Predykcja jest mylący: zwiększenie horyzontu nie pomaga, gdy prognoza jest przeterminowana. Zmienić treść na "Prognoza jest nieaktualna, uruchom odswiez_prognoze.bat".
- Ostrzeżenie `use_container_width` w aplikacji: zastąpić `width="stretch"`, bo parametr został usunięty po 2025-12-31.

## Testy

- Dopisać test przeglądarkowy (Edge bez okna przez `playwright-core`), który otwiera panel i sprawdza, że pojawia się tekst "SmogGuardAI" oraz brak błędów w konsoli.

## Sprzedaż i monetyzacja

- Model płatności (jednorazowo, subskrypcja, licencje szkolne), konta i logowanie, ochrona przed kopiowaniem, regulamin i polityka prywatności (RODO), sklep Google Play, hosting i domena, wsparcie klienta: do zaplanowania.
