from abc import ABC, abstractmethod
from typing import Dict, Set, List, Optional, Type, Any

from walrasquant.schema import Order, Position, Balance, AccountBalance
from walrasquant.constants import AccountType, ExchangeType


class StorageBackend(ABC):
    def __init__(
        self, strategy_id: str, user_id: str, table_prefix: str, log, **kwargs
    ):
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.table_prefix = table_prefix
        self._log = log
        self._storage_initialized = False

    @abstractmethod
    async def _init_conn(self) -> None:
        pass

    @abstractmethod
    async def _init_table(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def sync_orders(self, mem_orders: Dict[str, Order]) -> None:
        pass

    @abstractmethod
    async def sync_positions(self, mem_positions: Dict[str, Position]) -> None:
        pass

    @abstractmethod
    async def sync_open_orders(
        self,
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_orders: Dict[str, Order],
    ) -> None:
        pass

    @abstractmethod
    async def sync_balances(
        self, mem_account_balance: Dict[AccountType, AccountBalance]
    ) -> None:
        pass

    @abstractmethod
    def get_order(
        self,
        oid: str,
        mem_orders: Dict[str, Order],
    ) -> Optional[Order]:
        pass

    @abstractmethod
    def get_symbol_orders(self, symbol: str) -> Set[str]:
        pass

    @abstractmethod
    def get_all_positions(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        pass

    @abstractmethod
    def get_all_balances(self, account_type: AccountType) -> List[Balance]:
        pass

    @abstractmethod
    async def sync_params(self, mem_params: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def get_param(self, key: str, default: Any = None) -> Any:
        pass

    @abstractmethod
    def get_all_params(self) -> Dict[str, Any]:
        pass

    async def start(self) -> None:
        await self._init_conn()
        await self._init_table()
        self._storage_initialized = True

    def _encode(self, obj: Order | Position | Balance) -> bytes:
        import msgspec

        return msgspec.json.encode(obj)

    def _decode(
        self, data: bytes, obj_type: Type[Order | Position | Balance]
    ) -> Order | Position | Balance:
        import msgspec

        return msgspec.json.decode(data, type=obj_type)

    def _encode_param(self, obj: Any) -> bytes:
        import msgspec

        return msgspec.json.encode(obj)

    def _decode_param(self, data: bytes) -> Any:
        import msgspec

        return msgspec.json.decode(data)
