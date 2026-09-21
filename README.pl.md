# Xiaomi S400 Local for Home Assistant

[![Validate](https://github.com/kbpk/xiaomi-s400-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/kbpk/xiaomi-s400-homeassistant/actions/workflows/validate.yml)
[![HACS custom repository](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

Eksperymentalna integracja HACS dla Xiaomi Body Composition Scale S400
(`MJTZC01YM`, `yunmai.scales.ms103/ms104/ms107`). Odbiór danych i przechowywanie
kluczy odbywają się lokalnie. Sama integracja Home Assistant nie zawiera
klienta Xiaomi Cloud i nie prosi o dane konta Xiaomi. Osobne narzędzie
laboratoryjne może jednorazowo poprosić backend Xiaomi o podpis wymagany przez
factory-new S400 z auth version 2.

> [!WARNING]
> Projekt jest w fazie alpha. Provisioning auth v2 został potwierdzony na S400
> z firmware `2.1.1_0006`: waga zwróciła `REGISTER_OK`, a następnie zaakceptowała
> lokalny login tokenem. Pierwszy bind wymaga jednorazowego podpisania credentialu
> przez Xiaomi; po nim odbiór danych i loginy GATT są lokalne. Czysto lokalny
> provisioner nadal obsługuje tylko starszy auth version 1. Szczegółowe dowody,
> granice zgodności i analiza bez Bluetooth: [AUTH_V2.md](research/AUTH_V2.md).
> [Analiza oficjalnego APK Mi Home](research/MIHOME_V2.md) niezależnie
> potwierdza tę kolejność i identyfikuje brakujące poświadczenie rejestracji.

## Stan implementacji

- eksperymentalny provisioning standard-auth version 1 bez OOB przez P-256 ECDH,
  HKDF-SHA256 i AES-CCM;
- narzędzie auth v2 wykonujące ECDH lokalnie, proszące Xiaomi tylko o podpisany
  credential, sprawdzające oba podpisy lokalnie i zweryfikowane na S400 przez
  `REGISTER_OK` oraz późniejszy login tokenem;
- analiza captures bez Bluetooth i testowany offline format credentialu v2;
- zapis 16-bajtowego bindkey i 12-bajtowego tokenu dopiero po odpowiedzi
  rejestracyjnej urządzenia i poprawnym loginie;
- odszyfrowywanie MiBeacon v4/v5 oraz encje: masa, tętno, impedancja 50 kHz,
  impedancja 250 kHz, profil użytkownika, stabilizacja i RSSI;
- automatyczne połączenie po wybudzeniu wagi, login tokenem i lokalny odbiór
  bieżących oraz końcowych pomiarów z szyfrowanego kanału CMTP;
- redagowanie sekretów z diagnostyki Home Assistanta;
- samodzielne narzędzia do GATT trace i pairingu na Raspberry Pi OS/Debianie.

Starsza sekwencja standard-auth pochodzi z analizy implementacji open source.
Nie jest zgodna z całą procedurą wersji 2 znalezioną w publicznym SDK.
Integracja zgłasza sukces dopiero po odpowiedzi `0x11000000` i poprawnym loginie,
więc nie zapisze losowych, nieuzgodnionych kluczy.

## Instalacja przez HACS

1. Dodaj to repozytorium w HACS jako niestandardowe repozytorium typu
   **Integration**.
2. Pobierz **Xiaomi S400 Local** i uruchom ponownie Home Assistant.
3. Wybudź wagę i wybierz
   **Ustawienia → Urządzenia i usługi → Dodaj integrację → Xiaomi S400 Local**.
4. Jeżeli masz już bindkey i token, wybierz `Existing keys`. Token uruchamia
   automatyczny aktywny odbiór GATT; bez niego pozostaje odbiór reklam FE95.

Opcja `Local provisioning` jest obecnie przeznaczona do eksperymentów i zapisze
klucze tylko wtedy, gdy waga potwierdzi rejestrację oraz późniejszy login. Do
pasywnych reklam token nie jest potrzebny. Automatyczny aktywny strumień GATT
wymaga tokenu.

Instalacja ręczna polega na skopiowaniu katalogu
`custom_components/xiaomi_s400_local` do katalogu `custom_components`
instancji Home Assistanta i ponownym uruchomieniu HA.

## Pierwszy trace diagnostyczny

Istniejące captures można przeanalizować w WSL bez adaptera Bluetooth:

```bash
uv run python tools/s400_analyze_trace.py captures/s400-pair*.jsonl
```

Wynik zawiera wersję auth, informację o wymianie kluczy i kolejności `0x13`
względem danych rejestracji. Nie ujawnia surowych ramek ani kluczy.

Na Raspberry Pi OS lub Debianie:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lab.txt
.venv/bin/python tools/s400_diag.py --duration 60 --output captures/s400-gatt.jsonl
```

Bleak korzysta z usługi D-Bus BlueZ. Na typowym Raspberry Pi OS wystarcza
użytkownik mający dostęp do Bluetooth; jeżeli lokalna polityka D-Bus odrzuci
połączenie, uruchom pojedyncze narzędzie przez `sudo .venv/bin/python ...`.

Skrypt wykrywa PID S400, wypisuje pełną bazę GATT, subskrybuje wszystkie
charakterystyki `notify`/`indicate` i zapisuje reklamy oraz powiadomienia do
JSONL z prawami `0600`. Nie wysyła komend auth. Opcja `--read` dodatkowo czyta
charakterystyki oznaczone przez GATT jako czytelne.

### Windows / WSL

WSL nie korzysta automatycznie ze stosu Bluetooth Windows. Bez przekazanego
adaptera USB narzędzia można uruchomić bezpośrednio przez Windows Python i
backend WinRT biblioteki Bleak:

```powershell
$repo = "\\wsl.localhost\Ubuntu\home\kbpk\xiaomi\xiaomi-s400-homeassistant"
uv run --no-project --with-requirements "$repo\requirements-lab.txt" `
  "$repo\tools\s400_diag.py" --duration 60 `
  --output "$repo\captures\s400-gatt.jsonl"
```

Nazwa dystrybucji `Ubuntu` w ścieżce może być inna; pokaże ją `wsl -l -v`.
Pliki na Windows dziedziczą ACL katalogu zamiast uniksowego trybu `0600`.

## Samodzielny lokalny pairing

Dotyczy wyłącznie eksperymentalnej ścieżki GET_INFO version 1 bez OOB.
Badana S400 zgłasza version 2 i otrzyma komunikat o braku obsługi.

Po factory resecie i wybudzeniu wagi:

```bash
.venv/bin/python tools/s400_pair.py \
  --output private/s400-secrets.json \
  --trace captures/s400-pair.jsonl
```

Na Windows uruchom ten sam plik przez `uv` i backend WinRT:

```powershell
$repo = "\\wsl.localhost\Ubuntu\home\kbpk\xiaomi\xiaomi-s400-homeassistant"
uv run --no-project --with-requirements "$repo\requirements-lab.txt" `
  "$repo\tools\s400_pair.py" `
  --output "$repo\private\s400-secrets.json" `
  --trace "$repo\captures\s400-pair.jsonl"
```

Opcja `--stage-delay` steruje eksperymentalną przerwą między potwierdzeniem klucza
publicznego wagi a `SEND_DID` (domyślnie 0 s). Trace zapisuje także zakończenie
każdego zapisu, rozłączenie i wyjątek, aby odróżnić odrzucenie ramki od błędu
backendu Bluetooth.

Plik sekretów ma prawa `0600`. Trace zawiera ramki GATT i klucze publiczne,
ale nie zawiera wyprowadzonych tokenu, bindkey ani kluczy sesji. Nie publikuj
pliku `s400-secrets.json`.

## Jednorazowy provisioning auth v2 przez Xiaomi

To jest potwierdzona ścieżka dla factory-new S400 z auth v2. Token i bindkey
nadal powstają lokalnie z ECDH.
Do Xiaomi trafiają MAC, model, token i bindkey, tak jak w Mi Home; serwer zwraca
DID, certyfikat oraz podpis `DID || bindkey || UTC`. Tekstowy DID jest dopełniany
zerami z lewej strony do 20 bajtów, dokładnie jak w Mi Home. Skrypt sprawdza
podpis credentialu i certyfikat względem publicznego root key z SDK, wymaga
`REGISTER_OK`, a następnie sprawdza token lokalnym loginem GATT.

Na Windows z ASUS USB-BT400 uruchom narzędzie w zwykłym PowerShellu. Launcher
otwiera dedykowany profil Edge na aktualnej stronie konta Xiaomi. Zakończ w nim
logowanie oraz ewentualną weryfikację e-mail, a dopiero potem wróć do terminala.
Przed wysłaniem żądania provisioner wymaga cookie `passToken`; niedokończone
logowanie kończy się lokalnym błędem i nie generuje kolejnego kodu. Login i hasło
są odczytywane interaktywnie; hasło, cookies i odpowiedzi API nie trafiają do
argumentów, trace'u ani pliku wynikowego:

```powershell
$repo = "\\wsl.localhost\Ubuntu\home\kbpk\xiaomi\xiaomi-s400-homeassistant"
& "$repo\tools\windows\run_s400_xiaomi_pair.ps1" -Region de
```

Region musi odpowiadać regionowi konta Mi Home. Dla konta używanego w Polsce
typową wartością jest `de`; dostępne są też `cn`, `us`, `ru`, `tw`, `sg`, `in`
i `i2`. Dedykowany profil znajduje się lokalnie w
`%LOCALAPPDATA%\XiaomiS400Provisioner\EdgeProfile`, dzięki czemu cookies
przetrwają ponowne uruchomienie po czasowym limicie Xiaomi. Skrypt nie ponawia
automatycznie odrzuconej captchy.

Po sukcesie Xiaomi nie jest potrzebne do działania integracji. W Home Assistant
wprowadź 32 znaki `bindkey` i 24 znaki `token` z pliku wynikowego. Narzędzie nie
pobiera istniejących kluczy z konta i nie wylicza pomiarów w chmurze.

Test sprzętowy z 2026-09-21 potwierdził negocjację DMTU 242, transfer
wieloramkowego certyfikatu, lokalną weryfikację obu podpisów, odpowiedź
`11000000` (`REGISTER_OK`) i późniejszą odpowiedź `21000000` (`LOGIN_OK`).

Szczegóły protokołu, stan dowodów i workflow capture znajdują się w
[`research/PROTOCOL.md`](research/PROTOCOL.md) oraz
[`research/CAPTURE.md`](research/CAPTURE.md).

## Rozwój

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Trace BLE i pliki sekretów są ignorowane przez Git. Zasady zgłaszania wyników
oraz bezpiecznego przygotowania capture opisuje
[`CONTRIBUTING.md`](CONTRIBUTING.md).
