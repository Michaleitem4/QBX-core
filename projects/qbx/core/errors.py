"""Custom exceptions for QBX."""


class QBXError(Exception):
    """Base exception for QBX errors."""
    pass


class IntegrityError(QBXError):
    """Raised when data integrity check fails (e.g., checksum mismatch)."""
    pass


class CorruptionError(QBXError):
    """Raised when data corruption is detected."""
    pass


class PermissionError(QBXError):
    """Raised when operation is not permitted."""
    pass


class ConflictError(QBXError):
    """Raised when sync conflict is detected."""
    pass
