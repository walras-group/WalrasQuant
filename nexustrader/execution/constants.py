from enum import Enum


class ExecAlgorithmStatus(Enum):
    """Status of an execution algorithm order."""

    PENDING = "PENDING"  # Waiting for execution
    RUNNING = "RUNNING"  # Currently executing
    CANCELING = "CANCELING"  # Cancellation in progress
    COMPLETED = "COMPLETED"  # Execution completed
    CANCELED = "CANCELED"  # Execution canceled
    FAILED = "FAILED"  # Execution failed


class ExecAlgorithmCommandType(Enum):
    EXECUTE = "EXECUTE"
    CANCEL = "CANCEL"

    @property
    def is_execute(self) -> bool:
        """Return True if command is EXECUTE."""
        return self == ExecAlgorithmCommandType.EXECUTE
    
    @property
    def is_cancel(self) -> bool:
        """Return True if command is CANCEL."""
        return self == ExecAlgorithmCommandType.CANCEL
