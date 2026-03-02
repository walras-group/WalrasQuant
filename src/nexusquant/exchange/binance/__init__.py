from nexusquant.exchange.binance.constants import BinanceAccountType
from nexusquant.exchange.binance.exchange import BinanceExchangeManager
from nexusquant.exchange.binance.connector import (
    BinancePublicConnector,
    BinancePrivateConnector,
)
from nexusquant.exchange.binance.rest_api import BinanceApiClient
from nexusquant.exchange.binance.ems import BinanceExecutionManagementSystem
from nexusquant.exchange.binance.oms import BinanceOrderManagementSystem
from nexusquant.exchange.binance.factory import BinanceFactory

# Auto-register factory on import
try:
    from nexusquant.exchange.registry import register_factory

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
