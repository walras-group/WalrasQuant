from walrasquant.exchange.bybit.constants import BybitAccountType
from walrasquant.exchange.bybit.websockets import BybitWSClient
from walrasquant.exchange.bybit.connector import (
    BybitPublicConnector,
    BybitPrivateConnector,
)
from walrasquant.exchange.bybit.exchange import BybitExchangeManager
from walrasquant.exchange.bybit.rest_api import BybitApiClient
from walrasquant.exchange.bybit.ems import BybitExecutionManagementSystem
from walrasquant.exchange.bybit.oms import BybitOrderManagementSystem
from walrasquant.exchange.bybit.factory import BybitFactory

# Auto-register factory on import
try:
    from walrasquant.exchange.registry import register_factory

    register_factory(BybitFactory())
except ImportError:
    # Registry not available yet during bootstrap
    pass

__all__ = [
    "BybitAccountType",
    "BybitWSClient",
    "BybitPublicConnector",
    "BybitExchangeManager",
    "BybitApiClient",
    "BybitPrivateConnector",
    "BybitExecutionManagementSystem",
    "BybitOrderManagementSystem",
    "BybitFactory",
]
