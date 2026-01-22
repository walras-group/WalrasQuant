from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.component import LiveClock, TimeEvent
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.core.uuid import UUID4

from nautilus_trader.core import nautilus_pyo3  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpClient  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpMethod  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpResponse  # noqa

# from nautilus_trader.core.nautilus_pyo3 import MessageBus  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketClient  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketClientError  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketConfig  # noqa
from nautilus_trader.core.nautilus_pyo3 import (
    hmac_signature,  # noqa
    rsa_signature,  # noqa
    ed25519_signature,  # noqa
)
import nexuslog as logging


def setup_nautilus_core(
    trader_id: str,
    filename: str | None = None,
    level: str = "INFO",
    unix_ts: bool = False,
):
    """
    Setup logging for the application using nexuslog and initialize MessageBus and Clock.

    Args:
        trader_id: Unique identifier for the trader
        filename: Optional file path for log output. If None, logs to stdout.
        level: Minimum log level to record (TRACE, DEBUG, INFO, WARNING, ERROR)
        unix_ts: If True, emit unix timestamps instead of formatted local time.

    Returns:
        tuple: (msgbus, clock) - MessageBus and LiveClock instances
    """
    clock = LiveClock()
    msgbus = MessageBus(
        trader_id=TraderId(trader_id),
        clock=clock,
    )

    # Map log levels from string to nexuslog levels
    level_map = {
        "TRACE": logging.TRACE,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    log_level = level_map.get(level, logging.INFO)

    # Configure nexuslog using basicConfig
    logging.basicConfig(
        filename=filename,
        level=log_level,
        unix_ts=unix_ts,
    )

    return msgbus, clock


def usage():
    import nexuslog as logging

    print(UUID4().value)
    print(UUID4().value)
    print(UUID4().value)

    uuid_to_order_id = {}

    uuid = UUID4()

    order_id = "123456"

    uuid_to_order_id[uuid] = order_id

    print(uuid_to_order_id)

    clock = LiveClock()
    print(clock.timestamp())
    print(type(clock.timestamp_ms()))

    print(clock.utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z"))

    msgbus, clock = setup_nautilus_core(
        trader_id="TESTER-001",
        level="DEBUG",
    )

    log1 = logging.getLogger("logger1")
    log2 = logging.getLogger("logger2")
    log1.debug("This is a debug msg")
    log1.info("This is a info msg")
    log2.debug("This is a debug msg")
    log2.info("This is a info msg")

    # msgbus.subscribe(topic="order", handler=handler1)
    # msgbus.subscribe(topic="order", handler=handler2)
    # msgbus.subscribe(topic="order", handler=handler3)

    # try:
    #     while True:
    #         msgbus.publish(topic="order", msg="hello")
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     print("Exiting...")

    # print("done")
    # from datetime import timedelta, datetime, timezone

    # count = 0
    # name = "TEST_TIMER 111"

    # def count_handler(event: TimeEvent):
    #     nonlocal count
    #     count += 1

    #     print(
    #         f"[{clock.utc_now()}] {event.ts_event} {event.ts_init} {clock.timestamp_ns() - clock.next_time_ns(name)} {event.ts_event - clock.next_time_ns(name)}"
    #     )

    # # clock.register_default_handler(count_handler)

    # interval = timedelta(milliseconds=1000)
    # start_time = (datetime.now(tz=timezone.utc) + timedelta(seconds=1)).replace(
    #     microsecond=0
    # )
    # clock.set_timer(
    #     name=name,
    #     interval=interval,
    #     start_time=start_time,
    #     stop_time=None,
    #     callback=count_handler,
    # )

    # time.sleep(10000)


if __name__ == "__main__":
    usage()
