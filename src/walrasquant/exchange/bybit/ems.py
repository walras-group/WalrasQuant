import asyncio
from typing import Dict, List
from decimal import Decimal
from walrasquant.constants import AccountType, SubmitType
from walrasquant.schema import OrderSubmit, InstrumentId
from walrasquant.core.cache import AsyncCache
from walrasquant.core.nautilius_core import MessageBus, LiveClock
from walrasquant.core.entity import TaskManager
from walrasquant.core.registry import OrderRegistry
from walrasquant.exchange.bybit import BybitAccountType
from walrasquant.exchange.bybit.schema import BybitMarket
from walrasquant.base import ExecutionManagementSystem


class BybitExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, BybitMarket]

    def __init__(
        self,
        market: Dict[str, BybitMarket],
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
        self._bybit_account_type: BybitAccountType | None = None

    def _build_order_submit_queues(self):
        # if not self._private_connectors:
        #     raise RuntimeError(
        #         "No private connectors found for building order submit queues."
        #     )
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, BybitAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue(
                    maxsize=self._queue_maxsize
                )

    def _set_account_type(self):
        # if not self._private_connectors:
        #     raise RuntimeError(
        #         "No private connectors found for setting account type."
        #     )
        account_types = self._private_connectors.keys()
        self._bybit_account_type = (
            BybitAccountType.UNIFIED_TESTNET
            if BybitAccountType.UNIFIED_TESTNET in account_types
            else BybitAccountType.UNIFIED
        )

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        return self._bybit_account_type

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
        self, symbol: str, market: BybitMarket, px: float
    ) -> Decimal:
        min_order_qty = float(market.info.lotSizeFilter.minOrderQty)
        min_order_amt = float(
            market.info.lotSizeFilter.minOrderAmt
            or market.info.lotSizeFilter.minNotionalValue
        )
        min_order_amount = max(min_order_amt * 1.02 / px, min_order_qty)
        min_order_amount = self._amount_to_precision(
            symbol, min_order_amount, mode="ceil"
        )
        return min_order_amount
