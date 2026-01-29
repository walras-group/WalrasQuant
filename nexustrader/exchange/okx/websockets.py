import base64
import asyncio
import picows
from typing import Literal, Any, Callable, Dict, List

from nexustrader.base import WSClient
from nexustrader.exchange.okx.constants import (
    OkxAccountType,
    OkxKlineInterval,
    OkxRateLimiter,
)
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, hmac_signature


def user_pong_callback(self, frame: picows.WSFrame) -> bool:
    self._log.debug("Pong received")
    return (
        frame.msg_type == picows.WSMsgType.TEXT
        and frame.get_payload_as_memoryview() == b"pong"
    )


class OkxWSClient(WSClient):
    def __init__(
        self,
        account_type: OkxAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        api_key: str | None = None,
        secret: str | None = None,
        passphrase: str | None = None,
        business_url: bool = False,
        custom_url: str | None = None,
        max_subscriptions_per_client: int | None = None,
        max_clients: int | None = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._account_type = account_type
        self._business_url = business_url

        if custom_url:
            url = custom_url
        elif self.is_private:
            if not all([self._api_key, self._passphrase, self._secret]):
                raise ValueError("API Key, Passphrase, or Secret is missing.")
            url = f"{account_type.stream_url}/v5/private"
        else:
            endpoint = "business" if business_url else "public"
            url = f"{account_type.stream_url}/v5/{endpoint}"

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            specific_ping_msg=b"ping",
            ping_idle_timeout=5,
            ping_reply_timeout=2,
            user_pong_callback=user_pong_callback,
            max_subscriptions_per_client=max_subscriptions_per_client,
            max_clients=max_clients,
        )

    @property
    def is_private(self):
        return (
            self._api_key is not None
            or self._secret is not None
            or self._passphrase is not None
        )

    def _get_auth_payload(self):
        timestamp = int(self._clock.timestamp())
        message = str(timestamp) + "GET" + "/users/self/verify"
        digest = bytes.fromhex(hmac_signature(self._secret, message))  # type: ignore
        sign = base64.b64encode(digest)

        arg = {
            "apiKey": self._api_key,
            "passphrase": self._passphrase,
            "timestamp": timestamp,
            "sign": sign.decode("utf-8"),
        }
        payload = {"op": "login", "args": [arg]}
        return payload

    async def _auth(self, client_id: int | None = None):
        self.send(self._get_auth_payload(), client_id=client_id)
        await asyncio.sleep(5)

    def _send_payload(
        self,
        params: List[Dict[str, Any]],
        op: Literal["subscribe", "unsubscribe"] = "subscribe",
        chunk_size: int = 100,
        client_id: int | None = None,
    ):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {
                "op": op,
                "args": chunk,
            }
            self.send(payload, client_id=client_id)

    def _subscribe(self, params: List[Dict[str, Any]]):
        assigned = self._register_subscriptions(params)
        if not assigned:
            return
        for client_id, client_params in assigned.items():
            for param in client_params:
                self._log.debug(f"Subscribing to {param}...")
            if self._is_client_connected(client_id):
                self._send_payload(client_params, op="subscribe", client_id=client_id)

    def subscribe_funding_rate(self, symbols: List[str]):
        params = [{"channel": "funding-rate", "instId": symbol} for symbol in symbols]
        self._subscribe(params)

    def subscribe_index_price(self, symbols: List[str]):
        params = [{"channel": "index-tickers", "instId": symbol} for symbol in symbols]
        self._subscribe(params)

    def subscribe_mark_price(self, symbols: List[str]):
        params = [{"channel": "mark-price", "instId": symbol} for symbol in symbols]
        self._subscribe(params)

    def subscribe_order_book(
        self,
        symbols: List[str],
        channel: Literal[
            "books", "books5", "bbo-tbt", "books-l2-tbt", "books50-l2-tbt"
        ],
    ):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-order-book-channel
        """
        params = [{"channel": channel, "instId": symbol} for symbol in symbols]
        self._subscribe(params)

    def subscribe_trade(self, symbols: List[str]):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-all-trades-channel
        """
        params = [{"channel": "trades", "instId": symbol} for symbol in symbols]
        self._subscribe(params)

    def subscribe_candlesticks(
        self,
        symbols: List[str],
        interval: OkxKlineInterval,
    ):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-candlesticks-channel
        """
        if not self._business_url:
            raise ValueError("candlesticks are only supported on business url")
        channel = interval.value
        params = [{"channel": channel, "instId": symbol} for symbol in symbols]
        self._subscribe(params)

    def subscribe_account(self):
        params = {"channel": "account"}
        self._subscribe([params])

    def subscribe_account_position(self):
        params = {"channel": "balance_and_position"}
        self._subscribe([params])

    def subscribe_positions(
        self, inst_type: Literal["MARGIN", "SWAP", "FUTURES", "OPTION", "ANY"] = "ANY"
    ):
        params = {"channel": "positions", "instType": inst_type}
        self._subscribe([params])

    def subscribe_orders(
        self, inst_type: Literal["MARGIN", "SWAP", "FUTURES", "OPTION", "ANY"] = "ANY"
    ):
        params = {"channel": "orders", "instType": inst_type}
        self._subscribe([params])

    def subscribe_fills(self):
        params = {"channel": "fills"}
        self._subscribe([params])

    def _unsubscribe(self, params: List[Dict[str, Any]]):
        removed = self._unregister_subscriptions(params)
        if not removed:
            return
        for client_id, client_params in removed.items():
            for param in client_params:
                self._log.debug(f"Unsubscribing from {param}...")
            self._send_payload(client_params, op="unsubscribe", client_id=client_id)

    def unsubscribe_funding_rate(self, symbols: List[str]):
        params = [{"channel": "funding-rate", "instId": symbol} for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_index_price(self, symbols: List[str]):
        params = [{"channel": "index-tickers", "instId": symbol} for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_mark_price(self, symbols: List[str]):
        params = [{"channel": "mark-price", "instId": symbol} for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_order_book(
        self,
        symbols: List[str],
        channel: Literal[
            "books", "books5", "bbo-tbt", "books-l2-tbt", "books50-l2-tbt"
        ],
    ):
        params = [{"channel": channel, "instId": symbol} for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_trade(self, symbols: List[str]):
        params = [{"channel": "trades", "instId": symbol} for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_candlesticks(
        self,
        symbols: List[str],
        interval: OkxKlineInterval,
    ):
        if not self._business_url:
            raise ValueError("candlesticks are only supported on business url")
        channel = interval.value
        params = [{"channel": channel, "instId": symbol} for symbol in symbols]
        self._unsubscribe(params)

    def unsubscribe_account(self):
        params = {"channel": "account"}
        self._unsubscribe([params])

    def unsubscribe_account_position(self):
        params = {"channel": "balance_and_position"}
        self._unsubscribe([params])

    def unsubscribe_positions(
        self, inst_type: Literal["MARGIN", "SWAP", "FUTURES", "OPTION", "ANY"] = "ANY"
    ):
        params = {"channel": "positions", "instType": inst_type}
        self._unsubscribe([params])

    def unsubscribe_orders(
        self, inst_type: Literal["MARGIN", "SWAP", "FUTURES", "OPTION", "ANY"] = "ANY"
    ):
        params = {"channel": "orders", "instType": inst_type}
        self._unsubscribe([params])

    def unsubscribe_fills(self):
        params = {"channel": "fills"}
        self._unsubscribe([params])

    async def _resubscribe_for_client(
        self, client_id: int, subscriptions: List[Dict[str, Any]]
    ):
        if not subscriptions:
            return
        if self.is_private:
            await self._auth(client_id=client_id)
        self._send_payload(subscriptions, client_id=client_id)


class OkxWSApiClient(WSClient):
    def __init__(
        self,
        account_type: OkxAccountType,
        api_key: str,
        secret: str,
        passphrase: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._account_type = account_type

        url = f"{account_type.stream_url}/v5/private"
        self._limiter = OkxRateLimiter(enable_rate_limit=enable_rate_limit)

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            specific_ping_msg=b"ping",
            ping_idle_timeout=5,
            ping_reply_timeout=2,
            user_pong_callback=user_pong_callback,
        )

    def _get_auth_payload(self):
        timestamp = int(self._clock.timestamp())
        message = str(timestamp) + "GET" + "/users/self/verify"
        digest = bytes.fromhex(hmac_signature(self._secret, message))
        sign = base64.b64encode(digest)
        arg = {
            "apiKey": self._api_key,
            "passphrase": self._passphrase,
            "timestamp": timestamp,
            "sign": sign.decode("utf-8"),
        }
        payload = {"op": "login", "args": [arg]}
        return payload

    async def _auth(self, client_id: int | None = None):
        self.send(self._get_auth_payload(), client_id=client_id)
        await asyncio.sleep(5)

    async def _resubscribe_for_client(self, client_id: int, subscriptions: List[Any]):
        await self._auth(client_id=client_id)

    def _submit(self, id: str, op: str, params: Dict[str, Any]):
        payload = {
            "id": id,
            "op": op,
            "args": [params],
        }
        self.send(payload)

    async def place_order(
        self,
        id: str,
        instIdCode: int,
        tdMode: str,
        side: str,
        ordType: str,
        sz: str,
        **kwargs,
    ):
        params = {
            "instIdCode": instIdCode,
            "tdMode": tdMode,
            "side": side,
            "ordType": ordType,
            "sz": sz,
            **kwargs,
        }
        await self._limiter("/ws/order").limit("order", cost=1)
        self._submit(id, "order", params)

    async def cancel_order(self, id: str, instIdCode: int, clOrdId: str):
        params = {
            "instIdCode": instIdCode,
            "clOrdId": clOrdId,
        }
        await self._limiter("/ws/cancel").limit("cancel", cost=1)
        self._submit(id, "cancel-order", params)


# import asyncio  # noqa


# async def main():
#     from nexustrader.constants import settings
#     from nexustrader.core.entity import TaskManager
#     from nexustrader.core.nautilius_core import LiveClock, setup_nexus_core, UUID4

#     OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
#     OKX_SECRET = settings.OKX.DEMO_1.SECRET
#     OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE

#     log_guard = setup_nexus_core(  # noqa
#         trader_id="bnc-test",
#         level_stdout="DEBUG",
#     )

#     task_manager = TaskManager(
#         loop=asyncio.get_event_loop(),
#     )

#     ws_api_client = OkxWSApiClient(
#         account_type=OkxAccountType.DEMO,
#         api_key=OKX_API_KEY,
#         secret=OKX_SECRET,
#         passphrase=OKX_PASSPHRASE,
#         handler=lambda msg: print(msg),
#         task_manager=task_manager,
#         clock=LiveClock(),
#         enable_rate_limit=True,
#     )

#     await ws_api_client.connect()
#     # await ws_api_client.subscribe_orders()

#     # await ws_api_client.place_order(
#     #     id=strip_uuid_hyphens(UUID4().value),
#     #     instId="BTC-USDT-SWAP",
#     #     tdMode="cross",
#     #     side="buy",
#     #     ordType="limit",
#     #     sz="0.1",
#     #     px="100000"
#     #     # timeInForce="GTC",
#     # )

#     await ws_api_client.cancel_order(
#         id="ffab98098c664e7c847290192015089d",
#         instId="BTC-USDT-SWAP",
#         ordId="2791773453976276992",
#     )

#     await task_manager.wait()


# if __name__ == "__main__":
#     asyncio.run(main())
