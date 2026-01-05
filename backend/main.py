"""
FastAPI application entry point
"""
import os
# Disable ChromaDB telemetry before any imports
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "1"
os.environ["POSTHOG_DISABLED"] = "1"

from fastapi import FastAPI, Request, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from app.config import settings
from app.utils.errors import StaffPilotException
from app.utils.logger import logger
from app.api.v1 import tenants, chat, assistants, documents, billing, auth, integrations, capabilities, agents, campaigns, scheduled_posts
from typing import Optional
from urllib.parse import urlencode

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="StaffPilot - AI Assistant Platform API",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(tenants.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(assistants.router, prefix=settings.API_V1_PREFIX)
app.include_router(documents.router, prefix=settings.API_V1_PREFIX)
app.include_router(billing.router, prefix=settings.API_V1_PREFIX)
app.include_router(integrations.router, prefix=settings.API_V1_PREFIX)
app.include_router(capabilities.router, prefix=settings.API_V1_PREFIX)
app.include_router(agents.router, prefix=settings.API_V1_PREFIX)
app.include_router(campaigns.router, prefix=settings.API_V1_PREFIX)
app.include_router(scheduled_posts.router, prefix=settings.API_V1_PREFIX)


# Exception handlers
@app.exception_handler(StaffPilotException)
async def staffpilot_exception_handler(request: Request, exc: StaffPilotException):
    """Handle StaffPilot exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )


from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handle HTTPException - sanitize 500 errors to not expose internal details.
    400-level errors keep their messages since they're user-facing validation errors.
    """
    if exc.status_code >= 500:
        # Log the actual error for debugging
        logger.error(f"HTTP {exc.status_code} error: {exc.detail}")
        # Return generic message to client
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "An unexpected error occurred. Please try again later."}
        )
    # For 4xx errors, return the original message (these are intentional user-facing messages)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "StaffPilot API",
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )

