import logging
import yfinance as yf
import pandas as pd

log = logging.getLogger(__name__)


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_indicators(tickers: list[str]) -> dict[str, dict]:
    """Batch download price data and compute RSI(14) + SMA200 for each ticker.

    Returns dict keyed by ticker:
        {"price": float, "rsi": float, "sma200": float}
    Returns None for a ticker if data is insufficient.
    """
    if not tickers:
        return {}

    log.info("Downloading data for %d tickers", len(tickers))
    data = yf.download(tickers, period="2y", interval="1d", group_by="ticker", threads=True)

    results = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                close = data["Close"].dropna()
            else:
                close = data[ticker]["Close"].dropna()

            if len(close) < 200:
                log.warning("%s: only %d data points, skipping", ticker, len(close))
                continue

            rsi = compute_rsi(close, 14)
            sma200 = close.rolling(200).mean()

            current_price = float(close.iloc[-1])
            current_rsi = float(rsi.iloc[-1])
            current_sma200 = float(sma200.iloc[-1])

            results[ticker] = {
                "price": current_price,
                "rsi": current_rsi,
                "sma200": current_sma200,
            }
            log.info("%s — price=%.2f rsi=%.1f sma200=%.2f",
                     ticker, current_price, current_rsi, current_sma200)

        except Exception as e:
            log.error("%s: error computing indicators: %s", ticker, e)

    return results
