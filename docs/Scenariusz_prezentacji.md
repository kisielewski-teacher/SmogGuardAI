# Scenariusz prezentacji SmogGuardAI (10 minut) i lista kontrolna

Podział ról dla zespołu zostawiamy do ustalenia; poniżej czas, treść i co pokazać na ekranie.

## Plan wystąpienia

| Czas | Temat | Co mówimy | Co pokazujemy |
| --- | --- | --- | --- |
| 0:00–1:00 | Problem | Smog (pył PM10) szkodzi zdrowiu; chcemy wiedzieć dzień wcześniej, kiedy będzie gorzej. | Panel, zakładka „Predykcja”: kolor godzin wg norm GIOŚ |
| 1:00–2:30 | Dane | Oficjalna stacja GIOŚ w Słupsku od 2022 roku (prawie 40 tys. godzin) i pogoda IMGW. Dane są publiczne i weryfikowalne. Stacja miała awarie, więc nie „sklejamy” brakujących godzin. | Zakładka „Historia PM” |
| 2:30–4:30 | Uczciwy test | Model uczy się na danych do końca 2025, a sprawdzamy go na 2026, którego nie widział. Punkt odniesienia to zgadywanie „bez zmian”. | `docs/wykres_porownanie_metod.png` (szara linia) |
| 4:30–6:30 | Nowa metoda | Stara metoda to „głuchy telefon”: błąd rośnie w pętli 72 godzin. Nowa uczy osobny model na każdą godzinę. Na 72 h błąd spadł z 6,7 do 5,9 µg/m³. | Ten sam wykres, zielona linia; zakładka „Dokładność prognozy” |
| 6:30–7:30 | Wiatr | Dane pokazują, że smog niesie wiatr znad lądu; znad morza jest czysto. Model używa kierunku wiatru. | **Na żywo:** zakładka „Róża wiatrów”, przełącz „Sezon grzewczy” |
| 7:30–8:30 | Niepewność | Jedna liczba kłamie, więc pokazujemy pas: z ok. 80% szansą wartość będzie w nim. W teście trafiał 78% pomiarów. Jest szeroki, bo smog jest trudny do przewidzenia. | Zakładka „Predykcja”, zielony pas |
| 8:30–9:30 | Co nie wyszło | Prognoza pogody, sąsiednie stacje i mieszanie metod nie poprawiły wyników, więc ich nie wdrożyliśmy. Sprawdzamy pomysł, zanim go zbudujemy. | `docs/Jak_poprawilismy_prognoze.md`, rozdziały 9, 11, 12 |
| 9:30–10:00 | Wnioski | Prognoza o 21–26% lepsza od zgadywania, z uczciwym przedziałem. Dalej: kolejna zima testów, więcej danych. | Streszczenie 1-stronicowe |

## Najtrudniejsze pytania i krótkie odpowiedzi

- **Skąd wiecie, że nie oszukujecie?** Model nie widział danych testowych (od 1.01.2026), a porównujemy
  go na tych samych godzinach z prostym zgadywaniem „bez zmian”.
- **Dlaczego błąd to nadal ok. 6 µg/m³?** Smog zależy od wiatru, inwersji i palenisk, a mamy jedną
  stację. Błąd rośnie z horyzontem i pokazujemy to otwarcie.
- **Czy nowa metoda jest zawsze lepsza?** Nie: na +12 godzin stara, uczona na krótszej historii, była
  wiarygodnie lepsza. Łącznie i na 72 h wygrywa nowa.
- **Dlaczego nie użyliście prognozy pogody?** Sprawdziliśmy: nawet idealna prognoza nie poprawiła
  wyniku (rozdział 11 dokumentu).
- **Czy można tego używać do decyzji zdrowotnych?** To narzędzie informacyjne; obowiązują komunikaty GIOŚ
  i porada lekarza.
- **Skąd dane i czy wolno ich użyć?** GIOŚ i IMGW to dane publiczne; trzeba podać źródło. Przy sprzedaży
  sprawdzimy licencje (patrz `THIRD_PARTY_LICENSES.md`).

## Dzień przed prezentacją

- Uruchom `SmogGuardAI\run_full_pipeline.bat` (około 3 minuty) i poczekaj na komunikat o zakończeniu.
- Uruchom `SmogGuardAI\demo_check.bat` i napraw wszystko, co ma status `[FAIL]`.
- Uruchom `SmogGuardAI\run_tests.bat` (około minuty); wszystkie testy mają przejść.
- Przećwicz wystąpienie z zegarem; zmieść się w 10 minutach.
- Wydrukuj `docs/Streszczenie_dla_komisji.md` (1 strona) dla komisji.

## 30 minut przed

- Podłącz laptop do zasilania, wyłącz uśpienie ekranu i powiadomienia.
- Uruchom `run_pipeline_scheduled.bat` (około 2 minuty), żeby dane były świeże, potem `demo_check.bat`.
- Otwórz panel (http://localhost:8501), sprawdź zakładki „Predykcja”, „Dokładność prognozy”, „Róża wiatrów”.
- Otwórz w drugim oknie wykresy z `docs/` na wypadek problemu z panelem.

## Plan awaryjny

- **Brak internetu:** panel działa na zapisanych danych; powiedz, że dane na żywo odświeżają się
  tylko przy połączeniu.
- **Panel się nie uruchamia:** w katalogu `SmogGuardAI` wpisz `py -m streamlit run app/app_extended_multi.py`,
  a gdy to nie pomoże, pokaż wykresy z `docs/` i dokument `Jak_poprawilismy_prognoze.md`.
- **Dane nieświeże:** uruchom `run_pipeline_scheduled.bat`; gdy brak czasu, powiedz, jak stare są
  dane (panel pokazuje godzinę ostatniego pomiaru).
- **Pytanie, na które nie znasz odpowiedzi:** powiedz „tego nie sprawdziliśmy” i wskaż, jak byśmy to
  zbadali. Dokument pokazuje, że tak właśnie pracujemy.
