from __future__ import annotations

import pandas as pd

NAUTILUS_COLUMNS = (
    "ts_event",
    "ts_init",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def empty_nautilus_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_event": pd.Series([], dtype="uint64[pyarrow]"),
            "ts_init": pd.Series([], dtype="uint64[pyarrow]"),
            "open": pd.Series([], dtype="float64[pyarrow]"),
            "high": pd.Series([], dtype="float64[pyarrow]"),
            "low": pd.Series([], dtype="float64[pyarrow]"),
            "close": pd.Series([], dtype="float64[pyarrow]"),
            "volume": pd.Series([], dtype="uint64[pyarrow]"),
        }
    )
