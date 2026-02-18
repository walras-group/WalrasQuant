class BinanceClientError(Exception):
    """
    The base class for all Binance specific errors.
    """

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code}, message='{self.message}')"

    __str__ = __repr__


class BinanceServerError(Exception):
    """
    The base class for all Binance specific errors.
    """

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code}, message='{self.message}')"

    __str__ = __repr__


class BinanceRateLimitError(Exception):
    """
    Raised when Binance API rate limit is exceeded.
    """

    def __init__(
        self,
        message: str,
        retry_after: float = 0.0,
        api_type: str | None = None,
        rate_limit_type: str | None = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.api_type = api_type
        self.rate_limit_type = rate_limit_type
