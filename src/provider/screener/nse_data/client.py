from __future__ import annotations

from nselib import capital_market


class NseData:

    @staticmethod
    def nifty_50() -> list[str]:
        return capital_market.nifty50_equity_list()["Symbol"].tolist()

    @staticmethod
    def nifty_next_50() -> list[str]:
        return capital_market.niftynext50_equity_list()["Symbol"].tolist()

    @staticmethod
    def nifty_midcap_150() -> list[str]:
        return capital_market.niftymidcap150_equity_list()["Symbol"].tolist()

    @staticmethod
    def nifty_smallcap_250() -> list[str]:
        return capital_market.niftysmallcap250_equity_list()["Symbol"].tolist()

    @staticmethod
    def fno_stocks() -> list[str]:
        return capital_market.fno_equity_list()["symbol"].tolist()

    @staticmethod
    def all_equities() -> list[str]:
        return capital_market.equity_list()["SYMBOL"].tolist()
