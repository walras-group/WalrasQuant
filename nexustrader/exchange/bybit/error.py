class BybitError(Exception):
    """
    Represents Bybit specific errors.
    """

    def __init__(
        self,
        code: int | None,
        message: str | None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code}, message='{self.message}')"

    __str__ = __repr__


class BybitRateLimitError(Exception):
    """
    Raised when Bybit API rate limit is exceeded.
    """

    def __init__(
        self,
        message: str,
        retry_after: float = 0.0,
        scope: str | None = None,
        endpoint: str | None = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.scope = scope
        self.endpoint = endpoint
