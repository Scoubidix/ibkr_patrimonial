import json
import logging
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

from .ibkr import IBKRClient

log = logging.getLogger(__name__)
PENDING_PATH = Path("/app/data/pending.json")


def load_pending() -> list[dict]:
    if PENDING_PATH.exists():
        return json.loads(PENDING_PATH.read_text())
    return []


def save_pending(pending: list[dict]):
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(pending, indent=2))


def format_signal_message(signal: dict, order_amount: float) -> str:
    price = signal["price"]
    estimated_shares = order_amount / price if price > 0 else 0
    return (
        f"🔔 SIGNAL — {signal['ticker']}\n"
        f"📊 RSI(14) : {signal['rsi']:.1f} ✅\n"
        f"📈 SMA200 : {signal['sma200']:.2f}$ | Prix : {price:.2f}$ ✅\n"
        f"💰 Ordre suggéré : {order_amount:.2f}€ (~{estimated_shares:.2f} action)\n"
    )


def build_keyboard(ticker: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ OUI", callback_data=f"buy:{ticker}"),
            InlineKeyboardButton("❌ NON", callback_data=f"skip:{ticker}"),
            InlineKeyboardButton("⏳ REPORTER", callback_data=f"defer:{ticker}"),
        ]
    ])


class TelegramBot:
    def __init__(self, token: str, chat_id: str, ibkr: IBKRClient):
        self.token = token
        self.chat_id = chat_id
        self.ibkr = ibkr
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CallbackQueryHandler(self._on_callback))
        self._pending_signals: dict[str, dict] = {}

    async def send_signal(self, signal: dict, order_amount: float):
        ticker = signal["ticker"]
        self._pending_signals[ticker] = {**signal, "order_amount": order_amount}

        text = format_signal_message(signal, order_amount)
        keyboard = build_keyboard(ticker)

        await self.app.bot.send_message(
            chat_id=self.chat_id, text=text, reply_markup=keyboard
        )
        log.info("Sent signal alert for %s (%.2f€)", ticker, order_amount)

    async def send_text(self, text: str):
        await self.app.bot.send_message(chat_id=self.chat_id, text=text)

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if str(query.message.chat_id) != self.chat_id:
            return

        action, ticker = query.data.split(":", 1)
        signal = self._pending_signals.pop(ticker, None)

        if signal is None:
            await query.edit_message_text(f"⚠️ Signal expiré pour {ticker}")
            return

        if action == "buy":
            await self._execute_buy(query, signal)
        elif action == "skip":
            await query.edit_message_text(f"❌ {ticker} — ignoré")
            log.info("User skipped %s", ticker)
        elif action == "defer":
            await self._defer_signal(query, signal)

    async def _execute_buy(self, query, signal: dict):
        ticker = signal["ticker"]
        amount = signal["order_amount"]

        if not self.ibkr.is_connected:
            await query.edit_message_text(f"⚠️ IB Gateway déconnecté — ordre annulé pour {ticker}")
            return

        result = await self.ibkr.place_cash_order(
            ticker=ticker,
            exchange=signal["exchange"],
            currency=signal["currency"],
            amount=amount,
        )

        if result["success"]:
            await query.edit_message_text(
                f"✅ ORDRE EXÉCUTÉ — {ticker}\n"
                f"💰 Montant : {amount:.2f}€\n"
                f"📋 Status : {result['status']}\n"
                f"🆔 Order ID : {result['orderId']}"
            )
        else:
            await query.edit_message_text(f"❌ Erreur ordre {ticker}: {result['error']}")

    async def _defer_signal(self, query, signal: dict):
        ticker = signal["ticker"]
        pending = load_pending()
        # Avoid duplicates
        if not any(p["ticker"] == ticker for p in pending):
            pending.append(signal)
            save_pending(pending)
        await query.edit_message_text(f"⏳ {ticker} — reporté (re-alerte demain si signal valide)")
        log.info("Deferred %s", ticker)

    def clear_pending(self, ticker: str):
        pending = load_pending()
        pending = [p for p in pending if p["ticker"] != ticker]
        save_pending(pending)
