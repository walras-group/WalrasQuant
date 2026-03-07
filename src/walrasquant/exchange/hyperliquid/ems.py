import asyncio
from decimal import Decimal
from typing import Dict, List
from walrasquant.constants import AccountType, SubmitType
from walrasquant.schema import (
    CreateOrderSubmit,
    OrderSubmit,
    InstrumentId,
    BatchOrderSubmit,
)
from walrasquant.core.cache import AsyncCache
from walrasquant.core.nautilius_core import MessageBus, LiveClock
from walrasquant.core.entity import TaskManager
from walrasquant.core.registry import OrderRegistry
from walrasquant.exchange.hyperliquid import HyperLiquidAccountType
from walrasquant.exchange.hyperliquid.schema import HyperLiquidMarket
from walrasquant.exchange.hyperliquid.constants import oid_to_cloid_hex
from walrasquant.base import ExecutionManagementSystem
from walrasquant.schema import CancelAllOrderSubmit, CancelOrderSubmit


class HyperLiquidExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, HyperLiquidMarket]

    HYPER_LIQUID_ACCOUNT_TYPE_PRIORITY = [
        HyperLiquidAccountType.MAINNET,
        HyperLiquidAccountType.TESTNET,
    ]

    def __init__(
        self,
        market: Dict[str, HyperLiquidMarket],
        cache: AsyncCache,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        registry: OrderRegistry,
        queue_maxsize: int = 100_000,
    ):
        super().__init__(
            market=market,
            cache=cache,
            msgbus=msgbus,
            clock=clock,
            task_manager=task_manager,
            registry=registry,
            queue_maxsize=queue_maxsize,
        )
        self._hyperliquid_account_type: HyperLiquidAccountType = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, HyperLiquidAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue(
                    maxsize=self._queue_maxsize
                )
                break

    def _set_account_type(self):
        account_types = self._private_connectors.keys()
        for account_type in self.HYPER_LIQUID_ACCOUNT_TYPE_PRIORITY:
            if account_type in account_types:
                self._hyperliquid_account_type = account_type
                break

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        return self._hyperliquid_account_type

    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ):
        if isinstance(order, list):
            if not account_type:
                account_type = self._instrument_id_to_account_type(
                    order[0].instrument_id
                )

            # Split batch orders into chunks of 20
            for i in range(0, len(order), 20):
                batch = order[i : i + 20]
                self._safe_put(
                    self._order_submit_queues[account_type], (batch, submit_type)
                )
        else:
            if not account_type:
                account_type = self._instrument_id_to_account_type(order.instrument_id)
            self._safe_put(
                self._order_submit_queues[account_type], (order, submit_type)
            )

    def _get_min_order_amount(
        self, symbol: str, market: HyperLiquidMarket, px: float
    ) -> Decimal:
        # book = self._cache.bookl1(symbol)
        min_order_cost = market.limits.cost.min
        min_order_amount = super()._amount_to_precision(
            symbol, min_order_cost / px * 1.01, mode="ceil"
        )
        return min_order_amount

    async def _cancel_all_orders(
        self, order_submit: CancelAllOrderSubmit, account_type: AccountType
    ):
        # override the base method
        symbol = order_submit.symbol
        await self._cache.wait_for_inflight_orders(symbol)
        oids = self._cache.get_open_orders(symbol)
        for oid in oids:
            cancel_submit = CancelOrderSubmit(
                symbol=symbol,
                instrument_id=InstrumentId.from_str(symbol),
                oid=oid,
            )
            await self._cancel_order(cancel_submit, account_type)

    async def _create_order(
        self, order_submit: CreateOrderSubmit, account_type: AccountType
    ):
        """
        Create an order
        """
        oid = oid_to_cloid_hex(order_submit.oid)
        self._registry.register_order(oid)
        self._cache.add_inflight_order(order_submit.symbol, oid)
        await self._private_connectors[account_type]._oms.create_order(
            oid=oid,
            symbol=order_submit.symbol,
            side=order_submit.side,
            type=order_submit.type,
            amount=order_submit.amount,
            price=order_submit.price,
            time_in_force=order_submit.time_in_force,
            reduce_only=order_submit.reduce_only,
            **order_submit.kwargs,
        )

    async def _create_batch_orders(
        self, batch_orders: List[BatchOrderSubmit], account_type: AccountType
    ):
        new_batch_orders = []
        for order in batch_orders:
            oid = oid_to_cloid_hex(order.oid)
            self._registry.register_order(oid=oid)
            self._cache.add_inflight_order(order.symbol, oid)
            new_batch_orders.append(
                BatchOrderSubmit(
                    symbol=order.symbol,
                    instrument_id=order.instrument_id,
                    status=order.status,
                    side=order.side,
                    type=order.type,
                    amount=order.amount,
                    price=order.price,
                    time_in_force=order.time_in_force,
                    reduce_only=order.reduce_only,
                    oid=oid,
                    kwargs=order.kwargs,
                )
            )
        await self._private_connectors[account_type]._oms.create_batch_orders(
            orders=new_batch_orders,
        )

    async def _create_order_ws(
        self, order_submit: CreateOrderSubmit, account_type: AccountType
    ):
        """
        Create an order
        """
        oid = oid_to_cloid_hex(order_submit.oid)
        self._registry.register_order(oid)
        self._cache.add_inflight_order(order_submit.symbol, oid)
        await self._private_connectors[account_type]._oms.create_order_ws(
            oid=oid,
            symbol=order_submit.symbol,
            side=order_submit.side,
            type=order_submit.type,
            amount=order_submit.amount,
            price=order_submit.price,
            time_in_force=order_submit.time_in_force,
            reduce_only=order_submit.reduce_only,
            **order_submit.kwargs,
        )
