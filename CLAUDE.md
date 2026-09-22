# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Green Innowacje — a tree-watering monitoring app (volunteers water newly planted trees; statuses driven by rainfall data). The MVP is being built as a **Django 5.2 + DRF + PostgreSQL 16** app (Python 3.14, uv), headed for production. Language convention: **branch names, commit messages, code comments and docstrings in English**; user-facing strings (UI copy, e-mails, `verbose_name`, validation/error messages shown to users) and project docs (`README.md`, `docs/`) in Polish, positive tone (e.g. „Dziękujemy! Drzewo zostało podlane 🌱").

- `docs/ROADMAP.md` — agreed implementation plan: milestones M1–M4 with checkboxes, stack decisions, open questions. Check it before starting work and tick items off as they land.
- `spec/` and `poc/` are **gitignored** (local only) — never import from them at runtime.
  - `spec/Specyfikacja_Wykonawcza_MVP_…md` is the contract: DB schema (§3), REST API (§4), integrations (§5), cron + **status algorithm pseudocode (§6.2)**, security checklist (§7), required tests (§9). Its suggested stack is replaced by Django, but §3–7 still apply.
  - `spec/Dokument_UI_…md` — screens, status system, accessibility, microcopy. PDFs 1A2/1A5/1A7 describe Etap 2 features, not MVP.
  - `poc/` — static clickable mockup (open `poc/index.html`); source of the visual design (`poc/assets/styles.css`) to port into Django templates.

## Commands

```bash
docker compose up                                   # db + app (runserver), migrations run on start
docker compose exec app python manage.py seed_demo  # demo data; refuses unless DEBUG (or --force)
docker compose up -d db                             # only Postgres, on host port 5433 (.env points there)
uv sync                                             # deps incl. dev group
uv run pytest                                       # tests need PostgreSQL (DB trigger, partial indexes)
uv run pytest trees/tests/test_models.py::TestWateringAppendOnly
uv run ruff check . && uv run ruff format .
uv run python manage.py makemigrations --check --dry-run   # CI fails on missing migrations
```

Dependencies live in `pyproject.toml` / `uv.lock` (no requirements.txt). CI: `.github/workflows/ci.yml` (ruff, migration check, pytest on Postgres).

## Architecture

Single settings module `config/settings.py`, fully env-driven via django-environ (`.env.example` documents every variable). Apps:

- `accounts` — custom `User` (UUID pk, `email` as login stored lowercase, `display_name`, `role` volunteer/admin). **App permissions come from `role`** (`user.is_app_admin`); `is_staff`/`is_superuser` only gate the technical Django admin.
- `core` — `Config` key/value table holding drought thresholds (seeded by migration); read them via `load_drought_config()` → `DroughtConfig`. Also the `seed_demo` command.
- `trees` — `Locality`, `Tree` (UUID pk = permanent public URL), `Watering`, `Assignment`.
- `weather` — `WeatherDaily` (one row per locality/day; a missing row is NOT 0 mm).
- `notifications` — `EmailLog` (basis for the max-1-email-per-day rule).

Invariants enforced in the data layer — keep them:
- `waterings` is **append-only**: ORM `save`/`delete`/queryset `update`/`delete` raise `AppendOnlyError`, and a PostgreSQL trigger (migration `trees/0002`) blocks UPDATE/DELETE even from raw SQL.
- At most one active caretaker per tree: partial unique constraint `one_active_per_tree` (`ended_at IS NULL`).
- Trees are never deleted — `lifecycle='archived'`. FKs to trees/users use `PROTECT`.
- DB table names match the spec (`db_table = "users"`, `"trees"`, …).

URLs: `/admin/*` is reserved for the app's own admin panel (spec §4); the Django admin lives at `DJANGO_ADMIN_URL` (default `django-admin/`). DRF defaults are secure-by-default (`IsAuthenticated`, session auth + CSRF); public endpoints must opt in with `AllowAny`.

Tests: pytest-django; shared factory_boy factories in root `factories.py` (`TEST_PASSWORD`), fixtures in root `conftest.py`; per-app tests in `<app>/tests/`. External APIs (Open-Meteo, Nominatim) must be mocked (`respx`).

## Rules that shape the UI (from the specs)

- Status is always **color + icon + text** (never color alone). Touch targets ≥ 44 px, mobile-first.
- Public endpoints/screens (map, QR tree card) expose no personal data — watering history shows dates only; there is a required test for this.
- MVP roles: volunteer + admin only. Coordinator, photos, in-app/push notifications, offline mode are Etap 2.
- Spec bans for the MVP: Google Maps/Mapbox, OpenWeatherMap, paid APIs, Service Worker/offline, file upload, Web Push. Map = Leaflet + markercluster (served from `static/`, no CDN — CSP); weather = Open‑Meteo; reverse geocoding = Nominatim.
