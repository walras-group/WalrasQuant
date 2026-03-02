from walrasquant.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from walrasquant.strategy import Strategy
from walrasquant.constants import ExchangeType, KlineInterval
from walrasquant.exchange import BybitAccountType
from walrasquant.schema import Kline
from walrasquant.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        # self.subscribe_kline(
        #     "BTCUSDT-PERP.BYBIT", interval=KlineInterval.SECOND_1, use_aggregator=True
        # )
        self.subscribe_volume_kline(
            "BTCUSDT-PERP.BYBIT", volume_threshold=10, volume_type="DEFAULT"
        )

    def on_kline(self, kline: Kline):
        self.log.info(str(kline))


config = Config(
    strategy_id="bybit_subscribe_klines",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BYBIT: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR,
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
