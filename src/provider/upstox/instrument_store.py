"""Upstox master-contract downloader, cache, and symbol-to-key resolver.

Usage::

    from provider.upstox.instrument_store import (
        InstrumentStore,
    )

    store = InstrumentStore()
    key = store.resolve("RELIANCE")       # "NSE_EQ|INE002A01018"
    key = store.resolve("NIFTY")          # "NSE_INDEX|Nifty 50"
    key = store.resolve("TCS")            # "NSE_EQ|INE467B01029"

    # Search when you don't know the exact symbol
    hits = store.search("HDFC")
    for h in hits:
        print(h["trading_symbol"], h["instrument_key"])
"""

from __future__ import annotations

import gzip
import json
import time
from typing import Any
from urllib.request import urlopen

from utility.file_storage import FileStorage

__all__ = ["InstrumentStore"]

_MASTER_CONTRACT_URLS: dict[str, str] = {
    "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
    "MCX": "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json.gz",
    "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "COMPLETE": "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
    "GLOBAL": "https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz",
}

_REFRESH_INTERVAL_SECONDS = 6 * 3600
class InstrumentStore:
    """Download, cache, and look up Upstox instrument keys by trading symbol.

    Parameters
    ----------
    exchange :
        Default exchange to use when *exchange* is not passed to
        :meth:`resolve`.  One of ``"NSE"``, ``"BSE"``, ``"MCX"``.
    refresh_seconds :
        Maximum age (in seconds) of a cached file before it is re-downloaded.
    """

    def __init__(
        self,
        exchange: str = "NSE",
        refresh_seconds: int = _REFRESH_INTERVAL_SECONDS,
    ) -> None:
        self._storage = FileStorage("instrument_cache")
        self._exchange = exchange.upper()
        self._refresh_seconds = refresh_seconds
        self._instruments: list[dict[str, Any]] | None = None
        self._by_symbol: dict[str, list[dict[str, Any]]] = {}
        self._loaded_at: float = 0.0

    def resolve(self, symbol: str, *, exchange: str | None = None) -> str | None:
        """Return the *instrument_key* for a trading *symbol*.

        Parameters
        ----------
        symbol :
            The trading symbol (e.g. ``"RELIANCE"``, ``"TCS"``, ``"NIFTY"``).
            Lookup is case-insensitive.
        exchange :
            Optional exchange filter (``"NSE"``, ``"BSE"``, ``"MCX"``).
            Defaults to the store's configured exchange.

        Returns
        -------
        The ``instrument_key`` string or ``None`` if nothing matched.
        """
        self._ensure_loaded()
        exchange = (exchange or self._exchange).upper()
        candidates = self._by_symbol.get(symbol.upper(), [])
        for c in candidates:
            if c.get("exchange", "").upper() == exchange:
                return c["instrument_key"]
        if candidates:
            return candidates[0]["instrument_key"]
        return None

    def search(
        self, query: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search instruments by name or trading symbol (case-insensitive).

        Parameters
        ----------
        query :
            Sub-string to match against ``trading_symbol`` or ``name``.
        limit :
            Maximum number of results to return.

        Returns
        -------
        A list of matching instrument dicts (each contains at least
        ``trading_symbol``, ``instrument_key``, ``segment``, ``name``).
        """
        self._ensure_loaded()
        q = query.lower()
        results = []
        for inst in self._instruments:
            if q in inst.get("trading_symbol", "").lower() or q in inst.get(
                "name", ""
            ).lower():
                results.append(inst)
                if len(results) >= limit:
                    break
        return results

    def refresh(self) -> None:
        """Force a fresh download on the next lookup."""
        self._instruments = None
        self._by_symbol.clear()
        self._loaded_at = 0.0

    def _ensure_loaded(self) -> None:
        if self._instruments is not None and (
            time.monotonic() - self._loaded_at
        ) < self._refresh_seconds:
            return

        cache_key = f"{self._exchange}.json.gz"

        if self._storage.exists(cache_key) and self._is_fresh(cache_key):
            self._load_from_cache(cache_key)
        else:
            self._download_and_cache(cache_key)

    def _is_fresh(self, cache_key: str) -> bool:
        mtime = self._storage.mtime(cache_key)
        if mtime is None:
            return False
        return (time.time() - mtime) < self._refresh_seconds

    def _load_from_cache(self, cache_key: str) -> None:
        data = self._storage.get(cache_key)
        assert data is not None
        raw = json.loads(gzip.decompress(data))
        self._build_index(raw)

    def _download_and_cache(self, cache_key: str) -> None:
        url = _MASTER_CONTRACT_URLS.get(self._exchange)
        if url is None:
            raise ValueError(
                f"Unknown exchange: {self._exchange!r}. "
                f"Use one of: {list(_MASTER_CONTRACT_URLS)}"
            )

        with urlopen(url) as response:
            raw_bytes = response.read()

        self._storage.set(cache_key, raw_bytes)

        raw = json.loads(gzip.decompress(raw_bytes))
        self._build_index(raw)

    def _build_index(self, raw: list[dict[str, Any]]) -> None:
        self._instruments = raw
        self._by_symbol.clear()
        for inst in raw:
            symbol = inst.get("trading_symbol", "").upper()
            if symbol:
                self._by_symbol.setdefault(symbol, []).append(inst)
        self._loaded_at = time.monotonic()
