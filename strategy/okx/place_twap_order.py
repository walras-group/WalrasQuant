from datetime import timedelta
from decimal import Decimal
from walrasquant.constants import settings, OrderSide
from walrasquant.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
    LogConfig,
)
from walrasquant.constants import ExchangeType
from walrasquant.strategy import Strategy
from walrasquant.exchange import OkxAccountType
from walrasquant.engine import Engine
from walrasquant.execution import TWAPExecAlgorithm

OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
OKX_SECRET = settings.OKX.DEMO_1.SECRET
OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.symbols = ["SOLUSDT-PERP.OKX"]

    def on_start(self):
        self.subscribe_bookl1(self.symbols)
        self.schedule(
            func=self.place_twap_order,
            trigger="date",
            run_date=self.clock.utc_now() + timedelta(seconds=10),
        )

    def on_filled_order(self, order):
        self.log.info(f"Order filled: {order}")

    def place_twap_order(self):
        for symbol in self.symbols:
            self.create_algo_order(
                symbol=symbol,
                side=OrderSide.BUY,
                amount=Decimal("2"),
                exec_algorithm_id="TWAP",
                exec_params={
                    "horizon_secs": 100,  # 100 seconds
                    "interval_secs": 10,  # every 10 seconds
                    "n_tick_sz": 1,  # offset by 1 tick size
                    "use_limit": True,  # use limit orders
                },
                reduce_only=True,
            )


config = Config(
    strategy_id="okx_twap_demo",
    user_id="user_test",
    strategy=Demo(),
    log_config=LogConfig(level="INFO", filename="logs/okx_twap_demo.log"),
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
engine.add_exec_algorithm(
    algorithm=TWAPExecAlgorithm(),
)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
