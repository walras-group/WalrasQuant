from walrasquant.constants import settings
from walrasquant.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from walrasquant.strategy import Strategy
from walrasquant.constants import ExchangeType
from walrasquant.exchange import OkxAccountType
from walrasquant.schema import FundingRate, IndexPrice, MarkPrice
from walrasquant.engine import Engine


OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
OKX_SECRET = settings.OKX.DEMO_1.SECRET
OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        # in okx, you need to subscribe to all three of the following: funding rate, index price and mark price
        self.subscribe_funding_rate(symbols="BTCUSDT-PERP.OKX")
        self.subscribe_index_price(symbols="BTCUSDT.OKX")
        self.subscribe_mark_price(symbols="BTCUSDT-PERP.OKX")

    def on_funding_rate(self, funding_rate: FundingRate):
        print(funding_rate)

    def on_index_price(self, index_price: IndexPrice):
        print(index_price)

    def on_mark_price(self, mark_price: MarkPrice):
        print(mark_price)


config = Config(
    strategy_id="okx_subscribe_funding_rate",
    user_id="user_test",
    strategy=Demo(),
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
