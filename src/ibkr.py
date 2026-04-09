import asyncio
import logging
from ib_insync import IB, Stock, MarketOrder

log = logging.getLogger(__name__)


class IBKRClient:
    def __init__(self, host: str, port: int, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()

    async def connect(self, retries: int = 5, delay: int = 10) -> bool:
        for attempt in range(1, retries + 1):
            try:
                await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
                log.info("Connected to IB Gateway on %s:%s", self.host, self.port)
                return True
            except Exception as e:
                log.warning("Connection attempt %d/%d failed: %s", attempt, retries, e)
                if attempt < retries:
                    await asyncio.sleep(delay)
        log.error("Could not connect to IB Gateway after %d attempts", retries)
        return False

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
            log.info("Disconnected from IB Gateway")

    @property
    def is_connected(self) -> bool:
        return self.ib.isConnected()

    def get_cash_balance(self) -> float:
        for av in self.ib.accountValues():
            if av.tag == "TotalCashBalance" and av.currency == "BASE":
                return float(av.value)
        for av in self.ib.accountValues():
            if av.tag == "CashBalance" and av.currency == "BASE":
                return float(av.value)
        return 0.0

    def get_portfolio_value(self) -> float:
        # ib_insync uses NetLiquidationByCurrency with BASE
        for av in self.ib.accountValues():
            if av.tag == "NetLiquidationByCurrency" and av.currency == "BASE":
                return float(av.value)
        for av in self.ib.accountValues():
            if av.tag == "NetLiquidation" and av.currency == "BASE":
                return float(av.value)
        return 0.0

    async def place_cash_order(self, ticker: str, exchange: str, currency: str, amount: float) -> dict:
        contract = Stock(ticker, exchange, currency)
        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            log.error("Could not qualify contract for %s", ticker)
            return {"success": False, "error": f"Contract not qualified: {ticker}"}

        order = MarketOrder("BUY", 0)
        order.cashQty = amount

        trade = self.ib.placeOrder(contract, order)
        await asyncio.sleep(2)

        log.info("Order placed: BUY %s cashQty=%.2f — status: %s",
                 ticker, amount, trade.orderStatus.status)

        return {
            "success": True,
            "ticker": ticker,
            "cashQty": amount,
            "status": trade.orderStatus.status,
            "orderId": trade.order.orderId,
        }
