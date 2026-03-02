from walrasquant.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from walrasquant.strategy import Strategy
from walrasquant.constants import ExchangeType
from walrasquant.constants import KlineInterval
from walrasquant.exchange import OkxAccountType
from walrasquant.schema import Kline
from walrasquant.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_kline(
            "BTCUSDT-PERP.OKX", interval=KlineInterval.SECOND_1, use_aggregator=True
        )

    def on_kline(self, kline: Kline):
        self.log.info(str(kline))


config = Config(
    strategy_id="okx_subscribe_klines",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
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
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
