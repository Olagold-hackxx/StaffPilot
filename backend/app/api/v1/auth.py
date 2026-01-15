"""
Authentication API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.email_token import EmailToken, EmailTokenType
from app.schemas.user import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest,
    ResendVerificationRequest, MessageResponse
)
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.workers.notifications import (
    send_verification_email,
    send_password_reset_email,
    send_password_changed_email,
    send_welcome_email
)
from app.config import settings
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user and send verification email"""
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create user (not verified yet)
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        tenant_id=user_data.tenant_id,
        role=user_data.role,
        is_verified=False
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Create verification OTP token (10 min expiry)
    token = EmailToken.create_verification_token(user_id=user.id)
    db.add(token)
    await db.commit()
    
    # Queue verification email via Celery with OTP code
    send_verification_email.delay(
        to=user.email,
        user_name=user.full_name or "",
        otp_code=token.token
    )
    logger.info(f"User registered: {user.email}, verification OTP queued")
    
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login and get access token"""
    # Find user
    result = await db.execute(
        select(User).where(User.email == credentials.email)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Optional: Require email verification
    # Uncomment if you want to enforce email verification before login
    # if not user.is_verified:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Please verify your email before logging in"
    #     )
    
    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)  # Refresh to eagerly load all attributes for Pydantic serialization
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return current_user


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify email with OTP code"""
    # Find user by email first
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or code"
        )
    
    # Find valid token for this user
    result = await db.execute(
        select(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.token == request.code,
            EmailToken.token_type == "verify_email"
        )
    )
    token = result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )
    
    if not token.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code has expired or already been used"
        )
    
    # Mark user as verified
    user.is_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    
    # Mark token as used
    token.mark_as_used()
    
    await db.commit()
    
    # Queue welcome email via Celery
    send_welcome_email.delay(
        to=user.email,
        user_name=user.full_name or ""
    )
    logger.info(f"Email verified for user: {user.email}")
    
    return MessageResponse(message="Email verified successfully")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    request: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Resend email verification"""
    # Find user
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    # Always return success to prevent email enumeration
    if not user or user.is_verified:
        return MessageResponse(message="If an account exists with this email, a verification link has been sent")
    
    # Invalidate existing verification tokens
    existing_tokens = await db.execute(
        select(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.token_type == EmailTokenType.VERIFY_EMAIL,
            EmailToken.used_at == None
        )
    )
    for token in existing_tokens.scalars():
        token.mark_as_used()
    
    # Create new verification token
    new_token = EmailToken.create_verification_token(
        user_id=user.id,
        expire_hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS
    )
    db.add(new_token)
    await db.commit()
    
    # Queue verification email via Celery
    send_verification_email.delay(
        to=user.email,
        user_name=user.full_name or "",
        token=new_token.token
    )
    logger.info(f"Verification email resent to: {user.email}")
    
    return MessageResponse(message="If an account exists with this email, a verification link has been sent")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request password reset email"""
    # Find user
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    # Always return success to prevent email enumeration
    if not user:
        return MessageResponse(message="If an account exists with this email, a password reset link has been sent")
    
    # Invalidate existing reset tokens
    existing_tokens = await db.execute(
        select(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.token_type == EmailTokenType.RESET_PASSWORD,
            EmailToken.used_at == None
        )
    )
    for token in existing_tokens.scalars():
        token.mark_as_used()
    
    # Create new reset token
    reset_token = EmailToken.create_reset_token(
        user_id=user.id,
        expire_hours=settings.PASSWORD_RESET_EXPIRE_HOURS
    )
    db.add(reset_token)
    await db.commit()
    
    # Queue reset email via Celery
    send_password_reset_email.delay(
        to=user.email,
        user_name=user.full_name or "",
        token=reset_token.token
    )
    logger.info(f"Password reset email sent to: {user.email}")
    
    return MessageResponse(message="If an account exists with this email, a password reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token"""
    # Find token
    result = await db.execute(
        select(EmailToken).where(
            EmailToken.token == request.token,
            EmailToken.token_type == EmailTokenType.RESET_PASSWORD
        )
    )
    token = result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )
    
    if not token.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token has expired or already been used"
        )
    
    # Get user
    result = await db.execute(
        select(User).where(User.id == token.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    
    # Mark token as used
    token.mark_as_used()
    
    await db.commit()
    
    # Queue password changed confirmation email via Celery
    send_password_changed_email.delay(
        to=user.email,
        user_name=user.full_name or ""
    )
    logger.info(f"Password reset for user: {user.email}")
    
    return MessageResponse(message="Password reset successfully")
