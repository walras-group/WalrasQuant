# Code Reviewer Agent Memory

## Architecture Conventions

- Symbol format: `<SYMBOL>.<EXCHANGE>` e.g. `BTCUSDT-PERP.BINANCE`
- Each exchange EMS class is instantiated by its factory (`create_ems`) using a `BuildContext` dataclass
- `BuildContext` lives in `src/walrasquant/exchange/base_factory.py` — any new shared context fields must be added there
- `StorageBackend` abstract base is in `src/walrasquant/backends/db.py` — all concrete backends (sqlite, postgresql) must implement every `@abstractmethod`
- `AsyncCache` in `src/walrasquant/core/cache.py` owns all in-memory state; it calls the backend periodically and on close

## Recurring Mistake Patterns

### "Dangling else" indentation after removing an `if self._is_mock:` guard
When an `if self._is_mock: ... else: <real logic>` block is collapsed, the former `else:` body
retains its extra indentation level. Python's `ast` module catches this as an
`IndentationError` at import time.
- Confirmed in: `src/walrasquant/exchange/binance/ems.py` `_set_account_type` (lines 52-71)
- Confirmed in: `src/walrasquant/exchange/bitget/ems.py` `_instrument_id_to_account_type` (lines 86-91)
- Always run `python -m ast <file>` or `python -c "import ast; ast.parse(open('f').read())"` after any indentation-touching edit.

### Files that must be changed together (change coupling)
- Adding/removing an EMS constructor parameter requires changes in:
  1. The exchange EMS class (e.g. `exchange/binance/ems.py`)
  2. The exchange factory (e.g. `exchange/binance/factory.py`)
  3. `BuildContext` in `exchange/base_factory.py` (if it is a context-threaded param)
  4. Every call site in `engine.py` (`_build_public_connectors`, `_build_private_connectors`, `_build_ems`)
- Removing a schema type (e.g. `AlgoOrder`) requires updates in:
  backends/db.py, backends/db_sqlite.py, backends/db_postgresql.py, core/cache.py, schema.py, constants.py

### Test files not updated when symbols are removed
- `test/base/test_mock_linear_connector.py` imports `MockLinearConnector` and `BinanceAccountType.LINEAR_MOCK` — both removed from exports
- `test/base/test_execution_ems.py` passes `is_mock=False` kwarg to `BinanceExecutionManagementSystem` — kwarg removed
- `strategy/binance/mock_trading.py` imports `MockConnectorConfig` and uses `BinanceAccountType.LINEAR_MOCK` — both removed

## Key File Paths

- Engine: `src/walrasquant/engine.py`
- Base EMS: `src/walrasquant/base/ems.py`
- BuildContext: `src/walrasquant/exchange/base_factory.py`
- AsyncCache: `src/walrasquant/core/cache.py`
- StorageBackend ABC: `src/walrasquant/backends/db.py`
- Config dataclasses: `src/walrasquant/config.py`
- Schema structs: `src/walrasquant/schema.py`
- Constants / enums: `src/walrasquant/constants.py`

## Known Fragile Areas

- EMS `_set_account_type` and `_instrument_id_to_account_type` methods are sensitive to indentation changes when mock branches are removed
- `engine.py` `_build_*` methods have multiple `BuildContext` instantiation sites — easy to miss one when adding/removing a context field
- `StorageBackend` ABC: removing an `@abstractmethod` from the base does NOT automatically remove the implementation from concrete classes — dead code accumulates
