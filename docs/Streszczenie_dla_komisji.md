# SmogGuardAI — streszczenie dla komisji (1 strona)

## Co zrobiliśmy

**SmogGuardAI** przewiduje **stężenie pyłu PM10 w Słupsku na najbliższe 72 godziny** i pokazuje je
w panelu w przeglądarce razem z **przedziałem niepewności** (pas, w którym z prawdopodobieństwem
ok. 80% znajdzie się rzeczywista wartość). Panel działa na rzeczywistych, publicznych danych:
pomiary stacji **GIOŚ** (ul. Kniaziewicza) od 2022 roku (prawie 40 tysięcy godzin) i pogoda **IMGW**
(w tym kierunek wiatru).

## Najważniejsze wyniki (test na danych z 2026 roku, których modele nie widziały)

| Za ile godzin | Zgadywanie „bez zmian” | Nasz model | Poprawa |
| --- | --- | --- | --- |
| 24 | 7,05 µg/m³ | **5,58** | o 21% |
| 72 | 7,96 µg/m³ | **5,87** | o 26% |

Błąd = średnie odchylenie prognozy od pomiaru. Zgadywanie „bez zmian” to punkt odniesienia:
model musi je pokonać, inaczej nie ma sensu. Panel pokazuje te liczby na żywo (zakładka
„Dokładność prognozy”); wartości mogą różnić się o 0,1–0,2 µg/m³, bo okno testowe się przesuwa.

## Co poprawiło prognozę (sprawdzone testem)

- **Więcej lat danych** (4 lata zamiast 10 miesięcy) i naprawa błędu w danych IMGW z 2024 roku.
- **Nowa metoda:** osobny model na każdą godzinę prognozy zamiast pętli, w której błędy się kumulują
  (na 72 h błąd spadł z 6,7 do 5,9 µg/m³).
- **Kierunek wiatru:** smog jest najwyższy, gdy wieje znad lądu (południe, wschód), najniższy znad
  Bałtyku. Panel ma „różę wiatrów” na żywych danych.

## Co sprawdziliśmy i odrzuciliśmy (to też wynik)

Idealna prognoza pogody, dane z sąsiednich stacji (Koszalin, Gdynia…) oraz mieszanie metod **nie
poprawiły** wyników w uczciwym teście, więc ich nie wdrożyliśmy.

## Uczciwość i ograniczenia

- Oceniamy **poza próbą**: model uczy się na starszych danych, a błąd mierzymy na późniejszych.
- Przedział 80% w teście trafił w **78%** pomiarów; jest szeroki (ok. 17 µg/m³), bo smogu z jednej
  stacji nie da się dokładnie przewidzieć.
- Test obejmuje **jeden sezon**; wynik warto potwierdzić po następnej zimie. Brakuje pogody za
  październik 2026 (IMGW jeszcze jej nie opublikował).
- To narzędzie informacyjne, nie zastępuje komunikatów GIOŚ ani porady lekarza.

## Jak to sprawdzić

Pełny opis i wykresy: `docs/Jak_poprawilismy_prognoze.md`. Uruchomienie programu:
`SmogGuardAI\run_full_pipeline.bat`; kontrola gotowości: `SmogGuardAI\demo_check.bat`; testy:
`SmogGuardAI\run_tests.bat`. Źródła danych: GIOŚ (`powietrze.gios.gov.pl`), IMGW-PIB (`danepubliczne.imgw.pl`).
