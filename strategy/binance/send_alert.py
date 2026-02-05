from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, settings
from nexustrader.exchange import BinanceAccountType
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.alert_info("This is a info Message", "key:info")

        # can set ok alert after some time
        # time.sleep(5)
        # self.alert_ok(
        #     "This is a ok Message",
        #     "key:info"
        # )


config = Config(
    strategy_id="test_alert",
    user_id="river",
    strategy=Demo(),
    flashduty_integration_key=settings.config.flashduty_key,
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
