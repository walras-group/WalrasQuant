from walrasquant.exchange.bitget.exchange import BitgetExchangeManager
from walrasquant.exchange.bitget.connector import (
    BitgetPublicConnector,
    BitgetPrivateConnector,
)
from walrasquant.exchange.bitget.constants import BitgetAccountType
from walrasquant.exchange.bitget.ems import BitgetExecutionManagementSystem
from walrasquant.exchange.bitget.oms import BitgetOrderManagementSystem
from walrasquant.exchange.bitget.factory import BitgetFactory

# Auto-register factory on import
try:
    from walrasquant.exchange.registry import register_factory

    register_factory(BitgetFactory())
except ImportError:
    # Registry not available yet during bootstrap
    pass

__all__ = [
    "BitgetExchangeManager",
    "BitgetPublicConnector",
    "BitgetPrivateConnector",
    "BitgetAccountType",
    "BitgetExecutionManagementSystem",
    "BitgetOrderManagementSystem",
    "BitgetFactory",
]
