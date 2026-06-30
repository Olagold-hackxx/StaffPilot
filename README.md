# StaffPilot — AI-Powered Social Media Management Platform

StaffPilot (codenamed *Buzz / AIConnect*) is a full-stack SaaS platform that lets marketing teams generate, schedule, and publish AI-crafted social media content across every major platform — all from a single dashboard.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Full Stack with Docker Compose](#full-stack-with-docker-compose)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Background Workers](#background-workers)
- [AI & LLM Integration](#ai--llm-integration)
- [Social Media Integrations](#social-media-integrations)
- [RAG Pipeline](#rag-pipeline)
- [Deployment](#deployment)
- [Database Migrations](#database-migrations)
- [Troubleshooting](#troubleshooting)

---

## Overview

StaffPilot reduces the manual overhead of social media marketing by combining:

- **Multi-provider AI generation** — text, images, and video via Gemini, OpenAI, or Claude
- **One-click publishing** — to Facebook, Instagram, LinkedIn, Twitter/X, and TikTok
- **Brand-aware RAG** — upload company documents and have the AI reference them accurately
- **Campaign management** — plan, track, and report on advertising campaigns
- **Multi-tenant SaaS** — each organization is fully isolated via JWT-scoped tenancy

---

## Key Features

| Feature | Description |
|---|---|
| AI Content Generation | Text posts created by Gemini, GPT-4, or Claude with your brand voice |
| AI Image & Video Generation | Platform-sized images via Gemini Imagen 4; short-form video via Veo 3 |
| Post Scheduling | Queue posts and have Celery Beat publish them automatically |
| RAG Knowledge Base | Upload PDFs/DOCX files; content generation is grounded in your documents |
| Social OAuth | OAuth 2.0 flows for Facebook, Instagram, LinkedIn, Twitter/X, TikTok |
| Ad Campaign Management | Create and manage campaigns across Google Ads and Meta Ads |
| SEO Keyword Research | Keyword data pulled via SerpAPI during content planning |
| Analytics Dashboard | Performance metrics and content analytics across platforms |
| AI Chat Assistants | Configurable assistants (Digital Marketer, Customer Support) per tenant |
| Multi-tenancy | JWT tokens carry `tenant_id`; every query is tenant-scoped |
| Stripe Billing | Subscription management and payment flows |
| Media Storage | Cloudinary in production; local and S3 backends also supported |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                 Frontend (Vercel)                            │
│            Next.js 15 · React 19 · TailwindCSS              │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTPS
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   Railway Platform                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ FastAPI API  │  │ Celery Worker│  │  Celery Beat      │  │
│  │  (main.py)   │  │  (tasks)     │  │  (scheduler)      │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │
│         └─────────────────┴──────────────────-─┘             │
│                            │                                 │
│              ┌─────────────┴─────────────┐                  │
│              │     PostgreSQL 15          │                  │
│              └───────────────────────────┘                  │
│              ┌───────────────────────────┐                  │
│              │   Redis 7 (cache/broker)  │                  │
│              └───────────────────────────┘                  │
└──────────────────────────────────────────────────────────────┘

External Services
────────────────
Pinecone (vectors)   Cloudinary (media)    Google AI (Gemini)
Stripe (billing)     SerpAPI (SEO)         Gmail SMTP (email)
Facebook Graph API   Instagram Graph API   LinkedIn API
Twitter/X API        TikTok API            Google Ads API
Meta Ads API
```

---

## Tech Stack

### Backend

| Layer | Technology | Version |
|---|---|---|
| Framework | FastAPI | ≥ 0.109 |
| Server | Uvicorn | ≥ 0.24 |
| Database | PostgreSQL | 15 |
| ORM | SQLAlchemy (async) | 2.0.23 |
| Migrations | Alembic | 1.12 |
| Task Queue | Celery | 5.3 |
| Broker / Cache | Redis | 7 |
| Auth | python-jose (JWT) | 3.3 |
| AI Orchestration | LangChain / LangGraph | 0.1 / 0.0.20 |
| Vector Store | Pinecone | latest |
| Media Storage | Cloudinary | latest |

### Frontend

| Layer | Technology | Version |
|---|---|---|
| Framework | Next.js (App Router) | 15.5 |
| UI Library | React | 19.2 |
| Styling | TailwindCSS | 4.x |
| Components | Radix UI | latest |
| Forms | React Hook Form + Zod | latest |
| Charts | Recharts | 2.15 |
| Animation | Framer Motion | latest |
| Payments | Stripe.js | latest |

---

## Project Structure

```
buzz/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # Route handlers
│   │   │   ├── auth.py
│   │   │   ├── tenants.py
│   │   │   ├── assistants.py
│   │   │   ├── campaigns.py
│   │   │   ├── chat.py
│   │   │   ├── documents.py
│   │   │   ├── integrations.py
│   │   │   ├── billing.py
│   │   │   ├── capabilities.py
│   │   │   ├── agents.py
│   │   │   └── scheduled_posts.py
│   │   │
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── tenant.py
│   │   │   ├── assistant.py
│   │   │   ├── integration.py
│   │   │   ├── content.py
│   │   │   ├── campaign.py
│   │   │   ├── document.py
│   │   │   ├── conversation.py
│   │   │   ├── agent_execution.py
│   │   │   └── brand_asset.py
│   │   │
│   │   ├── services/
│   │   │   ├── llm/             # Multi-provider LLM factory
│   │   │   │   ├── base.py
│   │   │   │   ├── gemini.py
│   │   │   │   ├── openai.py
│   │   │   │   ├── anthropic.py
│   │   │   │   └── factory.py
│   │   │   │
│   │   │   ├── integrations/
│   │   │   │   ├── social/      # Per-platform posting services
│   │   │   │   │   ├── facebook.py
│   │   │   │   │   ├── instagram.py
│   │   │   │   │   ├── linkedin.py
│   │   │   │   │   ├── twitter.py
│   │   │   │   │   └── tiktok.py
│   │   │   │   ├── ads/         # Google Ads, Meta Ads
│   │   │   │   └── seo/         # SerpAPI
│   │   │   │
│   │   │   ├── storage/         # Cloudinary / S3 / local
│   │   │   ├── vector_store.py  # Pinecone
│   │   │   ├── rag_service.py
│   │   │   ├── ocr_service.py
│   │   │   └── email_service.py
│   │   │
│   │   ├── workers/             # Celery async tasks
│   │   │   ├── content_creation.py
│   │   │   ├── campaign_creation.py
│   │   │   ├── scheduled_posts.py
│   │   │   ├── ingestion.py
│   │   │   └── notifications.py
│   │   │
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── db/                  # Session & base config
│   │   ├── utils/               # Auth, errors, logging
│   │   └── config.py
│   │
│   ├── migrations/              # Alembic migration scripts
│   ├── main.py                  # FastAPI app entry point
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── Dockerfile.celery
│   ├── Dockerfile.celerybeat
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   │   ├── (dashboard)/dashboard/
│   │   │   ├── page.tsx         # Overview
│   │   │   ├── analytics/
│   │   │   ├── assistants/
│   │   │   ├── brand-assets/
│   │   │   ├── campaigns/
│   │   │   ├── chat/
│   │   │   ├── content/
│   │   │   ├── documents/
│   │   │   ├── integrations/
│   │   │   └── settings/
│   │   ├── login/  signup/  register/
│   │   ├── onboarding/
│   │   ├── pricing/  payment/
│   │   └── api/chat/route.ts    # Edge AI chat route
│   │
│   ├── components/
│   │   └── ui/                  # Radix UI primitives (shadcn/ui)
│   └── lib/
│
└── chromadb/                    # Standalone ChromaDB service (Railway)
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- A Pinecone account and index (dimension 768, cosine metric)
- A Cloudinary account
- A Google AI Studio API key (Gemini)

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp ENV_SETUP.md .env
# Edit .env with your credentials (see Environment Variables section)

# Start PostgreSQL and Redis via Docker
docker-compose up -d db redis

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn main:app --reload --port 8000

# In a second terminal — start the Celery worker
celery -A app.workers worker --loglevel=info

# In a third terminal — start the Celery beat scheduler
celery -A app.workers beat --loglevel=info
```

API docs are available at `http://localhost:8000/docs`.

### Frontend Setup

```bash
cd frontend

npm install

# Point the frontend at the local backend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
```

App runs at `http://localhost:3000`.

### Full Stack with Docker Compose

```bash
cd backend
docker-compose up --build
```

Starts PostgreSQL, Redis, the FastAPI backend, a Celery worker, and Celery beat together. The backend mounts the source directory so hot-reload is active.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | `redis://host:6379/0` |
| `CELERY_BROKER_URL` | `redis://host:6379/1` |
| `CELERY_RESULT_BACKEND` | `redis://host:6379/2` |
| `SECRET_KEY` | JWT signing secret (`openssl rand -hex 32`) |
| `GOOGLE_API_KEY` | Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key (optional) |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional) |
| `PINECONE_API_KEY` | Pinecone API key |
| `PINECONE_HOST` | Full Pinecone index host URL |
| `PINECONE_INDEX_NAME` | Pinecone index name |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `SERPAPI_API_KEY` | SerpAPI key for SEO research |
| `FRONTEND_URL` | Frontend base URL (CORS + redirects) |
| `GMAIL_USER` | Gmail address for outgoing email |
| `GMAIL_APP_PASSWORD` | Gmail app password |

### Social OAuth Variables

| Variable | Platform |
|---|---|
| `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET` | Facebook & Instagram |
| `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | LinkedIn |
| `TWITTER_CLIENT_ID` / `TWITTER_CLIENT_SECRET` | Twitter/X (OAuth 2.0) |
| `TWITTER_API_KEY` / `TWITTER_API_SECRET` | Twitter/X (OAuth 1.0a for media) |
| `TIKTOK_CLIENT_ID` / `TIKTOK_CLIENT_SECRET` | TikTok |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend base URL |

Full reference: `backend/ENV_SETUP.md`

---

## API Reference

Interactive Swagger docs: `GET /docs` | ReDoc: `GET /redoc`

### Authentication — `/api/v1/auth`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/signup` | Register a new user |
| POST | `/login` | Authenticate and receive JWT |
| POST | `/verify-email` | Verify OTP sent to email |
| POST | `/resend-verification` | Resend verification OTP |
| POST | `/forgot-password` | Request password-reset link |
| POST | `/reset-password` | Reset password with token |
| GET | `/me` | Get current authenticated user |

### Integrations — `/api/v1/integrations`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/status` | All platform connection statuses |
| GET | `/oauth/{platform}/init` | Start OAuth flow |
| GET | `/oauth/{platform}/callback` | OAuth callback handler |
| DELETE | `/{id}` | Disconnect a platform |
| PUT | `/{id}/default-page` | Set default page/org for a platform |

### Campaigns — `/api/v1/campaigns`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/` | Create a new campaign |
| GET | `/` | List all campaigns |
| GET | `/{id}` | Get campaign details |
| PUT | `/{id}` | Update campaign |
| DELETE | `/{id}` | Delete campaign |

### Documents — `/api/v1/documents`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/upload` | Upload a PDF or DOCX for RAG |
| GET | `/` | List uploaded documents |
| DELETE | `/{id}` | Delete document and its vectors |

### Assistants — `/api/v1/assistants`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/` | Create an AI assistant |
| GET | `/` | List assistants for tenant |
| PUT | `/{id}` | Update assistant config |
| DELETE | `/{id}` | Delete assistant |

---

## Background Workers

Celery handles all long-running operations asynchronously.

| Task | Module | Description |
|---|---|---|
| `process_content_creation_batch` | `content_creation.py` | Generate text + image/video, upload, and post |
| `publish_scheduled_post` | `scheduled_posts.py` | Publish queued posts at their scheduled time |
| `process_document_ingestion` | `ingestion.py` | Parse, chunk, embed, and upsert documents into Pinecone |
| `send_email_task` | `notifications.py` | Send emails asynchronously |

### Content Creation Flow

```
User request → API creates AgentExecution record
                │
                └─► Celery task:
                      1. RAG retrieval (Pinecone query)
                      2. SEO keyword research (SerpAPI)
                      3. Text generation (LLM)
                      4. Image/video generation (Gemini Imagen / Veo)
                      5. Upload media to Cloudinary
                      6. Publish to social platforms
                      7. Update AgentExecution status
```

### Celery Commands

```bash
# Worker
celery -A app.workers worker --loglevel=info

# Beat scheduler
celery -A app.workers beat --loglevel=info

# Monitor with Flower (runs on port 5555)
celery -A app.workers flower --port=5555

# Purge all pending tasks
celery -A app.workers purge
```

---

## AI & LLM Integration

The LLM layer is provider-agnostic. A factory pattern selects the active provider from the `DEFAULT_LLM_PROVIDER` setting.

```python
from app.services.llm.factory import create_llm_service

llm = create_llm_service()               # uses default
llm = create_llm_service("gemini")       # explicit: gemini | openai | anthropic

await llm.generate_content(prompt, context)
await llm.generate_image(prompt, aspect_ratio="1:1")
await llm.generate_video(prompt, duration_seconds=30)
await llm.generate_embedding(text)
```

### Models in Use

| Task | Model |
|---|---|
| Text generation | `gemini-2.5-flash` |
| Image generation | Gemini Imagen 4 (`imagen-4.0`) |
| Video generation | Google Veo 3 (`veo-3.1-generate-preview`) |
| Embeddings | `gemini-embedding-001` (768 dimensions) |

### Adding a New LLM Provider

1. Create `app/services/llm/new_provider.py` extending `BaseLLMService`
2. Implement `generate_content`, `generate_embedding`, and optionally `generate_image`
3. Register it in `app/services/llm/factory.py`

---

## Social Media Integrations

### OAuth Flow

```
1. Frontend calls  GET /api/v1/integrations/oauth/{platform}/init
2. Backend generates OAuth state, stores it in Redis, returns auth URL
3. User is redirected to the platform's consent screen
4. Platform redirects to the callback URL with an auth code
5. Backend exchanges the code for access/refresh tokens
6. SocialIntegration record is created/updated in PostgreSQL
7. Frontend is redirected with a success or error query param
```

Supported platforms: **Facebook**, **Instagram**, **LinkedIn**, **Twitter/X**, **TikTok**

### Posting

Each platform has a dedicated posting service under `app/services/integrations/social/`. All services accept the same interface: `post(content, access_token, media_urls, ...)`.

---

## RAG Pipeline

Document knowledge is stored in Pinecone and retrieved at generation time to ground AI output in company-specific facts.

```
Upload → Parse (PDF/DOCX) → Chunk (~500 tokens)
       → Embed (gemini-embedding-001)
       → Upsert to Pinecone (namespaced by tenant_id)

Generate → Query Pinecone with prompt embedding
         → Retrieve top-k chunks
         → Inject as context into LLM prompt
```

Pinecone index requirements: **dimension 768**, **cosine metric**.

---

## Deployment

### Backend — Railway

Deploy three separate Railway services from the `backend/` directory:

| Service | Start Command |
|---|---|
| API | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Celery Worker | `celery -A app.workers worker --loglevel=info` |
| Celery Beat | `celery -A app.workers beat --loglevel=info` |

Railway also provisions **PostgreSQL 15** and **Redis 7** as managed services. Set `DATABASE_URL` and `REDIS_URL` to the Railway-provided connection strings.

### Frontend — Vercel

Connect the `frontend/` directory to a Vercel project. Required environment variable:

```
NEXT_PUBLIC_API_URL=https://your-railway-backend.up.railway.app
```

The `frontend/vercel.json` rewrite rule handles client-side routing.

---

## Database Migrations

```bash
# Generate a new migration from model changes
alembic revision --autogenerate -m "describe the change"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Check current migration state
alembic current
```

Migration scripts live in `backend/migrations/versions/`.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Redis connection refused` | Redis not running | `docker-compose up -d redis` or check `REDIS_URL` |
| `Database connection failed` | PostgreSQL down or wrong URL | Check `DATABASE_URL`; run `alembic upgrade head` |
| OAuth callback returns error | Redirect URI mismatch | Ensure callback URL matches the registered URI in the platform's developer console |
| Image generation fails | Gemini key lacks Imagen access | Request Imagen API access in Google AI Studio |
| Pinecone upsert fails | Wrong host or index name | `PINECONE_HOST` must be the full host URL, not just the region |
| Celery tasks never execute | Worker not running | Start `celery -A app.workers worker` |
| Email not delivered | App password invalid | Use a Gmail App Password (not your account password) |

---

## License

Private — all rights reserved.
