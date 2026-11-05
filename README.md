# GREENowacje — monitorowanie podlewania drzew

Aplikacja webowa dla wolontariuszy opiekujących się młodymi drzewami. Publiczna mapa nasadzeń,
karta drzewa dostępna po zeskanowaniu kodu QR, oznaczanie podlania jednym kliknięciem
i automatyczny status suszy liczony z pogody oraz historii podlewań.

**Wersja:** 2.0.0 („Prototyp drugi”) — historia zmian w [`CHANGELOG.md`](CHANGELOG.md).
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
7. **Osiągnięcia** (`/osiagniecia`) — poziom (🌰 Nasiono → 🌲 Dąb), odznaki i ranking
   wolontariuszy z 30 dni (tylko po zalogowaniu).
8. **Baza wiedzy** (`/baza-wiedzy`) — opisy gatunków z infografikami, poradniki sadzenia
   i pielęgnacji, film instruktażowy. Publiczna; karta drzewa linkuje do opisu swojego gatunku.

## Panel administratora

Pod `/admin/` (konto z rolą administratora — w danych demo `admin@przyklad.pl`):

| Zakładka | Zawartość |
|---|---|
| Statystyki | drzewa per status i miejscowość, podlania z 7 i 30 dni, aktywni wolontariusze, drzewa bez opiekuna; karta „O aplikacji” (wersja, commit, data zbudowania) z linkiem do „Co nowego” (`/admin/wersja`) |
| Drzewa | filtry, edycja danych, archiwizacja i przywracanie (drzew nie usuwamy) |
| Użytkownicy | rola i aktywność konta, ostatnie logowanie, liczba drzew zarejestrowanych i pod opieką; na stronie osoby — lista jej drzew i wcześniejsza opieka. Własnego konta nie można zdegradować ani wyłączyć |
| Progi suszy | wartości z tabeli `config` + przycisk „Przelicz statusy teraz” |
| Zdjęcia | moderacja zdjęć drzew dodanych przez wolontariuszy |
| Gatunki | opisy gatunków w Bazie wiedzy: dodawanie, edycja, ukrywanie; infografika i zdjęcie (PNG/JPEG) zapisywane jako JPEG, zdjęcie przycinane do kadru 4:5 |
| Aktywność | logowania, nowe konta, działania przy drzewach i otwarcia karty z QR — kafelki 7/30 dni, wykres dzienny, tabela osób. Bez adresów IP |
| Eksport | CSV (drzewa, podlania, pogoda, aktywność) gotowe do otwarcia w polskim Excelu |

Techniczny Django admin (dla programisty) żyje osobno, pod `DJANGO_ADMIN_URL`.

## Zadania cykliczne

Kontener `cron` (ten sam obraz co aplikacja, uruchamiany przez `supercronic`) wykonuje
harmonogram z [`deploy/crontab`](deploy/crontab) w czasie polskim:

| Godzina | Zadanie |
|---|---|
| 03:30 | `prune_activity` — usuwa wpisy aktywności starsze niż `ACTIVITY_RETENTION_DAYS` (RODO) |
| 05:00 | `fetch_weather` — opady z Open-Meteo dla każdej miejscowości |
| 07:00 | `recompute_statuses` — statusy suszy dla aktywnych drzew |
| 07:30 | `send_digests` — e-maile o drzewach do podlania (najwyżej 1 dziennie na osobę) |

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
| `ACTIVITY_RETENTION_DAYS` | Ile dni trzymamy dziennik aktywności (domyślnie 365) |

Progi suszy **nie są** zmiennymi środowiskowymi — mieszkają w tabeli `config` i edytuje się
je w panelu administratora (zakładka „Progi suszy”).

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
- `gamification/rules.py` — punkty, poziomy i odznaki jako czyste funkcje. Liczone z tabel
  domenowych (podlania, drzewa, opieka), nie z dziennika aktywności, który jest czyszczony
  po roku — dzięki temu poziom nigdy nie spada.
- `activity/services.record()` — jedyne miejsce zapisu dziennika aktywności. Działania przy
  drzewach zapisują się w tej samej transakcji co sama operacja, więc odrzucona operacja
  nie zostawia śladu.
- `core/version.py` — numer wersji z `pyproject.toml` i notatki z `CHANGELOG.md`; strona
  „Co nowego” w panelu czyta changelog z działającego obrazu.

## Wdrożenie

Instancja demonstracyjna (do testów na telefonie i pokazu) wdraża się sama: każdy commit na
`main`, który przejdzie testy, trafia na serwer. Wdrożenie produkcyjne z backupami i pełnym
utwardzeniem to etap M4.

Jak to działa (`.github/workflows/ci.yml`):

1. **test** — lint, migracje, pytest (jak dla każdej gałęzi).
2. **image** — tylko `main`: GitHub Actions buduje obraz i wysyła go do GitHub Container
   Registry z tagami `sha-<commit>`, `latest` i numerem wersji (np. `2.0.0`). Do obrazu trafia
   też commit i data zbudowania — panel pokazuje je w karcie „O aplikacji”. Serwer (1 GB RAM)
   niczego nie buduje.
