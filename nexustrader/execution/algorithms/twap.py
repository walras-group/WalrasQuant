import math
from decimal import Decimal
from datetime import timedelta
from typing import Dict, List, Set

from nexustrader.core.nautilius_core import TimeEvent
from nexustrader.execution.algorithm import (
    ExecAlgorithm,
)
from nexustrader.execution.constants import ExecAlgorithmStatus
from nexustrader.execution.schema import ExecAlgorithmOrder
from nexustrader.execution.config import TWAPConfig
from nexustrader.schema import Order


class TWAPExecAlgorithm(ExecAlgorithm):
    """
    Time-Weighted Average Price (TWAP) Execution Algorithm.

    Splits a large order into smaller chunks and executes them
    at regular intervals over a specified time horizon.

    Required exec_params:
    ---------------------
    horizon_secs : int
        Total execution time horizon in seconds.
    interval_secs : int
        Interval between order slices in seconds.

    Optional exec_params:
    ---------------------
    use_limit : bool, default False
        If True, use limit orders instead of market orders.
    n_tick_sz : int, default 0
        Number of tick sizes to offset from the best bid/ask for limit orders.
        Positive for better price (more passive), negative for worse price (more aggressive).

    Example
    -------
    >>> # Execute 1 BTC over 5 minutes with 30-second intervals
    >>> oid = strategy.create_algo_order(
    ...     symbol="BTCUSDT-PERP.BINANCE",
    ...     side=OrderSide.BUY,
    ...     amount=Decimal("1.0"),
    ...     exec_algorithm_id="TWAP",
    ...     exec_params={
    ...         "horizon_secs": 300,
    ...         "interval_secs": 30,
    ...         "n_tick_sz": 0,
    ...     },
    ... )
    """

    def __init__(self, config: TWAPConfig | None = None):
        if config is None:
            config = TWAPConfig()
        super().__init__(config)

        # Track scheduled execution
        self._scheduled_sizes: Dict[str, List[Decimal]] = {}
        self._active_timers: Set[str] = set()
        # Track current limit order for each primary order (for use_limit mode)
        self._current_limit_oid: Dict[str, str] = {}
        # Track carryover amount from unfilled limit orders
        self._carryover_amount: Dict[str, Decimal] = {}

    def on_start(self):
        """Initialize TWAP algorithm."""
        pass

    def on_stop(self):
        """Cleanup timers on stop."""
        for timer_name in list(self._active_timers):
            self.cancel_timer(timer_name)
        self._active_timers.clear()

    def on_reset(self):
        """Reset TWAP state."""
        self._scheduled_sizes.clear()
        self._active_timers.clear()
        self._current_limit_oid.clear()
        self._carryover_amount.clear()

    def on_order(self, exec_order: ExecAlgorithmOrder):
        """
        Handle new order for TWAP execution.

        Parameters
        ----------
        exec_order : ExecAlgorithmOrder
            The order execution context containing symbol, side, amount, and params.
        """
        params = exec_order.params

        # Validate required parameters
        horizon_secs = params.get("horizon_secs")
        interval_secs = params.get("interval_secs")

        if not horizon_secs or not interval_secs:
            self._log.error(
                f"Missing required params for TWAP: horizon_secs={horizon_secs}, "
                f"interval_secs={interval_secs}"
            )
            exec_order.status = ExecAlgorithmStatus.FAILED
            return

        if horizon_secs < interval_secs:
            self._log.error(
                f"horizon_secs ({horizon_secs}) must be >= interval_secs ({interval_secs})"
            )
            exec_order.status = ExecAlgorithmStatus.FAILED
            return

        # Calculate number of slices
        num_slices = max(1, math.floor(horizon_secs / interval_secs))

        # Calculate slice size using proper precision
        total_amount = exec_order.total_amount
        slice_amount = self.amount_to_precision(
            exec_order.symbol, total_amount / num_slices, mode="floor"
        )

        # Check minimum order size
        min_amount = self.min_order_amount(exec_order.symbol)

        if slice_amount < min_amount:
            # If slice is too small, execute entire amount at once
            self._log.warning(
                f"TWAP slice size {slice_amount} below minimum {min_amount}, "
                f"executing full amount"
            )
            self._execute_slice(exec_order, total_amount)
            self.mark_complete(exec_order)
            return

        # Build schedule
        scheduled_sizes = [slice_amount] * num_slices
        remainder = total_amount - (slice_amount * num_slices)
        if remainder > min_amount:
            scheduled_sizes[-1] += remainder

        self._scheduled_sizes[exec_order.primary_oid] = list(scheduled_sizes)

        self._log.info(
            f"TWAP for {exec_order.primary_oid}: {len(scheduled_sizes)} slices of ~{slice_amount}, "
            f"horizon={horizon_secs}s, interval={interval_secs}s"
        )

        # Execute first slice immediately
        self._execute_next_slice(exec_order)

        # Set timer for remaining slices if there are more
        if len(self._scheduled_sizes.get(exec_order.primary_oid, [])) > 0:
            timer_name = f"twap_{exec_order.primary_oid}"
            self._active_timers.add(timer_name)
            self.set_timer(
                name=timer_name,
                interval=timedelta(seconds=interval_secs),
                callback=lambda event: self._on_timer_event(
                    event, exec_order.primary_oid
                ),
            )
        else:
            # Only one slice, mark complete immediately
            self.mark_complete(exec_order)

    def _on_timer_event(self, event: TimeEvent, primary_oid: str):
        """Handle timer event for next slice."""
        _ = event  # unused but required by timer callback signature

        if primary_oid not in self._primary_orders:
            self._log.warning(f"Primary order {primary_oid} not found for timer event")
            self._cleanup_timer(primary_oid)
            return

        exec_order = self._primary_orders[primary_oid]

        if exec_order.status != ExecAlgorithmStatus.RUNNING:
            self._cleanup_timer(primary_oid)
            return

        scheduled_sizes = self._scheduled_sizes.get(primary_oid, [])
        if not scheduled_sizes:
            # All slices already placed in previous timer event
            # Now check if the final limit order was filled
            self._handle_final_limit_order(exec_order)
            self._cleanup_timer(primary_oid)
            self.mark_complete(exec_order)
            return

        self._execute_next_slice(exec_order)
        # Don't handle final order here - let next timer event do it
        # so the last slice has time to fill

    def _execute_next_slice(self, exec_order: ExecAlgorithmOrder):
        """Execute the next TWAP slice."""
        scheduled_sizes = self._scheduled_sizes.get(exec_order.primary_oid, [])

        if not scheduled_sizes:
            return

        slice_amount = scheduled_sizes.pop(0)
        self._execute_slice(exec_order, slice_amount)

    def _execute_slice(self, exec_order: ExecAlgorithmOrder, slice_amount: Decimal):
        """Execute a single TWAP slice."""
        params = exec_order.params
        use_limit = params.get("use_limit", False)
        primary_oid = exec_order.primary_oid

        if use_limit:
            # Check and handle previous limit order if exists
            self._handle_previous_limit_order(exec_order)

            # Add any carryover amount from previous unfilled orders
            carryover = self._carryover_amount.pop(primary_oid, Decimal("0"))
            total_slice_amount = slice_amount + carryover
            if carryover > 0:
                self._log.debug(
                    f"Adding carryover {carryover} to slice, total: {total_slice_amount}"
                )

            # Get current market price
            bookl1 = self.cache.bookl1(exec_order.symbol)
            if bookl1:
                n_tick_sz = params.get("n_tick_sz", 0)
                tick_sz = self.tick_sz(exec_order.symbol)

                if exec_order.side.is_buy:
                    # For buy, offset positive = lower price (more passive)
                    raw_price = bookl1.bid - n_tick_sz * tick_sz
                else:
                    # For sell, offset positive = higher price (more passive)
                    raw_price = bookl1.ask + n_tick_sz * tick_sz

                price = self.price_to_precision(exec_order.symbol, raw_price)
                spawn_oid = self.spawn_limit(exec_order, total_slice_amount, price)
                # Track current limit order for next slice check
                self._current_limit_oid[primary_oid] = spawn_oid
            else:
                # Fallback to market order if no book data
                self._log.warning(
                    f"No book data for {exec_order.symbol}, using market order"
                )
                self.spawn_market(exec_order, total_slice_amount)
                self._current_limit_oid.pop(primary_oid, None)
        else:
            self.spawn_market(exec_order, slice_amount)

    def _handle_previous_limit_order(self, exec_order: ExecAlgorithmOrder):
        """
        Handle previous limit order before placing a new one.

        If previous order is not fully filled, cancel it and either:
        - Use market order for remaining if >= min_order_fill
        - Add remaining to carryover for next slice if < min_order_fill
        """
        primary_oid = exec_order.primary_oid
        prev_oid = self._current_limit_oid.get(primary_oid)

        if not prev_oid:
            return

        # Get the previous order from cache
        prev_order = self._cache.get_order(prev_oid).value_or(None)
        if not prev_order:
            self._current_limit_oid.pop(primary_oid, None)
            return

        # Check if order is still open (not fully filled)
        if not prev_order.is_opened:
            # Order is already closed (filled, canceled, etc.)
            self._current_limit_oid.pop(primary_oid, None)
            return

        # Calculate unfilled amount
        filled = prev_order.filled or Decimal("0")
        unfilled = prev_order.amount - filled

        if unfilled <= 0:
            self._current_limit_oid.pop(primary_oid, None)
            return

        self._log.info(
            f"Previous limit order {prev_oid} not fully filled. "
            f"Filled: {filled}, Unfilled: {unfilled}"
        )

        # Cancel the previous order
        self.cancel_spawned_order(exec_order, prev_oid)
        self._current_limit_oid.pop(primary_oid, None)

        # Get minimum order amount
        min_amount = self.min_order_amount(exec_order.symbol)

        if unfilled >= min_amount:
            # Use market order to take the remaining
            self._log.info(
                f"Using market order to fill remaining {unfilled} from previous slice"
            )
            self.spawn_market(exec_order, unfilled)
        else:
            # Add to carryover for next slice
            self._log.info(
                f"Unfilled amount {unfilled} below min {min_amount}, "
                f"carrying over to next slice"
            )
            existing_carryover = self._carryover_amount.get(primary_oid, Decimal("0"))
            self._carryover_amount[primary_oid] = existing_carryover + unfilled

    def _handle_final_limit_order(self, exec_order: ExecAlgorithmOrder):
        """
        Handle the final limit order when all slices are done.

        If the last limit order is not fully filled, cancel it and:
        - If unfilled >= min_order_amount: use market order to take remaining
        - If unfilled < min_order_amount: skip (no more slices to carry over to)
        """
        primary_oid = exec_order.primary_oid
        params = exec_order.params
        use_limit = params.get("use_limit", False)

        if not use_limit:
            return

        prev_oid = self._current_limit_oid.get(primary_oid)
        if not prev_oid:
            return

        prev_order = self._cache.get_order(prev_oid).value_or(None)
        if not prev_order:
            return

        if not prev_order.is_opened:
            return

        # Calculate unfilled amount
        filled = prev_order.filled or Decimal("0")
        unfilled = prev_order.amount - filled

        if unfilled <= 0:
            return

        # Cancel the previous order
        self.cancel_spawned_order(exec_order, prev_oid)

        # Check if unfilled amount meets minimum order requirement
        min_amount = self.min_order_amount(exec_order.symbol)

        if unfilled >= min_amount:
            self._log.info(
                f"Final slice limit order {prev_oid} not fully filled. "
                f"Filled: {filled}, Unfilled: {unfilled}. Taking with market order."
            )
            self.spawn_market(exec_order, unfilled)
        else:
            self._log.info(
                f"Final slice limit order {prev_oid} not fully filled. "
                f"Filled: {filled}, Unfilled: {unfilled} below min {min_amount}. Skipping."
            )

    def _cleanup_timer(self, primary_oid: str):
        """Cleanup timer for completed execution."""
        timer_name = f"twap_{primary_oid}"
        if timer_name in self._active_timers:
            self.cancel_timer(timer_name)
            self._active_timers.discard(timer_name)
        self._scheduled_sizes.pop(primary_oid, None)
        self._current_limit_oid.pop(primary_oid, None)
        self._carryover_amount.pop(primary_oid, None)

    def on_cancel(self, exec_order: ExecAlgorithmOrder):
        """Handle TWAP cancellation."""
        self._cleanup_timer(exec_order.primary_oid)
        exec_order.status = ExecAlgorithmStatus.CANCELED
        self._log.info(f"TWAP execution canceled for {exec_order.primary_oid}")

    def on_execution_complete(self, exec_order: ExecAlgorithmOrder):
        """Handle TWAP completion."""
        self._cleanup_timer(exec_order.primary_oid)
        filled_amount = exec_order.total_amount - exec_order.remaining_amount
        self._log.info(
            f"TWAP execution complete for {exec_order.primary_oid}, "
            f"filled {filled_amount} of {exec_order.total_amount}"
        )

    def on_spawned_order_failed(self, exec_order: ExecAlgorithmOrder, order: Order):
        """Handle spawned order failure."""
        self._log.error(
            f"TWAP spawned order {order.oid} failed for primary {exec_order.primary_oid}"
        )
        # Could implement retry logic here if needed
