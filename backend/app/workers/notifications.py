"""
Notification tasks (email, webhooks, etc.)
Uses Celery for async processing.
"""
from app.workers import celery_app
from app.utils.logger import logger
from app.config import settings


@celery_app.task(name="send_verification_email")
def send_verification_email(to: str, user_name: str, otp_code: str):
    """
    Send email verification email with OTP code via Celery.
    """
    import asyncio
    from app.services.email_service import get_email_service_instance
    
    logger.info(f"Sending verification OTP to {to}")
    
    try:
        email_service = get_email_service_instance()
        
        # Run async send in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                email_service.send_verification_email(to=to, user_name=user_name, otp_code=otp_code)
            )
        finally:
            loop.close()
        
        if result:
            logger.info(f"Verification email sent to {to}")
        else:
            logger.error(f"Failed to send verification email to {to}")
        
        return result
    except Exception as e:
        logger.error(f"Error sending verification email: {str(e)}")
        raise


@celery_app.task(name="send_password_reset_email")
def send_password_reset_email(to: str, user_name: str, token: str):
    """
    Send password reset email via Celery.
    """
    import asyncio
    from app.services.email_service import get_email_service_instance
    
    logger.info(f"Sending password reset email to {to}")
    
    try:
        email_service = get_email_service_instance()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                email_service.send_password_reset_email(to=to, user_name=user_name, token=token)
            )
        finally:
            loop.close()
        
        if result:
            logger.info(f"Password reset email sent to {to}")
        else:
            logger.error(f"Failed to send password reset email to {to}")
        
        return result
    except Exception as e:
        logger.error(f"Error sending password reset email: {str(e)}")
        raise


@celery_app.task(name="send_password_changed_email")
def send_password_changed_email(to: str, user_name: str):
    """
    Send password changed confirmation email via Celery.
    """
    import asyncio
    from app.services.email_service import get_email_service_instance
    
    logger.info(f"Sending password changed confirmation to {to}")
    
    try:
        email_service = get_email_service_instance()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                email_service.send_password_changed_email(to=to, user_name=user_name)
            )
        finally:
            loop.close()
        
        if result:
            logger.info(f"Password changed confirmation sent to {to}")
        else:
            logger.error(f"Failed to send password changed email to {to}")
        
        return result
    except Exception as e:
        logger.error(f"Error sending password changed email: {str(e)}")
        raise


@celery_app.task(name="send_welcome_email")
def send_welcome_email(to: str, user_name: str):
    """
    Send welcome email after email verification via Celery.
    """
    import asyncio
    from app.services.email_service import get_email_service_instance
    
    logger.info(f"Sending welcome email to {to}")
    
    try:
        email_service = get_email_service_instance()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                email_service.send_welcome_email(to=to, user_name=user_name)
            )
        finally:
            loop.close()
        
        if result:
            logger.info(f"Welcome email sent to {to}")
        else:
            logger.error(f"Failed to send welcome email to {to}")
        
        return result
    except Exception as e:
        logger.error(f"Error sending welcome email: {str(e)}")
        raise


@celery_app.task(name="send_email")
def send_email(to: str, subject: str, html_content: str, plain_content: str = None):
    """
    Send a generic email via Celery.
    """
    import asyncio
    from app.services.email_service import get_email_service_instance, EmailMessage
    
    logger.info(f"Sending email to {to}: {subject}")
    
    try:
        email_service = get_email_service_instance()
        message = EmailMessage(
            to=to,
            subject=subject,
            html_content=html_content,
            plain_content=plain_content
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(email_service.send(message))
        finally:
            loop.close()
        
        if result:
            logger.info(f"Email sent to {to}")
        else:
            logger.error(f"Failed to send email to {to}")
        
        return result
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise


@celery_app.task(name="send_webhook")
def send_webhook(url: str, payload: dict):
    """
    Send webhook notification.
    """
    import httpx
    
    logger.info(f"Sending webhook to {url}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
        
        logger.info(f"Webhook sent to {url}, status: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Failed to send webhook to {url}: {str(e)}")
        raise


@celery_app.task(name="send_content_approval_email")
def send_content_approval_email(
    to: str, 
    user_name: str, 
    platform: str, 
    content_preview: str,
    content_count: int = 1
):
    """
    Send content approval request email via Celery.
    """
    import asyncio
    from app.services.email_service import get_email_service_instance
    
    logger.info(f"Sending content approval email to {to} for {platform}")
    
    try:
        email_service = get_email_service_instance()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                email_service.send_content_approval_email(
                    to=to, 
                    user_name=user_name, 
                    platform=platform, 
                    content_preview=content_preview,
                    content_count=content_count
                )
            )
        finally:
            loop.close()
        
        if result:
            logger.info(f"Content approval email sent to {to}")
        else:
            logger.error(f"Failed to send content approval email to {to}")
        
        return result
    except Exception as e:
        logger.error(f"Error sending content approval email: {str(e)}")
        raise
