import numpy as np
from decimal import Decimal
from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
    LogConfig,
)
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.strategy import Strategy
from nexustrader.exchange import OkxAccountType
from nexustrader.engine import Engine
from nexustrader.indicator import RingBuffer

OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
OKX_SECRET = settings.OKX.DEMO_1.SECRET
OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE


class VolatilityIndicator:
    def __init__(self, n: int = 30):
        self._buffer = RingBuffer(n)

    def append(self, px: float):
        self._buffer.append(px)

    @property
    def value(self) -> float:
        if not self._buffer.is_full:
            return np.nan
        pxs = self._buffer.get_as_numpy_array()
        diff = np.diff(pxs)
        return np.sqrt(np.sum(np.square(diff)) / len(diff))

    @property
    def is_ready(self) -> bool:
        return self._buffer.is_full


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.n = 30
        self.symbol = "SOLUSDT-PERP.OKX"
        self.q_max = 0.1
        self.kappa = 0.3
        self.gamma = 0.5
        self.inv_gate = 0.8
        self.bid_oid = None
        self.ask_oid = None

        self.vol_indicator = VolatilityIndicator(n=self.n)

    def on_start(self):
        self.subscribe_bookl1(symbols=self.symbol)
        self.schedule(
            func=self.on_tick,
            trigger="interval",
            seconds=1,
        )

    def on_filled_order(self, order):
        if order.oid == self.bid_oid:
            self.log.info(f"Bid order filled: {order}")
            self.bid_oid = None
        elif order.oid == self.ask_oid:
            self.log.info(f"Ask order filled: {order}")
            self.ask_oid = None

    def on_tick(self):
        if not self.ready:
            return

        bookl1 = self.cache.bookl1(self.symbol)
        self.vol_indicator.append(bookl1.mid)
        amount_sz = self.min_order_amount(self.symbol)

        if not self.vol_indicator.is_ready:
            return

        vol_pct = self.vol_indicator.value / bookl1.mid

        pos = self.cache.get_position(self.symbol).value_or(None)
        q = 0 if pos is None else float(pos.signed_amount)

        q_pct = np.tanh(q / self.q_max)

        adj_mid = bookl1.mid * (1 - self.gamma * vol_pct * q_pct)

        half_spread_pct = self.kappa * vol_pct

        bid_px = min(adj_mid * (1 - half_spread_pct), bookl1.bid)
        ask_px = max(adj_mid * (1 + half_spread_pct), bookl1.ask)

        allow_buy = q < self.q_max * self.inv_gate
        allow_sell = q > -self.q_max * self.inv_gate

        self.log.info(
            f"s: {self.symbol}, Mid: {bookl1.mid:.2f}, bid: {bid_px:.2f}, ask: {ask_px:.2f}, bid_oid: {self.bid_oid}, ask_oid: {self.ask_oid}, q: {q:.2f}, vol%: {vol_pct * 100:.4f}%, allow_buy: {allow_buy}, allow_sell: {allow_sell}"
        )

        if not self.can_trade:
            return

        if not allow_buy:
            if self.bid_oid is not None:
                self.cancel_order_ws(
                    symbol=self.symbol,
                    oid=self.bid_oid,
                )
            self.bid_oid = None
        else:
            if self.bid_oid is not None:
                order = self.cache.get_order(self.bid_oid).value_or(None)
                if order is not None:
                    if Decimal(str(order.price)) != self.price_to_precision(self.symbol, bid_px):
                        self.cancel_order_ws(
                            symbol=self.symbol,
                            oid=self.bid_oid,
                        )
                        self.bid_oid = None
            if self.bid_oid is None:
                self.bid_oid = self.create_order_ws(
                    symbol=self.symbol,
                    side=OrderSide.BUY,
                    type=OrderType.POST_ONLY,
                    amount=amount_sz,
                    price=self.price_to_precision(self.symbol, bid_px),
                )

        if not allow_sell:
            if self.ask_oid is not None:
                self.cancel_order_ws(
                    symbol=self.symbol,
                    oid=self.ask_oid,
                )
            self.ask_oid = None
        else:
            if self.ask_oid is not None:
                order = self.cache.get_order(self.ask_oid).value_or(None)
                if order is not None:
                    if Decimal(str(order.price)) != self.price_to_precision(self.symbol, ask_px):
                        self.cancel_order_ws(
                            symbol=self.symbol,
                            oid=self.ask_oid,
                        )
                        self.ask_oid = None
            if self.ask_oid is None:
                self.ask_oid = self.create_order_ws(
                    symbol=self.symbol,
                    side=OrderSide.SELL,
                    type=OrderType.POST_ONLY,
                    amount=amount_sz,
                    price=self.price_to_precision(self.symbol, ask_px),
                )


config = Config(
    strategy_id="okx_simple_mm",
    user_id="user_test",
    strategy=Demo(),
    log_config=LogConfig(level="INFO", filename="logs/app.log"),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.DEMO,
            )
        ]
    },
    private_conn_config={
        ExchangeType.OKX: [
            PrivateConnectorConfig(
                account_type=OkxAccountType.DEMO,
            )
        ]
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
