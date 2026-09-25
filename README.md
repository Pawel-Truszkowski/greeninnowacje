# Green Innowacje — monitorowanie podlewania drzew

Aplikacja webowa dla wolontariuszy opiekujących się młodymi drzewami. Publiczna mapa nasadzeń,
karta drzewa dostępna po zeskanowaniu kodu QR, oznaczanie podlania jednym kliknięciem
i automatyczny status suszy liczony z pogody oraz historii podlewań.

**Stack:** Python 3.14, Django 5.2 LTS + DRF, PostgreSQL 16, Leaflet. Zależności: uv.
**Plan prac:** [`docs/ROADMAP.md`](docs/ROADMAP.md) · **Wskazówki dla Claude Code:** [`CLAUDE.md`](CLAUDE.md)

## Uruchomienie (Docker)

```bash
cp .env.example .env                    # uzupełnij DJANGO_SECRET_KEY
docker compose up                       # baza + aplikacja, migracje wykonują się same
docker compose exec app python manage.py seed_demo
```

- Aplikacja: http://localhost:8000
- Django admin (techniczny): http://localhost:8000/django-admin/ — ścieżkę ustawia `DJANGO_ADMIN_URL`
- Konta demo (hasło `podlewamy-drzewa`): `admin@przyklad.pl` (administrator),
  `anna.k@przyklad.pl`, `piotr.n@przyklad.pl`, `marta.w@przyklad.pl` (wolontariusze)

Dane demo to 2 miejscowości (Sierpc, Studzieniec), 14 drzew z historią podlewań i 14 dni pogody.
Daty liczone są względem dnia uruchomienia, więc demo zawsze wygląda aktualnie.

## Ścieżka demonstracyjna

1. **Mapa** (`/`) — pinezki w kolorach statusów, klastrowanie, filtry po statusie i miejscowości.
2. **Karta drzewa** (`/drzewo/<uuid>`) — to samo, co zobaczy ktoś po zeskanowaniu kodu QR:
   status, historia podlewań (same daty), wykres opadów z 14 dni, kod QR do pobrania.
3. **Logowanie** (`/logowanie`) — trzy pola, konto zakłada się w minutę.
4. **Karta po zalogowaniu** — przycisk „Oznacz jako podlane”, imiona podlewających,
   zgłoszenie się do opieki. Status przelicza się natychmiast po podlaniu.
5. **Moje drzewa** (`/moje-drzewa`) — lista od najpilniejszych, podlanie prosto z listy.
6. **Rejestracja drzewa** (`/rejestracja-drzewa`) — lokalizacja z GPS z korektą pinezki,
   wykrywanie duplikatu bliżej niż 2 m, kod QR na karcie nowego drzewa.

## Zadania cykliczne

Kontener `cron` (ten sam obraz co aplikacja, uruchamiany przez `supercronic`) wykonuje
harmonogram z [`deploy/crontab`](deploy/crontab) w czasie polskim:

| Godzina | Zadanie |
|---|---|
| 05:00 | `fetch_weather` — opady z Open-Meteo dla każdej miejscowości |
| 07:00 | `recompute_statuses` — statusy suszy dla aktywnych drzew |

```bash
docker compose logs -f cron                                   # podgląd przebiegów
docker compose exec app python manage.py fetch_weather --days 5   # ręczne uruchomienie
docker compose exec app python manage.py recompute_statuses --dry-run   # bez zapisu
```

Godzinami steruje zmienna `TZ`. Zadania celowo nie wykonują migracji — robi to usługa
`app` przy starcie.

## Praca bez Dockera

Baza nadal z Compose (port 5433 na hoście), reszta przez uv:

```bash
docker compose up -d db
uv sync                                    # zależności wraz z deweloperskimi
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
```

## Testy i jakość

```bash
uv run pytest                                      # cały zestaw (wymaga PostgreSQL)
uv run pytest trees/tests/test_status.py -q        # jeden plik
uv run pytest -k "duplicate" -q                    # testy pasujące do wzorca
uv run ruff check . && uv run ruff format .
uv run python manage.py makemigrations --check --dry-run
```

CI (`.github/workflows/ci.yml`) uruchamia lint, kontrolę kompletności migracji i testy
na PostgreSQL przy każdym pushu.

## Konfiguracja

Wszystkie zmienne opisuje [`.env.example`](.env.example). Warto zwrócić uwagę na:

| Zmienna | Znaczenie |
|---|---|
| `MAP_TILES_URL` | Szablon adresu kafelków z `{z}/{x}/{y}`. Domyślnie OSM Deutschland; na produkcji MapTiler z kluczem ograniczonym do domeny. Adres bez tych trzech znaczników jest odrzucany przy starcie (kontrola `core.E001`) |
| `TRUSTED_PROXY_HOPS` | Liczba zaufanych proxy przed aplikacją (1 za Caddy). Decyduje, skąd brane jest IP klienta do limitów prób logowania |
| `DJANGO_ADMIN_URL` | Ścieżka technicznego Django admina — `/admin/` jest zarezerwowane dla panelu aplikacji |
| `NOMINATIM_USER_AGENT` | Wymagana przez OSM identyfikacja aplikacji przy geokodowaniu |

Progi suszy **nie są** zmiennymi środowiskowymi — mieszkają w tabeli `config` i będą
edytowalne z panelu administratora.

## Jak to działa w środku

- `trees/status.py` — algorytm statusu jako czysta funkcja (bez bazy danych), zgodny z §6.2
  specyfikacji. Posadzenie liczy się jako podlanie, a świeżo zarejestrowane drzewo ma kilka dni
  karencji, zanim może trafić do „pilnie podlać”.
- `trees/services.py` — operacje zapisu: podlanie, opieka, rejestracja drzewa. Widoki HTML i API
  wołają te same funkcje, więc reguły nie rozjeżdżają się między wejściami.
- `trees/selectors.py` — zapytania odczytu. `public_tree_card()` jest jedynym miejscem
  definiującym, co widzi niezalogowany gość (historia bez imion, opiekun jako tak/nie).
- Historia podlewań jest **tylko do dopisywania** — pilnuje tego zarówno ORM, jak i trigger
  w PostgreSQL.

## Stan prac

Etap M1 (pionowy przekrój aplikacji) zamknięty: konta i uprawnienia, mapa publiczna, karta
drzewa z kodem QR, podlewanie, opieka nad drzewem i rejestracja drzew w terenie. 283 testy.
Kolejne etapy — integracja z Open-Meteo i zadania cykliczne, powiadomienia e-mail, panel
administratora, eksport CSV i wdrożenie produkcyjne — opisuje [`docs/ROADMAP.md`](docs/ROADMAP.md).
