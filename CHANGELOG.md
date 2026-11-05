# Historia zmian

Wszystkie istotne zmiany w aplikacji GREENowacje „Drzewo dla Pokoleń”.

Numer wersji: **pierwsza liczba to prototyp** - (2.x — „Prototyp
drugi”), **druga** rośnie przy nowych funkcjach, **trzecia** przy poprawkach. Format sekcji
według [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/). Wersje 1.x opisano
wstecznie, na podstawie historii repozytorium.

Jak wydać nową wersję — `README.md`, sekcja „Wydanie nowej wersji”.

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
