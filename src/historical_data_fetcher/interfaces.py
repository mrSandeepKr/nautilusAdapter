from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd


@runtime_checkable
class HistoricalDataFetcher(Protocol):
    """Provider-agnostic contract for normalising API responses into Nautilus DataFrames.

    Implementations MUST NOT persist to disk.
    """

    def fetch_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> "pd.DataFrame": ...
