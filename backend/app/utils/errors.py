"""
Custom exception classes
"""
from typing import Optional


class StaffPilotException(Exception):
    """Base exception for StaffPilot platform"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class TenantNotFoundError(StaffPilotException):
    """Tenant not found"""
    def __init__(self, tenant_id: str):
        super().__init__(
            f"Tenant with ID {tenant_id} not found",
            status_code=404
        )


class UserNotFoundError(StaffPilotException):
    """User not found"""
    def __init__(self, user_id: str):
        super().__init__(
            f"User with ID {user_id} not found",
            status_code=404
        )


class AssistantNotFoundError(StaffPilotException):
    """Assistant not found"""
    def __init__(self, assistant_id: str):
        super().__init__(
            f"Assistant with ID {assistant_id} not found",
            status_code=404
        )


class ConversationNotFoundError(StaffPilotException):
    """Conversation not found"""
    def __init__(self, conversation_id: str):
        super().__init__(
            f"Conversation with ID {conversation_id} not found",
            status_code=404
        )


class DocumentNotFoundError(StaffPilotException):
    """Document not found"""
    def __init__(self, document_id: str):
        super().__init__(
            f"Document with ID {document_id} not found",
            status_code=404
        )


class UnauthorizedError(StaffPilotException):
    """Unauthorized access"""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401)


class ForbiddenError(StaffPilotException):
    """Forbidden access"""
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403)


class ValidationError(StaffPilotException):
    """Validation error"""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class StorageError(StaffPilotException):
    """Storage operation error"""
    def __init__(self, message: str):
        super().__init__(message, status_code=500)

