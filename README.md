# walrasquant

`walrasquant` is a high-performance Python framework for quantitative trading.
It is designed for low-latency execution, multi-exchange connectivity, and strategy development at scale.

## Highlights

- Async-first architecture for real-time trading workflows
- Multi-exchange support (OKX, Binance, Bybit, Hyperliquid, Bitget)
- Built-in order and position lifecycle management
- Strategy framework with execution algorithms (including TWAP)
- Optional web API integration with FastAPI
- CLI and PM2 tooling for monitoring and operations

## Installation

### Requirements

- Python `>=3.11,<3.14`
- Redis (recommended for monitoring and shared runtime state)

### From PyPI

```bash
pip install walrasquant
```

### From source

```bash
git clone https://github.com/walras-group/WalrasQuant.git
cd WalrasQuant
uv pip install -e .
```

## Quick start

```python
from decimal import Decimal

from walrasquant.constants import settings, ExchangeType, OrderSide, OrderType
from walrasquant.config import Config, BasicConfig, PublicConnectorConfig, PrivateConnectorConfig
from walrasquant.engine import Engine
from walrasquant.exchange.okx import OkxAccountType
from walrasquant.schema import BookL1, Order
from walrasquant.strategy import Strategy


OKX_API_KEY = settings.OKX.DEMO_1.api_key
OKX_SECRET = settings.OKX.DEMO_1.secret
OKX_PASSPHRASE = settings.OKX.DEMO_1.passphrase


class DemoStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])
        self.signal = True

    def on_filled_order(self, order: Order):
        print(order)

    def on_bookl1(self, bookl1: BookL1):
        if not self.signal:
            return

        self.create_order(
            symbol="BTCUSDT-PERP.OKX",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )
        self.create_order(
            symbol="BTCUSDT-PERP.OKX",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )
        self.signal = False


config = Config(
    strategy_id="okx_demo_buy_sell",
    user_id="user_test",
    strategy=DemoStrategy(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [PublicConnectorConfig(account_type=OkxAccountType.DEMO)]
    },
    private_conn_config={
        ExchangeType.OKX: [PrivateConnectorConfig(account_type=OkxAccountType.DEMO)]
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
```

## CLI tools

After installation, the following commands are available:

- `walrasquant-cli` for monitoring and management workflows
- `wq-pm2` for PM2-based strategy process operations

## Documentation

- Local docs source: `docs/`

## Contributing

Contributions are welcome. Please open an issue or submit a PR.

## License

MIT License
