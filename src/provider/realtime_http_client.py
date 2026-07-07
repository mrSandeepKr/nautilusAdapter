from __future__ import annotations

import time
from collections import deque
from typing import Any

import requests


class RealtimeHttpClient:
    """Generic HTTP client with built-in two-tier rate limiting.

    Enforces both a per-second and per-minute cap transparently on every
    ``get()`` and ``post()`` call. Provider subclasses never need to think
    about throttling.

    Parameters
    ----------
    requests_per_second :
        Maximum sustained request rate per second.
    requests_per_minute :
        Maximum sustained request rate per minute.
    """

    def __init__(
        self,
        requests_per_second: int,
        requests_per_minute: int,
    ) -> None:
        self._rps = requests_per_second
        self._rpm = requests_per_minute
        self._timestamps: deque[float] = deque()
        self._lock: Any = None

    # -- public API ------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Perform a rate-limited GET request."""
        self._throttle()
        return requests.get(url, headers=headers, params=params, timeout=timeout)

    def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Perform a rate-limited POST request."""
        self._throttle()
        return requests.post(url, data=data, headers=headers, timeout=timeout)

    # -- internal --------------------------------------------------------------

    def _throttle(self) -> None:
        """Block until both the per-second and per-minute budgets allow a call."""
        now = time.monotonic()

        # Enforce per-second: wait at least 1/rps seconds since last call
        if self._timestamps:
            elapsed = now - self._timestamps[-1]
            min_gap = 1.0 / self._rps
            if elapsed < min_gap:
                time.sleep(min_gap - elapsed)
                now = time.monotonic()

        # Enforce per-minute: trim timestamps older than 60 s
        one_min_ago = now - 60.0
        while self._timestamps and self._timestamps[0] < one_min_ago:
            self._timestamps.popleft()

        if len(self._timestamps) >= self._rpm:
            oldest = self._timestamps[0]
            sleep_needed = 60.0 - (now - oldest)
            if sleep_needed > 0:
                time.sleep(sleep_needed)

        self._timestamps.append(time.monotonic())
