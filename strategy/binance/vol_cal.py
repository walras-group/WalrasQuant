import numpy as np
from walrasquant.config import Config, PublicConnectorConfig, BasicConfig
from walrasquant.strategy import Strategy
from walrasquant.constants import ExchangeType
from walrasquant.exchange import BinanceAccountType
from walrasquant.schema import BookL1
from walrasquant.engine import Engine
from walrasquant.indicator import RingBuffer


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
        self.symbol = "RIVERUSDT-PERP.BINANCE"
        self.vol_indicator = VolatilityIndicator(n=30)

    def on_start(self):
        self.subscribe_bookl1(symbols=self.symbol)
        self.schedule(
            func=self.on_tick,
            trigger="interval",
            seconds=1,
        )

    def on_tick(self):
        if not self.ready:
            return

        bookl1 = self.cache.bookl1(self.symbol)
        self.vol_indicator.append(bookl1.mid)

        if not self.vol_indicator.is_ready:
            return

        vol_pct = self.vol_indicator.value / bookl1.mid * 100

        self.log.info(
            f"Symbol: {self.symbol}, Mid: {bookl1.mid:.6f}, Vol%: {vol_pct:.4f}%"
        )


config = Config(
    strategy_id="subscribe_bookl1_binance",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
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
