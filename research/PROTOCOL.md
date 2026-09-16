# S400: stan protokołu i dowody

Aktualizacja 2026-09-08: [analiza standard-auth v2](AUTH_V2.md) rozstrzyga
znaczenie `02000000` i znajduje różnicę kolejności oraz podpisy serwera w
publicznym SDK. To zastępuje wcześniejszą hipotezę, że lokalne ECDH i sam DID
wystarczą także na badanej S400. Dalsza zgodność SDK z firmware S400 wymaga
potwierdzenia. Poniżej pozostaje historia eksperymentów z zaznaczonymi korektami.

„Potwierdzone” oznacza kod urządzenia/klienta open source
albo działający capture opisany przez autora implementacji. Zachowanie konkretnej
sztuki S400 pozostaje hipotezą do chwili zebrania trace z tego firmware.

## Identyfikacja

Potwierdzone w aktualnym `xiaomi-ble`: model `MJTZC01YM` używa co najmniej PID
`0x30D9`, `0x3BD5` i `0x48CF`. Warianty handlowe występują jako
`yunmai.scales.ms103`, `ms104` i `ms107`. Reklama jest w service data UUID
`0xFE95`; aktualny parser Home Assistanta rozpoznaje S400 w obiekcie MiBeacon
`0x6E16`.

Nie ma obecnie dowodu na jedną stałą pełną nazwę BLE dla wszystkich rewizji.
Kod `xiaomi-s400-live` na Linuksie wybiera urządzenie po MAC, a na macOS szuka
końcówki MAC w nazwie. Dlatego integracja identyfikuje wagę po PID w FE95, a
narzędzie diagnostyczne zapisuje rzeczywiste `local_name`, UUID-y i PID. Nazwę
z konkretnej sztuki należy uznać za wynik capture, nie stałą protokołu.

Źródła:

