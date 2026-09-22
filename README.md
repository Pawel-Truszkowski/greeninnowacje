# Green Innowacje — monitorowanie podlewania drzew

Aplikacja webowa dla wolontariuszy opiekujących się młodymi drzewami: mapa drzew, karta drzewa
z kodem QR, oznaczanie podlania i automatyczny status suszy na podstawie pogody.

Stack: Django 5.2 + DRF, PostgreSQL 16, Python 3.14, uv. Plan prac: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Uruchomienie lokalne (Docker)

```bash
cp .env.example .env            # uzupełnij DJANGO_SECRET_KEY
docker compose up               # baza + aplikacja, migracje wykonują się automatycznie
docker compose exec app python manage.py seed_demo   # dane demo (2 miejscowości, 14 drzew)
```

- Aplikacja: http://localhost:8000
- Django admin: http://localhost:8000/django-admin/ (ścieżka z `DJANGO_ADMIN_URL`)
- Konta demo: `admin@przyklad.pl` (administrator), `anna.k@przyklad.pl` (wolontariuszka) i inne
  wypisane przez `seed_demo`; hasło `podlewamy-drzewa`.

## Praca bez Dockera dla aplikacji

Baza nadal z Compose (`docker compose up -d db`, port 5433 na hoście), reszta przez uv:

```bash
uv sync                                    # zależności + dev (pytest, ruff)
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest                              # wszystkie testy (wymagają PostgreSQL)
uv run pytest trees/tests/test_models.py::TestWateringAppendOnly   # pojedynczy test/klasa
uv run ruff check . && uv run ruff format .
```

## Konfiguracja

Wszystkie zmienne środowiskowe opisuje [`.env.example`](.env.example). Progi suszy nie są
zmiennymi środowiskowymi — są w tabeli `config` (edytowalne przez administratora).
