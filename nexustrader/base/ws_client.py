import asyncio
import msgspec
from abc import ABC, abstractmethod
from types import MethodType
from typing import Any
from typing import Callable, Literal
import nexuslog as logging


from nexustrader.core.entity import TaskManager
from picows import (
    ws_connect,
    WSFrame,
    WSTransport,
    WSListener,
    WSMsgType,
    WSAutoPingStrategy,
    # PICOWS_DEBUG_LL,
)
from nexustrader.core.nautilius_core import LiveClock

# import logging

# file_handler = logging.FileHandler('.log/picows.log')
# file_handler.setLevel(PICOWS_DEBUG_LL)

# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# file_handler.setFormatter(formatter)

# picows_logger = logging.getLogger("picows")
# picows_logger.setLevel(PICOWS_DEBUG_LL)
# picows_logger.addHandler(file_handler)


class Listener(WSListener):
    """WebSocket listener implementation that handles connection events and message frames.

    Inherits from picows.WSListener to provide WebSocket event handling functionality.
    """

    def __init__(
        self,
        callback,
        logger,
        specific_ping_msg: bytes | None = None,
        user_pong_callback: Callable[["Listener", WSFrame], bool] | None = None,
        *args,
        **kwargs,
    ):
        """Initialize the WebSocket listener.

        Args:
            logger: Logger instance for logging events
            specific_ping_msg: Optional custom ping message
        """
        super().__init__(*args, **kwargs)
        self._log = logger
        self._specific_ping_msg: bytes | None = specific_ping_msg
        self._callback = callback

        if user_pong_callback:
            self.is_user_specific_pong = MethodType(user_pong_callback, self)

    def send_user_specific_ping(self, transport: WSTransport) -> None:
        """Send a custom ping message or default ping frame.

        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        if self._specific_ping_msg:
            transport.send(WSMsgType.TEXT, self._specific_ping_msg)
            self._log.debug(
                f"Sent user specific ping: `{self._specific_ping_msg.decode()}`."
            )
        else:
            transport.send_ping()
            self._log.debug("Sent default ping.")

    def on_ws_connected(self, transport: WSTransport) -> None:
        """Called when WebSocket connection is established.

        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        self._log.debug("Connected to Websocket...")

    def on_ws_disconnected(self, transport: WSTransport) -> None:
        """Called when WebSocket connection is closed.

        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        self._log.debug("Disconnected from Websocket.")

    def _decode_frame(self, frame: WSFrame) -> str:
        """Decode the payload of a WebSocket frame safely.

        Args:
            frame (picows.WSFrame): Received WebSocket frame

        Returns:
            str: Decoded payload as UTF-8 text or a placeholder for binary data
        """
        try:
            return frame.get_payload_as_utf8_text()
        except Exception:
            return f"<binary data: {len(frame.get_payload_as_bytes())} bytes>"

    def on_ws_frame(self, transport: WSTransport, frame: WSFrame) -> None:
        """Handle incoming WebSocket frames.

        Args:
            transport (picows.WSTransport): WebSocket transport instance
            frame (picows.WSFrame): Received WebSocket frame
        """
        try:
            match frame.msg_type:
                case WSMsgType.TEXT:
                    # Queue raw bytes for handler to decode
                    self._callback(frame.get_payload_as_bytes())
                    return
                case WSMsgType.CLOSE:
                    close_code = frame.get_close_code()
                    self._log.warning(
                        f"Received close frame. Close code: {str(close_code)}"
                    )
                    return
        except Exception as e:
            import traceback

            self._log.error(
                f"Error processing message: {str(e)}\nTraceback: {traceback.format_exc()}\nws_frame: {self._decode_frame(frame)}"
            )


class WSClient(ABC):
    def __init__(
        self,
        url: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        specific_ping_msg: bytes | None = None,
        reconnect_interval: int = 1,
        ping_idle_timeout: int = 2,
        ping_reply_timeout: int = 1,
        auto_ping_strategy: Literal[
            "ping_when_idle", "ping_periodically"
        ] = "ping_when_idle",
        enable_auto_ping: bool = True,
        enable_auto_pong: bool = True,
        user_pong_callback: Callable[["Listener", WSFrame], bool] | None = None,
        max_subscriptions_per_client: int | None = None,
        max_clients: int | None = None,
    ):
        self._clock = clock
        self._url = url
        self._specific_ping_msg = specific_ping_msg
        self._reconnect_interval = reconnect_interval
        self._ping_idle_timeout = ping_idle_timeout
        self._ping_reply_timeout = ping_reply_timeout
        self._enable_auto_pong = enable_auto_pong
        self._enable_auto_ping = enable_auto_ping
        self._user_pong_callback = user_pong_callback
        self._listeners: dict[int, WSListener | None] = {}
        self._transports: dict[int, WSTransport | None] = {}
        self._subscriptions: list[Any] = []
        self._client_subscriptions: dict[int, list[Any]] = {}
        self._wait_tasks: dict[int, asyncio.Task] = {}
        self._next_client_id = 0
        self._started = False
        self._max_subscriptions_per_client = max_subscriptions_per_client
        self._max_clients = max_clients
        self._callback = handler
        if auto_ping_strategy == "ping_when_idle":
            self._auto_ping_strategy = WSAutoPingStrategy.PING_WHEN_IDLE
        elif auto_ping_strategy == "ping_periodically":
            self._auto_ping_strategy = WSAutoPingStrategy.PING_PERIODICALLY
        self._task_manager = task_manager
        self._log = logging.getLogger(name=type(self).__name__)
        self._ready = asyncio.Event()  # Only set once on initial connection
        self._connection_change_callback: Callable[[int, bool], None] | None = None
        if self._max_subscriptions_per_client is not None:
            if self._max_subscriptions_per_client <= 0:
                raise ValueError("max_subscriptions_per_client must be positive")
        if self._max_clients is not None:
            if self._max_clients <= 0:
                raise ValueError("max_clients must be positive")

    @property
    def connected(self) -> bool:
        return any(transport is not None for transport in self._transports.values())

    def set_connection_change_callback(
        self, callback: Callable[[int, bool], None] | None
    ) -> None:
        self._connection_change_callback = callback

    def _notify_connection_change(self, client_id: int, connected: bool) -> None:
        if self._connection_change_callback is None:
            return
        try:
            self._connection_change_callback(client_id, connected)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log.warning(f"Connection change callback error: {exc}")

    def _is_client_connected(self, client_id: int) -> bool:
        return self._transports.get(client_id) is not None

    def _primary_client_id(self) -> int | None:
        if 0 in self._client_subscriptions or 0 in self._transports:
            return 0
        if self._client_subscriptions:
            return next(iter(self._client_subscriptions))
        if self._transports:
            return next(iter(self._transports))
        return None

    def _ensure_client(self, client_id: int) -> None:
        is_new_client = client_id not in self._client_subscriptions
        if client_id not in self._client_subscriptions:
            self._client_subscriptions[client_id] = []
        if client_id not in self._transports:
            self._transports[client_id] = None
        if client_id not in self._listeners:
            self._listeners[client_id] = None
        if client_id >= self._next_client_id:
            self._next_client_id = client_id + 1
        if is_new_client:
            self._notify_connection_change(client_id, False)
        if self._started:
            self._start_client_tasks(client_id)

    def _multi_client_enabled(self) -> bool:
        return self._max_subscriptions_per_client is not None

    def _get_client_id_for_new_subscription(self) -> int:
        if not self._multi_client_enabled():
            client_id = 0
            self._ensure_client(client_id)
            return client_id

        for client_id, subs in self._client_subscriptions.items():
            if len(subs) < self._max_subscriptions_per_client:  # type: ignore[operator]
                return client_id

        if (
            self._max_clients is not None
            and len(self._client_subscriptions) >= self._max_clients
        ):
            raise RuntimeError("Maximum number of websocket clients reached")

        client_id = self._next_client_id
        self._ensure_client(client_id)
        return client_id

    def _find_client_for_subscription(self, subscription: Any) -> int | None:
        for client_id, subs in self._client_subscriptions.items():
            if subscription in subs:
                return client_id
        return None

    def _register_subscriptions(self, subscriptions: list[Any]) -> dict[int, list[Any]]:
        assigned: dict[int, list[Any]] = {}
        for subscription in subscriptions:
            if subscription in self._subscriptions:
                continue
            client_id = self._get_client_id_for_new_subscription()
            self._subscriptions.append(subscription)
            self._client_subscriptions[client_id].append(subscription)
            assigned.setdefault(client_id, []).append(subscription)
        return assigned

    def _unregister_subscriptions(
        self, subscriptions: list[Any]
    ) -> dict[int, list[Any]]:
        removed: dict[int, list[Any]] = {}
        for subscription in subscriptions:
            if subscription not in self._subscriptions:
                continue
            client_id = self._find_client_for_subscription(subscription)
            if client_id is not None:
                self._client_subscriptions[client_id].remove(subscription)
                removed.setdefault(client_id, []).append(subscription)
            self._subscriptions.remove(subscription)
        return removed

    async def _connect(self, client_id: int):
        self._log.debug(
            f"Connecting to Websocket at {self._url} (client {client_id})..."
        )
        WSListenerFactory = lambda: Listener(  # noqa: E731
            self._callback,
            self._log,
            self._specific_ping_msg,
            self._user_pong_callback,
        )
        transport, listener = await ws_connect(
            WSListenerFactory,
            self._url,
            enable_auto_ping=self._enable_auto_ping,
            auto_ping_idle_timeout=self._ping_idle_timeout,
            auto_ping_reply_timeout=self._ping_reply_timeout,
            auto_ping_strategy=self._auto_ping_strategy,
            enable_auto_pong=self._enable_auto_pong,
        )
        self._transports[client_id] = transport
        self._listeners[client_id] = listener
        self._log.debug(
            f"Websocket connected successfully to {self._url} (client {client_id})."
        )
        self._notify_connection_change(client_id, True)

    async def connect(self):
        if not self._client_subscriptions:
            self._ensure_client(0)
        if self._started:
            primary_id = self._primary_client_id()
            if primary_id is not None:
                task = self._wait_tasks.get(primary_id)
                if task and not task.done():
                    self._log.debug("Websocket wait loop already running.")
                    return
        self._started = True
        for client_id in list(self._client_subscriptions.keys()):
            self._start_client_tasks(client_id)

    async def wait_ready(self):
        """Wait for the initial connection to be established.

        This method only waits for the first successful connection.
        Subsequent reconnections will not affect this event.
        """
        await self._ready.wait()

    async def _connection_handler(self, client_id: int):
        while True:
            try:
                await self._connect(client_id)
                await self._resubscribe_for_client(
                    client_id, self._client_subscriptions.get(client_id, [])
                )
                # Set ready event only on first successful connection
                if not self._ready.is_set():
                    self._ready.set()
                    self._log.debug("Initial connection ready.")
                transport = self._transports.get(client_id)
                if transport is None:
                    break
                await transport.wait_disconnected()
                self._log.debug(f"Websocket disconnected (client {client_id}).")
                self._notify_connection_change(client_id, False)
            except asyncio.CancelledError:
                self._log.debug(
                    f"Websocket connection loop cancelled (client {client_id})."
                )
                break
            except Exception as e:
                self._log.error(f"Connection error: {e}")
            # finally:
            #     self._clean_up_client(client_id)

            self._log.warning(
                f"Websocket reconnecting in {self._reconnect_interval} seconds (client {client_id})..."
            )
            await asyncio.sleep(self._reconnect_interval)

    def _start_client_tasks(self, client_id: int) -> None:
        wait_task = self._wait_tasks.get(client_id)
        if wait_task and not wait_task.done():
            return
        self._wait_tasks[client_id] = self._task_manager.create_task(
            self._connection_handler(client_id)
        )

    def _clean_up_client(self, client_id: int) -> None:
        self._transports[client_id] = None
        self._listeners[client_id] = None

    def send(self, payload: dict, client_id: int | None = None):
        target_id = client_id
        if target_id is None:
            target_id = self._primary_client_id()
            if target_id is None:
                self._log.warning(f"Websocket not connected. drop msg: {str(payload)}")
                return
        transport = self._transports.get(target_id)
        if transport is None:
            self._log.warning(f"Websocket not connected. drop msg: {str(payload)}")
            return
        transport.send(WSMsgType.TEXT, msgspec.json.encode(payload))

    def disconnect(self, client_id: int | None = None):
        if client_id is None:
            client_ids = list(self._transports.keys())
        else:
            client_ids = [client_id]

        for target_id in client_ids:
            transport = self._transports.get(target_id)
            if transport:
                transport.disconnect()

    @abstractmethod
    async def _resubscribe_for_client(self, client_id: int, subscriptions: list[Any]):
        pass
