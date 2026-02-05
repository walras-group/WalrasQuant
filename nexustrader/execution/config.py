from msgspec import Struct


class ExecAlgorithmConfig(Struct, kw_only=True, frozen=True):
    """
    Base configuration for all execution algorithms.

    Parameters
    ----------
    exec_algorithm_id : str | None
        The unique ID for the execution algorithm.
        If None, uses the class name.
    log_events : bool, default True
        If events should be logged by the execution algorithm.
    log_commands : bool, default True
        If commands should be logged by the execution algorithm.
    """

    exec_algorithm_id: str | None = None
    log_events: bool = True
    log_commands: bool = True


class TWAPConfig(ExecAlgorithmConfig, kw_only=True, frozen=True):
    """
    Configuration for TWAP (Time-Weighted Average Price) execution algorithm.

    Parameters
    ----------
    exec_algorithm_id : str, default "TWAP"
        The execution algorithm ID.
    """

    exec_algorithm_id: str = "TWAP"
