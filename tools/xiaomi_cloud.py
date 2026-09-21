"""Minimal Xiaomi Home API client used by the one-time S400 provisioner.

This module deliberately implements only account login and the two BLE
standard-auth endpoints needed during registration.  It does not enumerate
devices or retrieve existing keys from an account.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import string
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

LOGIN_URL = "https://account.xiaomi.com/pass/serviceLogin"
LOGIN_AUTH_URL = "https://account.xiaomi.com/pass/serviceLoginAuth2"
LOGIN_CALLBACK = "https://sts.api.io.mi.com/sts"
REGIONS = frozenset({"cn", "de", "us", "ru", "tw", "sg", "in", "i2"})


class XiaomiCloudError(RuntimeError):
    """The Xiaomi account or API request did not complete successfully."""


class XiaomiAuthenticationError(XiaomiCloudError):
    """Xiaomi rejected the supplied account credentials."""


class XiaomiVerificationRequired(XiaomiAuthenticationError):
    """The account requires an interactive verification in a browser."""

    def __init__(self, url: str) -> None:
        super().__init__("Xiaomi account verification is required")
        self.url = url


class XiaomiCaptchaRequired(XiaomiAuthenticationError):
    """The account captcha could not be completed interactively."""

    def __init__(self, url: str) -> None:
        super().__init__("Xiaomi account login requires a captcha")
        self.url = url


@dataclass(frozen=True, slots=True, repr=False)
class StandardBindResponse:
    """Root-signed material returned for BLE standard-auth v2."""

    certificate_der: bytes
    signature: bytes
    utc: int


def _json_response(raw: bytes) -> dict[str, Any]:
    """Decode Xiaomi's optional anti-JSON-hijacking response prefix."""
    text = raw.decode("utf-8")
    if text.startswith("&&&START&&&"):
        text = text[11:]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise XiaomiCloudError("Xiaomi returned a non-object JSON response")
    return value


