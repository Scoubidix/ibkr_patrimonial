import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .ibkr import IBKRClient
from .scanner import load_watchlist, scan
from .telegram_bot import TelegramBot, load_pending, save_pending

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

# Config from env
IB_HOST = os.environ.get("IB_HOST", "ib-gateway")
IB_PORT = int(os.environ.get("IB_PORT", "4002"))
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
RSI_THRESHOLD = float(os.environ.get("RSI_THRESHOLD", "50"))
SMA_MARGIN = float(os.environ.get("SMA_MARGIN", "0.10"))
MIN_CASH = float(os.environ.get("MIN_CASH", "50"))
MIN_ORDER = float(os.environ.get("MIN_ORDER", "10"))
PORTFOLIO_PCT = float(os.environ.get("PORTFOLIO_PCT", "0.01"))
CASH_USE_PCT = float(os.environ.get("CASH_USE_PCT", "0.90"))
SCAN_CRON = os.environ.get("SCAN_CRON", "*/5 * * * *")


def parse_cron(expr: str) -> dict:
    """Parse '*/5 * * * *' into APScheduler CronTrigger kwargs."""
    parts = expr.strip().split()
    fields = ["minute", "hour", "day", "month", "day_of_week"]
    return {fields[i]: parts[i] for i in range(min(len(parts), len(fields)))}


ibkr = IBKRClient(IB_HOST, IB_PORT)
bot: TelegramBot | None = None


async def run_scan():
    log.info("=== Starting scan ===")

    if not ibkr.is_connected:
        log.warning("IB Gateway not connected, attempting reconnect...")
        if not await ibkr.connect(retries=3, delay=5):
            if bot:
                await bot.send_text("🚨 IB Gateway déconnecté — scan annulé")
            return

    watchlist = load_watchlist()
    signals = scan(watchlist, RSI_THRESHOLD, SMA_MARGIN)

    # Also check deferred signals from pending.json
    pending = load_pending()
    pending_tickers = {s["ticker"] for s in signals}
    for p in pending:
        if p["ticker"] not in pending_tickers:
            rescan = scan([p], RSI_THRESHOLD, SMA_MARGIN)
            signals.extend(rescan)
    save_pending([])

    if not signals:
        log.info("No signals found")
        return

    cash = ibkr.get_cash_balance()
    portfolio_value = ibkr.get_portfolio_value()

    if cash < MIN_CASH:
        log.info("Cash %.2f < minimum %.2f — no orders", cash, MIN_CASH)
        if bot:
            await bot.send_text(f"ℹ️ Cash insuffisant : {cash:.2f}€ (min {MIN_CASH:.2f}€)")
        return

    for signal in signals:
        target_amount = portfolio_value * PORTFOLIO_PCT
        order_amount = min(target_amount, cash * CASH_USE_PCT)

        if order_amount < MIN_ORDER:
            log.info("%s: order amount %.2f < minimum %.2f — skipped",
                     signal["ticker"], order_amount, MIN_ORDER)
            continue

        if bot:
            await bot.send_signal(signal, order_amount)

    log.info("=== Scan complete ===")


async def main():
    global bot

    log.info("Starting IBKR Patrimonial Bot")
    log.info("Config: RSI<%s, SMA_MARGIN=%s, CRON=%s", RSI_THRESHOLD, SMA_MARGIN, SCAN_CRON)

    # Connect to IB Gateway (async)
    await ibkr.connect()

    # Init Telegram bot
    bot = TelegramBot(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ibkr)

    # Schedule scans
    scheduler = AsyncIOScheduler(timezone="Europe/Paris")
    cron_kwargs = parse_cron(SCAN_CRON)
    scheduler.add_job(run_scan, CronTrigger(**cron_kwargs), id="scan")
    scheduler.start()
    log.info("Scheduler started with cron: %s", SCAN_CRON)

    # Send startup message
    await bot.send_text(
        f"🟢 Bot démarré\n"
        f"📊 Watchlist : {len(load_watchlist())} tickers\n"
        f"⏰ Cron : {SCAN_CRON}\n"
        f"🔌 IB Gateway : {'✅' if ibkr.is_connected else '❌'}"
    )

    # Run Telegram polling + scheduler together
    async with bot.app:
        await bot.app.start()
        await bot.app.updater.start_polling()
        log.info("Telegram bot polling started")

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await bot.app.updater.stop()
            await bot.app.stop()
            scheduler.shutdown()
            ibkr.disconnect()
            log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
