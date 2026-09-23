# Roadmapa implementacji MVP — Green Innowacje (Django)

## Context
PoC (`poc/`) został zaakceptowany jako makieta. Teraz budujemy **działający produkt, docelowo produkcyjny** (mentor: „Ważne to będzie prod! Stąd bezpieczeństwo i django”). Źródłem prawdy dla zakresu jest `spec/Specyfikacja_Wykonawcza_MVP_…md`. Specyfikacja pozwala zmienić stack, jeśli zachowamy kontrakty z §3–7 (schemat DB, API, integracje, cron, bezpieczeństwo). Django i DRF to spełniają.

Decyzje ustalone z Pawłem (22.09.2026):
- Backend: **Django**. Frontend: **szablony Django + vanilla JS i fetch do `/api/*` (DRF)**. Warstwę wizualną przenosimy z PoC. Mentor jeszcze nie potwierdził wyboru frontendu, ale API w DRF zostawia drogę do SPA.
- Zakres: **specyfikacja MVP**. PDF-y 1A2, 1A5 i 1A7 („Drzewo dla Pokoleń”: kody QR wydrukowane na sadzonkach przed rejestracją, zdjęcia, wpisy, porady sezonowe) trafiają do **Etapu 2**.
- Termin **30.09 = kamień milowy M1** (pionowy przekrój działający end-to-end). Reszta MVP w październiku.
- Hosting i repozytorium nie są jeszcze ustalone. Wszystko budujemy na Docker Compose, więc zadziała na dowolnym VPS.

## Stack
| Warstwa | Wybór | Po co |
|---|---|---|
| Runtime | Python 3.14 (z `.python-version`), **Django 5.2 LTS**, DRF; zależności przez **uv** (`pyproject.toml` + `uv.lock`) | LTS do 2028 |
| DB | PostgreSQL 16, psycopg 3 | zgodnie z §3 |
| Hasła | `argon2-cffi` (`Argon2PasswordHasher` jako pierwszy) | §7 |
| Konfiguracja | `django-environ`, zmienne z §2 (+ `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`) | |
| Rate limit | własny licznik w PostgreSQL (`core/ratelimit.py`, atomowy `INSERT … ON CONFLICT`), bez Redisa — `django-ratelimit` odrzucony: z cache w DB nie liczy atomowo | §7: 10/15 min/IP na logowanie i rejestrację, 30/min/user na podlanie |
| Nagłówki | `django-csp`, `SECURE_*`/HSTS w Django, TLS w Caddy | §7 |
| QR | `qrcode[pil]`, PNG w pamięci | §1 |
| Mapa | Leaflet 1.9 + markercluster **serwowane lokalnie z `static/`** (bez CDN, prostszy CSP) | |
| HTTP klient | `httpx` (timeout, retry z backoff) | §5 |
| Serwer | gunicorn + whitenoise, Caddy (reverse proxy + TLS) | |
| Cron | management commands i kontener `supercronic` w Compose | §6: bez kolejek |
| Testy/jakość | pytest-django, factory_boy, `respx` (mock API), ruff; CI w GitHub Actions | §9 |

## Architektura (aplikacje Django)
```
config/          settings (jeden moduł sterowany env), urls, wsgi
accounts/        User (custom), rejestracja/logowanie, uprawnienia (IsVolunteer/IsAdmin)
trees/           Locality, Tree, Watering, Assignment; status.py, geo.py, services.py; API + widoki
weather/         WeatherDaily, open_meteo.py, management commands fetch_weather / recompute_statuses
notifications/   EmailLog, digest (send_digests), szablony maili PL
panel/           panel admina aplikacji (/admin/*): użytkownicy, config, archiwizacja, stats, CSV
core/            Config (klucz-wartość + typowany accessor), middleware, wspólne szablony
templates/ static/   przeniesione z poc/ (styles.css, komponenty statusu); JS w plikach, NIE inline (CSP)
docker-compose.yml  Dockerfile  Caddyfile  .env.example
```