def _rc4(key: bytes, value: bytes, *, drop: int = 1024) -> bytes:
    """Apply the legacy RC4 stream used by Xiaomi's encrypted API envelope."""
    if not key:
        raise ValueError("RC4 key cannot be empty")
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) & 0xFF
        state[i], state[j] = state[j], state[i]

    i = 0
    j = 0
    result = bytearray()
    for index in range(drop + len(value)):
        i = (i + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        stream = state[(state[i] + state[j]) & 0xFF]
        if index >= drop:
            result.append(value[index - drop] ^ stream)
    return bytes(result)


def _sha1_signature(
    method: str, url: str, fields: dict[str, str], signed_nonce: str
) -> str:
    path = urlparse(url).path
    if path.startswith("/app/"):
        path = path[4:]
    parts = [method.upper(), path]
    parts.extend(f"{key}={value}" for key, value in fields.items())
    parts.append(signed_nonce)
    digest = hashlib.sha1("&".join(parts).encode()).digest()  # noqa: S324
    return base64.b64encode(digest).decode()


def _signed_nonce(ssecurity: str, nonce: str) -> str:
    digest = hashlib.sha256(
        base64.b64decode(ssecurity) + base64.b64decode(nonce)
    ).digest()
    return base64.b64encode(digest).decode()


def _nonce(now_ms: int | None = None) -> str:
    millis = round(time.time() * 1000) if now_ms is None else now_ms
    value = os.urandom(8) + (millis // 60000).to_bytes(4, "big")
    return base64.b64encode(value).decode()


def _encrypted_fields(
    method: str,
    url: str,
    fields: dict[str, str],
    ssecurity: str,
    nonce: str,
) -> dict[str, str]:
    signed_nonce = _signed_nonce(ssecurity, nonce)
    encrypted = dict(fields)
    encrypted["rc4_hash__"] = _sha1_signature(method, url, encrypted, signed_nonce)
    key = base64.b64decode(signed_nonce)
    for name, value in encrypted.items():
        encrypted[name] = base64.b64encode(_rc4(key, value.encode("utf-8"))).decode()
    encrypted.update(
        {
            "signature": _sha1_signature(method, url, encrypted, signed_nonce),
            "ssecurity": ssecurity,
            "_nonce": nonce,
        }
    )
    return encrypted


def _decode_urlsafe(value: str, name: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeEncodeError) as error:
        raise XiaomiCloudError(f"Xiaomi returned invalid {name} encoding") from error


class XiaomiCloudClient:
    """Small stateful client for one Xiaomi account session."""

    def __init__(
        self,
        username: str,
        password: str,
        region: str,
        *,
        verification_callback: Callable[[str], None] | None = None,
        captcha_callback: Callable[[bytes], str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not username or not password:
            raise ValueError("username and password are required")
        if region not in REGIONS:
            raise ValueError(f"unsupported Xiaomi region: {region}")
        self.username = username
        self._password = password
        self.region = region
        self.timeout = timeout
        self._verification_callback = verification_callback
        self._captcha_callback = captcha_callback
        self._device_id = "".join(
            random.choice(string.ascii_lowercase) for _ in range(6)
        )
        agent_id = "".join(random.choice("ABCDE") for _ in range(13))
        self._user_agent = (
            "Android-7.1.1-1.0.0-ONEPLUS A3010-136-"
            f"{agent_id} APP/xiaomi.smarthome APPV/62830"
        )
        self._cookies = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookies))
        self._ssecurity: str | None = None
        self._user_id: str | None = None
        self._service_token: str | None = None

    def _set_account_cookie(self, name: str, value: str) -> None:
        self._cookies.set_cookie(
            Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain="account.xiaomi.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        )

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        request_headers = {"User-Agent": self._user_agent, **(headers or {})}
        body = None
        if fields is not None:
            body = urlencode(fields).encode("ascii")
            request_headers.setdefault(
                "Content-Type", "application/x-www-form-urlencoded"
            )
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as error:
            raise XiaomiCloudError(
                f"Xiaomi HTTP request failed with status {error.code}"
            ) from error
        except URLError as error:
            raise XiaomiCloudError("Could not connect to Xiaomi") from error

    def _cookie(self, name: str) -> str | None:
        for cookie in self._cookies:
            if cookie.name == name:
                return cookie.value
        return None

    def login(self) -> None:
        """Create a xiaomiio session without persisting account credentials."""
        self._cookies.clear()
        self._set_account_cookie("sdkVersion", "accountsdk-18.8.15")
        self._set_account_cookie("deviceId", self._device_id)
        self._set_account_cookie("userId", self.username)
        first_url = LOGIN_URL + "?" + urlencode({"sid": "xiaomiio", "_json": "true"})
        first = _json_response(self._request(first_url))
        sign = first.get("_sign")
        if not isinstance(sign, str) or not sign:
            raise XiaomiAuthenticationError("Xiaomi did not issue a login signature")

        attempts = 0
        captcha_code: str | None = None
        while True:
            attempts += 1
            auth_params: dict[str, str | int] = {"_json": "true"}
            fields = {
                "sid": str(first.get("sid") or "xiaomiio"),
                "hash": hashlib.md5(  # noqa: S324
                    self._password.encode()
                )
                .hexdigest()
                .upper(),
                "callback": str(first.get("callback") or LOGIN_CALLBACK),
                "qs": str(first.get("qs") or "%3Fsid%3Dxiaomiio%26_json%3Dtrue"),
                "user": self.username,
                "_sign": sign,
            }
            if captcha_code:
                fields["captCode"] = captcha_code
                auth_params["_dc"] = round(time.time() * 1000)
            auth_url = LOGIN_AUTH_URL + "?" + urlencode(auth_params)
            auth = _json_response(
                self._request(
                    auth_url,
                    method="POST",
                    fields=fields,
                )
            )
            notification_url = auth.get("notificationUrl")
            if isinstance(notification_url, str) and notification_url:
                if self._verification_callback is None or attempts >= 3:
                    raise XiaomiVerificationRequired(notification_url)
                self._verification_callback(notification_url)
                continue
            captcha_url = auth.get("captchaUrl")
            if isinstance(captcha_url, str) and captcha_url:
                absolute_url = urljoin(LOGIN_URL, captcha_url)
                if captcha_code is not None:
                    raise XiaomiAuthenticationError(
                        "Xiaomi rejected the submitted captcha"
                    )
                if self._captcha_callback is None or attempts >= 4:
                    raise XiaomiCaptchaRequired(absolute_url)
                captcha_code = self._captcha_callback(self._request(absolute_url))
                if not captcha_code:
                    raise XiaomiCaptchaRequired(absolute_url)
                continue

            location = auth.get("location")
            ssecurity = auth.get("ssecurity")
            user_id = auth.get("userId")
            if not all(
                isinstance(v, (str, int)) and str(v)
                for v in (location, ssecurity, user_id)
            ):
                raise XiaomiAuthenticationError("Xiaomi rejected the account login")
            location_host = urlparse(str(location)).hostname or ""
            if not location_host.endswith((".mi.com", ".xiaomi.com")):
                raise XiaomiAuthenticationError(
                    "Xiaomi returned an invalid login redirect"
                )
            self._ssecurity = str(ssecurity)
            self._user_id = str(user_id)
            self._request(str(location))
            self._service_token = self._cookie("serviceToken")
            if not self._service_token:
                raise XiaomiAuthenticationError("Xiaomi did not issue a service token")
            return

    def login_via_browser(self, cdp_url: str) -> None:
        """Create an API session from a user-authenticated Chromium profile."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise XiaomiCloudError(
                "Browser login requires the playwright package"
            ) from error

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.connect_over_cdp(
                    cdp_url, timeout=round(self.timeout * 1000)
                )
            except Exception as error:
                raise XiaomiCloudError(
                    "Could not connect to the local browser login session"
                ) from error
            contexts = browser.contexts
            if not contexts:
                raise XiaomiCloudError("The local browser has no active context")
            context = contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            account_cookies = context.cookies(["https://account.xiaomi.com/"])
            if not any(
                cookie.get("name") == "passToken" and cookie.get("value")
                for cookie in account_cookies
            ):
                raise XiaomiAuthenticationError(
                    "Dedicated browser login is not complete; no request was sent"
                )

            page.goto(
                LOGIN_URL + "?" + urlencode({"sid": "xiaomiio", "_json": "true"}),
                wait_until="domcontentloaded",
                timeout=round(self.timeout * 1000),
            )
            first = _json_response(page.locator("body").inner_text().encode())
            sign = first.get("_sign")
            active_session = (
                first.get("securityStatus") == 0
                and bool(first.get("location"))
                and bool(first.get("psecurity"))
            )
            if not (isinstance(sign, str) and sign) and not active_session:
                raise XiaomiAuthenticationError(
                    "Browser session cannot refresh xiaomiio credentials"
                )

            fields = {
                "sid": str(first.get("sid") or "xiaomiio"),
                "hash": hashlib.md5(self._password.encode()).hexdigest().upper(),  # noqa: S324
                "callback": str(first.get("callback") or LOGIN_CALLBACK),
                "qs": str(first.get("qs") or "%3Fsid%3Dxiaomiio%26_json%3Dtrue"),
                "user": self.username,
                "_json": "true",
            }
            if isinstance(sign, str) and sign:
                fields["_sign"] = sign
            with page.expect_navigation(
                wait_until="domcontentloaded",
                timeout=round(self.timeout * 1000),
            ):
                page.evaluate(
                    """fields => {
                        const form = document.createElement("form");
                        form.method = "POST";
                        form.action = "https://account.xiaomi.com/pass/serviceLoginAuth2";
                        for (const [name, value] of Object.entries(fields)) {
                            const input = document.createElement("input");
                            input.type = "hidden";
                            input.name = name;
                            input.value = value;
                            form.appendChild(input);
                        }
                        document.body.appendChild(form);
                        form.submit();
                    }""",
                    fields,
                )
            auth = _json_response(page.locator("body").inner_text().encode())
            notification_url = auth.get("notificationUrl")
            if isinstance(notification_url, str) and notification_url:
                raise XiaomiVerificationRequired(notification_url)
            captcha_url = auth.get("captchaUrl")
            if isinstance(captcha_url, str) and captcha_url:
                raise XiaomiCaptchaRequired(urljoin(LOGIN_URL, captcha_url))

            location = auth.get("location")
            ssecurity = auth.get("ssecurity")
            user_id = auth.get("userId")
            if not all(
                isinstance(value, (str, int)) and str(value)
                for value in (location, ssecurity, user_id)
            ):
                raise XiaomiAuthenticationError(
                    "Xiaomi rejected the browser-backed account login"
                )
            location_host = urlparse(str(location)).hostname or ""
            if not location_host.endswith((".mi.com", ".xiaomi.com")):
                raise XiaomiAuthenticationError(
                    "Xiaomi returned an invalid browser login redirect"
                )
            page.goto(
                str(location),
                wait_until="domcontentloaded",
                timeout=round(self.timeout * 1000),
            )
            service_token = next(
                (
                    cookie["value"]
                    for cookie in context.cookies([str(location)])
                    if cookie.get("name") == "serviceToken"
                ),
                None,
            )
            if not service_token:
                raise XiaomiAuthenticationError(
                    "Browser login did not issue a service token"
                )
            self._ssecurity = str(ssecurity)
            self._user_id = str(user_id)
            self._service_token = service_token

    def _api_url(self, path: str) -> str:
        prefix = "" if self.region == "cn" else f"{self.region}."
        return f"https://{prefix}api.io.mi.com/app/{path.lstrip('/')}"

    def _api(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._ssecurity or not self._user_id or not self._service_token:
            raise XiaomiAuthenticationError("Xiaomi client is not logged in")
        url = self._api_url(path)
        nonce = _nonce()
        fields = _encrypted_fields(
            "POST",
            url,
            {"data": json.dumps(payload, separators=(",", ":"))},
            self._ssecurity,
            nonce,
        )
        cookie = "; ".join(
            (
                f"userId={self._user_id}",
                f"serviceToken={self._service_token}",
                f"yetAnotherServiceToken={self._service_token}",
                "locale=en_GB",
                "timezone=GMT+02:00",
                "is_daylight=1",
                "dst_offset=3600000",
                "channel=MI_APP_STORE",
                "sdkVersion=accountsdk-18.8.15",
                f"deviceId={self._device_id}",
            )
        )
        raw = self._request(
            url,
            method="POST",
            fields=fields,
            headers={
                "Accept-Encoding": "identity",
                "Cookie": cookie,
                "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
                "X-XIAOMI-PROTOCAL-FLAG-CLI": "PROTOCAL-HTTP2",
            },
        )
        try:
            return _json_response(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, XiaomiCloudError):
            key = base64.b64decode(_signed_nonce(self._ssecurity, nonce))
            try:
                return _json_response(_rc4(key, base64.b64decode(raw)))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise XiaomiCloudError(
                    "Xiaomi returned an unreadable encrypted response"
                ) from error

    @staticmethod
    def _result(response: dict[str, Any], operation: str) -> dict[str, Any]:
        code = response.get("code", 0)
        if code not in (0, "0", None):
            raise XiaomiCloudError(f"Xiaomi rejected {operation} (code {code})")
        result = response.get("result", response)
        if not isinstance(result, dict):
            raise XiaomiCloudError(f"Xiaomi returned no result for {operation}")
        return result

    def apply_did(
        self,
        *,
        mac: str,
        model: str,
        token_hex: str,
        existing_did: str | None = None,
    ) -> str:
        """Register locally derived token material and obtain a BLE DID."""
        payload = {"mac": mac, "model": model, "token": token_hex}
        if existing_did:
            payload["did"] = existing_did
        result = self._result(
            self._api("/device/bltapplydid", payload), "DID allocation"
        )
        did = result.get("did")
        if not isinstance(did, str) or not did or len(did.encode()) > 20:
            raise XiaomiCloudError("Xiaomi returned an invalid BLE DID")
        return did

    def bind_standard(
        self,
        *,
        did: str,
        token_hex: str,
        bindkey_hex: str,
        smac: str,
    ) -> StandardBindResponse:
        """Request the root-signed registration credential for auth v2."""
        payload = {
            "did": did,
            "token": token_hex,
            "beacon_key": bindkey_hex,
            "props": [
                {"type": "prop", "key": "bind_key", "value": bindkey_hex},
                {"type": "prop", "key": "smac", "value": smac},
            ],
        }
        result = self._result(
            self._api("/v2/device/ble_standard_bind", payload),
            "BLE standard bind",
        )
        if result.get("success") is not True:
            raise XiaomiCloudError("Xiaomi did not approve BLE standard bind")
        cert = result.get("cloud_cert")
        signature = result.get("cloud_sign")
        utc = result.get("utc")
        if not isinstance(cert, str) or not isinstance(signature, str):
            raise XiaomiCloudError("Xiaomi omitted registration credential fields")
        if not isinstance(utc, int) or not 0 <= utc <= 0xFFFFFFFF:
            raise XiaomiCloudError("Xiaomi returned an invalid registration time")
        certificate_der = _decode_urlsafe(cert, "cloud certificate")
        signature_bytes = _decode_urlsafe(signature, "cloud signature")
        if not 0 < len(certificate_der) <= 512 or len(signature_bytes) != 64:
            raise XiaomiCloudError("Xiaomi returned invalid credential lengths")
        return StandardBindResponse(certificate_der, signature_bytes, utc)
