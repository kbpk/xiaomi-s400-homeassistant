# Standard-auth v2: analiza bez Bluetooth

Stan: 2026-09-16. **Znaleziono kod procedury zgłaszającej wersję 2** i
zweryfikowano jej kompletny transport na badanej S400. Waga przyjęła `0x13`,
92-bajtowy credential oraz certyfikat laboratoryjny, po czym zwróciła
`REGISTER_ERROR`. Nie mamy obrazu firmware S400 ani credentialu podpisanego
przez zaufany klucz, więc nie ukończono pierwszego bindu.

Aktualizacja: analiza [oficjalnego APK Mi Home 11.7.705](MIHOME_V2.md)
niezależnie potwierdza kolejność, format i pola `cloud_cert`/`cloud_sign`/`utc`.
Zidentyfikowano też endpoint `/v2/device/ble_standard_bind`.

Dodano `tools/s400_xiaomi_pair.py`, który implementuje brakujący wariant z
jednorazowym uzyskaniem produkcyjnego podpisu. Kod weryfikuje credential lokalnie
przed wysłaniem, lecz jego zgodność z produkcyjnym kontem i wagą oczekuje na
pierwszy test sprzętowy.

## Źródło i odtwarzalność

Publiczne repozytorium SDK AC792N zawiera archiwum
[`lib_mijia.a`](https://github.com/XiaoFanRen1/AC792N/blob/1b226eea849ba64a729276540ac82203adaac5ab/sdk/cpu/wl83/liba/lib_mijia.a).
Jego obiekt `mible_standard_auth.o` jest **LLVM bitcode z informacją debug**,
nie niedostępną biblioteką maszynową. Można odczytać przepływ sterowania,
stałe kryptograficzne i nazwy/offsety struktur. To publiczna kopia SDK dla
innego urządzenia i procesora; nie nazywamy jej firmware S400.

Rewizja: `1b226eea849ba64a729276540ac82203adaac5ab`.

| Plik | SHA-256 |
|---|---|
| `lib_mijia.a` | `17633a49062824a8f3749b43fedb34e48bbe509b76c6585725cc094d058f16d0` |
| `mible_standard_auth.o` | `fcb5a1e7debd7b053f26d78585dbdc82b1d426dbc663a622d8f90e56df6e14a3` |

Odtworzenie analizy na Linuksie (sieć potrzebna tylko do pobrania publicznego
artefaktu, bez Mi Home i konta Xiaomi):

```bash
mkdir -p /tmp/s400-auth-v2
cd /tmp/s400-auth-v2
curl --fail --location --output lib_mijia.a \
  https://raw.githubusercontent.com/XiaoFanRen1/AC792N/1b226eea849ba64a729276540ac82203adaac5ab/sdk/cpu/wl83/liba/lib_mijia.a
sha256sum lib_mijia.a
ar p lib_mijia.a mible_standard_auth.o > mible_standard_auth.o
sha256sum mible_standard_auth.o
llvm-dis-18 mible_standard_auth.o -o standard-auth.ll
rg -n 'store i16 2|opcode_recv|rxfer_rx_thd|root_pk|ecc_verify|ccm_decrypt' standard-auth.ll
```

Nie dodajemy cudzego archiwum, dekompilacji ani prywatnych captures do repo.
Poniższe numery linii odnoszą się do oryginalnego `mible_standard_auth.c`
w metadanych debug; funkcje są w większości włączone przez kompilator do
`mi_schd_process`. Numery w wygenerowanym `.ll` mogą zależeć od wersji LLVM.

| Miejsce w kodzie | Dowód |
|---|---|
| `dev_info_rsp`, od linii 586 | `protocol:u16`, `io:u16`, opcjonalny DID[20]; zapis `protocol = 2` |
| struktura `dev`, linie 94–108 | dane szyfrowane: DID[20], sig[64], UTC[4], MIC[4] |
| `reg_auth`, stan 752 | odbiór klucza aplikacji, typ 3, 64 bajty |
| stany 757–770 | generowanie klucza urządzenia, ECDH, wysłanie typu 3 |
| stany 796–819 | opcjonalne OOB, HMAC i wymiana randomów |
| stan 860 | oczekiwanie na opcode 19 (`0x13`); 20 (`0x14`) oznacza błąd |
| stan 864 | dopiero teraz odbiór typu 0 do bufora 92 bajtów |
| stan 871 | odbiór certyfikatu serwera typu 7, bufor 512 bajtów |
| przed stanem 905 | CCM-decrypt 88 bajtów + MIC 4; parsowanie certyfikatu DER |
| stan 905 | weryfikacja podpisu certyfikatu przez `root_pk` |
| stan 932 | weryfikacja podpisu danych rejestracji przez klucz serwera |
| końcówka `reg_auth` | zapis DID, tokenu i beacon key dopiero po weryfikacji |

Dodatkowa kontrola starszych źródeł:

- [Mi Home `BleStandardAuthRegisterConnector`](https://github.com/argahsuknesib/CyberSecurity-Summer-School-2021/blob/master/RiskInDroid/AndroidApp/xiaomi/sources/_m_j/fiw.java)
  interpretuje pierwsze dwa bajty GET_INFO jako wersję i odrzuca wartości >1.
- [starsza biblioteka w SDK Telink](https://github.com/telink-semi/tc_ble_mesh/tree/master/vc_debug_tool/ble_lt_mesh/vendor/common/mi_api/libs/standard_auth)
  zgłasza wersję 1; analizowany `stand-auth-cortex-m4.a` odbiera DID przed `0x13`.
- [kod transportu rxfer](https://github.com/atc1441/ATC_TLSR_Paper/blob/main/Firmware/components/vendor/common/mijia_ble/libs/common/mible_rxfer.c)
  wiąże gotowość odbioru z aktualnym stanem procedury. Sam poprawny zapis GATT
  nie oznacza, że aplikacja urządzenia jest już gotowa odebrać daną paczkę.

## Co naprawdę mówią captures S400

Badana S400: PID `0x3BD5`, firmware `2.1.1_0006`, odpowiedź identyfikacji układu
`RTL8762C`. W każdej zapisanej odpowiedzi GET_INFO payload wynosi `02000000`:

| Bajty | Interpretacja |
|---|---|
| `02 00` | wersja standard-auth = 2 |
| `00 00` | capabilities I/O = 0 |
| brak dalszych 20 bajtów | DID nie został zwrócony |

To **nie jest** wersja MiBeacon. Reklama osobno zgłasza MiBeacon 5 i tryb
standard-auth 2. Tryb standard-auth nie wyklucza weryfikacji podpisów w jego
nowszej wersji; poprzednie wnioskowanie w projekcie było zbyt szerokie.

W `s400-pair-6.jsonl`:

| Czas od startu | Operacja |
|---|---|
| 2.425 s | odebrano inline GET_INFO, payload `02000000` |
| 2.486 s | urządzenie potwierdziło odbiór publicznego klucza aplikacji |
| 2.847 s | klient potwierdził publiczny klucz urządzenia |
| 2.850 s | klient wysłał nagłówek danych typu 0 |
| 14.975 s | timeout bez gotowości odbioru |

Klient **nie wysłał `13000000` przed nagłówkiem**. Według znalezionego SDK
urządzenie w tym momencie czeka właśnie na tę komendę. Zmiany fragmentacji
i opóźnienia nie mogły usunąć tej różnicy stanu.

To wyjaśnienie jest zgodne z kodem i wszystkimi zakończonymi wymianami kluczy
w captures. Późniejszy test v2 potwierdził, że S400 przyjmuje także pozostałe
etapy transportu opisane przez SDK.

## Wynik pełnej próby transportu v2 na S400

Narzędzie `tools/s400_probe_v2.py` wykonało kontrolowaną próbę z własnym,
self-signed certyfikatem i własnym kluczem serwera. Nie łączy się ono z siecią
ani Xiaomi Cloud. `captures/s400-v2-minimal-cert.jsonl` potwierdza:

1. GET_INFO zwróciło version 2, I/O 0.
2. Oba punkty P-256 zostały wymienione i potwierdzone.
3. Po `13000000` S400 zgłosiła gotowość i przyjęła pełną 92-bajtową paczkę
   credentialu typu `0x00`.
4. S400 zgłosiła gotowość i przyjęła 239-bajtowy certyfikat DER typu `0x07`.
5. Dopiero po obu paczkach zwróciła `12000000` (`REGISTER_ERROR`).

Trace potwierdza więc na sprzęcie strukturę i kolejność transportu v2. Sam kod
wyniku nie wskazuje, która kontrola kryptograficzna zawiodła. Wniosek, że własny
certyfikat nie przechodzi zakotwiczenia zaufania, wynika z dokładnego przepływu
SDK: najpierw CCM i parser DER, następnie ECDSA certyfikatu z `root_pk`, potem
podpis `DID || bindkey || UTC`.

Próba kontrolna `captures/s400-v2-post-reject-login.jsonl` po ponownym
połączeniu uruchomiła login tokenem wyprowadzonym w odrzuconej sesji. S400
natychmiast zwróciła `e0000000` i nie wysłała challenge. Odrzucona rejestracja
nie pozostawiła więc używalnego tokenu ani stanu fail-open.

## Sekwencja wersji 2 w znalezionym SDK

```mermaid
sequenceDiagram
    participant C as Lokalny klient
    participant D as Urządzenie ze standard-auth v2
    C->>D: 0x0010: a2 00 00 00
    D-->>C: 0x0019 typ 0: version=2, io, opcjonalny DID
    C->>D: 0x0010: 15 + wybrane capabilities + 00
    C->>D: typ 3: app_public[64]
    D-->>C: typ 3: device_public[64]
    Note over C,D: P-256 ECDH; dla io=0 OOB to 16 zer
    Note over C,D: HKDF-SHA256 -> token[12], bindkey[16], did_key[16]
    Note over C: Czysto lokalnie brakuje certyfikatu i podpisu<br/>Provisioner może pobrać je jednorazowo z Xiaomi
    C->>D: 0x0010: 13 00 00 00
    C->>D: typ 0: CCM(DID[20] || signature[64] || UTC[4]) + MIC[4]
    C->>D: typ 7: server certificate DER
    Note over D: Verify(root_pk, certificate)<br/>Verify(server_pk, DID || bindkey || UTC)
    D-->>C: 11 00 00 00 po zapisie kluczy; w przeciwnym razie błąd
    C->>D: 24 00 00 00; typ 0x0b: app_random[16]
    D-->>C: typ 0x0d: device_random[16]; typ 0x0c: HMAC_device
    C->>D: typ 0x0a: HMAC_app
    D-->>C: 21 00 00 00
```

Dla niezerowych capabilities SDK wykonuje dodatkowe OOB. Przy wartości
`0x0010` tworzy OOB z pierwszych 16 bajtów SHA-256(app_public || device_public)
i używa lokalnego potwierdzenia numerycznego. Nasza S400 zgłosiła `io=0`,
więc nie ma dowodu, że ten wariant jest dla niej dostępny.

## Dokładny brakujący credential

Wynik HKDF ma 64 bajty; zakresy to token `[0:12]`, bindkey `[12:28]`,
did_key `[28:44]`. Info to ASCII `mible-setup-info` bez NUL. Dla braku OOB
salt stanowi 16 zer (HMAC-SHA256 daje tu ten sam wynik co salt pominięty).

Zaszyfrowany typ 0:

| Offset przed szyfrowaniem | Długość | Pole |
|---|---|---|
| 0 | 20 | DID |
| 20 | 64 | podpis ECDSA P-256, `r[32] || s[32]` |
| 84 | 4 | UTC, cztery bajty przekazywane też do podpisywanego komunikatu |
| po ciphertext | 4 | MIC AES-CCM |

Klucz AES to did_key[16], nonce `101112131415161718191a1b`, AAD ASCII `devID`.
Plaintext ma 88 bajtów; cała paczka 92. Little-endian UTC potwierdza także
`ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` w [kliencie Mi Home](MIHOME_V2.md).
Stary skrypt szyfrował sam DID[20],
więc nawet po naprawieniu kolejności wysyłałby zły format.

SDK buduje komunikat podpisu **w innej kolejności niż plaintext**:
`DID[20] || bindkey[16] || UTC[4]`, liczy SHA-256 i sprawdza ECDSA P-256.
Bindkey pochodzi z bieżącego ECDH; nie jest wstawiany przez serwer do urządzenia.
Certyfikat DER przychodzi osobnym typem `0x07`. Limit 512 bajtów jest pojemnością
bufora w tym SDK, a nie znaną stałą długością certyfikatu produkcyjnego S400.

Zakodowany w SDK publiczny punkt zaufania `root_pk`, X || Y (nie sekret):

```text
bef58b02dae3fff8541aa0448fbac44db7c69a2fa8f0b1b6ff7ad951db6628fa
d7f020ea39a2ee867fdd783fdc2fb086095cc2850413a2802c627dbdc715f4f9
```

SDK parsuje certyfikat, haszuje jego TBS i sprawdza podpis tym kluczem.
Dopiero po sukcesie używa klucza z certyfikatu do sprawdzenia podpisu
rejestracji. Nie znamy jeszcze produkcyjnego certyfikatu ani tego, czy dokładnie
ten sam root znajduje się w S400. Własny self-signed certyfikat nie przechodzi
tej ścieżki. Nazwa `REG_START_WO_PKI` dla `0x15` nie oznacza w tym wydaniu braku
sprawdzania podpisu serwera — analizowana procedura zaczyna się właśnie od `0x15`.

## A, B, C po tej analizie

- **A — generowanie sekretów lokalnie:** tak dla ECDH/HKDF w obu sprawdzonych
  generacjach. Nie wystarcza do zakończenia rejestracji w znalezionym SDK v2.
- **B — obowiązkowe poświadczenie wystawcy:** potwierdzone dla tego SDK v2.
  S400 przyjmuje cały odpowiadający mu transport, lecz odrzuca credential z
  własnym certyfikatem; dokładnie brakuje akceptowanego podpisu i certyfikatu,
  a nie algorytmu generowania tokenu.
- **C — alternatywna lokalna procedura:** brak dowodu na dostępną ścieżkę
  omijającą sprawdzenia. Sprawdzony handler dopuszcza start rejestracji przez
  `0x15`; nie znaleziono gałęzi wyłączającej podpis przy `io=0`.

Przechwycenie certyfikatu może dostarczyć publiczny klucz serwera, ale nie jego
klucz prywatny. Przechwycony podpis dotyczy konkretnego bindkey; samo odtworzenie
go przy nowym ECDH nie powinno przejść weryfikacji. Nie nazywamy tego dowodem
pełnej odporności implementacji firmware na replay lub błędy parsera.

DNS override, własne CA i hooki TLS mogą ujawnić request/response aplikacji.
Nie zastąpią jednak klucza wystawcy podpisu sprawdzanego na urządzeniu. Dlatego
na tym etapie stawianie fikcyjnego backendu Mi Home nie rozwiązuje rozpoznanej
przeszkody. [Analiza APK](MIHOME_V2.md) identyfikuje ścieżki API i logiczne
payloady, ale nie kompletny regionalny routing ani politykę TLS tej rozmowy.

## Co można wykonać teraz, bez adaptera

```bash
uv run python tools/s400_analyze_trace.py captures/s400-pair*.jsonl
uv run pytest tests/test_auth_v2.py
```

Analizator odtwarza przychodzące paczki obu formatów, odczytuje wersję i wykrywa
wysłanie danych przed `0x13`. Wypisuje metadane i wynik analizy; nie wypisuje
MAC, DID, kluczy ani surowych ramek. Jeden plik powinien zawierać jedną sesję.

Moduł `auth_v2.py` niezależnie implementuje format credentialu, obie weryfikacje
podpisów i szyfrowanie 92-bajtowej paczki. Testy używają sztucznego CA i serwera:
zmiana DID, bindkey, UTC lub podpisu jest odrzucana; własny certyfikat nie
przechodzi pod publicznym rootem SDK. **To test modelu kryptograficznego,
nie emulacja firmware i nie zakończony provisioning S400.**

Provisioner odczytuje teraz wersję i dla `2` kończy z konkretnym komunikatem
przed wysłaniem klucza aplikacji. Oddzielne narzędzie badawcze może wykonać
negatywny test pełnego transportu v2, ale nie zapisuje odrzuconych sekretów jako
działających. Obsługa istniejących bindkey i tokenu pozostaje dostępna.

## Jak rozstrzygnąć pozostałe hipotezy

1. Bez BLE: pozyskać obraz firmware dokładnie `2.1.1_0006` / PID
   `0x3BD5` i sprawdzić root, sekwencję `0x13 -> typ 0 -> typ 7` oraz wywołania
   weryfikacji. Katalog publiczny wymienia obraz 153 196 bajtów, ale nie uzyskano
   pliku; nie zastępujemy go innym SDK.
2. Wykonano bez BLE: przeanalizowano nowszy connector aplikacji Mi Home
   obsługujący GET_INFO=2. [Wyniki](MIHOME_V2.md) potwierdzają żądanie podpisu;
   nie znaleziono w tej gałęzi alternatywnego lokalnego wystawiania credentialu.
3. Wykonano na sprzęcie: `0x13`, typ 0 długości 92 i typ 7 z własnym
   certyfikatem zostały odebrane, po czym S400 zwróciła `0x12`.
4. Szukać wyłącznie odtwarzalnego sposobu uzyskania akceptowanego credentialu
   albo alternatywnego, potwierdzonego wejścia w stan registered. Zgadywanie
   komend na charakterystyce `0x8001` nie stanowi dowodu protokołu.

Nie da się odtworzyć dawnych sekretów ECDH z samych dwóch punktów publicznych
w zapisanych captures. Traces celowo nie zachowują prywatnych kluczy. Aby
wykorzystać istniejący trace do dekodowania credentialu, potrzebny byłby dodatkowo
sekret sesji pochodzący z własnego, kontrolowanego klienta.
