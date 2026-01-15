"""
Abstracted Email Service for sending transactional emails.
Supports multiple providers: SendGrid, Gmail/SMTP, Console (extensible).
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from app.config import settings
from app.utils.logger import logger


class EmailProvider(str, Enum):
    """Supported email providers"""
    SENDGRID = "sendgrid"
    GMAIL = "gmail"  # Gmail SMTP for development
    SMTP = "smtp"    # Generic SMTP
    CONSOLE = "console"  # For development - just logs emails


@dataclass
class EmailMessage:
    """Email message data structure"""
    to: str
    subject: str
    html_content: str
    plain_content: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    
    def __post_init__(self):
        if not self.from_email:
            self.from_email = settings.EMAIL_FROM_ADDRESS
        if not self.from_name:
            self.from_name = settings.EMAIL_FROM_NAME


class EmailTemplates:
    """HTML email templates for auth-related emails"""
    
    @staticmethod
    def _base_template(content: str, title: str = "StaffPilot") -> str:
        """Base HTML template wrapper"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 40px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo {{
            font-size: 28px;
            font-weight: bold;
            color: #6366f1;
        }}
        .button {{
            display: inline-block;
            background-color: #6366f1;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 6px;
            font-weight: 600;
            margin: 20px 0;
        }}
        .button:hover {{
            background-color: #4f46e5;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #666;
            font-size: 12px;
        }}
        .code {{
            background-color: #f3f4f6;
            padding: 12px 20px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 18px;
            letter-spacing: 2px;
            text-align: center;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">StaffPilot</div>
        </div>
        {content}
        <div class="footer">
            <p>© 2026 StaffPilot. All rights reserved.</p>
            <p>If you didn't request this email, you can safely ignore it.</p>
        </div>
    </div>
</body>
</html>
"""
    
    @classmethod
    def verify_email(cls, user_name: str, otp_code: str) -> str:
        """Email verification template with OTP code"""
        content = f"""
        <h2>Verify your email address</h2>
        <p>Hi{' ' + user_name if user_name else ''},</p>
        <p>Thanks for signing up for StaffPilot! Use the verification code below to complete your registration:</p>
        <div class="code-box">{otp_code}</div>
        <p>Enter this code on the verification page to activate your account.</p>
        <p><strong>This code will expire in 10 minutes.</strong></p>
        <p>If you didn't create an account, you can safely ignore this email.</p>
        """
        return cls._base_template(content, "Verify Your Email - StaffPilot")
    
    @classmethod
    def password_reset(cls, user_name: str, reset_url: str) -> str:
        """Password reset template"""
        content = f"""
        <h2>Reset your password</h2>
        <p>Hi{' ' + user_name if user_name else ''},</p>
        <p>We received a request to reset your password. Click the button below to create a new password:</p>
        <p style="text-align: center;">
            <a href="{reset_url}" class="button">Reset Password</a>
        </p>
        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #666; font-size: 14px;">{reset_url}</p>
        <p><strong>This link will expire in 1 hour.</strong></p>
        <p>If you didn't request a password reset, please ignore this email. Your password will remain unchanged.</p>
        """
        return cls._base_template(content, "Reset Your Password - StaffPilot")
    
    @classmethod
    def password_changed(cls, user_name: str) -> str:
        """Password changed confirmation template"""
        content = f"""
        <h2>Password changed successfully</h2>
        <p>Hi{' ' + user_name if user_name else ''},</p>
        <p>Your password has been changed successfully.</p>
        <p>If you didn't make this change, please contact our support team immediately.</p>
        """
        return cls._base_template(content, "Password Changed - StaffPilot")
    
    @classmethod
    def welcome(cls, user_name: str) -> str:
        """Welcome email after verification template"""
        content = f"""
        <h2>Welcome to StaffPilot! 🎉</h2>
        <p>Hi{' ' + user_name if user_name else ''},</p>
        <p>Your email has been verified and your account is now active.</p>
        <p>You can now start using StaffPilot to:</p>
        <ul>
            <li>Create AI-powered marketing campaigns</li>
            <li>Generate content for social media</li>
            <li>Manage your brand assets</li>
            <li>Schedule and publish posts</li>
        </ul>
        <p style="text-align: center;">
            <a href="{settings.FRONTEND_URL}/dashboard" class="button">Go to Dashboard</a>
        </p>
        """
        return cls._base_template(content, "Welcome to StaffPilot!")


class BaseEmailService(ABC):
    """Abstract base class for email services"""
    
    @abstractmethod
    async def send(self, message: EmailMessage) -> bool:
        """Send an email. Returns True if successful."""
        pass
    
    async def send_verification_email(self, to: str, user_name: str, otp_code: str) -> bool:
        """Send email verification email with OTP code"""
        html_content = EmailTemplates.verify_email(user_name, otp_code)
        
        message = EmailMessage(
            to=to,
            subject="Your verification code - StaffPilot",
            html_content=html_content,
            plain_content=f"Your StaffPilot verification code is: {otp_code}. This code expires in 10 minutes."
        )
        return await self.send(message)
    
    async def send_password_reset_email(self, to: str, user_name: str, token: str) -> bool:
        """Send password reset email"""
        reset_url = f"{settings.FRONTEND_URL}/auth/reset-password?token={token}"
        html_content = EmailTemplates.password_reset(user_name, reset_url)
        
        message = EmailMessage(
            to=to,
            subject="Reset your password - StaffPilot",
            html_content=html_content,
            plain_content=f"Reset your password by visiting: {reset_url}"
        )
        return await self.send(message)
    
    async def send_password_changed_email(self, to: str, user_name: str) -> bool:
        """Send password changed confirmation email"""
        html_content = EmailTemplates.password_changed(user_name)
        
        message = EmailMessage(
            to=to,
            subject="Password changed - StaffPilot",
            html_content=html_content,
            plain_content="Your password has been changed successfully."
        )
        return await self.send(message)
    
    async def send_welcome_email(self, to: str, user_name: str) -> bool:
        """Send welcome email after email verification"""
        html_content = EmailTemplates.welcome(user_name)
        
        message = EmailMessage(
            to=to,
            subject="Welcome to StaffPilot! 🎉",
            html_content=html_content,
            plain_content=f"Welcome to StaffPilot! Visit {settings.FRONTEND_URL}/dashboard to get started."
        )
        return await self.send(message)


class SendGridEmailService(BaseEmailService):
    """SendGrid email service implementation - recommended for production"""
    
    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY
        if not self.api_key:
            logger.warning("SendGrid API key not configured")
    
    async def send(self, message: EmailMessage) -> bool:
        """Send email via SendGrid"""
        if not self.api_key:
            logger.error("SendGrid API key not configured")
            return False
        
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            sg = SendGridAPIClient(self.api_key)
            
            mail = Mail(
                from_email=Email(message.from_email, message.from_name),
                to_emails=To(message.to),
                subject=message.subject,
                html_content=Content("text/html", message.html_content)
            )
            
            if message.plain_content:
                mail.add_content(Content("text/plain", message.plain_content))
            
            response = sg.send(mail)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully via SendGrid to {message.to}")
                return True
            else:
                logger.error(f"SendGrid error: {response.status_code} - {response.body}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {str(e)}")
            return False


class GmailEmailService(BaseEmailService):
    """
    Gmail SMTP email service - great for development.
    
    Requirements:
    1. Enable 2-Factor Authentication on your Google account
    2. Generate an App Password: https://myaccount.google.com/apppasswords
    3. Set SMTP_USERNAME to your Gmail address
    4. Set SMTP_PASSWORD to the App Password (not your regular password)
    """
    
    def __init__(self):
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        
        if not self.username or not self.password:
            logger.warning("Gmail SMTP credentials not configured (SMTP_USERNAME, SMTP_PASSWORD)")
    
    async def send(self, message: EmailMessage) -> bool:
        """Send email via Gmail SMTP"""
        if not self.username or not self.password:
            logger.error("Gmail SMTP credentials not configured")
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{message.from_name} <{message.from_email}>"
            msg["To"] = message.to
            
            if message.reply_to:
                msg["Reply-To"] = message.reply_to
            
            # Add plain text and HTML parts
            if message.plain_content:
                msg.attach(MIMEText(message.plain_content, "plain"))
            msg.attach(MIMEText(message.html_content, "html"))
            
            # Send via Gmail SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(
                    self.username,  # Gmail requires sender to be the authenticated user
                    message.to,
                    msg.as_string()
                )
            
            logger.info(f"Email sent successfully via Gmail to {message.to}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Gmail SMTP authentication failed. Make sure you're using an App Password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email via Gmail SMTP: {str(e)}")
            return False


class SMTPEmailService(BaseEmailService):
    """Generic SMTP email service - works with any SMTP server"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.use_tls = settings.SMTP_USE_TLS
        
        if not all([self.smtp_host, self.smtp_port]):
            logger.warning("SMTP configuration incomplete (SMTP_HOST, SMTP_PORT required)")
    
    async def send(self, message: EmailMessage) -> bool:
        """Send email via SMTP"""
        if not self.smtp_host or not self.smtp_port:
            logger.error("SMTP configuration incomplete")
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{message.from_name} <{message.from_email}>"
            msg["To"] = message.to
            
            if message.reply_to:
                msg["Reply-To"] = message.reply_to
            
            # Add plain text and HTML parts
            if message.plain_content:
                msg.attach(MIMEText(message.plain_content, "plain"))
            msg.attach(MIMEText(message.html_content, "html"))
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(
                    message.from_email,
                    message.to,
                    msg.as_string()
                )
            
            logger.info(f"Email sent successfully via SMTP to {message.to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {str(e)}")
            return False


class ConsoleEmailService(BaseEmailService):
    """Console email service for development - just logs emails"""
    
    async def send(self, message: EmailMessage) -> bool:
        """Log email to console instead of sending"""
        logger.info("=" * 60)
        logger.info("EMAIL (Console Mode - Not Actually Sent)")
        logger.info("=" * 60)
        logger.info(f"To: {message.to}")
        logger.info(f"From: {message.from_name} <{message.from_email}>")
        logger.info(f"Subject: {message.subject}")
        logger.info("-" * 60)
        logger.info(f"Plain Content: {message.plain_content}")
        logger.info("=" * 60)
        return True


def get_email_service() -> BaseEmailService:
    """
    Factory function to get the appropriate email service based on config.
    
    EMAIL_PROVIDER options:
    - 'gmail': Use Gmail SMTP (great for development)
    - 'smtp': Use generic SMTP server
    - 'sendgrid': Use SendGrid API (recommended for production)
    - 'console': Just log emails (for testing)
    """
    provider = getattr(settings, 'EMAIL_PROVIDER', 'console').lower()
    
    if provider == EmailProvider.GMAIL.value:
        return GmailEmailService()
    elif provider == EmailProvider.SMTP.value:
        return SMTPEmailService()
    elif provider == EmailProvider.SENDGRID.value:
        return SendGridEmailService()
    elif provider == EmailProvider.CONSOLE.value:
        return ConsoleEmailService()
    else:
        # Default to console in development, sendgrid in production
        if settings.DEBUG:
            logger.info("EMAIL_PROVIDER not set, using console mode for development")
            return ConsoleEmailService()
        logger.info("EMAIL_PROVIDER not set, using SendGrid for production")
        return SendGridEmailService()


# Singleton instance
_email_service: Optional[BaseEmailService] = None


def get_email_service_instance() -> BaseEmailService:
    """Get or create email service singleton"""
    global _email_service
    if _email_service is None:
        _email_service = get_email_service()
    return _email_service
