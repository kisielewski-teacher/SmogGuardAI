# Licencje bibliotek zewnętrznych (third-party)

SmogGuardAI korzysta z następujących bibliotek open-source (patrz `requirements.txt`).
Wszystkie są na licencjach permisywnych, pozwalających na użycie w produkcie
komercyjnym bez obowiązku udostępniania kodu źródłowego SmogGuardAI. Poniższa
lista jest wymagana prawnie (dołączenie informacji o licencji) przy dystrybucji
oprogramowania korzystającego z tych bibliotek.

| Biblioteka | Licencja | Link do licencji |
| --- | --- | --- |
| [requests](https://pypi.org/project/requests/) | Apache License 2.0 | <https://github.com/psf/requests/blob/main/LICENSE> |
| [pandas](https://pypi.org/project/pandas/) | BSD 3-Clause | <https://github.com/pandas-dev/pandas/blob/main/LICENSE> |
| [numpy](https://pypi.org/project/numpy/) | BSD 3-Clause | <https://github.com/numpy/numpy/blob/main/LICENSE.txt> |
| [matplotlib](https://pypi.org/project/matplotlib/) | Matplotlib License (BSD-compatible) | <https://matplotlib.org/stable/users/project/license.html> |
| [seaborn](https://pypi.org/project/seaborn/) | BSD 3-Clause | <https://github.com/mwaskom/seaborn/blob/master/LICENSE.md> |
| [scikit-learn](https://pypi.org/project/scikit-learn/) | BSD 3-Clause | <https://github.com/scikit-learn/scikit-learn/blob/main/COPYING> |
| [python-dateutil](https://pypi.org/project/python-dateutil/) | Apache 2.0 / BSD 3-Clause (dual) | <https://github.com/dateutil/dateutil/blob/master/LICENSE> |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | BSD 3-Clause | <https://github.com/theskumar/python-dotenv/blob/main/LICENSE> |
| [streamlit](https://pypi.org/project/streamlit/) | Apache License 2.0 | <https://github.com/streamlit/streamlit/blob/develop/LICENSE> |
| [plotly](https://pypi.org/project/plotly/) | MIT | <https://github.com/plotly/plotly.py/blob/master/LICENSE.txt> |
| [joblib](https://pypi.org/project/joblib/) | BSD 3-Clause | <https://github.com/joblib/joblib/blob/main/LICENSE.txt> |
| [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) | MIT | <https://www.crummy.com/software/BeautifulSoup/#Download> |
| [pytest](https://pypi.org/project/pytest/) | MIT | <https://github.com/pytest-dev/pytest/blob/main/LICENSE> |
| [pytest-xdist](https://pypi.org/project/pytest-xdist/) | MIT | <https://github.com/pytest-dev/pytest-xdist/blob/master/LICENSE> |
| [lightgbm](https://pypi.org/project/lightgbm/) | MIT | <https://github.com/microsoft/LightGBM/blob/master/LICENSE> |

## Źródła danych (nie są bibliotekami, ale też wymagają atrybucji)

| Źródło | Rodzaj danych | Warunki użycia |
| --- | --- | --- |
| [GIOŚ – EKOINFONET](https://powietrze.gios.gov.pl) | Pomiary zanieczyszczeń (PM10 itd.) | Dane publiczne — reużycie dozwolone pod warunkiem podania źródła: „Źródło danych: GIOŚ – EKOINFONET” |
| [IMGW-PIB](https://danepubliczne.imgw.pl) | Dane pogodowe (stacje synoptyczne) | Dane publiczne — reużycie dozwolone pod warunkiem podania źródła: „Źródło danych: IMGW-PIB” |
| [Syngeos](https://syngeos.pl) | Prywatne czujniki PM2.5/PM10 (widget publiczny) | Dane z publicznie dostępnego widgetu — bez formalnej licencji API; do zweryfikowania z Syngeos przy skalowaniu komercyjnym |

> Atrybucja źródeł danych jest już widoczna w interfejsie aplikacji
> (`app/app_extended_multi.py`, sekcja "Dane rzeczywiste i zweryfikowane" oraz
> "O projekcie — metodologia").

---

*Ten plik należy aktualizować przy każdej zmianie `requirements.txt` (dodaniu/usunięciu zależności).*
