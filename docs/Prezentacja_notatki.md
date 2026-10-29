# SmogGuardAI — prezentacja konkursowa — notatki mówcy

Notatki do kolejnych slajdów (czas w nawiasach to propozycja). Plik jest generowany przez
`src/build_presentation.py` z `docs/prezentacja/slajdy/`; edytuj slajdy, nie ten plik.

## Slajd 1: SmogGuardAI

[0:00] Dzień dobry. Przedstawiamy SmogGuardAI, program, który przewiduje stężenie pyłu PM10 w Słupsku na 72 godziny do przodu. Najważniejsze dla nas jest nie to, że prognoza jest dobra, ale że umiemy uczciwie pokazać, jak dobra jest naprawdę. Uzupełnij na slajdzie nazwę konkursu, imiona uczniów, szkołę, opiekuna i datę.

## Slajd 2: Smog szkodzi zdrowiu, więc chcemy znać go dzień wcześniej

[0:15] Pył PM10 to cząstki mniejsze niż 10 mikrometrów, które wnikają w drogi oddechowe. Dobowa norma w Polsce to 50 mikrogramów na metr sześcienny, zalecenie WHO 45. Chcemy wiedzieć dzień wcześniej, kiedy będzie gorzej. Pokazujemy to w panelu, zakładka Predykcja, gdzie godziny są pokolorowane według norm GIOŚ.

## Slajd 3: Uczymy się na prawdziwych, publicznych danych

[1:00] Dane są publiczne i każdy może je sprawdzić. PM10 pochodzi z oficjalnej stacji GIOŚ w Słupsku, prawie 40 tysięcy godzin od 2022 roku. Pogodę bierzemy z IMGW, ze stacji w Ustce, Koszalinie i Chojnicach, razem z kierunkiem wiatru. Stacja miała awarie, na przykład w kwietniu 2023 brakuje większości godzin. Nie wypełniamy tych luk wymyślonymi liczbami, godzina zostaje pusta. W panelu widać to w zakładce Historia PM.

## Slajd 4: Uczciwy test: model sprawdzamy na danych, których nie widział

[2:30] To najważniejszy slajd dla wiarygodności. W uczeniu maszynowym łatwo oszukać samego siebie, sprawdzając model na tych samych danych, na których się uczył. My uczymy go tylko na danych do końca 2025, a sprawdzamy na 2026, którego nigdy nie widział. Porównujemy z najprostszym zgadywaniem: za 24 godziny będzie tak samo jak teraz. Jeśli model tego nie pokona, nie ma sensu. Mamy 477 punktów startowych i test parowy z losowaniem dni, żeby odróżnić prawdziwą poprawę od szumu. Wcześniejszy backtest w panelu, z błędem około 2,7, liczył także dane uczące, więc go nie używamy jako dowodu.

## Slajd 5: Nowa metoda: osobny model na każdą godzinę zamiast pętli

[4:30] Skąd pomysł. Dłuższa historia nie poprawiała starej metody na 24 do 72 godzin, więc problem leżał w metodzie. Stara metoda umie przewidzieć tylko następną godzinę, a 72 godziny buduje w pętli: własna prognoza wraca jako dane do kolejnego kroku, więc błąd się powiela jak w głuchym telefonie. Nowa metoda uczy osobny model dla każdej z 72 godzin, używa algorytmu LightGBM. Na 72 godziny błąd spadł z 6,7 do 5,9 mikrograma, to około 12 procent przy tych samych danych.

## Slajd 6: Prognoza jest o 21–26% lepsza od zgadywania

