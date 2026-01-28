from typing import Callable, List, Dict
from typing import Any
from urllib.parse import urlencode
from nexustrader.base import WSClient
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceKlineInterval,
    BinanceRateLimiter,
)
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import hmac_signature, LiveClock


class BinanceWSClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        ws_suffix: str = "/ws",
        custom_url: str | None = None,
        max_subscriptions_per_client: int | None = None,
        max_clients: int | None = None,
    ):
        self._account_type = account_type
        url = account_type.ws_url

        if ws_suffix not in ["/ws", "/stream"]:
            raise ValueError(f"Invalid ws_suffix: {ws_suffix}")

        url += ws_suffix

        if custom_url is not None:
            url = custom_url

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
            max_subscriptions_per_client=max_subscriptions_per_client,
            max_clients=max_clients,
        )

    def _send_payload(
        self,
        params: List[str],
        method: str = "SUBSCRIBE",
        chunk_size: int = 50,
        client_id: int | None = None,
    ):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {
                "method": method,
                "params": chunk,
                "id": self._clock.timestamp_ms(),
            }
            self.send(payload, client_id=client_id)

    def _subscribe(self, params: List[str]):
        assigned = self._register_subscriptions(params)
        if not assigned:
            return
        for client_id, client_params in assigned.items():
            for param in client_params:
                self._log.debug(f"Subscribing to {param}...")
            if self._is_client_connected(client_id):
                self._send_payload(
                    client_params, method="SUBSCRIBE", client_id=client_id
                )

    def _unsubscribe(self, params: List[str]):
        removed = self._unregister_subscriptions(params)
        if not removed:
            return
        for client_id, client_params in removed.items():
            for param in client_params:
                self._log.debug(f"Unsubscribing from {param}...")
            self._send_payload(client_params, method="UNSUBSCRIBE", client_id=client_id)

    def subscribe_agg_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        self._subscribe(params)

    def subscribe_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        self._subscribe(params)

    def subscribe_book_ticker(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@bookTicker" for symbol in symbols]
        self._subscribe(params)

    def subscribe_partial_book_depth(self, symbols: List[str], level: int):
        if level not in (5, 10, 20):
            raise ValueError("Level must be 5, 10, or 20")
        params = [f"{symbol.lower()}@depth{level}@100ms" for symbol in symbols]
        self._subscribe(params)

    def subscribe_mark_price(self, symbols: List[str]):
        if not self._account_type.is_future:
            raise ValueError("Only Supported for `Future Account`")
        params = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        self._subscribe(params)

    def subscribe_user_data_stream(self, listen_key: str):
        self._subscribe([listen_key])

    def subscribe_kline(
        self,
        symbols: List[str],
        interval: BinanceKlineInterval,
    ):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@kline_{interval.value}" for symbol in symbols]
        self._subscribe(params)

    def unsubscribe_agg_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_book_ticker(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@bookTicker" for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_partial_book_depth(self, symbols: List[str], level: int):
        if level not in (5, 10, 20):
            raise ValueError("Level must be 5, 10, or 20")
        params = [f"{symbol.lower()}@depth{level}@100ms" for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_mark_price(self, symbols: List[str]):
        if not self._account_type.is_future:
            raise ValueError("Only Supported for `Future Account`")
        params = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_user_data_stream(self, listen_key: str):
        self._unsubscribe([listen_key])

    def unsubscribe_kline(
        self,
        symbols: List[str],
        interval: BinanceKlineInterval,
    ):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@kline_{interval.value}" for symbol in symbols]
        self._unsubscribe(params)

    async def _resubscribe_for_client(self, client_id: int, subscriptions: List[str]):
        if not subscriptions:
            return
        self._send_payload(subscriptions, client_id=client_id)


class BinanceWSApiClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        api_key: str,
        secret: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._account_type = account_type
        self._api_key = api_key
        self._secret = secret
        self._limiter = BinanceRateLimiter(enable_rate_limit)

        url = account_type.ws_order_url

        if not url:
            raise ValueError(f"WebSocket URL not supported for {account_type}")

        super().__init__(
            url=url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    def _generate_signature_v2(self, query: str) -> str:
        signature = hmac_signature(self._secret, query)
        return signature

    def _send_payload(
        self,
        id: str,
        method: str,
        params: Dict[str, Any],
        required_ts: bool = True,
        auth: bool = True,
    ):
        if required_ts:
            params["timestamp"] = self._clock.timestamp_ms()

        if auth:
            params["apiKey"] = self._api_key
            query = urlencode(sorted(params.items()))
            signature = self._generate_signature_v2(query)
            params["signature"] = signature

        payload = {
            "method": method,
            "id": id,
            "params": params,
        }
        self.send(payload)

    async def spot_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter.api_order_limit(cost=1)
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def spot_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter.api_order_limit(cost=1)
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def usdm_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter.fapi_order_limit(cost=0)
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def usdm_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter.fapi_order_limit(cost=1)
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def coinm_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter.dapi_order_limit(cost=0)
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def coinm_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter.dapi_order_limit(cost=1)
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    def _subscribe(self, subscriptions: List[tuple[Dict[str, Any], str]]):
        assigned = self._register_subscriptions(subscriptions)
        if not assigned:
            return
        for client_id, client_subs in assigned.items():
            for params, method in client_subs:
                self._log.debug(f"Subscribing to {method} with {params}...")
            if self._is_client_connected(client_id):
                for params, method in client_subs:
                    request_id = f"{self._clock.timestamp_ms()}"
                    self._send_payload(
                        id=request_id,
                        method=method,
                        params=dict(params),
                        auth=True,
                    )

    async def _resubscribe_for_client(
        self, client_id: int, subscriptions: List[tuple[Dict[str, Any], str]]
    ):
        if not subscriptions:
            return
        for params, method in subscriptions:
            request_id = f"s{self._clock.timestamp_ms()}"
            self._send_payload(
                id=request_id,
                method=method,
                params=dict(params),
                auth=True,
            )

    def subscribe_spot_user_data_stream(self):
        if not self._account_type.is_spot:
            raise ValueError("Only Supported for `Spot Account`")
        params: Dict[str, Any] = {}
        self._subscribe([(params, "userDataStream.subscribe.signature")])
