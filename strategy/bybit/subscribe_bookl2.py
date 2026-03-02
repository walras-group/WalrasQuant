from walrasquant.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from walrasquant.strategy import Strategy
from walrasquant.constants import ExchangeType, BookLevel
from walrasquant.exchange import BybitAccountType
from walrasquant.schema import BookL2
from walrasquant.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_bookl2(symbols="BTCUSDT-PERP.BYBIT", level=BookLevel.L50)

    def on_bookl2(self, bookl2: BookL2):
        self.log.info(str(bookl2))


config = Config(
    strategy_id="bybit_subscribe_bookl2",
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
