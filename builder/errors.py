"""Error type shared by all builder modules."""


class BuildError(Exception):
    """A build failure with a human-readable message and a process exit code."""

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message