Kluczowe decyzje przy mapowaniu §3 na Django:
- **Custom User od pierwszej migracji**: UUID jako pk, `email` jako `USERNAME_FIELD` (unikalność bez rozróżniania wielkości liter przez `UniqueConstraint(Lower('email'))` zamiast `citext`), `display_name`, `role` ∈ {volunteer, admin}, `is_active`.
- **Kolizja `/admin/`**: specyfikacja wymaga `/admin/*` dla panelu aplikacji, więc Django admin przenosimy pod nieoczywisty URL z env i dajemy do niego dostęp tylko superuserowi.
- **`waterings` tylko do dopisywania**: model rzuca wyjątek przy update/delete, a migracja `RunSQL` dodaje trigger PostgreSQL blokujący UPDATE/DELETE. Działa nawet przy jednym użytkowniku bazy i pokrywa test integracyjny z §9.
- **Jeden aktywny opiekun**: `UniqueConstraint(fields=['tree'], condition=Q(ended_at__isnull=True))`, odpowiednik EXCLUDE z §3.
- **Pogoda UPSERT**: `bulk_create(update_conflicts=True, unique_fields=['locality','day'])`.
- **Algorytm statusu** (§6.2) jako czysta funkcja w `trees/status.py`, bez zapytań do DB. Dostaje dzień, konfigurację, opady per dzień, daty podlań i datę posadzenia/utworzenia, więc da się ją łatwo przetestować jednostkowo. Wywołują ją `recompute_statuses` i endpoint podlania.
- **Duplikat < 2 m**: najpierw wstępny filtr po bbox w SQL, potem haversine w `trees/geo.py`. W odpowiedzi 409 z danymi istniejącego drzewa, a `force=true` mimo to zapisuje.
- **IP za proxy**: rate limit liczony po prawdziwym IP klienta, przekazywanym przez Caddy w X-Forwarded-For; ufamy tylko Caddy.

---

## M1 — Pionowy przekrój (do 30.09) 🎯
**Cel do sprawdzenia:** skan QR → publiczna karta → logowanie → „Oznacz jako podlane” → status się zmienia. Wszystko działa w `docker compose up` na danych z seeda, a na serwerze testowym, jeśli do tego czasu będzie dostępny.

- [x] **22–23.09** — Repozytorium, Dockerfile i Compose (app, db), settings z env, **wszystkie modele i migracje** (w tym trigger append-only i seed `Config`), komenda `seed_demo` (2 miejscowości, 10+ drzew, podlania, pogoda, na bazie `poc/assets/data.js`), CI (ruff + pytest)
- [x] **24.09** — Auth: rejestracja (min. 10 znaków, argon2), logowanie i wylogowanie (sesja cookie, CSRF), rate limit, uprawnienia per rola; szkielet **testów macierzy endpoint × rola**; bazowy layout i nagłówek z PoC
- [x] **25.09** — `GET /api/trees` (bbox/status/locality, tylko aktywne), strona mapy (Leaflet + klastry, filtry z PoC); `GET /api/trees/{id}/public` + test „brak danych osobowych”; `/drzewo/{uuid}` (widok publiczny); `qr.png`
- [ ] **28.09** — `status.py` + testy wszystkich przypadków brzegowych z §6.2; `POST …/waterings` (natychmiastowe przeliczenie, zwraca nowy status, toast „Dziękujemy!…”); karta rozszerzona; assign/unassign (409); `/moje-drzewa` (sortowanie wg §4)
- [ ] **29.09** — Rejestracja drzewa: GPS z korektą pinezki, klient Nominatim (User-Agent, throttle, mock w testach), dopasowanie lub utworzenie miejscowości, 409 duplikatu + `force`, ekran sukcesu z QR
- [ ] **30.09** — Stabilizacja, ręczne E2E ścieżek z §9, README (uruchomienie jedną komendą), demo dla mentora

**Poza M1 celowo:** pobieranie pogody z API (w M1 pogoda pochodzi z seeda), e-maile, panel admina aplikacji (w M1 wystarczy Django admin), statystyki i CSV, pełne utwardzenie produkcyjne.

