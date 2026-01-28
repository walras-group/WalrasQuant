import nexuslog as logging
from nexustrader.constants import settings


use_nautilius = settings.get("USE_NAUTILIUS", False)

if use_nautilius:
    try:
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
    except ImportError as e:
        raise ImportError(
            "Nautilus Trader is not installed. Please install run `pip install nautilus-trader` to use Nautilus features."
        ) from e
else:
    from nexuscore import (
        MessageBus,
        LiveClock,
        TimeEvent,
        TraderId,
        UUID4,
        hmac_signature,
        rsa_signature,
        ed25519_signature,
    )


def setup_nexus_core(
    trader_id: str,
    filename: str | None = None,
    level: str = "INFO",
    name_levels: dict[str | None, str] | None = None,
    unix_ts: bool = False,
    batch_size: int | None = None,
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

    _name_levels = None
    if name_levels:
        _name_levels = {
            name: level_map.get(lvl_str, logging.INFO)
            for name, lvl_str in name_levels.items()
        }

    # Configure nexuslog using basicConfig
    logging.basicConfig(
        filename=filename,
        level=log_level,
        name_levels=_name_levels,
        unix_ts=unix_ts,
        batch_size=batch_size,
    )

    return msgbus, clock
