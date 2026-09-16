# Mi Home: niezależne potwierdzenie auth version 2

Analiza statyczna z 2026-09-09. APK pobrano z
[oficjalnego sklepu Xiaomi](https://app.mi.com/details?id=com.xiaomi.smarthome),
bez logowania, uruchamiania aplikacji, emulatora i Bluetooth. Wersja `11.7.705`
jest także obecna w tablicy ciągów manifestu pobranego APK.

Bezpośredni [artefakt APK na CDN Xiaomi](https://fga1.market.xiaomi.com/download/AppStore/05f575517da7147e99cac51fe1dfc74f5453353fe/com.xiaomi.smarthome.apk),
244 432 389 bajtów, SHA-256:
`fb55b990cb7c782df0049b181fe7ee2d5ce4abe28f97c5999a2ebe95d649d09d`.

| Część APK | SHA-256 |
|---|---|
| `classes13.dex` | `5c18b1c01914360db8cba779b4357079733840ea4f735246a750e5d53f515f8c` |
| `classes14.dex` | `d2da678a49fdff35db4537f37c34e8bc98c8f67f74452e30b771a2d7b062535e` |

Źródłem ustaleń jest kod DEX odczytany przez JADX 1.5.6. Dekompilator zgłosił
błędy w części całego DEX; opisujemy czytelne konkretne gałęzie i porównujemy
je z niezależnym kodem SDK. Nie kompilujemy zdekompilowanego kodu ani nie
traktujemy go jako oryginalnego kodu Java. Pełna dekompilacja pozostaje poza repo.

## Rozpoznanie wersji i kolejność BLE

Oryginalna nazwa klasy w DEX:
`com.xiaomi.smarthome.core.server.internal.bluetooth.security.standardauth.OooOO0`.
W logach przedstawia się jako `BleStandardAuthRegisterConnector`.

Metoda `OooOOo0(int, byte[])` czyta dwa pierwsze bajty GET_INFO jako wersję.
Metoda `OooOo0o()` wyprowadza z ECDH token[12], bindkey[16] i did_key[16].
Callback `standardauth.OooO.onResponse()` po otrzymaniu DID wybiera osobną
ścieżkę **dokładnie dla `version == 2`**.

Ta ścieżka:

1. Wywołuje API `ble_standard_bind` z lokalnie wyprowadzonymi sekretami.
2. Callback `_m_j.zs0`, gałąź v2, odczytuje `success`, `cloud_cert`,
   `cloud_sign` i `utc` z obiektu odpowiedzi.
3. Tworzy plaintext[88]: DID[20], podpis[64], UTC[4] **little-endian**.
4. Szyfruje go kluczem did_key, nonce `10..1b`, AAD `devID`.
5. `_m_j.at0`, gałąź 1, wywołuje `OooOO0.OooOo0(..., true, ...)`,
   która wysyła `13 00 00 00` przez `writeNoRsp` na charakterystykę komend.
6. Callback `standardauth.OooO0O0`, gałąź 1, wysyła zaszyfrowane dane typu 0,
   a po ich potwierdzeniu zdekodowany certyfikat typu 7.
7. Czeka na wynik rejestracji urządzenia.

Kolejność i format zgadzają się z [SDK standard-auth v2](AUTH_V2.md).
To dodatkowy dowód, że dotychczasowa cisza nie wymaga do wyjaśnienia
hipotezy o wadliwym adapterze czy arbitralnym opóźnieniu.

Mi Home przyjmuje też GET_INFO version 3 i ma dla niej dodatkowe pola informacji
urządzenia. W analizowanym callbacku wersja 3 nie wybiera tej samej gałęzi co 2.
**Nie dowodzi to możliwości przełączenia S400 na wersję 3.** GET_INFO jest
odpowiedzią urządzenia; w tej ścieżce nie znaleziono komendy negocjującej jego
wersję auth. Zmiana warunku w aplikacji nie zmieni automatu urządzenia.

## Endpointy i logiczne payloady

Klasa `_m_j.n3` w `classes14.dex` tworzy poniższe `BleNetRequest`.
Konstruktor `BleKeyValuePair(String)` nadaje parametrowi nazwę `data`.
Poniższy JSON opisuje jego wartość **przed dalszym opakowaniem przez klienta
sieciowego**, a nie kompletny zaszyfrowany request HTTP z nagłówkami i cookies.
Nie wysyłaliśmy tych żądań.

`OooOOo(...)`: `POST /device/bltapplydid`:

```json
{
  "mac": "<adres z kontekstu urządzenia>",
  "model": "<model urządzenia>",
  "token": "<lokalnie wyprowadzony token, hex>",
  "did": "<opcjonalny istniejący DID>"
}
```

Pole `did` jest pomijane, jeśli puste. Callback prowadzi do otrzymania DID,
ale nie odtworzono tu całej zewnętrznej koperty odpowiedzi HTTP.

`OooOOO0(...)`: `POST /v2/device/ble_standard_bind`:

```json
{
  "did": "<DID>",
  "token": "<token, hex>",
  "beacon_key": "<bindkey, hex>",
  "props": [
    {"type": "prop", "key": "bind_key", "value": "<bindkey, hex>"},
    {"type": "prop", "key": "smac", "value": "<smac z BleDeviceProp>"}
  ]
}
```

Obie metody mogą dodać `homeId` i `uid`, gdy bieżący obiekt `Home` ma
`permitLevel == 9`. Nie utożsamiamy `smac` z MAC wagi bez dalszej analizy
pochodzenia tej właściwości.

Obiekt wyniku konsumowany przez callback v2:

```json
{
  "success": true,
  "cloud_cert": "<certyfikat DER zakodowany Base64 URL-safe>",
  "cloud_sign": "<podpis 64 bajty zakodowany Base64 URL-safe>",
  "utc": 1700000000
}
```

Wartość czasu powyżej jest przykładowa. Algorytm Base64 potwierdza
`_m_j.eq.OooOO0(..., 24)` w `classes10.dex`: bit `0x10` wybiera alfabet
z `-` i `_`. Certyfikat i podpis nie są ciągami hex. Dla starszej ścieżki
klient używa `POST /device/bltbind` bez dodatkowego pola `beacon_key`.

`BleNetRequest` przechodzi przez zwykły klient Mi Home API. Publiczne, działające
klienty `xiaomi-ble` i `hass-xiaomi-miot` potwierdzają regionalny routing
`https://<region>.api.io.mi.com/app`, sesję `sid=xiaomiio` oraz kopertę
`ENCRYPT-RC4`: nonce, `signed_nonce = SHA-256(ssecurity || nonce)`, szyfrowanie
RC4 po odrzuceniu pierwszych 1024 bajtów strumienia i podpis SHA-1 pól koperty.
Region `cn` nie ma prefiksu. Implementacja ograniczona do dwóch endpointów jest
w `tools/xiaomi_cloud.py`.

Nie przechwycono jeszcze udanego żądania z konta ani odpowiedzi dla tej S400,
więc zgodność bieżącego backendu tych dwóch endpointów pozostaje do testu na
sprzęcie. Narzędzie używa bezpośredniego HTTPS i systemowego magazynu CA; piny
APK nie biorą udziału, ponieważ Mi Home nie pośredniczy w żądaniu.

Pole `smac` zostało rozstrzygnięte przez przepływ danych w APK. Parser
`MiotBleAdvPacket` czyta MAC obecny w FE95, odwraca kolejność sześciu bajtów i
formatuje go wielkimi literami z dwukropkami. Connector pobiera dokładnie tę
wartość z `BleDeviceProp`. W zebranych reklamach S400 osadzony MAC jest zgodny z
adresem urządzenia widzianym przez Windows.

## Co to zmienia dla całkowicie lokalnego provisionera

Token i bindkey są wyprowadzane **przed** żądaniem bindu i przesyłane przez
aplikację do backendu. Nie są sekretem, który urządzenie potrafi dostać tylko
z odpowiedzi chmury. Problemem jest zaakceptowanie rejestracji: SDK v2 wymaga
podpisu powiązanego z tym bindkey i certyfikatu zaufanego wystawcy.

Nie znaleziono w tej ścieżce klucza prywatnego wystawcy ani lokalnej procedury
wystawiania takiego poświadczenia. Aplikacja nie zastępuje błędu tego API
lokalnym podpisem. Własny backend zwracający sam `success: true` nie dostarczy
88-bajtowego poprawnie podpisanego plaintextu.

Do rozstrzygnięcia możliwości obejścia pozostaje **kod firmware S400**, nie
sam wybór emulatora Androida. Publiczny katalog wymienia
[`yunmai.scales.ms104` / `2.1.1_0006`](https://vacuum.mindsolo.net/en/firmwares/3347/versions/23965),
obraz APP o rozmiarze 153 196 bajtów. Pobrana publiczna strona nie podała URL
obrazu (`url: null`); nie pobrano ani nie przeanalizowano tego firmware.
Informacja katalogowa jest tropem do pozyskania pliku, nie dowodem jego zawartości.

## Provisioner z jednorazowym podpisaniem

`tools/s400_xiaomi_pair.py` odtwarza bieżącą gałąź Mi Home bez uruchamiania APK:

1. loguje się do `sid=xiaomiio`, nie zapisując hasła ani cookies;
2. wykonuje ECDH z wagą i lokalnie wyprowadza token, bindkey oraz did_key;
3. wywołuje `bltapplydid`, a następnie `ble_standard_bind`;
4. przed wysłaniem odpowiedzi sprawdza certyfikat względem publicznego root key
   z SDK i podpis danych względem klucza z certyfikatu;
5. wysyła typ 0 i typ 7, wymaga `REGISTER_OK`, wykonuje lokalny login tokenem i
   dopiero wtedy zapisuje sekrety z prawami `0600`.

Jest to świadome odejście od celu „zero Xiaomi podczas pierwszego bindu”. Po
udanym bindzie ścieżka pomiarowa pozostaje całkowicie lokalna. Na dzień tej
aktualizacji klient ma testy jednostkowe koperty i walidacji danych, ale nie ma
jeszcze udanego wyniku z produkcyjnego konta i S400.

## Odtworzenie analizy APK

Z pobranego APK (wyłącznie w katalogu laboratoryjnym):

```bash
sha256sum mihome.apk
unzip -j mihome.apk classes13.dex classes14.dex classes10.dex -d dex
jadx -r --no-replace-consts -d decompiled dex/classes13.dex
jadx -r --no-replace-consts --single-class _m_j.n3 \
  --single-class-output n3.java dex/classes14.dex
jadx -r --no-replace-consts --single-class _m_j.eq \
  --single-class-output eq.java dex/classes10.dex
rg -n 'bindDidToServerV2|cloud_cert|cloud_sign|writeCloudCert' decompiled
rg -n 'bltapplydid|ble_standard_bind' n3.java
```

JADX może nadawać aliasy pakietom; oryginalne nazwy `com.xiaomi.smarthome...`
są zachowane w DEX i komentarzach anonimowych callbacków. Obfuscowane nazwy
klas są specyficzne dla wskazanego APK. To nie są stabilne nazwy hooków
obejmujące wszystkie wersje Mi Home.
