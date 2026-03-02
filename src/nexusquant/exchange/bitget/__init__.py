from nexusquant.exchange.bitget.exchange import BitgetExchangeManager
from nexusquant.exchange.bitget.connector import (
    BitgetPublicConnector,
    BitgetPrivateConnector,
)
from nexusquant.exchange.bitget.constants import BitgetAccountType
from nexusquant.exchange.bitget.ems import BitgetExecutionManagementSystem
from nexusquant.exchange.bitget.oms import BitgetOrderManagementSystem
from nexusquant.exchange.bitget.factory import BitgetFactory

# Auto-register factory on import
try:
    from nexusquant.exchange.registry import register_factory

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
