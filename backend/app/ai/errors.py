class AIError(Exception):
    """Base class for every AI-layer error."""


class AIUnavailableError(AIError):
    """The model could not be reached: server down, timeout, 5xx, or model not downloaded.

    Callers should treat this as "no AI right now" and fall back to a human.
    """


class AIInvalidOutputError(AIError):
    """The model answered, but its output failed validation even after retries.

    `raw_output` is kept for debugging. Do not show it to customers.
    """

    def __init__(self, message: str, raw_output: str, attempts: int) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.attempts = attempts