[5:30] Szara przerywana linia to zgadywanie bez zmian. Pomarańczowa i żółta to stara metoda uczona na 4 latach i na 1 roku. Zielona to nowa metoda. Na 24 godziny błąd spadł z 7,05 do 5,58 mikrograma, czyli o 21 procent, na 72 godziny z 7,96 do 5,87, o 26 procent. Łącznie na wszystkich 72 godzinach nowa metoda jest wiarygodnie lepsza od starej, na 72 godziny wyraźnie. Uczciwie: na 12 godzin stara metoda uczona na krótszej historii była wiarygodnie lepsza. Pokazujemy to w dokumencie. W panelu te liczby są w zakładce Dokładność prognozy i odświeżają się przy każdym pełnym uruchomieniu, mogą się różnić o 0,1 do 0,2.

## Slajd 7: Skąd wieje wiatr, taki jest smog

[6:30] Tu pokaż na żywo panel, zakładka Róża wiatrów, i przełącz na sezon grzewczy. W archiwum IMGW był kierunek wiatru, a my go nie pobieraliśmy. Dane pokazują wyraźną zależność: gdy wiatr wieje znad lądu, z południowego wschodu i południa, zimą średnie PM10 to 21 do 23 mikrogramów. Gdy wieje znad Bałtyku i z północy, około 15. Model używa kierunku wiatru jako dwóch liczb, składowej wschód-zachód i północ-południe, bo kąt 359 i 1 stopień to prawie ten sam kierunek. Poprawa łączna jest mała, około 1,4 procent, ale statystycznie wiarygodna. To zależność, a nie dowód przyczyny, bo wiatr wiąże się też z innymi czynnikami pogody.

## Slajd 8: Zamiast jednej liczby pokazujemy pas niepewności

[7:30] Jedna liczba, na przykład jutro 15 mikrogramów, sugeruje dokładność, której nie ma. Dlatego panel pokazuje zielony pas: z prawdopodobieństwem około 80 procent rzeczywiste PM10 znajdzie się w pasie. Sprawdziliśmy to uczciwie. Surowe modele były zbyt pewne siebie, pas trafiał tylko 74 procent. Dodaliśmy kalibrację i teraz trafia 78 procent, blisko deklarowanych 80. Cena uczciwości jest taka, że pas jest szeroki, średnio około 17 mikrogramów, od około 10 na godzinę do około 18 na 72 godziny. To jest prawdziwy obraz tego, jak trudno przewidzieć smog z jednej stacji. Pokaż na żywo zakładkę Predykcja.

## Slajd 9: Sprawdziliśmy trzy pomysły i ich nie wdrożyliśmy

[8:30] Chcemy pokazać też to, co nie zadziałało, bo tak pracuje się naprawdę. Po pierwsze, prognoza pogody. Podaliśmy modelowi pogodę, która naprawdę wystąpiła, czyli idealną prognozę, i błąd nie spadł. Prawdziwa prognoza byłaby gorsza, więc nie ma sensu jej podłączać. Po drugie, dane z sąsiednich stacji, Koszalina, Kościerzyny, Gdyni i Gdańska, także jako stacja leżąca pod wiatr: nieznacznie gorzej. Słupsk ma w swojej historii większość informacji o tle regionalnym. Po trzecie, mieszanie starej i nowej metody: nie da się wykazać poprawy. Dzięki temu oszczędziliśmy pracę nad elementami, które by nic nie dały. Szczegóły są w rozdziałach 9, 11 i 12 dokumentu.

## Slajd 10: Wnioski i dalsze plany

[9:30] Podsumowanie. Po pierwsze, prognoza na 72 godziny jest o 21 do 26 procent lepsza od prostego zgadywania i ma uczciwy przedział niepewności. Po drugie, każdy wynik sprawdzamy na danych, których model nie widział, także te, które nam nie wyszły. Ograniczenia: test obejmuje jedną zimę, a pogody za październik 2026 jeszcze nie ma, bo IMGW publikuje ją po zakończeniu miesiąca. Wynik potwierdzimy po kolejnej zimie. To narzędzie informacyjne, nie zastępuje komunikatów GIOŚ ani porady lekarza. Dziękujemy. Najtrudniejsze pytania i odpowiedzi są w pliku Scenariusz_prezentacji.md, a pełny opis w Jak_poprawilismy_prognoze.md.
