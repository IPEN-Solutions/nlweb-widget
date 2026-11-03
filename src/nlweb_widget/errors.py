"""Structured runtime errors used at provider and protocol boundaries."""


class NLWebWidgetError(RuntimeError):
    """Base class for expected widget runtime failures."""


class OptionalDependencyError(NLWebWidgetError):
    """Raised when an optional provider dependency is not installed."""


class ProviderInitializationError(NLWebWidgetError):
    """Raised when an optional provider cannot initialize its persistent state."""


class RetrievalError(NLWebWidgetError):
    """Raised when a retrieval provider cannot execute a requested operation."""


class ContentIngestionError(NLWebWidgetError):
    """Raised when a configured content source cannot be normalized."""


class ContentSyncError(NLWebWidgetError):
    """Raised when execution of a configured source fails during synchronization."""
