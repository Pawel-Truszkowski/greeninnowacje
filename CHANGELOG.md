# Historia zmian

Wszystkie istotne zmiany w aplikacji GREENowacje „Drzewo dla Pokoleń”.

Numer wersji: **pierwsza liczba to prototyp** - (2.x — „Prototyp
drugi”), **druga** rośnie przy nowych funkcjach, **trzecia** przy poprawkach. Format sekcji
według [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/). Wersje 1.x opisano
wstecznie, na podstawie historii repozytorium.

Jak wydać nową wersję — `README.md`, sekcja „Wydanie nowej wersji”.

## [2.4.0] — 2026-11-24

Więcej odznak — coś nowego do zdobycia przez cały sezon, nie tylko pierwszego dnia.

### Dodano
- **34 odznaki zamiast 10**, pogrupowane na stronie Osiągnięć: Podlewanie, Regularność,
  Opieka, Sadzenie, Odkrywanie i Zdjęcia.
- **Kolejne progi** w znanych seriach: 3, 25, 100 i 250 drzewo-dni podlewania, 3 i 15
  zarejestrowanych drzew, 5 i 10 drzew pod opieką, 7 dni, 90 dni i rok opieki nad jednym
  drzewem, 5 i 20 zdjęć.
- **Regularność liczona w tygodniach** — „Stały rytm” (4 tygodnie z rzędu) i „Cały sezon”
  (12 tygodni od maja do września). Młode drzewo potrzebuje obfitego podlania raz–dwa razy
  w tygodniu, a nie codziennie.
- **„Ranny ptaszek” i „Wieczorny podlewacz”** — za podlewanie w chłodnych godzinach, kiedy
  mniej wody paruje.
- **„Dobry sąsiad” i „Sąsiedzka pomoc”** — za podlewanie drzew, którymi nie opiekujesz się Ty.
- **„Botanik”, „Dendrolog” i „Wędrowiec”** — za drzewa różnych gatunków i w różnych
  miejscowościach.
- **„Ratownik” i „Anioł stróż”** — za podlanie drzewa, które pilnie potrzebowało wody.
  Aplikacja zapamiętuje teraz status drzewa w chwili podlania; podlania sprzed tej wersji
  nie mają tej informacji, więc te dwie odznaki liczą się od dziś.

### Zmieniono
- Nowe odznaki obejmują też wcześniejszą pracę. Gdy wpadnie ich kilka naraz, zamiast długiej
  listy pojawia się jeden komunikat „Masz N nowych odznak!”, a na stronie Osiągnięć czekają
  oznaczone „Nowa!”.

## [2.3.0] — 2026-11-23

Odzyskiwanie dostępu do konta.

### Dodano
- **„Nie pamiętasz hasła?”** na stronie logowania: podajesz e-mail, dostajesz link do
  ustawienia nowego hasła. Link działa przez godzinę i tylko raz, a po zmianie hasła
  aplikacja od razu Cię loguje i wylogowuje z pozostałych urządzeń.
- To samo w API: `POST /api/auth/password-reset` i `POST /api/auth/password-reset/confirm`.

### Bezpieczeństwo
- Odpowiedź jest zawsze taka sama — nie da się sprawdzić, czy dany adres ma konto.
- Limit prób z jednego adresu IP (jak przy logowaniu) i najwyżej 3 wiadomości na godzinę
  na jeden adres e-mail.
- E-mail z linkiem nie zużywa dziennego limitu powiadomień o suchych drzewach.

## [2.2.1] — 2026-11-20

Poprawki ochrony przed fikcyjnymi drzewami.

### Poprawiono
- **Dzienny limit nie da się obejść** wysyłając wiele zgłoszeń naraz — rejestracje jednej
  osoby są teraz sprawdzane po kolei.
- **Dezaktywacja konta przy archiwizacji jego drzew** kończy też opiekę tej osoby nad
  cudzymi drzewami, więc inni wolontariusze mogą je od razu przejąć.
- Gdy limit jest wyczerpany, a do formularza dołączono zdjęcie, aplikacja mówi, że trzeba
  je wybrać ponownie.
- Ujemna wartość `TREE_REGISTRATION_DAILY_LIMIT` zatrzymuje start aplikacji z czytelnym
  błędem, zamiast psuć każdą rejestrację.

## [2.2.0] — 2026-11-11

Ochrona mapy przed fikcyjnymi drzewami.

