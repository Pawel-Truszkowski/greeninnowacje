# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Green Innowacje — a tree-watering monitoring app (volunteers water newly planted trees; statuses driven by rainfall data). The MVP is being built as a **Django 5.2 + DRF + PostgreSQL 16** app (Python 3.14, uv), headed for production. Language convention: **branch names, commit messages, code comments and docstrings in English**; user-facing strings (UI copy, e-mails, `verbose_name`, validation/error messages shown to users) and project docs (`README.md`, `docs/`) in Polish, positive tone (e.g. „Dziękujemy! Drzewo zostało podlane 🌱").

- `docs/ROADMAP.md` — agreed implementation plan: milestones M1–M4 with checkboxes, stack decisions, open questions. Check it before starting work and tick items off as they land.
- `spec/` and `poc/` are **gitignored** (local only) — never import from them at runtime.
  - `spec/Specyfikacja_Wykonawcza_MVP_…md` is the contract: DB schema (§3), REST API (§4), integrations (§5), cron + **status algorithm pseudocode (§6.2)**, security checklist (§7), required tests (§9). Its suggested stack is replaced by Django, but §3–7 still apply.
  - `spec/Dokument_UI_…md` — screens, status system, accessibility, microcopy. PDFs 1A2/1A5/1A7 describe Etap 2 features, not MVP.
  - `poc/` — static clickable mockup (open `poc/index.html`); source of the visual design (`poc/assets/styles.css`) to port into Django templates.

## How we work (since 2026-09-23)

1. **Plan first.** One small feature per cycle: enter plan mode, present the plan (goal, files, contract, acceptance criteria, tests), wait for approval.
2. **Paweł writes the implementation**; Claude reviews it — correctness, spec conformance, security — explains every finding and applies only the fixes he accepts.
3. Claude may write tests, scaffolding and fixes on request, and always explains what changed and why.

Roadmap progress is tracked with checkboxes in `docs/ROADMAP.md`.

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

Scheduled jobs live in `deploy/crontab`, run by a `supercronic` container (`cron` service, same image as the app, `TZ` from the environment). `core/tests/test_crontab.py` ties the schedule to the code — a renamed management command fails the suite instead of failing silently every morning.

Dependencies live in `pyproject.toml` / `uv.lock` (no requirements.txt). CI: `.github/workflows/ci.yml` (ruff, migration check, pytest on Postgres). **A push to `main` deploys**: after the tests, the same workflow builds the image to GHCR and restarts the demo server over SSH (`docker-compose.prod.yml`, `APP_IMAGE=…:sha-<commit>`); secrets live in the GitHub environment `production`, setup steps in `README.md` → „Wdrożenie”.

## Architecture

Single settings module `config/settings.py`, fully env-driven via django-environ (`.env.example` documents every variable). Apps:

