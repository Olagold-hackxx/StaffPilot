"""
Database session management
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, Engine
from app.config import settings
from app.utils.logger import logger
import threading
import ssl
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Global engine for FastAPI app (main process)
_engine: AsyncEngine | None = None
_engine_lock = threading.Lock()

# Per-process SYNC engine cache for Celery workers
# Using sync sessions eliminates event loop issues!
_worker_sync_engine: Engine | None = None
_worker_sync_engine_lock = threading.Lock()
_worker_sync_session_factory = None

def _get_ssl_context():
    """Create SSL context for database connections if SSL is required"""
    if not settings.DATABASE_SSL_REQUIRED:
        return None
    
    ssl_context = ssl.create_default_context()
    
    # If CA certificate is provided, use it
    if settings.DATABASE_SSL_CA:
        ca_path = settings.DATABASE_SSL_CA
        
        # If it's a file path, use it directly
        if os.path.isfile(ca_path):
            ssl_context.load_verify_locations(ca_path)
        # Otherwise, treat it as certificate content and write to temp file
        elif not os.path.exists(ca_path):
            # Assume it's certificate content from env variable
            # Write to a temporary file
            ca_file_path = Path("/tmp/postgres-ca.crt")
            ca_file_path.write_text(settings.DATABASE_SSL_CA)
            ssl_context.load_verify_locations(str(ca_file_path))
        else:
            ssl_context.load_verify_locations(ca_path)
    
    return ssl_context

def get_engine() -> AsyncEngine:
    """Get or create the database engine (thread-safe)"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                connect_args = {}
                ssl_context = _get_ssl_context()
                if ssl_context:
                    connect_args["ssl"] = ssl_context
                
                # Add timeout settings for asyncpg
                # command_timeout: timeout for individual SQL commands (in seconds)
                connect_args["command_timeout"] = 30
                # server_settings can include connection timeout
                connect_args.setdefault("server_settings", {})
                
                _engine = create_async_engine(
                    settings.DATABASE_URL,
                    echo=settings.DATABASE_ECHO,
                    future=True,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,  # Verify connections before using
                    pool_recycle=3600,  # Recycle connections after 1 hour
                    pool_timeout=30,  # Timeout for getting connection from pool (seconds)
                    connect_args=connect_args,
                )
    return _engine


def get_worker_engine() -> AsyncEngine:
    """
    DEPRECATED: Use create_worker_session_factory() instead for sync sessions.
    
    This function is kept for backward compatibility but should not be used.
    Celery workers should use sync sessions via create_worker_session_factory().
    """
    # This should not be called anymore - workers use sync sessions
    raise NotImplementedError("Use create_worker_session_factory() for sync sessions instead")

def _convert_async_url_to_sync(url: str) -> str:
    """
    Convert async database URL to sync URL.
    postgresql+asyncpg:// -> postgresql:// (psycopg2)
    """
    parsed = urlparse(url)
    # Replace asyncpg with standard postgresql (psycopg2)
    if parsed.scheme.startswith("postgresql+asyncpg"):
        scheme = "postgresql"
    elif parsed.scheme.startswith("postgresql"):
        scheme = "postgresql"
    else:
        scheme = parsed.scheme
    
    return urlunparse((scheme,) + parsed[1:])

def create_worker_session_factory():
    """
    Create a SYNC session factory for Celery workers.
    
    This is much simpler than async:
    - No event loop issues
    - No asyncio.run() needed for database operations
    - Standard SQLAlchemy sync sessions 
    - Can share engine across tasks in same worker process
    """
    global _worker_sync_session_factory, _worker_sync_engine
    
    if _worker_sync_session_factory is None:
        with _worker_sync_engine_lock:
            if _worker_sync_session_factory is None:
                # Convert async URL to sync URL (postgresql+asyncpg -> postgresql)
                sync_url = _convert_async_url_to_sync(settings.DATABASE_URL)
                
                # SSL configuration for sync engine (psycopg2)
                connect_args = {}
                if settings.DATABASE_SSL_REQUIRED:
                    if settings.DATABASE_SSL_CA:
                        ca_path = settings.DATABASE_SSL_CA
                        if not os.path.isfile(ca_path):
                            # Write certificate content to temp file
                            ca_file_path = Path("/tmp/postgres-ca.crt")
                            ca_file_path.write_text(settings.DATABASE_SSL_CA)
                            ca_path = str(ca_file_path)
                        connect_args["sslrootcert"] = ca_path
                    connect_args["sslmode"] = "require"
                
                # Calculate pool size based on worker concurrency
                worker_concurrency = int(os.environ.get("CELERY_WORKER_CONCURRENCY", "4"))
                pool_size = worker_concurrency + 2
                max_overflow = max(2, worker_concurrency // 2)
                
                # Create sync engine (psycopg2)
                # Only pass connect_args if it's not empty
                engine_kwargs = {
                    "url": sync_url,
                    "echo": settings.DATABASE_ECHO,
                    "pool_size": pool_size,
                    "max_overflow": max_overflow,
                    "pool_pre_ping": True,  # Safe for sync
                    "pool_recycle": 3600,
                    "pool_timeout": 5,
                }
                if connect_args:
                    engine_kwargs["connect_args"] = connect_args
                
                _worker_sync_engine = create_engine(**engine_kwargs)
                
                # Create sync session factory
                _worker_sync_session_factory = sessionmaker(
                    bind=_worker_sync_engine,
                    class_=Session,
                    expire_on_commit=False,
                    autocommit=False,
                    autoflush=False,
                )
    
    return _worker_sync_session_factory

# Lazy async session factory for FastAPI app
# Don't create at module import time to avoid issues when workers import this module
_async_session_local = None

def get_async_session_local():
    """Get or create async session factory for FastAPI (lazy initialization)"""
    global _async_session_local
    if _async_session_local is None:
        _async_session_local = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_local

# For backward compatibility - AsyncSessionLocal is now a function
# Use get_async_session_local() directly, or call AsyncSessionLocal() which will work the same
def AsyncSessionLocal():
    """Lazy async session factory - creates session on first call"""
    return get_async_session_local()()


async def get_db() -> AsyncSession:
    """
    Dependency for getting database session
    """
    try:
        session_factory = get_async_session_local()
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()
    except Exception as e:
        # Log connection errors for debugging
        logger.error(f"Database connection error: {str(e)}", exc_info=True)
        raise

