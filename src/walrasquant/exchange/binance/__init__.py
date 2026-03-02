from walrasquant.exchange.binance.constants import BinanceAccountType
from walrasquant.exchange.binance.exchange import BinanceExchangeManager
from walrasquant.exchange.binance.connector import (
    BinancePublicConnector,
    BinancePrivateConnector,
)
from walrasquant.exchange.binance.rest_api import BinanceApiClient
from walrasquant.exchange.binance.ems import BinanceExecutionManagementSystem
from walrasquant.exchange.binance.oms import BinanceOrderManagementSystem
from walrasquant.exchange.binance.factory import BinanceFactory

# Auto-register factory on import
try:
    from walrasquant.exchange.registry import register_factory

    register_factory(BinanceFactory())
except ImportError:
    # Registry not available yet during bootstrap
    pass

__all__ = [
    "BinanceAccountType",
    "BinanceExchangeManager",
    "BinancePublicConnector",
    "BinancePrivateConnector",
    "BinanceHttpClient",
    "BinanceApiClient",
    "BinanceExecutionManagementSystem",
    "BinanceOrderManagementSystem",
    "BinanceFactory",
]