- `accounts` — custom `User` (UUID pk, `email` as login stored lowercase, `display_name`, `role` volunteer/admin). **App permissions come from `role`** (`user.is_app_admin`); `is_staff`/`is_superuser` only gate the technical Django admin. Role checks live in `accounts/permissions.py` (`IsVolunteer`/`IsAppAdmin` for DRF, `app_admin_required` for views). Auth has HTML pages (`views.py`: `/logowanie`, `/rejestracja`, `/wyloguj`) and JSON endpoints (`api.py`: `/api/auth/*`) sharing the same forms (`RegistrationForm`, `LoginForm`); the JSON ones are plain Django views, not DRF, so CSRF is enforced for anonymous users too (login CSRF).
- `core` — `Config` key/value table holding drought thresholds (seeded by migration); read them via `load_drought_config()` → `DroughtConfig`. Also the `seed_demo` command and **rate limiting**: `core/ratelimit.py` (`@rate_limit(group, rate, key="ip"|"user")` sets `request.limited`; atomic counters in PostgreSQL, no Redis) with the real client IP from `core/net.py` (`TRUSTED_PROXY_HOPS`).
- `trees` — `Locality`, `Tree` (UUID pk = permanent public URL), `Watering`, `Assignment`. Write operations live in `trees/services.py` (watering, caretaker assignment, `register_tree`, `recompute_tree_status`) — HTML views and API views both call these, so invariants cannot drift between entry points. The drought algorithm is a pure function in `trees/status.py` (no DB access; spec §6.2). Two rules worth knowing: **planting counts as a watering** (`planted_on` is a wet day — trees are watered when planted), and a tree stays out of URGENT for `DAYS_SOON` days after registration (`in_registration_grace`), so adding an older tree doesn't raise a false alarm. Registration (`register_tree`) resolves the locality (volunteer's name > Nominatim in `trees/nominatim.py` > error asking for one) and rejects a tree within 2 m via `find_duplicate` unless `force` is set; distances come from `trees/geo.py` (bbox prefilter in SQL + haversine in Python, no PostGIS). Read queries live in `trees/selectors.py`: **`public_tree_card()` is the single definition of what an anonymous visitor may see** (watering history as dates only, caretaker as a bool) and feeds both the HTML card and `/api/trees/{id}/public` — extend it there, never in a view. `extended_tree_card()` is the logged-in variant and the only place volunteer names join tree data. Status label/hint/icon come from `trees/status_display.py` (template tag `{% status_badge %}`, and the map script via `json_script`).
- `weather` — `WeatherDaily` (one row per locality/day; a missing row is NOT 0 mm).
- `notifications` — `EmailLog` (basis for the max-1-email-per-day rule).
- `panel` — the app's own admin panel at `/admin/*` (stats, trees, users, drought thresholds) plus `/api/admin/*`. Pages use `app_admin_required`, API uses `IsAppAdmin`; forms in `panel/forms.py` are shared by both, so validation cannot drift. An admin cannot demote or deactivate their own account.

Invariants enforced in the data layer — keep them:
- `waterings` is **append-only**: ORM `save`/`delete`/queryset `update`/`delete` raise `AppendOnlyError`, and a PostgreSQL trigger (migration `trees/0002`) blocks UPDATE/DELETE even from raw SQL.
- At most one active caretaker per tree: partial unique constraint `one_active_per_tree` (`ended_at IS NULL`).
- Trees are never deleted — `lifecycle='archived'`. FKs to trees/users use `PROTECT`.
- DB table names match the spec (`db_table = "users"`, `"trees"`, …).

URLs: `/admin/*` is reserved for the app's own admin panel (spec §4); the Django admin lives at `DJANGO_ADMIN_URL` (default `django-admin/`). DRF defaults are secure-by-default (`IsAuthenticated`, session auth + CSRF); public endpoints must opt in with `AllowAny`.

Front-end: only the map runs JavaScript (`static/js/map.js`, fed by `/api/trees`); everything else is server-rendered. Values coming from the API go into the DOM via `textContent` — never `innerHTML` — because species/notes are user input. Charts use SVG geometry instead of `style=` so a strict CSP stays possible.

Templates: `templates/base.html` (header/nav, server-rendered toast from `messages`), `templates/includes/` form partials; CSS `static/css/app.css` ported from the PoC, font and libraries vendored under `static/` (no CDNs, no inline `style=`/`<script>` — keeps a strict CSP possible).

Tests: pytest-django; **`accounts/tests/test_authz_matrix.py` holds the endpoint × role matrix — every new endpoint must get a row there**; shared factory_boy factories in root `factories.py` (`TEST_PASSWORD`), fixtures in root `conftest.py`; per-app tests in `<app>/tests/`. External APIs (Open-Meteo, Nominatim) must be mocked (`respx`); `trees/tests/test_registration.py` stubs `trees.services.reverse_locality` by default and exercises the real client in exactly one test.

## Rules that shape the UI (from the specs)

- Status is always **color + icon + text** (never color alone). Touch targets ≥ 44 px, mobile-first.
- Public endpoints/screens (map, QR tree card) expose no personal data — watering history shows dates only; there is a required test for this.
- MVP roles: volunteer + admin only. Coordinator, photos, in-app/push notifications, offline mode are Etap 2.
- Spec bans for the MVP: Google Maps/Mapbox, OpenWeatherMap, paid APIs, Service Worker/offline, file upload, Web Push. Map = Leaflet + markercluster (served from `static/`, no CDN — CSP); weather = Open‑Meteo; reverse geocoding = Nominatim.
