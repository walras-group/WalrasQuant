# NexusTrader Project Guide

## Overview

NexusTrader is a high-performance, professional-grade quantitative trading platform designed for cryptocurrency trading across multiple exchanges (Binance, Bybit, OKX, Hyperliquid, Bitget). The platform is built with Python 3.11+ and optimized for low-latency execution using async/await patterns.

**Key Design Philosophy:**
- **Performance First**: Uses uvloop, picows (Cython-based WebSocket), and msgspec for maximum throughput
- **Event-Driven Architecture**: Built on Rust-powered MessageBus and Clock from nautilius framework
- **Modular Design**: Clear separation between connectors, execution systems, and strategy logic

## Project Structure

```
nexustrader/
├── base/           # Base connector classes and management systems
├── core/           # Core utilities (cache, entity, nautilus integration)
├── exchange/       # Exchange-specific implementations
├── execution/      # Execution algorithms (TWAP, custom algos)
├── cli/            # Command-line interface and monitoring
├── web/            # FastAPI integration for strategy webhooks
├── backends/       # Storage backends (SQLite, PostgreSQL)
└── *.py            # Main modules (engine, strategy, schema, config, etc.)
```

## Core Architecture

### 1. Engine (`engine.py`)
The central orchestrator that:
- Initializes all components (connectors, cache, message bus, clock)
- Manages the event loop (uvloop on non-Windows platforms)
- Coordinates between public/private connectors and strategies
- Handles strategy lifecycle (start, stop, dispose)

### 2. Strategy (`strategy.py`)
Base class for all trading strategies. Key features:
- **Event callbacks**: `on_bookl1`, `on_trade`, `on_kline`, `on_filled_order`, etc.
- **Timer mode**: Schedule logic with `schedule()`
- **Custom signals**: External signal integration via `on_custom_signal()`
- **Indicators**: Built-in indicator manager with warmup support
- **Order management**: `create_order`, `create_algo_order`, `cancel_order`

### 3. Connectors (`base/`)
- **PublicConnector**: Market data (orderbook, trades, klines)
- **PrivateConnector**: Account data, order execution
- **ExchangeManager**: Per-exchange coordinator
- **ExecutionManagementSystem (EMS)**: Order submission
- **OrderManagementSystem (OMS)**: Order state tracking
- **SubscriptionManagementSystem (SMS)**: Data subscription management

### 4. Exchange Implementations (`exchange/`)
Each exchange has its own subdirectory with:
- Exchange-specific connectors
- Account type definitions
- Market metadata handling
- WebSocket/REST protocol handling

### 5. Schema (`schema.py`)
Data structures using `msgspec.Struct` for performance:
- Market data: `BookL1`, `BookL2`, `Trade`, `Kline`
- Orders: `Order`, `CreateOrderSubmit`, `ModifyOrderSubmit`
- Account: `AccountBalance`, `Position`
- Instruments: `InstrumentId`, `BaseMarket`

### 6. Execution Algorithms (`execution/`)
- Built-in `TWAPExecAlgorithm` for time-weighted execution
- Base `ExecAlgorithm` class for custom algorithm development

## Development Guidelines

### Adding a New Exchange

1. Create directory in `nexustrader/exchange/<exchange_name>/`
2. Implement `PublicConnector` and `PrivateConnector` inheriting from base classes
3. Add `ExchangeType` enum in `constants.py`
4. Register in `exchange/registry.py`
5. Implement exchange-specific account types

### Creating a Strategy

```python
from nexustrader.strategy import Strategy

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__()
        # Subscriptions
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])

    def on_bookl1(self, bookl1: BookL1):
        # Trading logic here
        pass
```

### Creating Custom Indicators

```python
from nexustrader.indicator import Indicator

class MyIndicator(Indicator):
    def __init__(self):
        super().__init__(
            params={"period": 20},
            name="MyIndicator",
            warmup_period=40,
            warmup_interval=KlineInterval.MINUTE_1,
        )

    def handle_kline(self, kline: Kline):
        # Process data
        pass
```

### Creating Execution Algorithms

```python
from nexustrader.execution.algorithm import ExecAlgorithm

class MyAlgo(ExecAlgorithm):
    def on_order(self, exec_order: ExecAlgorithmOrder):
        # Split order and spawn child orders
        self.spawn_market(exec_order, quantity)
```

## Key Design Patterns

### 1. Message-Driven Communication
- Uses Rust-powered MessageBus for pub/sub
- Topics for different data types (bookl1, trade, kline, etc.)
- Decouples producers from consumers

### 2. Async/Await Everywhere
- All I/O operations are async
- Use `asyncio` for concurrency
- Avoid blocking operations in strategy callbacks

### 3. State Management
- `AsyncCache`: Centralized state for positions, balances, orders
- Persists to SQLite/PostgreSQL
- Redis support for distributed scenarios

### 4. Precision Handling
- Use `Decimal` for all price/amount calculations
- Exchange-specific precision via `amount_to_precision` / `price_to_precision`

## Important Constants

### ExchangeType
- `BINANCE`, `BYBIT`, `OKX`, `HYPERLIQUID`, `BITGET`

### OrderSide / OrderType / OrderStatus
- Side: `BUY`, `SELL`
- Type: `LIMIT`, `MARKET`, `STOP_MARKET`, `STOP_LIMIT`
- Status: `PENDING`, `ACCEPTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `FAILED`

### DataType
- `BOOKL1`, `BOOKL2`, `TRADE`, `KLINE`, `FUNDING_RATE`, etc.

## Configuration System

Strategy configuration via `Config` class:
- `strategy_id`: Unique strategy identifier
- `user_id`: User identifier
- `basic_config`: Exchange API credentials
- `public_conn_config`: Public connector settings
- `private_conn_config`: Private connector settings
- `storage_backend`: `REDIS` or `MEMORY`
- `web_config`: Optional FastAPI server

## Testing

- Unit tests in `test/`
- Mock connector available: `MockLinearConnector`
- Strategy examples in `strategy/` directory

## Performance Considerations

1. **WebSocket**: Use picows-based connectors for best performance
2. **Serialization**: msgspec is ~10x faster than json
3. **Event Loop**: uvloop provides 2-4x speedup on Linux/macOS
4. **Database**: Async drivers (aiosqlite, asyncpg) for non-blocking I/O

## Common Patterns

### Multi-Exchange Strategy
```python
# Subscribe to same symbol on multiple exchanges
self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE", "BTCUSDT-PERP.OKX"])
```

### Arbitrage Pattern
```python
def on_bookl1(self, bookl1: BookL1):
    if bookl1.exchange == ExchangeType.BINANCE:
        self.binance_price = bookl1.best_bid
    elif bookl1.exchange == ExchangeType.OKX:
        self.okx_price = bookl1.best_ask
    # Check arbitrage opportunity
```

### Position Management
```python
# Get current position
position = self.cache.position.get("BTCUSDT-PERP.BINANCE")
if position and position.quantity > 0:
    # Close position
    self.create_order(..., reduce_only=True)
```

## Important Notes

1. **Symbol Format**: Always use `<SYMBOL>.<EXCHANGE>` format (e.g., `BTCUSDT-PERP.BINANCE`)
2. **Time Awareness**: Use `self.clock.utc_now()` for consistent timestamps
3. **Logging**: Use `self.log.info/warning/error` from strategy context
4. **Error Handling**: Always handle `on_failed_order` callbacks
5. **Cleanup**: Call `engine.dispose()` in finally blocks for graceful shutdown
