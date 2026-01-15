from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
import secrets
import random
from datetime import datetime, timedelta, timezone
from app.db.base import Base


class EmailTokenType(str, enum.Enum):
    """Types of email tokens"""
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class EmailToken(Base):
    __tablename__ = "email_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_type = Column(
        PG_ENUM('verify_email', 'reset_password', name='emailtokentype', create_type=False),
        nullable=False
    )
    token = Column(String(255), unique=True, nullable=False, index=True)
    
    # Expiration and usage tracking
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", backref="email_tokens")
    
    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)
    
    @classmethod
    def generate_otp(cls) -> str:
        """Generate a 6-digit OTP code"""
        return str(random.randint(100000, 999999))
    
    @classmethod
    def create_verification_token(cls, user_id: uuid.UUID, expire_minutes: int = 10) -> "EmailToken":
        """Create an email verification OTP token (6-digit code, 10 min expiry)"""
        return cls(
            user_id=user_id,
            token_type="verify_email",
            token=cls.generate_otp(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
        )
    
    @classmethod
    def create_reset_token(cls, user_id: uuid.UUID, expire_hours: int = 1) -> "EmailToken":
        """Create a password reset token"""
        return cls(
            user_id=user_id,
            token_type="reset_password",
            token=cls.generate_token(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expire_hours)
        )
    
    @property
    def is_expired(self) -> bool:
        """Check if token has expired"""
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def is_used(self) -> bool:
        """Check if token has been used"""
        return self.used_at is not None
    
    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)"""
        return not self.is_expired and not self.is_used
    
    def mark_as_used(self):
        """Mark the token as used"""
        self.used_at = datetime.now(timezone.utc)
    
    def __repr__(self):
        return f"<EmailToken(id={self.id}, type={self.token_type}, user_id={self.user_id})>"
