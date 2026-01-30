from abc import ABC
import nexuslog as logging
from typing import Optional
from httpx import AsyncClient, Client
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.constants import RateLimiter, RateLimiterSync
from nexustrader.base.retry import RetryManager


class ApiClient(ABC):
    def __init__(
        self,
        clock: LiveClock,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        rate_limiter: RateLimiter = None,
        rate_limiter_sync: RateLimiterSync = None,
        retry_manager: RetryManager = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._timeout = timeout
        self._log = logging.getLogger(name=type(self).__name__)
        self._session: Optional[AsyncClient] = None
        self._sync_session: Optional[Client] = None
        self._clock = clock
        self._limiter = rate_limiter
        self._limiter_sync = rate_limiter_sync
        self._retry_manager: RetryManager = retry_manager

    def _init_session(self, base_url: str | None = None):
        if self._session is None:
            kwargs = {"timeout": self._timeout}
            if base_url:
                kwargs["base_url"] = base_url
            self._session = AsyncClient(**kwargs)

    def _get_rate_limit_cost(self, cost: int = 1):
        return cost

    def _init_sync_session(self, base_url: str | None = None):
        if self._sync_session is None:
            kwargs = {"timeout": self._timeout}
            if base_url:
                kwargs["base_url"] = base_url
            self._sync_session = Client(**kwargs)

    async def close_session(self):
        """Close the session"""
        if self._session:
            await self._session.aclose()
            self._session = None
        if self._sync_session:
            self._sync_session.close()
            self._sync_session = None
