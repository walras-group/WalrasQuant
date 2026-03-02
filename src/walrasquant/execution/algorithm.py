from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Callable, Dict, List, Literal, Mapping
from datetime import timedelta

import nexuslog as logging

from walrasquant.base.ems import ExecutionManagementSystem
from walrasquant.constants import (
    ExchangeType,
    OrderType,
    SubmitType,
    TimeInForce,
)
from walrasquant.core.cache import AsyncCache
from walrasquant.core.entity import OidGen, TaskManager
from walrasquant.core.nautilius_core import LiveClock, MessageBus, TimeEvent
from walrasquant.core.registry import OrderRegistry
from walrasquant.schema import (
    BaseMarket,
    BatchOrder,
    BatchOrderSubmit,
    CancelOrderSubmit,
    CreateOrderSubmit,
    InstrumentId,
    Order,
)
from walrasquant.execution.config import ExecAlgorithmConfig
from walrasquant.execution.constants import ExecAlgorithmStatus
from walrasquant.execution.schema import ExecAlgorithmCommand, ExecAlgorithmOrder


class ExecAlgorithm(ABC):
    """
    Base class for all execution algorithms.

    This class allows traders to implement their own customized execution algorithms
    for order splitting, TWAP, VWAP, iceberg orders, etc.

    Parameters
    ----------
    config : ExecAlgorithmConfig, optional
        The execution algorithm configuration.

    Example
    -------
    >>> class MyAlgorithm(ExecAlgorithm):
    ...     def on_order(self, exec_order: ExecAlgorithmOrder):
    ...         # Split order into two parts
    ...         half = exec_order.total_amount / 2
    ...         self.spawn_market(exec_order, half)
    ...         self.spawn_market(exec_order, half)
    """

    def __init__(self, config: ExecAlgorithmConfig | None = None):
        if config is None:
            config = ExecAlgorithmConfig()

        self._id = config.exec_algorithm_id or type(self).__name__
        self._config = config
        self._log = logging.getLogger(name=f"ExecAlgorithm.{self._id}")

        # Internal state
        self._initialized = False
        self._running = False

        # Core components (set during registration)
        self._msgbus: MessageBus | None = None
        self._clock: LiveClock | None = None
        self._cache: AsyncCache | None = None
        self._task_manager: TaskManager | None = None
        self._oidgen: OidGen | None = None
        self._registry: OrderRegistry | None = None
        self._market: Mapping[str, BaseMarket] | None = None
        self._ems: Mapping[ExchangeType, ExecutionManagementSystem] | None = (
            None  # Reference to EMS for order submission
        )

        # Order tracking
        self._exec_spawn_ids: Dict[str, int] = {}  # primary_oid -> spawn sequence
        self._primary_orders: Dict[
            str, ExecAlgorithmOrder
        ] = {}  # primary_oid -> order tracking
        self._spawned_to_primary: Dict[str, str] = {}  # spawned_oid -> primary_oid

    @property
    def id(self) -> str:
        """Return the execution algorithm ID."""
        return self._id

    @property
    def config(self) -> ExecAlgorithmConfig:
        """Return the execution algorithm configuration."""
        return self._config

    @property
    def is_running(self) -> bool:
        """Return whether the algorithm is running."""
        return self._running

    def tick_sz(self, symbol: str) -> float:
        return self.get_market(symbol).precision.price

    def lot_sz(self, symbol: str) -> float:
        return self.get_market(symbol).precision.amount

    # ==================== Registration ====================

    def register(
        self,
        msgbus: MessageBus,
        clock: LiveClock,
        cache: AsyncCache,
        task_manager: TaskManager,
        oidgen: OidGen,
        registry: OrderRegistry,
        market: Mapping[str, BaseMarket],
        ems: Mapping[ExchangeType, ExecutionManagementSystem],
    ):
        """
        Register the execution algorithm with the system.
        Called by Engine during initialization.

        Parameters
        ----------
        msgbus : MessageBus
            The message bus for communication.
        clock : LiveClock
            The clock for time-related operations.
        cache : AsyncCache
            The cache for data access.
        task_manager : TaskManager
            The task manager for async operations.
        oidgen : OidGen
            The order ID generator.
        registry : OrderRegistry
            The order registry.
        market : Mapping[str, BaseMarket]
            The market information.
        ems : ExecutionManagementSystem
            The execution management system.
        """
        self._msgbus = msgbus
        self._clock = clock
        self._cache = cache
        self._task_manager = task_manager
        self._oidgen = oidgen
        self._registry = registry
        self._market = market
        self._ems = ems

        # Register MessageBus endpoint for commands
        self._msgbus.register(
            endpoint=f"{self._id}.execute", handler=self._handle_execute_command
        )

        self._initialized = True
        self._log.info(f"ExecAlgorithm {self._id} registered")

    def _subscribe_order_events(self):
        """Subscribe to order events from the message bus."""
        self._msgbus.subscribe(topic="pending", handler=self._on_order_pending)
        self._msgbus.subscribe(topic="accepted", handler=self._on_order_accepted)
        self._msgbus.subscribe(
            topic="partially_filled", handler=self._on_order_partially_filled
        )
        self._msgbus.subscribe(topic="filled", handler=self._on_order_filled)
        self._msgbus.subscribe(topic="canceled", handler=self._on_order_canceled)
        self._msgbus.subscribe(topic="failed", handler=self._on_order_failed)

    # ==================== Lifecycle ====================

    def start(self):
        """Start the execution algorithm."""
        if not self._initialized:
            raise RuntimeError("ExecAlgorithm not registered")
        self._running = True
        self._subscribe_order_events()
        self.on_start()
        self._log.info(f"ExecAlgorithm {self._id} started")

    def stop(self):
        """Stop the execution algorithm."""
        self._running = False
        self.on_stop()
        self._log.info(f"ExecAlgorithm {self._id} stopped")

    def reset(self):
        """Reset the execution algorithm state."""
        self._exec_spawn_ids.clear()
        self._primary_orders.clear()
        self._spawned_to_primary.clear()
        self.on_reset()
        self._log.info(f"ExecAlgorithm {self._id} reset")

    # ==================== Command Handling ====================

    def _handle_execute_command(self, command: ExecAlgorithmCommand):
        """Handle incoming execution command from Strategy."""
        if not self._running:
            self._log.warning(
                f"ExecAlgorithm {self._id} is not running, ignoring command"
            )
            return

        if self._config.log_commands:
            self._log.debug(f"Received command: {command}")

        if command.command_type.is_execute:
            self._handle_order_execution(command)
        elif command.command_type.is_cancel:
            self._handle_cancel_execution(command)

    def _handle_order_execution(self, command: ExecAlgorithmCommand):
        """Handle new order execution request."""
        order_params = command.order_params

        if order_params is None:
            self._log.error("Order params is None")
            return

        # Create primary order tracking
        exec_order = ExecAlgorithmOrder(
            primary_oid=order_params.oid,
            symbol=order_params.symbol,
            side=order_params.side,
            total_amount=order_params.amount,
            remaining_amount=order_params.amount,
            params=command.exec_params,
            account_type=order_params.account_type,
            reduce_only=order_params.reduce_only,
            status=ExecAlgorithmStatus.RUNNING,
        )

        self._primary_orders[order_params.oid] = exec_order

        # Call user implementation
        self.on_order(exec_order)

    def _handle_cancel_execution(self, command: ExecAlgorithmCommand):
        """Handle execution cancellation request."""
        primary_oid = command.primary_oid

        if primary_oid is None:
            self._log.error("Primary oid is None for cancel command")
            return

        if primary_oid not in self._primary_orders:
            self._log.warning(f"Primary order {primary_oid} not found for cancellation")
            return

        exec_order = self._primary_orders[primary_oid]
        exec_order.status = ExecAlgorithmStatus.CANCELING

        # Cancel all active spawned orders
        for spawned_oid in exec_order.spawned_oids:
            order = self._cache.get_order(spawned_oid).value_or(None)
            if not order:
                continue

            if order.is_opened:
                self.cancel_spawned_order(exec_order, spawned_oid)

        self.on_cancel(exec_order)

    # ==================== Order Event Handlers ====================

    def _on_order_pending(self, order: Order):
        """Handle order pending event."""
        if order.oid in self._spawned_to_primary:
            primary_oid = self._spawned_to_primary[order.oid]
            exec_order = self._primary_orders.get(primary_oid)
            if exec_order:
                if self._config.log_events:
                    self._log.debug(f"Spawned order {order.oid} pending")
                self.on_spawned_order_pending(exec_order, order)

    def _on_order_accepted(self, order: Order):
        """Handle order accepted event."""
        if order.oid in self._spawned_to_primary:
            primary_oid = self._spawned_to_primary[order.oid]
            exec_order = self._primary_orders.get(primary_oid)
            if exec_order:
                if self._config.log_events:
                    self._log.debug(f"Spawned order {order.oid} accepted")
                self.on_spawned_order_accepted(exec_order, order)

    def _on_order_partially_filled(self, order: Order):
        """Handle order partially filled event."""
        if order.oid in self._spawned_to_primary:
            primary_oid = self._spawned_to_primary[order.oid]
            exec_order = self._primary_orders.get(primary_oid)
            if exec_order:
                if self._config.log_events:
                    self._log.debug(
                        f"Spawned order {order.oid} partially filled: {order.filled}"
                    )
                self.on_spawned_order_partially_filled(exec_order, order)

    def _on_order_filled(self, order: Order):
        """Handle order filled event."""
        if order.oid in self._spawned_to_primary:
            primary_oid = self._spawned_to_primary[order.oid]
            exec_order = self._primary_orders.get(primary_oid)
            if exec_order:
                # Update remaining amount
                if order.filled:
                    exec_order.remaining_amount -= order.filled
                if self._config.log_events:
                    self._log.debug(
                        f"Spawned order {order.oid} filled, remaining: {exec_order.remaining_amount}"
                    )
                self.on_spawned_order_filled(exec_order, order)

    def _on_order_canceled(self, order: Order):
        """Handle order canceled event."""
        if order.oid in self._spawned_to_primary:
            primary_oid = self._spawned_to_primary[order.oid]
            exec_order = self._primary_orders.get(primary_oid)
            if exec_order:
                if self._config.log_events:
                    self._log.debug(f"Spawned order {order.oid} canceled")
                self.on_spawned_order_canceled(exec_order, order)

    def _on_order_failed(self, order: Order):
        """Handle order failed event."""
        if order.oid in self._spawned_to_primary:
            primary_oid = self._spawned_to_primary[order.oid]
            exec_order = self._primary_orders.get(primary_oid)
            if exec_order:
                if self._config.log_events:
                    self._log.warning(f"Spawned order {order.oid} failed")
                self.on_spawned_order_failed(exec_order, order)

    # ==================== Order Spawning ====================

    # def _generate_spawn_id(self, primary_oid: str) -> str:
    #     """Generate a unique ID for a spawned order."""
    #     spawn_seq = self._exec_spawn_ids.get(primary_oid, 0) + 1
    #     self._exec_spawn_ids[primary_oid] = spawn_seq
    #     return f"{primary_oid}-S{spawn_seq}"

    def spawn_market(
        self,
        exec_order: ExecAlgorithmOrder,
        quantity: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool | None = None,
        **kwargs,
    ) -> str:
        """
        Spawn a new MARKET order from the primary order.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The primary order execution context.
        quantity : Decimal
            The spawned order quantity.
        time_in_force : TimeInForce
            Time in force for the order.
        reduce_only : bool | None
            If None, inherits from primary order.

        Returns
        -------
        str
            The spawned order ID.
        """
        spawn_oid = self._oidgen.oid

        if reduce_only is None:
            reduce_only = exec_order.reduce_only

        # Create order submit
        order_submit = CreateOrderSubmit(
            symbol=exec_order.symbol,
            oid=spawn_oid,
            instrument_id=InstrumentId.from_str(exec_order.symbol),
            side=exec_order.side,
            type=OrderType.MARKET,
            amount=quantity,
            price=None,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            kwargs=kwargs,
        )

        # Track spawned order
        exec_order.spawned_oids.append(spawn_oid)
        self._spawned_to_primary[spawn_oid] = exec_order.primary_oid

        # Submit via EMS
        self._registry.register_order(spawn_oid)
        self._ems[order_submit.instrument_id.exchange]._submit_order(
            order_submit, SubmitType.CREATE, exec_order.account_type
        )

        self._log.debug(
            f"Spawned MARKET order {spawn_oid} qty={quantity} for primary {exec_order.primary_oid}"
        )
        return spawn_oid

    def spawn_market_ws(
        self,
        exec_order: ExecAlgorithmOrder,
        quantity: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool | None = None,
        **kwargs,
    ) -> str:
        """
        Spawn a new MARKET order via WebSocket from the primary order.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The primary order execution context.
        quantity : Decimal
            The spawned order quantity.
        time_in_force : TimeInForce
            Time in force for the order.
        reduce_only : bool | None
            If None, inherits from primary order.

        Returns
        -------
        str
            The spawned order ID.
        """
        spawn_oid = self._oidgen.oid

        if reduce_only is None:
            reduce_only = exec_order.reduce_only

        order_submit = CreateOrderSubmit(
            symbol=exec_order.symbol,
            oid=spawn_oid,
            instrument_id=InstrumentId.from_str(exec_order.symbol),
            side=exec_order.side,
            type=OrderType.MARKET,
            amount=quantity,
            price=None,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            kwargs=kwargs,
        )

        exec_order.spawned_oids.append(spawn_oid)
        self._spawned_to_primary[spawn_oid] = exec_order.primary_oid

        self._registry.register_order(spawn_oid)
        self._ems[order_submit.instrument_id.exchange]._submit_order(
            order_submit, SubmitType.CREATE_WS, exec_order.account_type
        )

        self._log.debug(
            f"Spawned MARKET order (WS) {spawn_oid} qty={quantity} for primary {exec_order.primary_oid}"
        )
        return spawn_oid

    def spawn_limit(
        self,
        exec_order: ExecAlgorithmOrder,
        quantity: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool | None = None,
        post_only: bool = False,
        **kwargs,
    ) -> str:
        """
        Spawn a new LIMIT order from the primary order.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The primary order execution context.
        quantity : Decimal
            The spawned order quantity.
        price : Decimal
            The limit price.
        time_in_force : TimeInForce
            Time in force for the order.
        reduce_only : bool | None
            If None, inherits from primary order.
        post_only : bool
            If True, use POST_ONLY order type.
        **kwargs,
        Returns
        -------
        str
            The spawned order ID.
        """
        spawn_oid = self._oidgen.oid

        if reduce_only is None:
            reduce_only = exec_order.reduce_only

        order_type = OrderType.POST_ONLY if post_only else OrderType.LIMIT

        # Create order submit
        order_submit = CreateOrderSubmit(
            symbol=exec_order.symbol,
            oid=spawn_oid,
            instrument_id=InstrumentId.from_str(exec_order.symbol),
            side=exec_order.side,
            type=order_type,
            amount=quantity,
            price=price,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            kwargs=kwargs,
        )

        # Track spawned order
        exec_order.spawned_oids.append(spawn_oid)
        self._spawned_to_primary[spawn_oid] = exec_order.primary_oid

        # Submit via EMS
        self._registry.register_order(spawn_oid)
        self._ems[order_submit.instrument_id.exchange]._submit_order(
            order_submit, SubmitType.CREATE, exec_order.account_type
        )

        self._log.debug(
            f"Spawned LIMIT order {spawn_oid} qty={quantity} price={price} for primary {exec_order.primary_oid}"
        )
        return spawn_oid

    def spawn_limit_ws(
        self,
        exec_order: ExecAlgorithmOrder,
        quantity: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool | None = None,
        post_only: bool = False,
        **kwargs,
    ) -> str:
        """
        Spawn a new LIMIT order via WebSocket from the primary order.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The primary order execution context.
        quantity : Decimal
            The spawned order quantity.
        price : Decimal
            The limit price.
        time_in_force : TimeInForce
            Time in force for the order.
        reduce_only : bool | None
            If None, inherits from primary order.
        post_only : bool
            If True, use POST_ONLY order type.

        Returns
        -------
        str
            The spawned order ID.
        """
        spawn_oid = self._oidgen.oid

        if reduce_only is None:
            reduce_only = exec_order.reduce_only

        order_type = OrderType.POST_ONLY if post_only else OrderType.LIMIT

        order_submit = CreateOrderSubmit(
            symbol=exec_order.symbol,
            oid=spawn_oid,
            instrument_id=InstrumentId.from_str(exec_order.symbol),
            side=exec_order.side,
            type=order_type,
            amount=quantity,
            price=price,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            kwargs=kwargs,
        )

        exec_order.spawned_oids.append(spawn_oid)
        self._spawned_to_primary[spawn_oid] = exec_order.primary_oid

        self._registry.register_order(spawn_oid)
        self._ems[order_submit.instrument_id.exchange]._submit_order(
            order_submit, SubmitType.CREATE_WS, exec_order.account_type
        )

        self._log.debug(
            f"Spawned LIMIT order (WS) {spawn_oid} qty={quantity} price={price} for primary {exec_order.primary_oid}"
        )
        return spawn_oid

    def spawn_batch_orders(
        self,
        exec_order: ExecAlgorithmOrder,
        orders: List[BatchOrder],
    ) -> List[str]:
        """
        Spawn a batch of orders from the primary order.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The primary order execution context.
        orders : List[BatchOrder]
            List of batch orders to spawn.

        Returns
        -------
        List[str]
            List of spawned order IDs.
        """
        batch_orders: List[BatchOrderSubmit] = []
        spawn_oids: List[str] = []

        for order in orders:
            spawn_oid = self._oidgen.oid
            batch_order = BatchOrderSubmit(
                symbol=order.symbol,
                instrument_id=InstrumentId.from_str(order.symbol),
                side=order.side,
                type=order.type,
                oid=spawn_oid,
                amount=order.amount,
                price=order.price,
                time_in_force=order.time_in_force,
                reduce_only=order.reduce_only,
                kwargs=order.kwargs,
            )
            batch_orders.append(batch_order)
            spawn_oids.append(spawn_oid)

            exec_order.spawned_oids.append(spawn_oid)
            self._spawned_to_primary[spawn_oid] = exec_order.primary_oid
            self._registry.register_order(spawn_oid)

            self._log.debug(
                f"Spawned batch order {spawn_oid} for primary {exec_order.primary_oid}"
            )

        self._ems[batch_orders[0].instrument_id.exchange]._submit_order(
            batch_orders, SubmitType.BATCH, exec_order.account_type
        )

        return spawn_oids

    def cancel_spawned_order(self, exec_order: ExecAlgorithmOrder, spawned_oid: str):
        """Cancel a spawned order."""
        self._cache.mark_cancel_intent(spawned_oid)

        cancel_submit = CancelOrderSubmit(
            symbol=exec_order.symbol,
            instrument_id=InstrumentId.from_str(exec_order.symbol),
            oid=spawned_oid,
            kwargs={},
        )

        self._ems[cancel_submit.instrument_id.exchange]._submit_order(
            cancel_submit, SubmitType.CANCEL, exec_order.account_type
        )
        self._log.debug(f"Canceling spawned order {spawned_oid}")

    def cancel_spawned_order_ws(
        self, exec_order: ExecAlgorithmOrder, spawned_oid: str, **kwargs
    ):
        """Cancel a spawned order via WebSocket."""
        self._cache.mark_cancel_intent(spawned_oid)

        cancel_submit = CancelOrderSubmit(
            symbol=exec_order.symbol,
            instrument_id=InstrumentId.from_str(exec_order.symbol),
            oid=spawned_oid,
            kwargs=kwargs,
        )

        self._ems[cancel_submit.instrument_id.exchange]._submit_order(
            cancel_submit, SubmitType.CANCEL_WS, exec_order.account_type
        )
        self._log.debug(f"Canceling spawned order (WS) {spawned_oid}")

    def get_algo_order(self, primary_oid: str) -> ExecAlgorithmOrder | None:
        """
        Get an ExecAlgorithmOrder by its primary order ID.

        Parameters
        ----------
        primary_oid : str
            The primary order ID.

        Returns
        -------
        ExecAlgorithmOrder | None
            The execution algorithm order, or None if not found.
        """
        return self._primary_orders.get(primary_oid)

    def mark_complete(self, exec_order: ExecAlgorithmOrder):
        """
        Mark execution as complete.

        Call this method when your execution logic determines the order is done.
        This can be called from any hook (on_spawned_order_filled, on_cancel,
        timer callbacks, etc.) based on your algorithm's completion criteria.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The execution order to mark as complete.

        Example
        -------
        >>> def on_spawned_order_filled(self, exec_order, order):
        ...     if exec_order.remaining_amount <= 0:
        ...         self.mark_complete(exec_order)
        """
        exec_order.status = ExecAlgorithmStatus.COMPLETED
        self._log.info(
            f"Execution completed for primary order {exec_order.primary_oid}"
        )
        self.on_execution_complete(exec_order)

    # ==================== Timer Support ====================

    def set_timer(
        self,
        name: str,
        interval: timedelta,
        callback: Callable[[TimeEvent], None],
        start_time: int | None = None,
        stop_time: int | None = None,
    ):
        """
        Set a timer for scheduled execution.

        Parameters
        ----------
        name : str
            The timer name.
        interval : timedelta
            The interval between timer events.
        callback : Callable[[TimeEvent], None]
            The callback function.
        start_time : int | None
            The start time in nanoseconds.
        stop_time : int | None
            The stop time in nanoseconds.
        """
        self._clock.set_timer(
            name=name,
            interval=interval,
            start_time=start_time,
            stop_time=stop_time,
            callback=callback,
        )

    def cancel_timer(self, name: str):
        """Cancel a timer."""
        self._clock.cancel_timer(name)

    # ==================== Utility Methods ====================

    @property
    def cache(self) -> AsyncCache:
        """Get the cache instance."""
        return self._cache

    def get_market(self, symbol: str) -> BaseMarket:
        """Get market information for a symbol."""
        return self._market[symbol]

    @property
    def timestamp_ms(self) -> int:
        """Get current timestamp in milliseconds."""
        return self._clock.timestamp_ms()

    # ==================== Precision Methods ====================

    def amount_to_precision(
        self,
        symbol: str,
        amount: Decimal | float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        """
        Convert the amount to the precision of the market.

        Parameters
        ----------
        symbol : str
            The trading symbol.
        amount : Decimal | float
            The amount to convert.
        mode : Literal["round", "ceil", "floor"]
            The rounding mode.

        Returns
        -------
        Decimal
            The amount with correct precision.
        """
        instrument_id = InstrumentId.from_str(symbol)
        return self._ems[instrument_id.exchange]._amount_to_precision(
            instrument_id.symbol, amount, mode
        )

    def price_to_precision(
        self,
        symbol: str,
        price: Decimal | float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        """
        Convert the price to the precision of the market.

        Parameters
        ----------
        symbol : str
            The trading symbol.
        price : Decimal | float
            The price to convert.
        mode : Literal["round", "ceil", "floor"]
            The rounding mode.

        Returns
        -------
        Decimal
            The price with correct precision.
        """
        instrument_id = InstrumentId.from_str(symbol)
        return self._ems[instrument_id.exchange]._price_to_precision(
            instrument_id.symbol, price, mode
        )

    def min_order_amount(self, symbol: str, px: float | None = None) -> Decimal:
        """
        Get the minimum order amount for a symbol.

        Parameters
        ----------
        symbol : str
            The trading symbol.
        px : float | None
            The price for cost-based minimum calculation.
            If None, uses current market mid price from bookl1.

        Returns
        -------
        Decimal
            The minimum order amount.
        """
        instrument_id = InstrumentId.from_str(symbol)
        px = px or self.cache.bookl1(symbol).mid
        if px is None:
            raise ValueError(
                "px must be provided if you call `min_order_amount` or just set `px`"
            )
        return self._ems[instrument_id.exchange]._get_min_order_amount(
            instrument_id.symbol, self.get_market(symbol), px
        )

    # ==================== User Overridable Hooks ====================

    def on_start(self):
        """Called when algorithm starts. Override in subclass."""
        pass

    def on_stop(self):
        """Called when algorithm stops. Override in subclass."""
        pass

    def on_reset(self):
        """Called when algorithm resets. Override in subclass."""
        pass

    @abstractmethod
    def on_order(self, exec_order: ExecAlgorithmOrder):
        """
        Called when a new order is received for execution.
        Must be implemented by subclass.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The order execution context.
        """
        pass

    def on_cancel(self, exec_order: ExecAlgorithmOrder):
        """Called when execution is being canceled. Override in subclass."""
        pass

    def on_spawned_order_pending(self, exec_order: ExecAlgorithmOrder, order: Order):
        """Called when spawned order is pending. Override in subclass."""
        pass

    def on_spawned_order_accepted(self, exec_order: ExecAlgorithmOrder, order: Order):
        """Called when spawned order is accepted. Override in subclass."""
        pass

    def on_spawned_order_partially_filled(
        self, exec_order: ExecAlgorithmOrder, order: Order
    ):
        """Called when spawned order is partially filled. Override in subclass."""
        pass

    def on_spawned_order_filled(self, exec_order: ExecAlgorithmOrder, order: Order):
        """Called when spawned order is filled. Override in subclass."""
        pass

    def on_spawned_order_canceled(self, exec_order: ExecAlgorithmOrder, order: Order):
        """Called when spawned order is canceled. Override in subclass."""
        pass

    def on_spawned_order_failed(self, exec_order: ExecAlgorithmOrder, order: Order):
        """Called when spawned order fails. Override in subclass."""
        pass

    def on_execution_complete(self, exec_order: ExecAlgorithmOrder):
        """Called when execution is complete. Override in subclass."""
        pass
