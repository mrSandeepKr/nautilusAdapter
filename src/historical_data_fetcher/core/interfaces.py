from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd


@runtime_checkable
class HistoricalDataFetcher(Protocol):
    """Provider-agnostic contract for backtest-ready historical data fetchers.

    Implementations are responsible for parsing provider-specific API
    responses and transforming them into Nautilus Trader's strict Parquet
    bar schema (see ``core/README.md``).
    """

    def fetch_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> Path | None:
        """Fetch candles for ``instrument`` between ``from_date`` and ``to_date``.

        Args:
            instrument: Provider-specific instrument key (e.g. ``NSE_INDEX|Nifty 50``).
            interval: High-level interval string (e.g. ``1minute``, ``1day``).
            from_date: Start date (provider-expected format, typically ``YYYY-MM-DD``).
            to_date: End date (provider-expected format, typically ``YYYY-MM-DD``).

        Returns:
            Path to the written Parquet file on success, or ``None`` if the
            provider wrote no rows.
        """
        ...


@runtime_checkable
class DataStore(Protocol):
    """User-facing contract for offline-first historical data reads.

    Implementations serve from local Parquet storage when available and
    otherwise delegate to a wrapped :class:`HistoricalDataFetcher`, which
    writes the freshly fetched file back into the store.
    """

    def get_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> "pd.DataFrame":
        """Return candles for ``[from_date, to_date]`` as a Nautilus DataFrame."""
        ...