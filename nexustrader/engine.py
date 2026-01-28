import asyncio
import platform
import nexuslog as logging
from typing import Dict
from collections import defaultdict
from nexustrader.constants import AccountType, ExchangeType
from nexustrader.config import Config, WebConfig
from nexustrader.strategy import Strategy
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.error import EngineBuildError
from nexustrader.base import (
    ExchangeManager,
    PublicConnector,
    PrivateConnector,
    ExecutionManagementSystem,
    SubscriptionManagementSystem,
    OrderManagementSystem,
    MockLinearConnector,
)
from nexustrader.exchange.registry import get_factory
from nexustrader.exchange.base_factory import BuildContext

from nexustrader.core.entity import TaskManager, ZeroMQSignalRecv
from nexustrader.core.nautilius_core import setup_nexus_core
from nexustrader.schema import InstrumentId
from nexustrader.web.app import StrategyFastAPI
from nexustrader.web.server import StrategyWebServer
from nexustrader.base.ws_client import WSClient
from nexustrader.core.connection import (
    ConnectionState,
    ConnectionPolicyState,
    ConnectionRole,
)
from nexustrader.push import FlashDutyPushService


class Engine:
    @staticmethod
    def set_loop_policy():
        # if python version < 3.13, using uvloop for non-Windows platform

        if platform.system() != "Windows":
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    def __init__(self, config: Config):
        self._config = config
        self._is_built = False
        self._scheduler_started = False
        self.set_loop_policy()
        self._loop = asyncio.new_event_loop()
        self._task_manager = TaskManager(self._loop)

        self._exchanges: Dict[ExchangeType, ExchangeManager] = {}
        self._public_connectors: Dict[AccountType, PublicConnector] = {}
        self._private_connectors: Dict[AccountType, PrivateConnector] = {}

        trader_id = f"{self._config.strategy_id}-{self._config.user_id}"

        self._custom_signal_recv = None

        # Initialize nautilus core components and configure nexuslog
        self._msgbus, self._clock = setup_nexus_core(
            trader_id=trader_id,
            filename=self._config.log_config.filename,
            level=self._config.log_config.level,
            name_levels=self._config.log_config.name_levels,
            unix_ts=self._config.log_config.unix_ts,
            batch_size=self._config.log_config.batch_size,
        )

        # Create logger instance for Engine
        self._log = logging.getLogger(type(self).__name__)

        self._cache: AsyncCache = AsyncCache(
            strategy_id=config.strategy_id,
            user_id=config.user_id,
            msgbus=self._msgbus,
            clock=self._clock,
            task_manager=self._task_manager,
            storage_backend=config.storage_backend,
            db_path=config.db_path,
            sync_interval=config.cache_sync_interval,
            expired_time=config.cache_expired_time,
        )

        self._registry = OrderRegistry()
        self._oms: Dict[ExchangeType, OrderManagementSystem] = {}
        self._ems: Dict[ExchangeType, ExecutionManagementSystem] = {}
        self._custom_ems: Dict[ExchangeType, ExecutionManagementSystem] = {}

        self._sms = SubscriptionManagementSystem(
            exchanges=self._exchanges,
            public_connectors=self._public_connectors,
            task_manager=self._task_manager,
            clock=self._clock,
        )

        self._push_service = FlashDutyPushService(
            integration_key=self._config.flashduty_integration_key,
            strategy_id=self._config.strategy_id,
            user_id=self._config.user_id,
        )

        self._strategy: Strategy = config.strategy
        self._strategy._init_core(
            cache=self._cache,
            msgbus=self._msgbus,
            clock=self._clock,
            task_manager=self._task_manager,
            ems=self._ems,
            sms=self._sms,
            exchanges=self._exchanges,
            private_connectors=self._private_connectors,
            public_connectors=self._public_connectors,
            push_service=self._push_service,
            strategy_id=config.strategy_id,
            user_id=config.user_id,
            enable_cli=config.enable_cli,
        )

        self._web_app: StrategyFastAPI | None = None
        self._web_server: StrategyWebServer | None = None
        self._prepare_web_interface()

        self._connection_registry: Dict[
            tuple[str, str, str, str, int], ConnectionState
        ] = {}
        self._connection_policy_state: ConnectionPolicyState | None = None

    def _prepare_web_interface(self) -> None:
        web_app = getattr(self._strategy, "web_app", None)
        if not web_app:
            return
        if not isinstance(web_app, StrategyFastAPI):
            raise EngineBuildError(
                "Strategy.web_app must be created with `create_strategy_app()` or `StrategyFastAPI`."
            )

        self._web_app = web_app
        self._web_app.bind_strategy(self._strategy)

    def _start_web_interface(self) -> None:
        if not self._web_app:
            return

        web_config: WebConfig = getattr(self._config, "web_config", WebConfig())
        if not web_config.enabled:
            self._log.debug("Web interface disabled via configuration")
            return

        if not self._web_app.has_user_routes():
            self._log.debug(
                "Web interface enabled but no user routes registered; skipping startup"
            )
            return

        self._web_server = StrategyWebServer(
            self._web_app,
            host=web_config.host,
            port=web_config.port,
            log_level=web_config.log_level,
        )
        try:
            self._web_server.start()
            self._log.info(
                f"Web interface started on http://{web_config.host}:{web_config.port}"
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log.error(f"Failed to start web interface: {exc}")
            self._web_server = None

    def _public_connector_check(self):
        # Group connectors by exchange
        exchange_connectors = defaultdict(dict)
        for account_type, connector in self._public_connectors.items():
            exchange_id = ExchangeType(account_type.exchange_id.lower())
            exchange_connectors[exchange_id][account_type] = connector

        # Validate each exchange's connectors
        for exchange_id, connectors in exchange_connectors.items():
            exchange = self._exchanges[exchange_id]
            basic_config = self._config.basic_config.get(exchange_id)

            if not basic_config:
                raise EngineBuildError(
                    f"Basic config for {exchange_id} is not set. Please add `{exchange_id}` in `basic_config`."
                )

            # Validate each connector configuration
            for account_type in connectors.keys():
                exchange.validate_public_connector_config(account_type, basic_config)

            # Validate connector limits
            exchange.validate_public_connector_limits(connectors)

    def _build_public_connectors(self):
        # Create build context
        context = BuildContext(
            msgbus=self._msgbus,
            clock=self._clock,
            task_manager=self._task_manager,
            cache=self._cache,
            registry=self._registry,
            is_mock=self._config.is_mock,
        )

        for exchange_id, public_conn_configs in self._config.public_conn_config.items():
            factory = get_factory(exchange_id)
            exchange = self._exchanges[exchange_id]

            for config in public_conn_configs:
                public_connector = factory.create_public_connector(
                    config, exchange, context
                )
                self._public_connectors[config.account_type] = public_connector

        self._public_connector_check()

    def _build_private_connectors(self):
        if self._config.is_mock:
            for (
                exchange_id,
                mock_conn_configs,
            ) in self._config.private_conn_config.items():
                if not mock_conn_configs:
                    raise EngineBuildError(
                        f"Private connector config for {exchange_id} is not set. Please add `{exchange_id}` in `private_conn_config`."
                    )
                for mock_conn_config in mock_conn_configs:
                    account_type = mock_conn_config.account_type

                    if mock_conn_config.account_type.is_linear_mock:
                        private_connector = MockLinearConnector(
                            initial_balance=mock_conn_config.initial_balance,
                            account_type=account_type,
                            exchange=self._exchanges[exchange_id],
                            msgbus=self._msgbus,
                            clock=self._clock,
                            cache=self._cache,
                            task_manager=self._task_manager,
                            overwrite_balance=mock_conn_config.overwrite_balance,
                            overwrite_position=mock_conn_config.overwrite_position,
                            fee_rate=mock_conn_config.fee_rate,
                            quote_currency=mock_conn_config.quote_currency,
                            update_interval=mock_conn_config.update_interval,
                            leverage=mock_conn_config.leverage,
                        )
                        self._private_connectors[account_type] = private_connector
                    elif mock_conn_config.account_type.is_inverse_mock:
                        # NOTE: currently not supported
                        raise EngineBuildError(
                            f"Mock connector for {account_type} is not supported."
                        )
                    elif mock_conn_config.account_type.is_spot_mock:
                        # NOTE: currently not supported
                        raise EngineBuildError(
                            f"Mock connector for {account_type} is not supported."
                        )
                    else:
                        raise EngineBuildError(
                            f"Unsupported account type: {account_type} for mock connector."
                        )

        else:
            # Create build context
            context = BuildContext(
                msgbus=self._msgbus,
                clock=self._clock,
                task_manager=self._task_manager,
                cache=self._cache,
                registry=self._registry,
                is_mock=self._config.is_mock,
            )

            for (
                exchange_id,
                private_conn_configs,
            ) in self._config.private_conn_config.items():
                if not private_conn_configs:
                    raise EngineBuildError(
                        f"Private connector config for {exchange_id} is not set. Please add `{exchange_id}` in `private_conn_config`."
                    )

                factory = get_factory(exchange_id)
                exchange = self._exchanges[exchange_id]

                for config in private_conn_configs:
                    # Let factory determine account type (handles testnet mapping)
                    account_type = factory.get_private_account_type(exchange, config)

                    private_connector = factory.create_private_connector(
                        config, exchange, context, account_type
                    )
                    self._private_connectors[account_type] = private_connector

    def _build_exchanges(self):
        for exchange_id, basic_config in self._config.basic_config.items():
            factory = get_factory(exchange_id)
            self._exchanges[exchange_id] = factory.create_manager(basic_config)

    def _build_custom_signal_recv(self):
        zmq_config = self._config.zero_mq_signal_config
        if zmq_config:
            if not hasattr(self._strategy, "on_custom_signal"):
                raise EngineBuildError(
                    "Please add `on_custom_signal` method to the strategy."
                )

            self._custom_signal_recv = ZeroMQSignalRecv(
                zmq_config, self._strategy.on_custom_signal, self._task_manager
            )

    def set_custom_ems(self, exchange_id: ExchangeType, ems_class: type) -> None:
        """
        Set a custom ExecutionManagementSystem class for a specific exchange.

        Args:
            exchange_id: The exchange type to set the custom EMS for
            ems_class: A custom EMS class that inherits from ExecutionManagementSystem
        """
        if not issubclass(ems_class, ExecutionManagementSystem):
            raise TypeError(
                "Custom EMS class must inherit from ExecutionManagementSystem"
            )
        self._custom_ems[exchange_id] = ems_class

    def _build_ems(self):
        # Create build context
        context = BuildContext(
            msgbus=self._msgbus,
            clock=self._clock,
            task_manager=self._task_manager,
            cache=self._cache,
            registry=self._registry,
            is_mock=self._config.is_mock,
        )

        for exchange_id, exchange in self._exchanges.items():
            # Check if there's a custom EMS for this exchange
            if exchange_id in self._custom_ems:
                self._ems[exchange_id] = self._custom_ems[exchange_id](
                    market=exchange.market,
                    cache=self._cache,
                    msgbus=self._msgbus,
                    clock=self._clock,
                    task_manager=self._task_manager,
                    registry=self._registry,
                    is_mock=self._config.is_mock,
                )
                self._ems[exchange_id]._build(self._private_connectors)
                continue

            # Use factory to create EMS
            factory = get_factory(exchange_id)
            ems = factory.create_ems(exchange, context)
            ems._build(self._private_connectors)
            self._ems[exchange_id] = ems

    def _connection_key(
        self,
        role: ConnectionRole,
        exchange_id: str,
        account_type: str,
        ws_name: str,
        client_id: int,
    ) -> tuple[str, str, str, str, int]:
        return (role, exchange_id, account_type, ws_name, client_id)

    def _recompute_connection_policy(self) -> None:
        md_required = [
            state
            for state in self._connection_registry.values()
            if state.is_md() and state.required
        ]
        td_required = [
            state
            for state in self._connection_registry.values()
            if state.is_td() and state.required
        ]

        md_ok = bool(md_required) and all(state.connected for state in md_required)
        td_ok = bool(td_required) and all(state.connected for state in td_required)

        policy = ConnectionPolicyState(md_ok=md_ok, td_ok=td_ok)

        if policy == self._connection_policy_state:
            return

        self._connection_policy_state = policy
        self._log.debug(
            "Connection policy update: "
            f"md_ok={policy.md_ok} td_ok={policy.td_ok} "
            f"allow_open={policy.allow_open} allow_trade={policy.allow_trade} "
            f"allow_close_only={policy.allow_close_only}"
        )

        self._msgbus.send(
            endpoint="connection_status",
            msg=policy,
        )

    def _register_ws_client(
        self,
        ws_client: WSClient,
        role: ConnectionRole,
        account_type: AccountType,
        ws_name: str,
        required: bool,
    ) -> None:
        exchange_id = getattr(account_type, "exchange_id", str(account_type))
        account_label = str(account_type)

        def _callback(client_id: int, connected: bool) -> None:
            key = self._connection_key(
                role, exchange_id, account_label, ws_name, client_id
            )
            state = ConnectionState(
                role=role,
                exchange_id=str(exchange_id),
                account_type=account_label,
                ws_name=ws_name,
                client_id=client_id,
                required=required,
                connected=connected,
                changed_at_ms=self._clock.timestamp_ms(),
            )
            self._connection_registry[key] = state
            self._recompute_connection_policy()

        ws_client.set_connection_change_callback(_callback)

    def _register_connection_callbacks(self) -> None:
        for account_type, connector in self._public_connectors.items():
            ws_client = getattr(connector, "_ws_client", None)
            if isinstance(ws_client, WSClient):
                self._register_ws_client(
                    ws_client=ws_client,
                    role="MD",
                    account_type=account_type,
                    ws_name="public",
                    required=True,
                )
            business_ws_client = getattr(connector, "_business_ws_client", None)
            if isinstance(business_ws_client, WSClient):
                self._register_ws_client(
                    ws_client=business_ws_client,
                    role="MD",
                    account_type=account_type,
                    ws_name="business",
                    required=True,
                )

        for account_type, connector in self._private_connectors.items():
            oms = getattr(connector, "_oms", None)
            if not oms:
                continue
            ws_client = getattr(oms, "_ws_client", None)
            if isinstance(ws_client, WSClient):
                self._register_ws_client(
                    ws_client=ws_client,
                    role="TD",
                    account_type=account_type,
                    ws_name="oms",
                    required=True,
                )
            ws_api_client = getattr(oms, "_ws_api_client", None)
            if isinstance(ws_api_client, WSClient):
                self._register_ws_client(
                    ws_client=ws_api_client,
                    role="TD",
                    account_type=account_type,
                    ws_name="oms_api",
                    required=True,
                )

    def _build(self):
        self._build_exchanges()
        self._build_public_connectors()
        self._build_private_connectors()
        self._build_ems()
        self._build_custom_signal_recv()
        self._register_connection_callbacks()
        self._is_built = True

    async def _start_connectors(self):
        # Start all public connectors
        for connector in self._public_connectors.values():
            await connector.connect()

        # Wait for all public connectors to be ready
        for connector in self._public_connectors.values():
            await connector.wait_ready()

        # Start all private connectors
        for connector in self._private_connectors.values():
            await connector.connect()

        # Wait for all private connectors to be ready
        for connector in self._private_connectors.values():
            await connector.wait_ready()

    async def _start_ems(self):
        for ems in self._ems.values():
            await ems.start()

    def _start_scheduler(self):
        self._strategy._scheduler.start()
        self._scheduler_started = True

    async def _start(self):
        await self._sms.start()
        await self._start_ems()
        await self._start_connectors()
        if self._custom_signal_recv:
            await self._custom_signal_recv.start()
        self._strategy._on_start()
        self._start_scheduler()
        await self._task_manager.wait()

    async def _cancel_all_open_orders(self):
        """Cancel all open orders across all exchanges during shutdown."""
        # Get all open orders grouped by symbol
        symbol_to_orders = defaultdict(set)
        for exchange, oids in self._cache._mem_open_orders.items():
            if not oids:
                continue
            for oid in oids:
                order = self._cache._mem_orders.get(oid)
                if order:
                    symbol_to_orders[order.symbol].add(oid)

        if not symbol_to_orders:
            self._log.debug("No open orders to cancel")
            return

        total_symbols = len(symbol_to_orders)
        total_orders = sum(len(oids) for oids in symbol_to_orders.values())
        self._log.info(
            f"Cancelling {total_orders} open orders across {total_symbols} symbols..."
        )

        # Cancel orders for each symbol
        for symbol, oids in symbol_to_orders.items():
            # Determine account type for this symbol
            instrument_id = InstrumentId.from_str(symbol)
            ems = self._ems.get(instrument_id.exchange)
            if not ems:
                self._log.warning(
                    f"EMS {instrument_id.exchange} not found for {symbol}"
                )
                continue

            account_type = ems._instrument_id_to_account_type(instrument_id)
            connector = self._private_connectors.get(account_type)
            if not connector:
                self._log.warning(f"Private connector not found for {account_type}")
                continue

            # Cancel all orders for this symbol
            self._log.debug(f"Cancelling {len(oids)} orders for {symbol}")
            await connector._oms.cancel_all_orders(instrument_id.symbol)

        # Wait briefly for cancellations to be acknowledged
        await asyncio.sleep(0.1)
        self._log.info("Order cancellation completed")

    async def _dispose(self):
        # Cancel all open orders if configured
        if self._config.exit_after_cancel:
            await self._cancel_all_open_orders()

        if self._scheduler_started:
            try:
                # Remove all jobs first to prevent new executions
                self._strategy._scheduler.remove_all_jobs()
                # Short delay to allow running jobs to complete
                await asyncio.sleep(0.05)
                # Shutdown without waiting for jobs to complete
                self._strategy._scheduler.shutdown(wait=False)
            except (asyncio.CancelledError, RuntimeError):
                # Suppress expected shutdown exceptions
                pass

        for connector in self._public_connectors.values():
            await connector.disconnect()
        for connector in self._private_connectors.values():
            await connector.disconnect()

        await asyncio.sleep(0.2)  # NOTE: wait for the websocket to disconnect

        await self._task_manager.cancel()
        await self._cache.close()
        self._push_service.shutdown()

    def start(self):
        self._build()
        self._loop.run_until_complete(self._cache.start())  # Initialize cache
        self._start_web_interface()
        self._loop.run_until_complete(self._start())

    def _close_event_loop(self):
        """Close event loop with proper error handling."""
        if self._loop.is_closed():
            return

        try:
            # Cancel any remaining tasks
            pending_tasks = asyncio.all_tasks(self._loop)
            if pending_tasks:
                self._log.debug(f"Cancelling {len(pending_tasks)} pending tasks")
                for task in pending_tasks:
                    task.cancel()

            self._loop.close()
            self._log.debug("Event loop closed successfully")

        except Exception as e:
            self._log.warning(f"Event loop close error: {e}")

    def dispose(self):
        try:
            try:
                self._strategy._on_stop()
            except Exception as e:
                # Ensure strategy stop errors don't block shutdown
                self._log.warning(f"Strategy on_stop error: {e}")

            self._loop.run_until_complete(self._dispose())
        except Exception as e:
            # Never let dispose crash; make shutdown best-effort
            self._log.error(f"Dispose error: {e}")
        finally:
            if self._web_server:
                try:
                    self._web_server.stop()
                except Exception as exc:  # pragma: no cover - defensive cleanup
                    self._log.debug(f"Error stopping web server: {exc}")
                finally:
                    self._web_server = None
            if self._web_app:
                self._web_app.unbind_strategy()

            self._close_event_loop()
            logging.shutdown()
