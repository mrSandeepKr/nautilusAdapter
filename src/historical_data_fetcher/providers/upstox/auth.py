import datetime
import json
import secrets
import threading
import time
import urllib.parse
from pathlib import Path

import pyotp
import pytz
import requests

from historical_data_fetcher.providers.upstox.exceptions import (
    MissingAuthenticationError,
    RedirectChainError,
    TOTPGenerationError,
    TokenExchangeError,
    TwoFactorAuthError,
)

_AUTHORIZE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
_LOGIN_TIMEOUT_MS = 90_000
_FIELD_TIMEOUT_MS = 25_000
_IST = pytz.timezone("Asia/Kolkata")


def _generate_totp(secret: str) -> str:
    if not secret:
        raise TOTPGenerationError("UPSTOX_TOTP_SECRET is empty.")
    try:
        return pyotp.TOTP(secret.replace(" ", "")).now()
    except Exception as exc:
        raise TOTPGenerationError(f"Failed to generate TOTP code: {exc}") from exc


def _next_expiry_ist() -> datetime.datetime:
    now_ist = datetime.datetime.now(_IST)
    expiry = now_ist.replace(hour=3, minute=30, second=0, microsecond=0)
    if now_ist >= expiry:
        expiry += datetime.timedelta(days=1)
    return expiry


class _TokenManager:
    """Stores the access token and its expiry timestamp as JSON on disk."""

    def __init__(self, token_filepath: Path) -> None:
        self.token_filepath = Path(token_filepath)

    def get_token(self) -> str | None:
        if not self.token_filepath.exists():
            return None
        try:
            data = json.loads(self.token_filepath.read_text())
        except (json.JSONDecodeError, ValueError):
            return None
        token = data.get("access_token")
        expires_at = data.get("expires_at")
        if not token or not expires_at:
            return None
        try:
            expiry_dt = datetime.datetime.fromisoformat(expires_at)
            now_ist = datetime.datetime.now(_IST)
            if now_ist + datetime.timedelta(hours=1) >= expiry_dt:
                return None
            return token
        except (ValueError, TypeError):
            return None

    def save_token(self, token: str, expires_at: str) -> None:
        data = {
            "access_token": token,
            "expires_at": expires_at,
        }
        self.token_filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.token_filepath.with_suffix(self.token_filepath.suffix + ".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(self.token_filepath)


class UpstoxAuthenticator:
    """Automates the Upstox OAuth2 login + TOTP flow and caches the access token.

    The current Upstox OAuth login is a three-step flow:
      1. Enter mobile number → request OTP
      2. Enter TOTP (from authenticator app) → Continue
      3. Enter 6-digit trading PIN → Continue

    After approval, Upstox redirects to ``redirect_uri`` with a ``code`` query
    parameter; that code is exchanged at the v2 token endpoint for an
    ``access_token``.

    This module performs zero data fetching — it only authenticates.
    """

    def __init__(
        self,
        mobile_no: str,
        pin: str,
        totp_secret: str,
        api_key: str,
        api_secret: str,
        redirect_uri: str,
        token_cache_path: Path,
        use_cache: bool = True,
    ) -> None:
        self.mobile_no = mobile_no
        self.pin = pin
        self.totp_secret = totp_secret
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self._use_cache = use_cache
        self._cache = _TokenManager(token_cache_path)
        self._lock = threading.Lock()

    def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, reusing cache unless ``force_refresh``.

        Thread-safe: a threading lock ensures only one caller runs the
        Playwright login flow at a time.

        Proactive refresh: if the cached token has less than 1 hour until
        expiry, it is treated as stale and the login flow is re-run.
        """
        with self._lock:
            if not force_refresh and self._use_cache:
                cached = self._cache.get_token()
                if cached:
                    return cached
            code = self._run_login_flow()
            token, expires_at = self._exchange_code(code)
            self._cache.save_token(token, expires_at)
            return token

    def _build_authorize_url(self) -> str:
        params = {
            "response_type": "code",
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
            "state": secrets.token_urlsafe(16),
        }
        return f"{_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def _run_login_flow(self) -> str:
        try:
            from playwright.sync_api import (
                TimeoutError as PlaywrightTimeoutError,
                sync_playwright,
            )
        except ImportError as exc:
            raise MissingAuthenticationError(
                "playwright is not installed; run `pip install playwright && "
                "playwright install chromium` to enable automated Upstox login."
            ) from exc

        authorize_url = self._build_authorize_url()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            code_holder: dict[str, str] = {}

            def _on_request(request) -> None:
                if "code=" in (request.url or "") and self.redirect_uri.split("?")[
                    0
                ] in request.url:
                    parsed = urllib.parse.urlparse(request.url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "code" in qs:
                        code_holder["code"] = qs["code"][0]

            page.on("request", _on_request)

            try:
                page.goto(authorize_url, timeout=_LOGIN_TIMEOUT_MS)

                page.wait_for_selector("#mobileNum", timeout=_FIELD_TIMEOUT_MS)
                page.fill("#mobileNum", self.mobile_no)
                page.click("button:has-text('Get OTP')")

                page.wait_for_selector("#otpNum", timeout=_FIELD_TIMEOUT_MS)
                otp = _generate_totp(self.totp_secret)
                page.fill("#otpNum", otp)
                page.click("button:has-text('Continue')")

                page.wait_for_selector(
                    "input[type='password']", timeout=_FIELD_TIMEOUT_MS
                )
                pin_inputs = page.locator("input[type='password']").all()
                if len(pin_inputs) >= len(self.pin):
                    for i, digit in enumerate(self.pin):
                        pin_inputs[i].fill(digit)
                else:
                    pin_inputs[0].fill(self.pin)
                page.click("button:has-text('Continue')")

                deadline = time.time() + (_LOGIN_TIMEOUT_MS / 1000)
                while time.time() < deadline:
                    if code_holder.get("code"):
                        return code_holder["code"]
                    page.wait_for_timeout(250)

                raise RedirectChainError(
                    "Login completed but no authorization `code` was captured. "
                    f"Final URL: {page.url}"
                )

            except PlaywrightTimeoutError as exc:
                raise TwoFactorAuthError(
                    f"Timed out waiting for Upstox login page element: {exc}"
                ) from exc
            finally:
                browser.close()

    def _exchange_code(self, code: str) -> tuple[str, str]:
        payload = {
            "code": code,
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            response = requests.post(_TOKEN_URL, data=payload, timeout=15)
        except requests.RequestException as exc:
            raise TokenExchangeError(
                f"Network error during token exchange: {exc}"
            ) from exc

        if response.status_code != 200:
            raise TokenExchangeError(
                f"Token endpoint returned {response.status_code}: {response.text}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise TokenExchangeError(
                f"Token response was not JSON: {exc}"
            ) from exc

        token = body.get("access_token")
        if not token:
            raise TokenExchangeError(f"No access_token in response: {body}")

        expires_in = body.get("expires_in")
        if expires_in:
            expires_at = (
                datetime.datetime.now(_IST)
                + datetime.timedelta(seconds=int(expires_in))
            ).isoformat()
        else:
            expires_at = _next_expiry_ist().isoformat()
        return token, expires_at
