import json
import logging
from pathlib import Path

from .indicators import fetch_indicators

log = logging.getLogger(__name__)


def load_watchlist(path: str = "watchlist.json") -> list[dict]:
    with open(path) as f:
        return json.load(f)


def scan(watchlist: list[dict], rsi_threshold: float, sma_margin: float) -> list[dict]:
    """Scan watchlist for buy signals.

    Args:
        watchlist: list of {"ticker", "exchange", "currency", "sector", "type"}
        rsi_threshold: RSI must be below this (e.g. 50 for test, 30 for prod)
        sma_margin: price must be <= SMA200 * (1 + sma_margin)

    Returns list of signals:
        [{...watchlist fields, "price", "rsi", "sma200"}]
    """
    tickers = [w["ticker"] for w in watchlist]
    indicators = fetch_indicators(tickers)

    ticker_map = {w["ticker"]: w for w in watchlist}
    signals = []

    for ticker, data in indicators.items():
        rsi = data["rsi"]
        price = data["price"]
        sma200 = data["sma200"]
        sma_limit = sma200 * (1 + sma_margin)

        if rsi < rsi_threshold and price <= sma_limit:
            signal = {**ticker_map[ticker], **data}
            signals.append(signal)
            log.info("SIGNAL: %s — RSI=%.1f < %s, price=%.2f <= SMA200+%.0f%%=%.2f",
                     ticker, rsi, rsi_threshold, price, sma_margin * 100, sma_limit)
        else:
            log.debug("%s — no signal (RSI=%.1f, price=%.2f, sma_limit=%.2f)",
                      ticker, rsi, price, sma_limit)

    log.info("Scan complete: %d signals out of %d tickers", len(signals), len(tickers))
    return signals
