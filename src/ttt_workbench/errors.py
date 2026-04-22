from __future__ import annotations


class WorkbenchError(Exception):
    """Base typed workbench error with a user-facing message."""

    def __init__(self, message: str, *, code: str = "workbench_error") -> None:
        super().__init__(message)
        self.user_message = message
        self.code = code


class ProviderRequestError(WorkbenchError):
    """Raised when a provider/endpoint request fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="provider_request_error")


class ModelDiscoveryError(WorkbenchError):
    """Raised when model discovery cannot complete."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="model_discovery_error")
