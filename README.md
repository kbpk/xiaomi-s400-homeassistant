# Xiaomi S400 Local for Home Assistant

[![Validate](https://github.com/kbpk/xiaomi-s400-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/kbpk/xiaomi-s400-homeassistant/actions/workflows/validate.yml)
[![HACS custom repository](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

Eksperymentalna integracja HACS dla Xiaomi Body Composition Scale S400
(`MJTZC01YM`, `yunmai.scales.ms103/ms104/ms107`). Provisioning, odbiór danych
i przechowywanie kluczy odbywają się lokalnie. Integracja nie zawiera klienta
Xiaomi Cloud i nie prosi o dane konta Xiaomi.

> [!WARNING]
> Projekt jest w fazie alpha. Pasywne dekodowanie MiBeacon ma testy, ale pełny
> lokalny provisioning nie działa jeszcze na badanej S400 z firmware
> `2.1.1_0006`. Rzeczywisty trace dochodzi do wymiany kluczy P-256; waga nie
> odpowiada na kolejny nagłówek `SEND_DID`. Potrzebujemy porównawczego HCI snoop
> z Mi Home, zanim flow pairingu będzie można uznać za gotowy.

## Stan implementacji

- zaimplementowany, lecz jeszcze nieukończony na sprzęcie provisioning Mi Home
  BLE standard-auth przez P-256 ECDH, HKDF-SHA256 i AES-CCM;
- zapis 16-bajtowego bindkey i 12-bajtowego tokenu dopiero po odpowiedzi
  rejestracyjnej urządzenia i poprawnym loginie;
- odszyfrowywanie MiBeacon v4/v5 oraz encje: masa, tętno, impedancja 50 kHz,
  impedancja 250 kHz, profil użytkownika, stabilizacja i RSSI;
- redagowanie sekretów z diagnostyki Home Assistanta;
- samodzielne narzędzia do GATT trace i pairingu na Raspberry Pi OS/Debianie.

Kod standard-auth jest potwierdzony przez implementacje open source. Akceptacja
tego wariantu przez każdą wersję firmware S400 wymaga jeszcze testu na sprzęcie.
Integracja zgłasza sukces dopiero po odpowiedzi `0x11000000` i poprawnym loginie,
więc nie zapisze losowych, nieuzgodnionych kluczy.

## Instalacja przez HACS

1. Dodaj to repozytorium w HACS jako niestandardowe repozytorium typu
   **Integration**.
2. Pobierz **Xiaomi S400 Local** i uruchom ponownie Home Assistant.
3. Wybudź wagę i wybierz
   **Ustawienia → Urządzenia i usługi → Dodaj integrację → Xiaomi S400 Local**.
4. Jeżeli masz już bindkey, wybierz `Existing keys`.

Opcja `Local provisioning` jest obecnie przeznaczona do eksperymentów i zapisze
klucze tylko wtedy, gdy waga potwierdzi rejestrację oraz późniejszy login. Do
pasywnych reklam token nie jest potrzebny.

Instalacja ręczna polega na skopiowaniu katalogu
`custom_components/xiaomi_s400_local` do katalogu `custom_components`
instancji Home Assistanta i ponownym uruchomieniu HA.

## Pierwszy trace diagnostyczny

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
