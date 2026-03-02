"""
Binance exchange factory implementation.
"""

from nexusquant.constants import ExchangeType, AccountType
from nexusquant.config import (
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexusquant.exchange.base_factory import ExchangeFactory, BuildContext
from nexusquant.base import (
    ExchangeManager,
    PublicConnector,
    PrivateConnector,
    ExecutionManagementSystem,
)

from nexusquant.exchange.binance.exchange import BinanceExchangeManager
from nexusquant.exchange.binance.connector import (
    BinancePublicConnector,
    BinancePrivateConnector,
)
from nexusquant.exchange.binance.ems import BinanceExecutionManagementSystem


class BinanceFactory(ExchangeFactory):
    """Factory for creating Binance exchange components."""

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BINANCE

    def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
        """Create BinanceExchangeManager."""
        ccxt_config = {
            "apiKey": basic_config.api_key,
            "secret": basic_config.secret,
            "sandbox": basic_config.testnet,
        }
        if basic_config.passphrase:
            ccxt_config["password"] = basic_config.passphrase

        return BinanceExchangeManager(ccxt_config)

    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
    ) -> PublicConnector:
        """Create BinancePublicConnector."""
        return BinancePublicConnector(
            account_type=config.account_type,
            exchange=exchange,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            enable_rate_limit=config.enable_rate_limit,
            custom_url=config.custom_url,
            max_subscriptions_per_client=config.max_subscriptions_per_client,
            max_clients=config.max_clients,
        )

    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
        account_type: AccountType = None,
    ) -> PrivateConnector:
        """Create BinancePrivateConnector."""
        # Use provided account_type or fall back to config
        final_account_type = account_type or config.account_type

        return BinancePrivateConnector(
            exchange=exchange,
            account_type=final_account_type,
            cache=context.cache,
            clock=context.clock,
            msgbus=context.msgbus,
            registry=context.registry,
            enable_rate_limit=config.enable_rate_limit,
            task_manager=context.task_manager,
            max_retries=config.max_retries,
            delay_initial_ms=config.delay_initial_ms,
            delay_max_ms=config.delay_max_ms,
            backoff_factor=config.backoff_factor,
            max_subscriptions_per_client=config.max_subscriptions_per_client,
            max_clients=config.max_clients,
        )

    def create_ems(
        self, exchange: ExchangeManager, context: BuildContext
    ) -> ExecutionManagementSystem:
        """Create BinanceExecutionManagementSystem."""
        return BinanceExecutionManagementSystem(
            market=exchange.market,
            cache=context.cache,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            registry=context.registry,
            is_mock=context.is_mock,
            queue_maxsize=context.queue_maxsize,
        )
