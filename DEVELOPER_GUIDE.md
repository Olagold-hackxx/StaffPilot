# StaffPilot (AIConnect) - Developer Technical Guide

> **Comprehensive technical documentation for developers joining or taking over the project**

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Database Models](#database-models)
6. [Backend Services](#backend-services)
7. [API Endpoints](#api-endpoints)
8. [Celery Workers & Tasks](#celery-workers--tasks)
9. [AI/LLM Integration](#aillm-integration)
10. [Vector Store & RAG](#vector-store--rag)
11. [Social Media Integrations](#social-media-integrations)
12. [Authentication & Authorization](#authentication--authorization)
13. [Storage Configuration](#storage-configuration)
14. [Deployment](#deployment)
15. [Local Development Setup](#local-development-setup)
16. [Environment Variables](#environment-variables)
17. [Common Operations](#common-operations)

---

## Project Overview

**StaffPilot** (codenamed "AIConnect" / "Buzz") is an AI-powered social media management platform that:

- Generates social media content using AI (Gemini, OpenAI, or Claude)
- Creates AI-generated images and videos for posts
- Connects to social platforms (Facebook, Instagram, LinkedIn, Twitter/X, TikTok)
- Schedules and publishes posts automatically
- Uses RAG (Retrieval Augmented Generation) with uploaded documents
- Manages advertising campaigns across platforms
- Provides analytics and performance tracking

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vercel)                                     │
│                      Next.js 15 + React 19 + TailwindCSS                     │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Railway Platform                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ FastAPI Backend │  │  Celery Worker  │  │    Celery Beat (Scheduler)  │  │
│  │   (main.py)     │  │                 │  │                             │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────┬───────────────┘  │
│           │                    │                          │                  │
│           └────────────┬───────┴──────────────────────────┘                  │
│                        ▼                                                     │
│           ┌─────────────────────────┐                                        │
│           │   Railway PostgreSQL    │                                        │
│           │     (Primary DB)        │                                        │
│           └─────────────────────────┘                                        │
│                                                                              │
│           ┌─────────────────────────┐                                        │
│           │    Railway Redis        │                                        │
│           │  (Cache + Celery Broker)│                                        │
│           └─────────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘

External Services:
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│  Pinecone  │ │ Cloudinary │ │ Google AI  │ │   Stripe   │ │  SerpAPI   │
│ (Vectors)  │ │ (Storage)  │ │ (Gemini)   │ │ (Billing)  │ │   (SEO)    │
└────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘

┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│  Facebook  │ │  Instagram │ │  LinkedIn  │ │  Twitter   │ │   TikTok   │
│  Graph API │ │  Graph API │ │    API     │ │    API     │ │    API     │
└────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘
```

---

## Technology Stack

### Backend

| Component    | Technology        | Version  |
| ------------ | ----------------- | -------- |
| Framework    | FastAPI           | ≥0.109.0 |
| Server       | Uvicorn           | ≥0.24.0  |
| Database     | PostgreSQL        | 15       |
| ORM          | SQLAlchemy        | 2.0.23   |
| Migrations   | Alembic           | 1.12.1   |
| Task Queue   | Celery            | 5.3.4    |
| Cache/Broker | Redis             | 7.x      |
| Auth         | python-jose (JWT) | 3.3.0    |

### Frontend

| Component     | Technology            | Version |
| ------------- | --------------------- | ------- |
| Framework     | Next.js               | 15.5.9  |
| React         | React                 | 19.2.0  |
| Styling       | TailwindCSS           | 4.x     |
| UI Components | Radix UI              | Latest  |
| Forms         | React Hook Form + Zod | Latest  |
| Charts        | Recharts              | 2.15.4  |

### External Services

| Service                | Purpose                              |
| ---------------------- | ------------------------------------ |
| **Pinecone**           | Vector database for RAG embeddings   |
| **Cloudinary**         | Media storage (images, videos)       |
| **Google AI (Gemini)** | Content, image, and video generation |
| **OpenAI**             | Alternative LLM provider             |
| **Anthropic Claude**   | Alternative LLM provider             |
| **Stripe**             | Payment processing                   |
| **SerpAPI**            | SEO keyword research                 |
| **Gmail SMTP**         | Email notifications                  |

---

## Project Structure

```
buzz/
├── backend/
│   ├── app/
│   │   ├── api/v1/                    # API route handlers
│   │   │   ├── auth.py                # Authentication endpoints
│   │   │   ├── users.py               # User management
│   │   │   ├── tenants.py             # Multi-tenant management
│   │   │   ├── assistants.py          # AI assistants
│   │   │   ├── integrations.py        # Social media OAuth
│   │   │   ├── content.py             # Content creation
│   │   │   ├── campaigns.py           # Ad campaigns
│   │   │   ├── documents.py           # Document uploads
│   │   │   ├── analytics.py           # Analytics
│   │   │   ├── billing.py             # Stripe billing
│   │   │   └── storage.py             # File storage
│   │   │
│   │   ├── models/                    # SQLAlchemy models
│   │   │   ├── user.py                # User model
│   │   │   ├── tenant.py              # Tenant (organization)
│   │   │   ├── assistant.py           # AI Assistant config
│   │   │   ├── integration.py         # Social integrations
│   │   │   ├── content.py             # Generated content
│   │   │   ├── campaign.py            # Ad campaigns
│   │   │   ├── document.py            # RAG documents
│   │   │   ├── conversation.py        # Chat history
│   │   │   ├── agent_execution.py     # Task executions
│   │   │   ├── brand_asset.py         # Brand assets
│   │   │   └── ...
│   │   │
│   │   ├── services/                  # Business logic
│   │   │   ├── llm/                   # LLM providers
│   │   │   │   ├── base.py            # Abstract base class
│   │   │   │   ├── gemini.py          # Google Gemini
│   │   │   │   ├── openai.py          # OpenAI GPT
│   │   │   │   ├── anthropic.py       # Claude
│   │   │   │   └── factory.py         # Provider factory
│   │   │   │
│   │   │   ├── integrations/          # Platform integrations
│   │   │   │   ├── social/            # Social posting
│   │   │   │   │   ├── facebook.py
│   │   │   │   │   ├── instagram.py
│   │   │   │   │   ├── linkedin.py
│   │   │   │   │   ├── twitter.py
│   │   │   │   │   └── tiktok.py
│   │   │   │   ├── ads/               # Ad platforms
│   │   │   │   └── seo/               # SEO tools
│   │   │   │
│   │   │   ├── storage/               # File storage
│   │   │   │   ├── base.py
│   │   │   │   ├── local.py
│   │   │   │   ├── s3.py
│   │   │   │   └── cloudinary.py
│   │   │   │
│   │   │   ├── vector_store.py        # Pinecone integration
│   │   │   ├── rag_service.py         # RAG retrieval
│   │   │   ├── email_service.py       # Email notifications
│   │   │   └── ...
│   │   │
│   │   ├── workers/                   # Celery tasks
│   │   │   ├── __init__.py            # Celery app config
│   │   │   ├── content_creation.py    # Content generation tasks
│   │   │   ├── campaign_creation.py   # Campaign tasks
│   │   │   ├── scheduled_posts.py     # Post scheduling
│   │   │   ├── notifications.py       # Email tasks
│   │   │   └── ingestion.py           # Document ingestion
│   │   │
│   │   ├── schemas/                   # Pydantic schemas
│   │   ├── db/                        # Database config
│   │   ├── utils/                     # Utilities
│   │   └── config.py                  # Settings
│   │
│   ├── migrations/                    # Alembic migrations
│   ├── Dockerfile                     # Backend container
│   ├── Dockerfile.celery              # Celery worker container
│   ├── Dockerfile.celerybeat          # Celery beat container
│   ├── docker-compose.yml             # Local development
│   ├── requirements.txt               # Python dependencies
│   └── main.py                        # FastAPI entry point
│
└── frontend/
    ├── app/                           # Next.js App Router
    │   ├── (auth)/                    # Auth pages (login, signup)
    │   ├── (dashboard)/               # Dashboard pages
    │   │   └── dashboard/
    │   │       ├── assistants/        # AI assistant management
    │   │       ├── content/           # Content creation
    │   │       ├── campaigns/         # Campaign management
    │   │       ├── integrations/      # Social connections
    │   │       ├── analytics/         # Analytics
    │   │       └── settings/          # User settings
    │   ├── api/                       # API routes (edge functions)
    │   └── layout.tsx                 # Root layout
    │
    ├── components/                    # React components
    │   ├── ui/                        # Radix UI primitives
    │   └── ...                        # Feature components
    │
    └── lib/                           # Utilities
```

---

## Database Models

### Core Models

| Model               | Table                 | Description                            |
| ------------------- | --------------------- | -------------------------------------- |
| `User`              | `users`               | User accounts with email/password      |
| `Tenant`            | `tenants`             | Organizations/companies (multi-tenant) |
| `Assistant`         | `assistants`          | AI assistants per tenant               |
| `SocialIntegration` | `social_integrations` | Connected social accounts              |
| `Content`           | `contents`            | Generated social content               |
| `ScheduledPost`     | `scheduled_posts`     | Scheduled content posts                |
| `Document`          | `documents`           | Uploaded RAG documents                 |
| `Campaign`          | `campaigns`           | Ad campaigns                           |
| `BrandAsset`        | `brand_assets`        | Logos, images for AI reference         |
| `Conversation`      | `conversations`       | Chat history                           |
| `AgentExecution`    | `agent_executions`    | Task execution logs                    |

### Key Relationships

```
Tenant (1) ─────┬────── (N) User
                ├────── (N) Assistant
                ├────── (N) SocialIntegration
                ├────── (N) Content
                ├────── (N) Document
                ├────── (N) Campaign
                └────── (N) BrandAsset

Assistant (1) ──┬────── (N) Conversation
                ├────── (N) SocialIntegration
                └────── (N) AgentExecution
```

---

## Backend Services

### LLM Service (`app/services/llm/`)

Factory pattern for multiple LLM providers:

```python
from app.services.llm.factory import create_llm_service

# Uses DEFAULT_LLM_PROVIDER from settings
llm = create_llm_service()

# Or specify provider
llm = create_llm_service("gemini")  # gemini, openai, anthropic

# Content generation
response = await llm.generate_content(prompt, context)

# Image generation (Gemini only)
images = await llm.generate_image(prompt, aspect_ratio="1:1")

# Video generation (Gemini Veo only)
video = await llm.generate_video(prompt, duration_seconds=30)

# Embeddings
embedding = await llm.generate_embedding(text)
```

### Vector Store (`app/services/vector_store.py`)

Pinecone integration for RAG:

```python
from app.services.vector_store import VectorStore

store = VectorStore()

# Upsert document chunks
await store.upsert_chunks(
    tenant_id="...",
    document_id="...",
    chunks=[{"content": "...", "metadata": {...}}]
)

# Query similar chunks
results = await store.query(
    tenant_id="...",
    query_embedding=[...],
    top_k=10
)

# Delete document
await store.delete_document(tenant_id, document_id)
```

### Storage Service (`app/services/storage/`)

Cloudinary used in production:

```python
from app.services.storage import get_storage

storage = get_storage()  # Returns CloudinaryStorage in prod

# Upload image
url = await storage.upload(
    file_data=bytes,
    filename="image.png",
    folder="tenant_123/images"
)

# Delete file
await storage.delete(public_id)
```

### Email Service (`app/services/email_service.py`)

Gmail SMTP for notifications:

```python
from app.services.email_service import EmailService

email_service = EmailService()

# Send verification OTP
await email_service.send_verification_email(email, otp_code)

# Send password reset
await email_service.send_password_reset_email(email, reset_link)
```

---

## API Endpoints

### Authentication (`/api/v1/auth`)

| Method | Endpoint               | Description            |
| ------ | ---------------------- | ---------------------- |
| POST   | `/signup`              | Register new user      |
| POST   | `/login`               | Login, get JWT token   |
| POST   | `/verify-email`        | Verify OTP code        |
| POST   | `/resend-verification` | Resend OTP             |
| POST   | `/forgot-password`     | Request password reset |
| POST   | `/reset-password`      | Reset with token       |
| GET    | `/me`                  | Get current user       |

### Integrations (`/api/v1/integrations`)

| Method | Endpoint                     | Description                        |
| ------ | ---------------------------- | ---------------------------------- |
| GET    | `/status`                    | Get all platform connection status |
| GET    | `/oauth/{platform}/init`     | Start OAuth flow                   |
| GET    | `/oauth/{platform}/callback` | OAuth callback                     |
| DELETE | `/{id}`                      | Disconnect integration             |
| PUT    | `/{id}/default-page`         | Set default page/org               |

### Content (`/api/v1/content`)

| Method | Endpoint           | Description                 |
| ------ | ------------------ | --------------------------- |
| POST   | `/create`          | Start content creation task |
| GET    | `/executions/{id}` | Get execution status        |
| GET    | `/scheduled`       | Get scheduled posts         |
| POST   | `/schedule`        | Schedule a post             |

### Documents (`/api/v1/documents`)

| Method | Endpoint  | Description             |
| ------ | --------- | ----------------------- |
| POST   | `/upload` | Upload document for RAG |
| GET    | `/`       | List documents          |
| DELETE | `/{id}`   | Delete document         |

---

## Celery Workers & Tasks

### Worker Configuration (`app/workers/__init__.py`)

```python
from celery import Celery

celery_app = Celery(
    "staffpilot",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Task routing
celery_app.conf.task_routes = {
    'app.workers.content_creation.*': {'queue': 'content'},
    'app.workers.scheduled_posts.*': {'queue': 'scheduled'},
    'app.workers.notifications.*': {'queue': 'notifications'},
}
```

### Key Tasks

| Task                             | Module                | Description                      |
| -------------------------------- | --------------------- | -------------------------------- |
| `process_content_creation_batch` | `content_creation.py` | Generate content + images/videos |
| `publish_scheduled_post`         | `scheduled_posts.py`  | Publish at scheduled time        |
| `process_document_ingestion`     | `ingestion.py`        | Process uploaded docs for RAG    |
| `send_email_task`                | `notifications.py`    | Send emails async                |

### Content Creation Flow

```
1. User Request → API endpoint → Creates AgentExecution
2. Celery Task starts:
   ├── Step 1: RAG Retrieval (query Pinecone)
   ├── Step 2: Keyword Research (SerpAPI)
   ├── Step 3: Content Generation (LLM)
   ├── Step 4: Image/Video Generation (Gemini)
   ├── Step 5: Upload to Cloudinary
   └── Step 6: Post to Social Platforms
3. Update AgentExecution status
```

---

## AI/LLM Integration

### Gemini Configuration

```python
# Models used
GOOGLE_MODEL_CONTENT = "gemini-2.5-flash"        # Text generation
GOOGLE_MODEL_IMAGE = "gemini-2.5-flash-image"    # Image generation
GOOGLE_MODEL_VIDEO = "veo-3.1-generate-preview"  # Video generation
GOOGLE_EMBEDDING_MODEL = "gemini-embedding-001"    # Embeddings
```

### Image Generation with Brand Context

```python
def _generate_image_prompt(
    platform: str,
    content: str,
    company_name: Optional[str] = None,
    brand_voice: Optional[str] = None,
    rag_context: Optional[str] = None
) -> str:
    """
    Generates prompts with:
    - Company name (exact spelling)
    - Brand voice/style
    - RAG context for product names
    - Platform-specific requirements
    """
```

---

## Vector Store & RAG

### Pinecone Setup

```python
# Environment variables
PINECONE_API_KEY=your-api-key
PINECONE_HOST=your-index-host.pinecone.io
PINECONE_INDEX_NAME=staffpilot

# Index configuration
EMBEDDING_DIMENSION = 768  # gemini-embedding-001
METRIC = "cosine"
```

### RAG Pipeline

1. **Document Upload** → PDF/DOCX parsed
2. **Chunking** → Split into ~500 token chunks
3. **Embedding** → Generate via Gemini embedding model
4. **Upsert** → Store in Pinecone with tenant_id filter
5. **Query** → Retrieve relevant chunks during content generation

---

## Social Media Integrations

### OAuth Flow

```
1. Frontend: GET /api/v1/integrations/oauth/{platform}/init
2. Backend: Generate state, store in Redis, return auth URL
3. User: Redirected to platform OAuth screen
4. Platform: Redirects to callback URL
5. Backend: Exchange code for tokens, fetch profile/pages
6. Database: Create/update SocialIntegration record
7. Frontend: Redirected with success/error status
```

### Posting Services (`app/services/integrations/social/`)

Each platform has a posting service:

```python
# Facebook
FacebookPostingService.post(
    content=text,
    access_token=page_token,
    page_id=page_id,
    media_urls=[urls],
    is_personal_account=False  # Fallback to personal if no pages
)

# Instagram (requires Facebook Page with linked IG)
InstagramPostingService.post(...)

# LinkedIn
LinkedInPostingService.post(...)

# Twitter/X
TwitterPostingService.post(...)

# TikTok
TikTokPostingService.post(...)
```

---

## Authentication & Authorization

### JWT Tokens

```python
# Token payload
{
    "sub": "user_uuid",
    "tenant_id": "tenant_uuid",
    "exp": expiration_timestamp
}

# Header
Authorization: Bearer <token>
```

### Multi-Tenancy

Every request includes `tenant_id`:

- Extracted from JWT token
- Used to filter all database queries
- Ensures data isolation

---

## Storage Configuration

### Cloudinary (Production)

```python
STORAGE_BACKEND=cloudinary
CLOUDINARY_CLOUD_NAME=your-cloud
CLOUDINARY_API_KEY=your-key
CLOUDINARY_API_SECRET=your-secret
```

### File Structure

```
cloudinary://{cloud_name}/
├── {tenant_id}/
│   ├── images/
│   │   └── generated_image_{timestamp}.png
│   ├── videos/
│   │   └── generated_video_{timestamp}.mp4
│   └── documents/
│       └── uploaded_doc.pdf
```

---

## Deployment

### Railway (Backend)

**Services deployed:**

1. **FastAPI Backend** - Main API server
2. **Celery Worker** - Background task processor
3. **Celery Beat** - Scheduled task scheduler
4. **PostgreSQL** - Database (Railway managed)
5. **Redis** - Cache + Celery broker (Railway managed)

**Deployment settings:**

```yaml
# Build command
pip install -r requirements.txt

# Start commands
# Backend:
uvicorn main:app --host 0.0.0.0 --port $PORT

# Celery Worker:
celery -A app.workers worker --loglevel=info

# Celery Beat:
celery -A app.workers beat --loglevel=info
```

**Environment Variables on Railway:**

- Copy all from `.env` file
- Update DATABASE_URL to Railway PostgreSQL URL
- Update REDIS_URL to Railway Redis URL
- Set FRONTEND_URL to Vercel deployment URL

### Vercel (Frontend)

**Settings:**

```json
// vercel.json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/" }]
}
```

**Environment Variables:**

```
NEXT_PUBLIC_API_URL=https://your-railway-backend.railway.app
```

**Build command:** `npm run build`
**Output directory:** `.next`

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 15 (or use Docker)
- Redis 7 (or use Docker)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp ENV_SETUP.md .env
# Edit .env with your values

# Start supporting services (Postgres + Redis)
docker-compose up -d db redis

# Run migrations
alembic upgrade head

# Start backend
uvicorn main:app --reload --port 8000

# In another terminal - start Celery worker
celery -A app.workers worker --loglevel=info

# In another terminal - start Celery beat
celery -A app.workers beat --loglevel=info
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start development server
npm run dev
```

### Using Docker Compose (Full Stack)

```bash
cd backend
docker-compose up --build
```

This starts: PostgreSQL, Redis, Backend, Celery Worker, Celery Beat

---

## Environment Variables

### Required Variables

| Variable           | Description                                       |
| ------------------ | ------------------------------------------------- |
| `DATABASE_URL`     | PostgreSQL connection string                      |
| `REDIS_URL`        | Redis connection string                           |
| `SECRET_KEY`       | JWT secret (generate with `openssl rand -hex 32`) |
| `GOOGLE_API_KEY`   | Gemini API key                                    |
| `PINECONE_API_KEY` | Pinecone vector DB key                            |
| `PINECONE_HOST`    | Pinecone index host URL                           |
| `CLOUDINARY_*`     | Cloudinary credentials                            |

### Social OAuth Variables

| Variable                    | Description                  |
| --------------------------- | ---------------------------- |
| `FACEBOOK_APP_ID/SECRET`    | Facebook OAuth app           |
| `INSTAGRAM_APP_ID/SECRET`   | Instagram (same as Facebook) |
| `LINKEDIN_CLIENT_ID/SECRET` | LinkedIn OAuth app           |
| `TWITTER_CLIENT_ID/SECRET`  | Twitter OAuth 2.0 app        |
| `TIKTOK_CLIENT_ID/SECRET`   | TikTok OAuth app             |

### Full list: See `backend/ENV_SETUP.md`

---

## Common Operations

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

### Celery Commands

```bash
# Start worker
celery -A app.workers worker --loglevel=info

# Start beat scheduler
celery -A app.workers beat --loglevel=info

# Monitor with Flower
celery -A app.workers flower --port=5555

# Purge all tasks
celery -A app.workers purge
```

### Testing Social Integrations

1. Set OAuth credentials in `.env`
2. Start backend with `--reload`
3. Go to `/dashboard/integrations` in frontend
4. Click "Connect" for desired platform
5. Complete OAuth flow
6. Check logs for any errors

### Adding New LLM Provider

1. Create `app/services/llm/new_provider.py`
2. Extend `BaseLLMService`
3. Implement required methods
4. Register in `factory.py`

---

## Troubleshooting

### Common Issues

| Issue                        | Solution                                  |
| ---------------------------- | ----------------------------------------- |
| "Redis connection refused"   | Start Redis or check REDIS_URL            |
| "Database connection failed" | Check DATABASE_URL, run migrations        |
| "OAuth callback failed"      | Check redirect URIs match in app settings |
| "Image generation failed"    | Verify GOOGLE_API_KEY has imagen access   |
| "Pinecone error"             | Check PINECONE_HOST is the full host URL  |

### Logs

```bash
# Backend logs
# Look for request/response details

# Celery worker logs
# Shows task execution, errors

# Railway logs
# railway logs --service <service-name>
```

---

## Contact & Support

- **Repository:** [Internal Git]
- **Documentation:** This file + `ENV_SETUP.md`
- **API Docs:** `http://localhost:8000/docs` (FastAPI Swagger)

---

_Last updated: January 2026_
