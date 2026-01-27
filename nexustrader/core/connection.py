from dataclasses import dataclass
from typing import Literal


ConnectionRole = Literal["MD", "TD"]


@dataclass(frozen=True)
class ConnectionState:
    role: ConnectionRole
    exchange_id: str
    account_type: str
    ws_name: str
    client_id: int
    required: bool
    connected: bool
    changed_at_ms: int

    def is_md(self) -> bool:
        return self.role == "MD"

    def is_td(self) -> bool:
        return self.role == "TD"


@dataclass(frozen=True)
class ConnectionPolicyState:
    md_ok: bool
    td_ok: bool

    @property
    def allow_open(self) -> bool:
        return self.md_ok and self.td_ok

    @property
    def allow_trade(self) -> bool:
        return self.td_ok

    @property
    def allow_close_only(self) -> bool:
        return self.td_ok and not self.md_ok
