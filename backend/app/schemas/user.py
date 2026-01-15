"""
Pydantic schemas for User
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    tenant_id: UUID
    role: UserRole = UserRole.MEMBER


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: UUID
    tenant_id: UUID
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_login_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Auth flow schemas
class ForgotPasswordRequest(BaseModel):
    """Request to initiate password reset"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request to reset password with token"""
    token: str
    new_password: str = Field(..., min_length=8)


class VerifyEmailRequest(BaseModel):
    """Request to verify email with OTP code"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class ResendVerificationRequest(BaseModel):
    """Request to resend verification email"""
    email: EmailStr


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


