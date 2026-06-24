"""Custom exceptions for JARVIS."""


class ContextBudgetError(Exception):
    """Raised when even the minimum required context exceeds the total token budget."""
    pass


class MemoryWriteError(Exception):
    """Raised when a memory write operation fails."""
    pass


class EpisodicStoreError(Exception):
    """Raised when Qdrant operations fail."""
    pass
