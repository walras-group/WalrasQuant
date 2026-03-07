import asyncio
from decimal import Decimal
from typing import Dict, List, Literal
from walrasquant.constants import AccountType, SubmitType
from walrasquant.schema import OrderSubmit, InstrumentId
from walrasquant.core.cache import AsyncCache
from walrasquant.core.nautilius_core import MessageBus, LiveClock
from walrasquant.core.entity import TaskManager
from walrasquant.core.registry import OrderRegistry
from walrasquant.exchange.okx import OkxAccountType
from walrasquant.exchange.okx.schema import OkxMarket
from walrasquant.base import ExecutionManagementSystem
from walrasquant.schema import CancelAllOrderSubmit, CancelOrderSubmit


class OkxExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, OkxMarket]

    OKX_ACCOUNT_TYPE_PRIORITY = [
        OkxAccountType.DEMO,
        # OkxAccountType.AWS,
        OkxAccountType.LIVE,
    ]

    def __init__(
        self,
        market: Dict[str, OkxMarket],
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
        self._okx_account_type: OkxAccountType = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, OkxAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue(
                    maxsize=self._queue_maxsize
                )
                break

    def _set_account_type(self):
        account_types = self._private_connectors.keys()
        for account_type in self.OKX_ACCOUNT_TYPE_PRIORITY:
            if account_type in account_types:
                self._okx_account_type = account_type
                break

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        return self._okx_account_type

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
        self, symbol: str, market: OkxMarket, px: float
    ) -> Decimal:
        min_order_amount = market.limits.amount.min
        min_order_amount = super()._amount_to_precision(
            symbol, min_order_amount, mode="ceil"
        )

        if not market.spot:
            # for linear and inverse, the min order amount is contract size and ctVal is base amount per contract
            min_order_amount *= Decimal(market.info.ctVal)

        return min_order_amount

    # override the base method
    def _amount_to_precision(
        self,
        symbol: str,
        amount: float,
        mode: Literal["round"] | Literal["ceil"] | Literal["floor"] = "round",
    ) -> Decimal:
        market = self._market[symbol]
        ctVal = Decimal("1")
        if not market.spot:
            ctVal = Decimal(market.info.ctVal)
            amount = Decimal(str(amount)) / ctVal
        return super()._amount_to_precision(symbol, amount, mode) * ctVal

    async def _cancel_all_orders(
        self, order_submit: CancelAllOrderSubmit, account_type: AccountType
    ):
        # override the base methods
        symbol = order_submit.symbol
        await self._cache.wait_for_inflight_orders(symbol)
        oids = self._cache.get_open_orders(symbol, include_canceling=True)
        for oid in oids:
            cancel_submit = CancelOrderSubmit(
                symbol=symbol,
                instrument_id=InstrumentId.from_str(symbol),
                oid=oid,
            )
            await self._cancel_order(cancel_submit, account_type)