3. **deploy** — przez SSH: kopiuje `docker-compose.prod.yml`, pobiera obraz, restartuje `app`
   i `cron`, a na koniec sprawdza, czy strona odpowiada. Migracje i pliki statyczne wykonują się
   przy starcie kontenera ([`deploy/entrypoint.sh`](deploy/entrypoint.sh)). Plik `.env` i baza
   na serwerze nie są ruszane.
4. **release** — gdy wersja w `pyproject.toml` jest nowa: tag `v<wersja>` i GitHub Release
   z opisem zmian z [`CHANGELOG.md`](CHANGELOG.md). Dla już wydanej wersji nic nie robi.

Ponowne wdrożenie bez nowego commita: zakładka **Actions → CI → Run workflow** (gałąź `main`).
Powrót do poprzedniej wersji — na serwerze, z tagiem wcześniejszego commita:

```bash
APP_IMAGE=ghcr.io/pawel-truszkowski/greeninnowacje:sha-1a2b3c4 \
  docker compose -f docker-compose.prod.yml up -d --no-build
```

### Wydanie nowej wersji

Numer wersji ma postać `X.Y.Z`: **X** to prototyp uzgodniony z Greenowacjami (2 — „Prototyp
drugi”), **Y** rośnie przy nowych funkcjach, **Z** przy poprawkach. Jedynym źródłem numeru jest
`version` w `pyproject.toml`; stopka aplikacji pokazuje go wszystkim.

1. Podnieś `version` w `pyproject.toml` i uruchom `uv lock` (wersja jest też w `uv.lock`).
2. Dopisz na górze `CHANGELOG.md` sekcję `## [X.Y.Z] — RRRR-MM-DD` — prostym językiem, dla
   Greenowacji, nie dla programistów.
3. Otwórz PR. Po scaleniu do `main` CI wdroży wersję, otaguje ją i opublikuje Release.

Commity bez podniesienia wersji też się wdrażają — wersja zbiera je do najbliższego wydania.
`core/tests/test_versioning.py` pilnuje, żeby numer, `uv.lock` i `CHANGELOG.md` się zgadzały.

### Jednorazowa konfiguracja

**Na serwerze** — katalog z plikiem `.env` (wzór: [`deploy/env.prod.example`](deploy/env.prod.example))
i osobny klucz SSH tylko dla GitHuba:

```bash
ssh-keygen -t ed25519 -N "" -C "github-actions-deploy" -f ~/gh-deploy   # na swoim komputerze
ssh-copy-id -i ~/gh-deploy.pub -p <PORT_SSH> root@srvXX.mikr.us
ssh-keyscan -p <PORT_SSH> srvXX.mikr.us        # odcisk porównaj z tym, który widzisz przy logowaniu
```

**Na GitHubie** — *Settings → Environments → New environment* o nazwie `production`
(w *Deployment branches* zostaw tylko `main`), a w nim:

| Rodzaj | Nazwa | Wartość |
|---|---|---|
| Secret | `SSH_HOST` | np. `srvXX.mikr.us` |
| Secret | `SSH_PORT` | port SSH serwera |
| Secret | `SSH_USER` | np. `root` |
| Secret | `SSH_PRIVATE_KEY` | zawartość `~/gh-deploy` (klucz prywatny) |
| Secret | `SSH_KNOWN_HOSTS` | wynik `ssh-keyscan` |
| Variable | `REMOTE_DIR` | katalog projektu na serwerze, np. `/root/projects/greeninnowacje` |
| Variable | `APP_URL` | adres strony z `https://`, bez ukośnika na końcu |

Obraz w GHCR jest prywatny; serwer pobiera go jednorazowym tokenem zadania i od razu się
wylogowuje, więc żadne hasło do rejestru nie zostaje na serwerze.

## Stan prac

| Etap | Zakres | Stan |
|---|---|---|
| M1 | Konta, mapa publiczna, karta drzewa z QR, podlewanie, opieka, rejestracja w terenie | ✅ 30.09 |
| M2 | Open-Meteo, zadania cykliczne, panel administratora | ✅ 25.09 |
| M3 | Powiadomienia e-mail, eksport CSV | ✅ 29.09 |
| Etap 2 | Koordynator, powiadomienia w aplikacji, zdjęcia drzew, Baza wiedzy z opisami gatunków | ✅ 30.10 (wersja 1.2.0) |
| Prototyp drugi | Grywalizacja, monitoring aktywności, drzewa użytkownika w panelu, wersjonowanie | ✅ 5.11 (wersja 2.0.0) |
| M4 | Utwardzenie produkcyjne, backup, wdrożenie na VPS | w toku — automatyczny deploy wersji demo działa |

1314 testów. Szczegóły i otwarte kwestie: [`docs/ROADMAP.md`](docs/ROADMAP.md).