### Dodano
- **Dzienny limit rejestracji drzew** — wolontariusz może dodać do 20 drzew w ciągu doby.
  Koordynatorzy i administratorzy nie mają limitu, bo na akcjach sadzenia rejestrują wiele
  drzew naraz. Liczą się tylko zapisane drzewa, więc błąd w formularzu nie zużywa limitu.
- **Archiwizacja wszystkich drzew jednej osoby** — na stronie użytkownika w panelu jeden
  przycisk zdejmuje z mapy wszystkie jej drzewa i od razu (domyślnie) dezaktywuje konto.
  Podlania i historia zostają; pojedyncze drzewo można przywrócić w zakładce „Drzewa”.

## [2.1.0] — 2026-11-07

### Dodano
- **Kody QR gatunków** — na stronie każdego gatunku w Bazie wiedzy jest jego kod QR
  do pobrania, dostępny dla każdego. Koordynatorzy i administratorzy mogą też wydrukować
  arkusz A4 z 12 naklejkami (kod, nazwa gatunku i podpis „Zeskanuj i dowiedz się, jak dbać
  o swoje drzewko 🌱”), np. na rozdawane sadzonki, także jeszcze niezarejestrowane
  w aplikacji. Te same przyciski są w panelu, w zakładce „Gatunki”. Adres strony gatunku
  się nie zmienia, więc wydrukowane kody działają nawet po zmianie nazwy gatunku.

## [2.0.0] — 2026-11-05

„Prototyp drugi” — odpowiedź na feedback Greenowacji.

### Dodano
- **Grywalizacja** — strona „Osiągnięcia”: poziomy od 🌰 Nasiona do 🌲 Dębu, 10 odznak
  i ranking wolontariuszy z ostatnich 30 dni (widoczny tylko po zalogowaniu). Podlanie liczy
  się raz na drzewo dziennie. Komunikat „🏅 Nowa odznaka!” po jej zdobyciu.
- **Monitoring aktywności** — zakładka „Aktywność” w panelu: logowania, nieudane logowania,
  nowe konta, działania przy drzewach i otwarcia karty drzewa z kodu QR, z wykresem 30 dni
  i eksportem CSV. Bez adresów IP; wpisy starsze niż rok są usuwane automatycznie.
- **Drzewa użytkownika** — w zakładce „Użytkownicy” widać, kto ile drzew zarejestrował
  i iloma się opiekuje, a na stronie osoby — listę tych drzew i wcześniejszą opiekę.
- **Numer wersji** w stopce aplikacji, a w panelu — commit, data zbudowania i strona
  „Co nowego” z tą listą zmian.

### Naprawiono
- Dwa komunikaty naraz (np. podziękowanie i nowa odznaka) wyświetlają się jeden nad
  drugim — wcześniej drugi zasłaniał pierwszy.

## [1.2.0] — 2026-10-30

### Dodano
- **Baza wiedzy** — cztery działy (gatunki, sadzenie, pielęgnacja, filmy) z tekstami
  mentora, infografikami z wersją tekstową i filmem „Jak posadzić drzewo”.
- **Opisy gatunków** — osiem gatunków z infografiką i zdjęciem; karta drzewa linkuje
  do opisu jego gatunku. Administratorzy dodają i edytują opisy w panelu.
- Automatyczne wdrażanie wersji demonstracyjnej po zmianach w gałęzi `main`.

### Zmieniono
- Nowa nazwa i wygląd: GREENowacje, z paskiem informacji o finansowaniu z UE.

## [1.1.0] — 2026-10-01

### Dodano
- **Zdjęcia drzew** — dodawane z karty drzewa (aparat lub galeria), z moderacją w panelu.
- **Rola koordynatora** — widok obszaru, przypisywanie i zwalnianie opiekunów, własne
  podsumowanie e-mail.
- **Powiadomienia** w aplikacji, gdy drzewo pilnie potrzebuje wody, oraz codzienne
  podsumowania e-mail.
- Eksport drzew, podlań i danych pogodowych do CSV.

## [1.0.0] — 2026-09-25

„Prototyp pierwszy” — MVP.

### Dodano
- Mapa drzew ze statusami (kolor + ikona + tekst) i publiczna karta drzewa z kodem QR.
- Rejestracja i logowanie wolontariuszy; rejestracja drzewa z GPS, ustalaniem
  miejscowości i wykrywaniem duplikatów.
- Podlewanie, opieka nad drzewem i lista „Moje drzewa”.
- Status suszy liczony z danych pogodowych Open‑Meteo, przeliczany codziennie.
- Panel administratora: statystyki, drzewa, użytkownicy, progi suszy.
