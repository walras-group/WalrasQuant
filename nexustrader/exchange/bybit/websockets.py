import msgspec
import asyncio
import picows

from typing import Any, Callable, List

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, hmac_signature
from nexustrader.exchange.bybit.schema import (
    BybitWsMessageGeneral,
    BybitWsApiGeneralMsg,
)
from nexustrader.exchange.bybit.constants import (
    BybitAccountType,
    BybitKlineInterval,
    BybitRateLimiter,
)


def user_pong_callback(self, frame: picows.WSFrame) -> bool:
    if frame.msg_type != picows.WSMsgType.TEXT:
        self._log.debug(
            f"Received non-text frame for pong callback. ws_frame: {self._decode_frame(frame)}"
        )
        return False

    raw = frame.get_payload_as_bytes()
    try:
        message = msgspec.json.decode(raw, type=BybitWsMessageGeneral)
        self._log.debug(f"Received pong message: {message}")
        return message.is_pong
    except msgspec.DecodeError:
        self._log.error(
            f"Failed to decode pong message. ws_frame: {self._decode_frame(frame)}"
        )
        return False


def user_api_pong_callback(self, frame: picows.WSFrame) -> bool:
    if frame.msg_type != picows.WSMsgType.TEXT:
        self._log.debug(
            f"Received non-text frame for pong callback. ws_frame: {self._decode_frame(frame)}"
        )
        return False

    raw = frame.get_payload_as_bytes()
    try:
        message = msgspec.json.decode(raw, type=BybitWsApiGeneralMsg)
        self._log.debug(f"Received pong message: {message}")
        return message.is_pong
    except msgspec.DecodeError:
        self._log.error(
            f"Failed to decode pong message. ws_frame: {self._decode_frame(frame)}"
        )
        return False


class BybitWSClient(WSClient):
    def __init__(
        self,
        account_type: BybitAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        api_key: str | None = None,
        secret: str | None = None,
        custom_url: str | None = None,
        max_subscriptions_per_client: int | None = None,
        max_clients: int | None = None,
    ):
        self._account_type = account_type
        self._api_key = api_key
        self._secret = secret

        if self.is_private:
            url = account_type.ws_private_url
        else:
            url = account_type.ws_public_url
        if custom_url:
            url = custom_url
        # Bybit: do not exceed 500 requests per 5 minutes
        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            ping_idle_timeout=10,
            ping_reply_timeout=2,
            specific_ping_msg=msgspec.json.encode({"op": "ping"}),
            auto_ping_strategy="ping_periodically",
            user_pong_callback=user_pong_callback,
            max_subscriptions_per_client=max_subscriptions_per_client,
            max_clients=max_clients,
        )

    @property
    def is_private(self):
        return self._api_key is not None or self._secret is not None

    def _generate_signature(self):
        expires = self._clock.timestamp_ms() + 1_000
        signature = hmac_signature(self._secret, f"GET/realtime{expires}")  # type: ignore
        return signature, expires

    def _get_auth_payload(self):
        signature, expires = self._generate_signature()
        return {"op": "auth", "args": [self._api_key, expires, signature]}

    async def _auth(self, client_id: int | None = None):
        self.send(self._get_auth_payload(), client_id=client_id)
        await asyncio.sleep(5)

    def _send_payload(
        self,
        params: List[str],
        chunk_size: int = 100,
        op: str = "subscribe",
        client_id: int | None = None,
    ):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {"op": op, "args": chunk}
            self.send(payload, client_id=client_id)

    def _subscribe(self, topics: List[str]):
        assigned = self._register_subscriptions(topics)
        if not assigned:
            return
        for client_id, client_topics in assigned.items():
            for topic in client_topics:
                self._log.debug(f"Subscribing to {topic}...")
            if self._is_client_connected(client_id):
                self._send_payload(client_topics, op="subscribe", client_id=client_id)

    def _unsubscribe(self, topics: List[str]):
        removed = self._unregister_subscriptions(topics)
        if not removed:
            return
        for client_id, client_topics in removed.items():
            for topic in client_topics:
                self._log.debug(f"Unsubscribing from {topic}...")
            self._send_payload(client_topics, op="unsubscribe", client_id=client_id)

    def subscribe_order_book(self, symbols: List[str], depth: int):
        """subscribe to orderbook"""
        topics = [f"orderbook.{depth}.{symbol}" for symbol in symbols]
        self._subscribe(topics)

    def subscribe_trade(self, symbols: List[str]):
        """subscribe to trade"""
        topics = [f"publicTrade.{symbol}" for symbol in symbols]
        self._subscribe(topics)

    def subscribe_ticker(self, symbols: List[str]):
        """subscribe to ticker"""
        topics = [f"tickers.{symbol}" for symbol in symbols]
        self._subscribe(topics)

    def subscribe_kline(self, symbols: List[str], interval: BybitKlineInterval):
        """subscribe to kline"""
        topics = [f"kline.{interval.value}.{symbol}" for symbol in symbols]
        self._subscribe(topics)

    def unsubscribe_order_book(self, symbols: List[str], depth: int):
        """unsubscribe from orderbook"""
        topics = [f"orderbook.{depth}.{symbol}" for symbol in symbols]
        self._unsubscribe(topics)

    def unsubscribe_trade(self, symbols: List[str]):
        """unsubscribe from trade"""
        topics = [f"publicTrade.{symbol}" for symbol in symbols]
        self._unsubscribe(topics)

    def unsubscribe_ticker(self, symbols: List[str]):
        """unsubscribe from ticker"""
        topics = [f"tickers.{symbol}" for symbol in symbols]
        self._unsubscribe(topics)

    def unsubscribe_kline(self, symbols: List[str], interval: BybitKlineInterval):
        """unsubscribe from kline"""
        topics = [f"kline.{interval.value}.{symbol}" for symbol in symbols]
        self._unsubscribe(topics)

    async def _resubscribe_for_client(self, client_id: int, subscriptions: List[str]):
        if not subscriptions:
            return
        if self.is_private:
            await self._auth(client_id=client_id)
        self._send_payload(subscriptions, client_id=client_id)

    def subscribe_order(self, topic: str = "order"):
        """subscribe to order"""
        self._subscribe([topic])

    def subscribe_position(self, topic: str = "position"):
        """subscribe to position"""
        self._subscribe([topic])

    def subscribe_wallet(self, topic: str = "wallet"):
        """subscribe to wallet"""
        self._subscribe([topic])