## M2 — Pogoda i panel admina (~1–7.10)
- [ ] `weather/open_meteo.py`: zapytanie z §5.1, timeout 10 s, 3 ponowienia z backoff; brak danych nie jest traktowany jako 0 mm, tylko logowany jako niekompletność. Backfill ostatnich `RAIN_WINDOW_DAYS` dni przy tworzeniu nowej miejscowości.
- [ ] Komendy `fetch_weather`, `recompute_statuses` (idempotentne, uruchamiane z CLI) i kontener `supercronic` z harmonogramem z §6 (Europe/Warsaw).
- [ ] Panel `/admin/*`: użytkownicy (rola, is_active), edycja i archiwizacja drzewa, config z walidacją (liczby dodatnie, SOON < URGENT) + przycisk „Przelicz statusy teraz”.
- **Wynik:** status zmienia się na podstawie prawdziwej pogody.

## M3 — Powiadomienia, statystyki, eksport (~8–14.10)
- [ ] SMTP z env (zgodny z Brevo). Dwa szablony PL (tekst + prosty HTML) z §5.3; limit 1 e-mail na użytkownika dziennie; `EmailLog`; komenda `send_digests` (07:30).
- [ ] `GET /api/admin/stats` i ekran statystyk (liczniki z §4).
- [ ] Eksport CSV (drzewa, podlania, pogoda) w UTF-8 z BOM, sprawdzony w Excelu.
- **Wynik:** e-maile przychodzą, admin ma dashboard i eksporty.

## M4 — Utwardzenie produkcyjne i wdrożenie (~15–23.10)
- [ ] Przejście przez checklistę z §7: HTTPS + HSTS, CSP (tylko domena kafelków), `X-Content-Type-Options`, `Referrer-Policy`, walidacja współrzędnych (granice Polski) i długości pól, rate limit na podlanie, bezpieczne cookies, `check --deploy` bez ostrzeżeń.
- [ ] Caddy w Compose; `pg_dump` o 03:00 + kopia poza serwer (rclone) + **sprawdzone przywracanie**.
- [ ] Dokumentacja: README, `.env.example` z opisem wszystkich zmiennych, instrukcja deployu na VPS, instrukcja administratora (PL).
- [ ] Pełny zestaw testów z §9, E2E na produkcji, przekazanie kont (MapTiler, SMTP) organizacji.
- **Wynik:** DoD spełnione, aplikacja działa na produkcji.

## Bufor (~24–31.10)
Kalibracja progów suszy na prawdziwych danych, poprawki po pierwszych testach z wolontariuszami.

## Etap 2 (po MVP, do decyzji klienta)
Rola koordynatora; powiadomienia w aplikacji i Web Push; tryb offline (PWA + synchronizacja); zdjęcia drzew; z PDF-ów: pula kodów QR drukowanych przed rejestracją drzewa, wpisy uczestników, porady sezonowe, katalog gatunków i odmian owocowych, kilku opiekunów jednego drzewa.

---

## Otwarte kwestie (do mentora lub klienta)
1. **Frontend:** potwierdzić szablony Django vs SPA. Do 24.09 dotyczy to tylko backendu, więc nic nie blokuje.
2. **Hosting, domena, repozytorium** (repo mentora `pio3m/greeninnowacje` czy nowe?). Blokuje wdrożenie na serwer testowy w M1 i produkcję w M4.
3. **Brakuje „Dokumentu Architektonicznego v0.2”:** specyfikacja odwołuje się do niego (progi, sekcja 12 = Definition of Done), a lokalnie mamy tylko v0.1 (11 sekcji). Poszukać na Google Drive mentora.
4. **Prywatność (RODO):** według PDF-ów drzewa rosną w prywatnych ogrodach, a publiczna mapa pokazuje dokładne współrzędne. Czy w MVP mapa ma być publiczna z pełną dokładnością?
5. Konta MapTiler i SMTP (Brevo) zakładane na organizację. Na czas developmentu kafelki OSM.
6. Nazwa marki w UI: „Green Innowacje” (spec, PoC) czy „Greenowacje – Drzewo dla Pokoleń” (PDF-y)?


## Weryfikacja
- Każdy kamień milowy kończy się wynikiem z listy powyżej, sprawdzonym ręcznie w przeglądarce (również na telefonie: GPS, QR) oraz zielonym CI.
- M1: `docker compose up` → `seed_demo` → przejście ścieżki QR → karta → logowanie → podlanie; testy statusu, PII i macierzy ról przechodzą.
- M4: `python manage.py check --deploy` bez ostrzeżeń, test przywrócenia backupu, CSV otwarty w Excelu z polskimi znakami.
