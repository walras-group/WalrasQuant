from walrasquant.exchange.hyperliquid.exchange import HyperLiquidExchangeManager
from walrasquant.exchange.hyperliquid.constants import HyperLiquidAccountType
from walrasquant.exchange.hyperliquid.connector import (
    HyperLiquidPublicConnector,
    HyperLiquidPrivateConnector,
)
from walrasquant.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem
from walrasquant.exchange.hyperliquid.ems import HyperLiquidExecutionManagementSystem
from walrasquant.exchange.hyperliquid.factory import HyperLiquidFactory

# Auto-register factory on import
try:
    from walrasquant.exchange.registry import register_factory

    register_factory(HyperLiquidFactory())
except ImportError:
    # Registry not available yet during bootstrap
    pass

__all__ = [
    "HyperLiquidExchangeManager",
    "HyperLiquidAccountType",
    "HyperLiquidPublicConnector",
    "HyperLiquidPrivateConnector",
    "HyperLiquidOrderManagementSystem",
    "HyperLiquidExecutionManagementSystem",
    "HyperLiquidFactory",
]