class BybitWSApiClient(WSClient):
    def __init__(
        self,
        account_type: BybitAccountType,
        api_key: str,
        secret: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._api_key = api_key
        self._secret = secret
        self._account_type = account_type

        url = account_type.ws_api_url
        self._limiter = BybitRateLimiter(
            enable_rate_limit=enable_rate_limit,
        )

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            ping_idle_timeout=5,
            ping_reply_timeout=2,
            specific_ping_msg=msgspec.json.encode({"op": "ping"}),
            user_pong_callback=user_api_pong_callback,
        )

    def _generate_signature(self):
        expires = self._clock.timestamp_ms() + 1_000
        signature = hmac_signature(self._secret, f"GET/realtime{expires}")
        return signature, expires

    def _get_auth_payload(self):
        signature, expires = self._generate_signature()
        return {"op": "auth", "args": [self._api_key, expires, signature]}

    async def _auth(self, client_id: int | None = None):
        self.send(self._get_auth_payload(), client_id=client_id)
        await asyncio.sleep(5)

    def _submit(self, reqId: str, op: str, args: list[dict]):
        payload = {
            "reqId": reqId,
            "header": {
                "X-BAPI-TIMESTAMP": self._clock.timestamp_ms(),
            },
            "op": op,
            "args": args,
        }
        self.send(payload)

    async def create_order(
        self,
        id: str,
        symbol: str,
        side: str,
        orderType: str,
        qty: str,
        category: str,
        **kwargs,
    ):
        arg = {
            "symbol": symbol,
            "side": side,
            "orderType": orderType,
            "qty": qty,
            "category": category,
            **kwargs,
        }
        op = "order.create"
        if category == "spot":
            await self._limiter("20/s").limit(key=op, cost=1)
        else:
            await self._limiter("10/s").limit(key=op, cost=1)
        self._submit(reqId=f"n{id}", op=op, args=[arg])

    async def cancel_order(
        self, id: str, symbol: str, orderLinkId: str, category: str, **kwargs
    ):
        arg = {
            "symbol": symbol,
            "orderLinkId": orderLinkId,
            "category": category,
            **kwargs,
        }
        op = "order.cancel"
        if category == "spot":
            await self._limiter("20/s").limit(key=op, cost=1)
        else:
            await self._limiter("10/s").limit(key=op, cost=1)
        self._submit(reqId=f"c{id}", op=op, args=[arg])

    async def _resubscribe_for_client(self, client_id: int, subscriptions: List[str]):
        await self._auth(client_id=client_id)
