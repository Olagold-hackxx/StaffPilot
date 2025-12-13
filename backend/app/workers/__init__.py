"""
Celery workers for background tasks
"""
import os
# Disable ChromaDB telemetry before any imports
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "1"
os.environ["POSTHOG_DISABLED"] = "1"

from celery import Celery
from app.config import settings
import ssl
from celery.schedules import crontab


# Dynamically build Redis broker configuration
broker_url = settings.CELERY_BROKER_URL
broker_transport_options = {}

# Dynamically build Redis result backend configuration
result_backend_url = settings.CELERY_RESULT_BACKEND
result_backend_transport_options = {
    "retry_policy": {
        "timeout": 5.0
    },
    "visibility_timeout": 3600,  # 1 hour
    "socket_keepalive": True,
    "socket_keepalive_options": {},
}

# Check if SSL is required (either from setting or rediss:// URL)
broker_use_ssl_flag = settings.REDIS_USE_SSL or broker_url.startswith('rediss://')
backend_use_ssl_flag = settings.REDIS_USE_SSL or result_backend_url.startswith('rediss://')

# Only include SSL settings if SSL is required
# Celery requires ssl_cert_reqs to be CERT_NONE, CERT_OPTIONAL, or CERT_REQUIRED
# Must be set in transport_options for rediss:// URLs
if broker_use_ssl_flag:
    broker_transport_options["ssl_cert_reqs"] = ssl.CERT_NONE

if backend_use_ssl_flag:
    result_backend_transport_options["ssl_cert_reqs"] = ssl.CERT_NONE

# Create Celery app with Redis as broker and result backend
# Configure SSL before creating app if using rediss://
celery_app = Celery("staffpilot")

# Configure Celery with Redis-optimized settings
celery_config = {
    # Broker and backend URLs
    "broker_url": broker_url,
    "result_backend": result_backend_url,
    
    # Serialization
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    
    # Timezone
    "timezone": "UTC",
    "enable_utc": True,
    
    # Task tracking
    "task_track_started": True,
    "task_time_limit": 1800,  # 30 minutes
    
    # Redis-specific settings
    "broker_connection_retry_on_startup": True,
    "broker_connection_retry": True,
    "broker_connection_max_retries": 10,
}

# Add SSL configuration if needed
# For rediss:// URLs, Celery requires ssl_cert_reqs to be explicitly set in transport_options
if broker_use_ssl_flag:
    celery_config["broker_use_ssl"] = {
        "ssl_cert_reqs": ssl.CERT_NONE
    }
    celery_config["broker_transport_options"] = broker_transport_options
elif broker_transport_options:
    celery_config["broker_transport_options"] = broker_transport_options

if backend_use_ssl_flag:
    celery_config["redis_backend_use_ssl"] = {
        "ssl_cert_reqs": ssl.CERT_NONE
    }
    celery_config["result_backend_transport_options"] = result_backend_transport_options
else:
    celery_config["result_backend_transport_options"] = result_backend_transport_options

# Disable Celery telemetry to avoid errors
# This prevents the "capture() takes 1 positional argument but 3 were given" error
import os
os.environ.setdefault("CELERY_SEND_TASK_EVENTS", "False")

# Add remaining configuration
celery_config.update({
    # Disable telemetry
    "worker_send_task_events": False,
    "task_send_sent_event": False,
    
    # Task result settings
    "result_expires": 3600,  # Results expire after 1 hour
    "result_persistent": True,  # Persist results in Redis
    
    # Worker settings
    "worker_prefetch_multiplier": 1,  # Prefetch 1 task at a time to prevent blocking
    "worker_max_tasks_per_child": 1000,  # Restart worker after 1000 tasks
    
    # Task routing (optional - comment out to use default queue)
    # Uncomment to route tasks to specific queues:
    # "task_routes": {
    #     "app.workers.ingestion.*": {"queue": "ingestion"},
    #     "app.workers.content_creation.*": {"queue": "content"},
    #     "app.workers.notifications.*": {"queue": "notifications"},
    # },
    
    # Task acknowledgment
    "task_acks_late": False,  # Acknowledge tasks before execution to prevent blocking on hangs
    "task_reject_on_worker_lost": True,  # Reject tasks if worker dies
    
    # Worker logging - reduce verbosity for scheduled tasks
    "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    "worker_task_log_format": "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
    
    # Celery Beat schedule for periodic tasks
    "beat_schedule": {
        'check-scheduled-posts': {
            'task': 'scheduled_posts.check_scheduled',
            'schedule': crontab(minute='*/2'),  # Run every 2 minutes to check for scheduled posts
            'options': {
                'expires': 300,  # Task expires after 5 minutes if not picked up
                'time_limit': 1800,  # 30 minutes hard limit
            }
        },
    },
})

celery_app.conf.update(celery_config)

# Import tasks to register them
from app.workers import ingestion, notifications, content_creation, campaign_creation, scheduled_posts  # noqa

