# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Green Innowacje — a tree-watering monitoring app (volunteers water newly planted trees; statuses driven by rainfall data). The repo currently holds **only a clickable proof of concept** for client sign-off of flow and look, plus the specs for the real MVP. All UI copy, code comments and specs are in Polish — keep new copy in Polish, positive tone (e.g. „Dziękujemy! Drzewo zostało podlane 🌱").

- `poc/` — static HTML/CSS/JS mockup, mock data only, no backend, no persistence.
- `spec/` — source of truth for the real product:
  - `Specyfikacja_Wykonawcza_MVP_…md` — stack, env vars, PostgreSQL schema, REST API contract, cron jobs, **status algorithm pseudocode (§6.2)**, security checklist, 5‑week plan, required tests.
  - `Dokument_Architektoniczny_…md` — functional requirements, business rules, conceptual data model, open questions.
  - `Dokument_UI_…md` — personas, site map per role, screen descriptions, status system, accessibility, microcopy.
  - PDFs (1A2, 1A5, 1A7) — demo content, event scenario, tree-planting rollout guide.
- `assets/` — logo source files (the PoC uses its own copy in `poc/assets/logo.png`).

## Running the PoC

No build, no package manager, no tests, no linter. Open `poc/index.html` directly in a browser, or serve statically:

    cd poc && python3 -m http.server 8000

Internet is required (Google Fonts, OSM tiles via unpkg Leaflet, qrcodejs from jsDelivr).

## PoC architecture

Each screen is a standalone HTML page that loads, in order: CDN libs → `assets/data.js` → `assets/app.js` → an inline `<script>` that renders the page (mostly via template strings into `#content`). No modules/bundler — everything is global.

- `assets/data.js` — mock "database": `LOCALITIES`, `WEATHER` (14 days of mm per locality, index 13 = today), `USERS`, `CURRENT_USER` (demo persona = `USERS[0]`), `TREES`, `CONFIG` (drought thresholds, mirrors the spec's `config` table), plus helpers (`getTree`, `getUser`, `getLocality`, `lastWatering`, `queryParam`, `daysAgo`, `fmtDate*`). Dates are stored as **days-ago offsets** (`plantedDaysAgo`, `waterings[].d`) so the demo always looks current — keep that convention.
- `assets/app.js` — shared UI: `STATUS` map + `statusBadge()` / `pinHtml()`, `renderHeader(activeHref)`, `toast()`, `weatherChart()`, and the „🎬 Ekrany demo" panel. `DEMO_SCREENS` is the screen registry — **add new pages there** (grouped as „Zakres MVP" vs „Etap 2").
- `assets/styles.css` — design system; CSS variables in `:root` (brand palette from the logo: `--green-800 #135133`, `--cream #f5efdd`; status colors `--ok/--soon/--urgent` with `-bg` variants).
- Pages take the tree via `?id=t01` (`queryParam('id', 't01')`).
- Tree statuses (`OK` / `SOON` / `URGENT`) are **hardcoded in `TREES`**, not computed; the real algorithm is spec §6.2.

## Rules that shape the UI (from the specs)

- Status is always **color + icon + text** (never color alone). Touch targets ≥ 44 px, mobile-first.
- Public screens (map, `drzewo-public.html` QR card) show no volunteer personal data — watering history shows dates only.
- MVP roles: volunteer + admin only. Out-of-MVP features (tree photos, in-app notifications, coordinator role, offline mode) are shown only on `etap2-*.html` pages / as placeholders, clearly marked with the orange „Etap 2" banner. Don't pull them into MVP screens.
- Spec bans for the MVP: Google Maps/Mapbox, OpenWeatherMap, paid APIs, Service Worker/offline, file upload, Web Push. Map = Leaflet + markercluster; weather = Open‑Meteo; reverse geocoding = Nominatim.
