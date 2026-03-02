from decimal import Decimal
from typing import Any, Dict, List
from msgspec import Struct, field

from nexusquant.constants import OrderSide, OrderType, AccountType
from nexusquant.execution.constants import (
    ExecAlgorithmStatus,
    ExecAlgorithmCommandType,
)


class ExecAlgorithmOrderParams(Struct, kw_only=True):
    """Parameters for the primary order."""

    oid: str
    symbol: str
    side: OrderSide
    amount: Decimal
    account_type: AccountType
    reduce_only: bool = False
    price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET


class ExecAlgorithmCommand(Struct, kw_only=True):
    """
    Command to send to an execution algorithm.
    """

    command_type: ExecAlgorithmCommandType  # "EXECUTE" or "CANCEL"
    exec_algorithm_id: str
    order_params: ExecAlgorithmOrderParams | None = None
    exec_params: Dict[str, Any] = field(default_factory=dict)
    primary_oid: str | None = None  # For cancel commands

    @property
    def is_execute(self) -> bool:
        """Return True if command is EXECUTE."""
        return self.command_type == ExecAlgorithmCommandType.EXECUTE

    @property
    def is_cancel(self) -> bool:
        """Return True if command is CANCEL."""
        return self.command_type == ExecAlgorithmCommandType.CANCEL


class ExecAlgorithmOrder(Struct, kw_only=True):
    """
    Represents a primary order being executed by an algorithm.
    Tracks the relationship between primary and spawned orders.
    """

    primary_oid: str
    symbol: str
    side: OrderSide
    total_amount: Decimal
    remaining_amount: Decimal
    spawned_oids: List[str] = field(default_factory=list)
    status: ExecAlgorithmStatus = ExecAlgorithmStatus.PENDING
    params: Dict[str, Any] = field(default_factory=dict)
    account_type: AccountType | None = None
    reduce_only: bool = False