- [tablica modeli i PID xiaomi-ble](https://github.com/Bluetooth-Devices/xiaomi-ble/blob/main/src/xiaomi_ble/devices.py)
- [dekoder obiektu 0x6E16](https://github.com/Bluetooth-Devices/xiaomi-ble/blob/main/src/xiaomi_ble/parser.py)
- [zgłoszenie z przykładami surowych wartości](https://github.com/AlexxIT/XiaomiGateway3/issues/1388)

Obiekt `0x6E16` ma dziewięć bajtów: `<profile_id:u8, packed:u32le,
timestamp:u32le>`. `packed[0:11]` to masa ×10, kolejne 7 bitów to tętno minus
50, a pozostałe bity to impedancja ×10. Obecny `xiaomi-ble` interpretuje ramkę
z masą i impedancją jako 50 kHz, a końcową ramkę bez masy/tętna jako 250 kHz.

MiBeacon v4/v5 szyfruje payload AES-CCM z 16-bajtowym bindkey i 4-bajtowym MIC.
Nonce składa się z odwróconego MAC, PID+frame counter i 3-bajtowego ext counter;
AAD to `0x11`. Dokładna implementacja jest w
[`_decrypt_mibeacon_v4_v5`](https://github.com/Bluetooth-Devices/xiaomi-ble/blob/main/src/xiaomi_ble/parser.py).

Nagłówek FE95 zaczyna się od `frame_control:u16le`, `product_id:u16le` i
`frame_counter:u8`. W `frame_control` bity 15–12 oznaczają wersję, 11–10 tryb
auth, bit 8 stan rejestracji, bit 6 obecność obiektu, bit 5 capabilities, bit 4
MAC i bit 3 szyfrowanie. Dalej występują pola opcjonalne i obiekty; w ramce
szyfrowanej końcówka zawiera 3-bajtowy licznik rozszerzony oraz 4-bajtowy MIC.

## Trzy odrębne warstwy

1. **Reklamy FE95:** pasywne, MiBeacon v4/v5, AES-CCM, długotrwały bindkey 16 B.
2. **Rejestracja/provisioning:** usługa GATT FE95 z charakterystykami `0x0010`
   (UPNP) i `0x0019` (AVDTP), ephemeral P-256 ECDH, HKDF-SHA256 z info
   `mible-setup-info`; wyniki obejmują token 12 B, bindkey 16 B i klucz DID 16 B.
3. **Późniejszy login GATT:** dwa losowe ciągi 16 B, HKDF-SHA256 z tokenu i info
   `mible-login-info`, wzajemne HMAC-SHA256. Klucze sesji szyfrują kanały
   `0x001a/0x001b` AES-CCM.

Po loginie komunikat CMTP ma postać `iter:u16le || ciphertext || tag:4B`.
Nonce urządzenie → klient to `dev_iv[4] || 00000000 || iter[2] || 0000`;
dla klient → urządzenie używany jest analogicznie `app_iv`. Implementacja
S400 używa AES-CCM bez AAD.

UUID-y obserwowane dla aktywnego S400 przez `xiaomi-s400-live`:

| UUID krótki | Rola |
|---|---|
| `0x0010` | komendy i wynik auth |
| `0x0017` | AVCTP, kanał dodatkowy |
| `0x0019` | fragmentowane dane auth |
| `0x001a` | szyfrowane app → urządzenie |
| `0x001b` | szyfrowane urządzenie → app |
| `0x001c` | kanał dodatkowy |

Źródła: [stałe i kod loginu S400](https://github.com/nokistin/xiaomi-s400-live/tree/main/xiaomi_s400_live),
[dokumentacja miauth](https://github.com/dnandha/miauth/tree/main/doc).

## Starszy diagram rejestracji i loginu (GET_INFO version 1)

Nie stosować tej kolejności do GET_INFO version 2. Aktualny diagram i różnice:
[AUTH_V2.md](AUTH_V2.md#sekwencja-wersji-2-w-znalezionym-sdk).

```mermaid
sequenceDiagram
    participant HA as Lokalny klient
    participant S as S400
    HA->>S: UPNP a2 00 00 00 (GET_INFO)
    S-->>HA: AVDTP version + io + opcjonalny DID
    HA->>S: UPNP 15 00 00 00 (SET_KEY)
    HA->>S: AVDTP header + public key P-256 X||Y
    S-->>HA: AVDTP header + device public key X||Y
    Note over HA,S: ECDH; HKDF(info="mible-setup-info")<br/>token[12], bindkey[16], DID-key[16]
    HA->>S: AES-CCM(DID), nonce 10..1b, AAD="devID"
    HA->>S: UPNP 13 00 00 00 (AUTH)
    S-->>HA: 11 00 00 00 (register OK)
    HA->>S: UPNP 24 00 00 00 + app_random[16]
    S-->>HA: device_random[16] + HMAC_device
    Note over HA,S: HKDF(token, app_random||device_random,<br/>info="mible-login-info")
    HA->>S: HMAC_app
    S-->>HA: 21 00 00 00 (login OK)
```

Pełna kolejność ramek jest potwierdzona w
[lokalnym aktywatorze atc1441](https://github.com/atc1441/atc1441.github.io/blob/main/Temp_universal_mi_activate.html)
oraz [implementacji `MiClient.register`](https://github.com/dnandha/miauth/blob/main/lib/python/miauth/mi/miclient.py).

## Odpowiedź A/B/C

**A jest potwierdzona dla starszej rejestracji version 1**, a generowanie tokenu
i bindkey przez ECDH/HKDF występuje też w znalezionym SDK version 2.

**B jest potwierdzona dla znalezionego SDK version 2:** przed zapisem kluczy
wymaga ono certyfikatu serwera oraz podpisu DID, bindkey i UTC. Próba na S400
potwierdziła cały transport tych pól i odrzucenie własnego certyfikatu wynikiem
`0x12000000`. Dokładną kolejność kontroli kryptograficznych potwierdza kod SDK;
sam kod błędu S400 nie rozróżnia, która z nich zakończyła się niepowodzeniem.

**C pozostaje niepotwierdzona:** nie znaleziono w tym SDK alternatywnej ścieżki
rejestracji bez podpisu serwera. Dokładny format, publiczny root i odtwarzalne
źródło znajdują się w [AUTH_V2.md](AUTH_V2.md).

## Wynik pierwszego capture na sprzęcie

Capture `captures/s400-gatt.jsonl` potwierdził dla badanej sztuki nazwę
`Xiaomi Scale S400 <suffix>`, PID `0x3BD5`, FE95 oraz charakterystyki `0x0010`,
`0x0017`–`0x001c`. Dodatkowa charakterystyka `0x0018` ma właściwości
`notify` i `write-without-response`. Wszystkie subskrypcje poza standardowym
Service Changed (`0x2a05`) zostały zaakceptowane.

`captures/s400-pair.jsonl` potwierdził lokalnie następującą część rejestracji:

1. `GET_INFO` zwróciło wersję auth i capabilities I/O bez pola DID.
2. S400 zaakceptował `SET_KEY`, odebrał 64-bajtowy punkt P-256 klienta i
   potwierdził całą paczkę.
3. S400 wysłał własny 64-bajtowy punkt P-256 w czterech ramach.
4. Po potwierdzeniu tego punktu klient wysłał `SEND_DID`; trace urwał się przed
   `RCV_RDY`, więc zaszyfrowany DID i `AUTH` nie zostały jeszcze wysłane.

Drugi capture `captures/s400-pair-2.jsonl` rozstrzygnął niejasność transportową.
WinRT zakończył zapis `SEND_DID` powodzeniem po przerwie 0,25 s. Waga przez 12 s
nie wysłała żadnej odpowiedzi, po czym klient zakończył połączenie z powodu
timeoutu. Brak odpowiedzi wystąpił więc zarówno bez przerwy w pierwszej próbie,
jak i z przerwą w drugiej; hipoteza zbyt szybkiego przejścia jest osłabiona.

Reklama `3058d53b0068fdcc8a43d408` dekoduje się jako MiBeacon v5,
`auth_mode=2` (standard auth), `registered=0`, `solicited=0`; capability `0x08`
nie zawiera pola I/O/OOB. Badana sztuka deklaruje więc dokładnie standard-auth,
a nie secure-auth. Czterobajtowy wynik `GET_INFO` to konsekwentnie `02000000`,
podczas gdy ogólny aktywator atc1441 ma specjalną gałąź dla `01000000`.
Aktualizacja: to wersje protokołu 2 i 1, a nie dwa warianty statusu.

Niepotwierdzony fragment zaczyna się dokładnie od odpowiedzi `RCV_RDY` na
`SEND_DID`. Waga nie zobaczyła jeszcze zaszyfrowanej treści DID, dlatego cisza
nie jest dowodem odrzucenia jego lokalnej wartości. Możliwe są: dodatkowy warunek
stanu urządzenia, wiadomość na innym kanale FE95 albo wariant sekwencji S400.
Skrypt monitoruje teraz również `0x0017`, `0x0018`, `0x001a`, `0x001b` i
`0x001c` oraz odczytuje `0x0004`, aby rozstrzygnąć dwie pierwsze możliwości.
Jeżeli nie pojawi się dodatkowa wiadomość, potrzebny będzie porównawczy HCI snoop
z pierwszego bindu Mi Home.

Po analizie drugiego capture znaleziono jeszcze jeden konkretny kandydat:
`miauth/doc/ble_security_proto.txt` opisuje pomijany przez bibliotekę „official
greeting” (`0xA4` oraz wymiana `000004xx`/`000005xx`) przed `GET_INFO`. Nowszy,
oparty na btsnoop kod dla Xiaomi S200 dodatkowo potwierdza, że w tej generacji
wag Mi Home najpierw subskrybuje `0x001b`, `0x001a`, `0x001c`, `0x0019`, odpytuje
`0x001c` komendami `00`, `01`, `080100`, `03`, a następnie wykonuje greeting.
Autor oznacza te kroki jako wymagane przed auth. S400 udostępnia identyczne
kanały, a dotychczasowy klient całkowicie pomijał ten etap. Skrypt wykonuje go
teraz domyślnie; `--skip-official-init` pozwala zachować poprzedni przebieg jako
próbę kontrolną. Zastosowanie tej sekwencji do rejestracji S400 pozostaje
hipotezą do potwierdzenia kolejnym trace.

Trzeci capture `captures/s400-pair-3.jsonl` potwierdził tę hipotezę. S400
odpowiedział na komplet zapytań `0x001c`, wykonał negocjację po `0xA4` z
parametrem `0xF2` i zwrócił wersję `2.1.1_0006` z `0x0004`. Odpowiedź na
zapytanie `03` identyfikuje układ jako `RTL8762C`. Po inicjalizacji
`GET_INFO` zmieniło format odpowiedzi ze starej paczki wieloramkowej na
pojedynczą ramkę `0000020002000000`. Pierwsze cztery bajty oznaczają single-frame
typu `0x00`, a payload nadal wynosi `02000000`. Klient przerwał wyłącznie dlatego,
że nie obsługiwał jeszcze tego formatu. Parser obsługuje teraz single-frame i
odpowiada jego potwierdzeniem `00000300`, zgodnie z capture nowszej wagi.

Czwarty capture `captures/s400-pair-4.jsonl` potwierdził następny skutek
negocjacji. Po przyjęciu single-frame `GET_INFO` klient wysłał stary nagłówek
klucza `000000030400`, deklarujący cztery fragmenty po 18 bajtów. S400
natychmiast odpowiedział `00000104`, zamiast `RCV_RDY`. Negocjacyjna ramka testowa
ma 240 bajtów po prefiksie, więc 64-bajtowy klucz mieści się w jednym fragmencie.
Klient wyznacza teraz rozmiar fragmentu z ramki testowej i dynamicznie buduje
liczbę fragmentów. W tym capture nagłówek klucza powinien więc mieć postać
`000000030100`; ta sama zasada obejmuje 24-bajtowy zaszyfrowany DID i 32-bajtowy
HMAC loginu.

Piąty capture `captures/s400-pair-5.jsonl` potwierdził tę zmianę: nagłówek
`000000030100` otrzymał `RCV_RDY`, cały 64-bajtowy klucz klienta został przyjęty,
a S400 zwrócił własny poprawny 64-bajtowy klucz jako single-frame typu `0x03`.
Po ACK klient czekał jednak 0,25 s i nagłówek DID `000000000100` ponownie nie
otrzymał `RCV_RDY`. Pierwsze próby bez pauzy nie zawierały official-init, dlatego
nie są próbą kontrolną dla obecnego przebiegu. Domyślna pauza wynosi teraz zero;
`--stage-delay` pozostaje parametrem eksperymentalnym.

Szósty capture `captures/s400-pair-6.jsonl` wykonał pełną aktualną sekwencję bez
sztucznej pauzy. Wynik jest identyczny: zapis `000000000100` kończy się lokalnie
powodzeniem, lecz przez 12 s nie ma `RCV_RDY` ani żadnej wiadomości na
`0x0017`, `0x0018`, `0x001a`, `0x001b` lub `0x001c`. Hipoteza o wymaganym
opóźnieniu jest więc odrzucona. Potwierdzony lokalnie prefiks protokołu kończy się
na ACK `00000300` dla 64-bajtowego klucza publicznego S400. Kolejnym wymaganym
dowodem jest HCI snoop pierwszego bindu Mi Home; trzeba porównać wszystkie
operacje GATT od tego ACK do chwili, gdy urządzenie zgłasza gotowość na DID.

Przed capture Mi Home pozostaje jeszcze jedna ograniczona próba. Aktywator
atc1441 po ECDH ma nagłówek DID zakodowany na stałe jako `000000000200` i dzieli
24-bajtowy ciphertext na fragmenty 18 + 6 B. Nie dowodzi to zachowania S400 po
negocjacji dużego transportu, lecz pozwala sprawdzić, czy firmware ma osobny
sztywny warunek dwóch ramek dla typu DID. Opcja `--did-chunk-size 18` odtwarza
dokładnie ten wariant i zapisuje wybraną wartość w trace.

Plik `captures/s400-pair-7.jsonl` nie jest wynikiem tej próby: pole
`did_chunk_size` ma wartość `null`, a wysłany nagłówek to ponownie
`000000000100`. Potwierdza wynik szóstej sesji, ale nie rozstrzyga wariantu
dwuramkowego. Ósmy capture wykonał już właściwy test: pole `did_chunk_size`
wynosi `18`, klient wysłał `000000000200`, a waga ponownie nie odpowiedziała
przez 12 s. Sztywny wymóg dwóch fragmentów DID jest więc odrzucony. Po tej
próbie CLI wróciło do wynegocjowanego rozmiaru jako ustawienia domyślnego.

Oficjalne repozytorium `mijia_ble_standard` ma gałąź `realtek` dla RTL8762,
czyli rodziny układu zgłoszonej przez S400. Gałąź zawiera jednak wyłącznie
instrukcję uzyskania dostępu do prywatnego `mijia_ble_mesh`; właściwe
`mijia_ble_libs` ze stanem standard-auth także jest prywatne. Publiczny starszy
nagłówek definiuje `strict_bind_confirm` oraz `mible_std_auth_permit_bind`, a
dokumentacja dopuszcza trzy tryby rozpoczęcia bindu: wybór w aplikacji, próg RSSI
i lokalne potwierdzenie urządzenia. Nie ma w nim kodu, który łączy stan
`02000000` z którymkolwiek z tych trybów. Reklama S400 ma `solicited=0`, co według
dokumentacji wyklucza aktywne okno device-confirm w chwili capture, ale nie
rozróżnia APP-confirm od RSSI-confirm.

Powyższy stan badań został przekroczony 2026-09-08: publiczny LLVM bitcode
standard-auth version 2 wskazuje kolejny opcode `0x13`, jeszcze przed odbiorem
danych rejestracji. Zawiera też ich nowy format i weryfikacje podpisów. Dalsze
badania bez Bluetooth opisano w [AUTH_V2.md](AUTH_V2.md).
Minimalny wymagany wycinek zaczyna się od zapisu `15000000`, obejmuje wymianę
obu punktów P-256 i kończy po pierwszej operacji następującej po ACK klucza
urządzenia. Dopiero ten ślad rozstrzygnie, czy Mi Home wysyła inną komendę GATT,
czeka na zmianę stanu urządzenia, czy wykonuje dodatkowy krok poza BLE.

## Home Assistant

Wbudowana integracja `xiaomi_ble` obsługuje S400 od wersji biblioteki 0.37.0.
Dla MiBeacon v4/v5 przyjmuje 32 znaki hex (16 B) i do pasywnego odbioru nie
potrzebuje tokenu. Kod config flow zapisuje bindkey w `ConfigEntry`; encje S400
to masa, tętno, impedancja 50/250 kHz, profil i stabilizacja.

Źródła:

- [config flow Home Assistant](https://github.com/home-assistant/core/blob/dev/homeassistant/components/xiaomi_ble/config_flow.py)
- [integracja Xiaomi BLE](https://www.home-assistant.io/integrations/xiaomi_ble/)
- [PR/issue dodający S400](https://github.com/Bluetooth-Devices/xiaomi-ble/issues/158)

Ta integracja HACS implementuje oba tory. Z bindkey dekoduje reklamy FE95. Jeżeli
wpis zawiera również 12-bajtowy token, reklama wybudzonej wagi uruchamia lokalne
połączenie, login standard-auth i odbiór szyfrowanych ramek CMTP. CMTP przenosi
bieżącą masę i stabilizację, a ramka końcowa także profil, czas oraz impedancje.
Połączenie nie wymaga komunikacji sieciowej. Nadal nierozwiązane pozostaje
uzyskanie podpisanego credentialu potrzebnego do pierwszej rejestracji auth v2.

W osobnym 120-sekundowym teście niepowiązanej wagi zasubskrybowano `0x8002` i
wszystkie charakterystyki notify FE95. Nie odebrano żadnego notification. Kod
iOS znaleziony w publicznym repo, który nazywa `0x8002` kanałem masy, nie zawiera
capture ani testu S400; jego komendy `0x8001` są opisane jako warianty protokołu
i nie są wykonywane w gałęzi S400. Nie używamy ich jako podstawy integracji.
