# Wdrożenie demonstracyjne na Mikrusa

Instancja do testów na telefonie i pokazania mentorowi. **To nie jest wdrożenie
produkcyjne** — backupy, Caddy, CSP i pełna checklista bezpieczeństwa (§7 specyfikacji)
czekają na etap M4.

Założenia: Mikrus 2.0 (1 GB RAM), Docker na serwerze, dostęp przez subdomenę Mikrusa
z HTTPS, kod wysyłany przez `rsync`.

## Pierwsze wdrożenie

### 1. Na serwerze: katalog i konfiguracja

```bash
ssh -p <PORT_SSH> root@srvXX.mikr.us
mkdir -p /prjects/greeninnowacje && cd /projects/greeninnowacje
```

Przygotuj `.env` (wzór: [`deploy/env.prod.example`](../deploy/env.prod.example)).
Klucz podpisujący wygenerujesz komendą:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Koniecznie ustaw: `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, `APP_BASE_URL`, `APP_PORT` oraz klucz MapTiler.

### 2. Z komputera: wysłanie kodu

```bash
SSH_HOST=root@srvXX.mikr.us SSH_PORT=<PORT_SSH> ./deploy/deploy.sh
```

Skrypt kopiuje projekt (bez `.env`, bazy, `poc/` i `spec/`), buduje obraz i podnosi
usługi. Pierwsze budowanie na 1 GB RAM trwa kilka minut.

### 3. Dane demonstracyjne

```bash
cd /opt/greeninnowacje
docker compose -f docker-compose.prod.yml exec app \
    python manage.py seed_demo --force --password '<silne hasło>'
```

Flaga `--force` jest potrzebna, bo komenda odmawia działania przy `DEBUG=false`.
Instancja jest publiczna — nie używaj hasła z rozwoju lokalnego.

### 4. Pogoda na start

```bash
docker compose -f docker-compose.prod.yml exec app python manage.py fetch_weather --days 5
docker compose -f docker-compose.prod.yml exec app python manage.py recompute_statuses
```

Dalej zrobi to harmonogram: 05:00 pogoda, 07:00 statusy.

## Aktualizacja

```bash
SSH_HOST=root@srvXX.mikr.us SSH_PORT=<PORT_SSH> ./deploy/deploy.sh
```

Migracje i pliki statyczne wykonują się przy starcie kontenera
([`deploy/entrypoint.sh`](../deploy/entrypoint.sh)). Baza mieszka w wolumenie Dockera,
więc wdrożenie jej nie dotyka.

## Porty — najczęstsza pułapka

Maszyna ma publiczny adres **tylko w IPv6**. Po IPv4 działają wyłącznie porty, które
Mikrus przekierowuje ze współdzielonego adresu — domyślnie dwa, o numerach kończących
się numerem serwera (dla `bob108`: `20108` i `30108`, SSH na `10108`). Dodatkowe porty
przydziela obsługa na zgłoszenie.

**Panel pozwala wpisać przy subdomenie dowolny port i nie sprawdza, czy jest on
przekierowany.** Subdomena zwraca wtedy `502`, mimo że aplikacja działa bez zarzutu.
Zdarzyło nam się to przy pierwszym wdrożeniu: przydzielony port 40004 nie był routowany
i dopiero wymiana na 40005 rozwiązała sprawę.

### Jak sprawdzić, gdzie leży problem

Sprawdzaj warstwami, od środka maszyny na zewnątrz — pierwsza, która zawiedzie, wskazuje
winowajcę:

```bash
# 1. czy proces nasłuchuje
ss -tlnp | grep <PORT>

# 2. czy odpowiada lokalnie
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<PORT>/ -H "Host: <subdomena>"

# 3. czy port jest osiągalny z internetu (z własnego komputera)
curl -s -o /dev/null -w "%{http_code}\n" http://srv69.mikr.us:<PORT>/

# 4. czy ruch z proxy dociera do aplikacji
docker compose -f docker-compose.prod.yml logs app | grep "GET /"
```

Jeśli kroki 1–2 działają, a 3 zwraca „Connection refused”, port nie jest przekierowany —
warto to zgłosić obsłudze Mikrusa. Rozstrzygający dowód: zatrzymaj aplikację i postaw na
tym porcie `python3 -m http.server <PORT>`. Gdy i on nie odbiera połączeń, wiadomo na
pewno, że problem jest poza aplikacją.

Jeśli krok 3 działa, a subdomena nadal zwraca `502`, sprawdź w panelu, czy wskazuje na
właściwy port — i pamiętaj, że zmiana potrzebuje chwili na rozpropagowanie.

## Diagnostyka

```bash
docker compose -f docker-compose.prod.yml ps          # stan usług
docker compose -f docker-compose.prod.yml logs -f app # logi aplikacji
docker compose -f docker-compose.prod.yml logs cron   # przebiegi zadań
docker stats --no-stream                              # zużycie pamięci
```

| Objaw | Przyczyna |
|---|---|
| `DisallowedHost` w logach | subdomena spoza `DJANGO_ALLOWED_HOSTS` |
| Błąd CSRF przy logowaniu | brak `https://subdomena` w `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Pętla przekierowań | `DJANGO_SECURE_SSL_REDIRECT=true`, a proxy nie przekazuje `X-Forwarded-Proto` |
| Kafelki „invalid key” | subdomena niedodana do dozwolonych domen klucza MapTiler |
| Kod QR prowadzi na `localhost` | `APP_BASE_URL` nadal ma wartość lokalną |
| Kontener ubity przez system | brak pamięci — zmniejsz `GUNICORN_WORKERS` do 1 |
| `502` przy działającej aplikacji | port przy subdomenie nie jest przekierowany — patrz sekcja „Porty" |
| `400` przy wejściu po adresie serwera | adres spoza `DJANGO_ALLOWED_HOSTS` (to działa `ALLOWED_HOSTS`, nie awaria) |

## Czego tu brakuje (M4)

Backup `pg_dump` z kopią poza serwer i sprawdzonym przywracaniem, Caddy z własnym
certyfikatem, nagłówki CSP i HSTS, `manage.py check --deploy` bez ostrzeżeń,
instrukcja administratora.
