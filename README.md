# Jamify - AI DJ

A personalized AI DJ that creates continuous mixes tailored to your music taste. Built with FastAPI, React, and ElevenLabs voice integration.

## 🎵 Features

- 🎙️ **Voice Onboarding** - Natural conversation with ElevenLabs AI to discover your music preferences
- 🎵 **5 Personalized Moods** - Flow, Energy, Chill, Party, and Late Night moods tailored to you
- 🎧 **Continuous Audio Streaming** - Seamless mixes with intelligent transitions
- 📊 **Feedback-Based Learning** - Like/dislike tracks to improve recommendations
- 🎤 **AI DJ Commentary** - Personalized introductions and transitions
- 🌐 **Global Catalog** - Access to millions of tracks via Deezer integration
- 📱 **PWA Support** - Install as a native app on iOS and Android

## 🏗️ Architecture

```
frontend/              # React + Vite + TypeScript PWA
backend_v2/            # FastAPI async backend
  ├── api/             # REST endpoints & WebSocket
  ├── models/          # SQLAlchemy database models
  ├── services/        # Business logic (mood generation, acquisition, etc.)
  ├── orchestration/   # Audio pipeline & mixing
  ├── integrations/    # External APIs (Deezer, ElevenLabs, OpenRouter)
  ├── catalog/         # Track selection & diversity ranking
  └── streaming/       # Real-time audio streaming
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL (or SQLite for development)

### Backend Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys and database URL

# Run database migrations
cd backend_v2
alembic upgrade head

# Start the backend server
uvicorn backend_v2.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Production Build

```bash
# Build frontend
cd frontend
npm run build

# Serve with backend (set SERVE_FRONTEND=true)
cd ../backend_v2
SERVE_FRONTEND=true uvicorn backend_v2.main:app --port 8000
```

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# ElevenLabs (required for voice onboarding)
ELEVENLABS_API_KEY=your_key_here
ONBOARD_TOOL_SECRET=your_secret_here

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/ai_dj

# OpenRouter (for LLM features)
OPENROUTER_API_KEY=your_key_here

# CORS (for development)
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern async web framework
- **SQLAlchemy** - ORM with Alembic migrations
- **WebSocket** - Real-time status events
- **Deezer API** - Music catalog & metadata
- **ElevenLabs** - Voice AI for onboarding
- **OpenRouter** - LLM API gateway

### Frontend
- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool & dev server
- **Tailwind CSS** - Styling
- **Framer Motion** - Animations
- **Radix UI** - Accessible components
- **Howler.js** - Audio playback
- **PWA** - Service worker & offline support

## 📁 Project Structure

```
ai-djv2/
├── backend_v2/          # Python backend
│   ├── api/             # API routes
│   ├── models/          # Database models
│   ├── services/        # Business logic
│   ├── orchestration/   # Audio mixing pipeline
│   ├── integrations/     # External APIs
│   └── migrations/      # Database migrations
├── frontend/            # React frontend
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── pages/       # Page components
│   │   ├── hooks/       # Custom hooks
│   │   └── lib/         # Utilities
│   └── public/          # Static assets
├── docs/                # Documentation
└── e2e/                 # End-to-end tests
```

## 🧪 Development

### Running Tests

```bash
# Backend tests
cd backend_v2
pytest

# Frontend tests
cd frontend
npm test
```

### Database Migrations

```bash
cd backend_v2

# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 📚 Documentation

### Core Documentation
- [API Documentation](docs/README.md) - API endpoints and usage
- [Implementation Complete](docs/IMPLEMENTATION_COMPLETE.md) - Backend mood & track redesign
- [Release Notes](docs/release_notes.md) - Latest features and improvements

### Fixes & Issues
- [Fixes Summary](docs/FIXES_SUMMARY.md) - Onboarding fixes (FK constraint, redirect loop)
- [Mood Diversity Fix](docs/MOOD_DIVERSITY_FIX_SUMMARY.md) - Mood similarity resolution
- [Stream Startup Fix](docs/stream_startup_fix.md) - Audio buffering improvements
- [Voice Onboarding Fix](docs/voice_onboarding_fix.md) - iOS PWA connection stability
- [Known Issues](docs/issues.md) - Current backend issues and suggested fixes
- [GitHub Issues Template](docs/github-issues.md) - Ready-to-create GitHub issues

### Development Guides
- [Ship Checklist](docs/ship_checklist.md) - Pre-deployment checklist
- [Frontend Guide](backend_v2/docs/frontend-guide.md) - Frontend development guide

## 🐛 Known Issues

### Critical Issues (Need Immediate Fix)

1. **HistoryItem dict access error** - `HistoryItem` is a dataclass but code uses `.get()` method
   - Location: `backend_v2/orchestration/agents.py:543-552`
   - Impact: Catalog selection crashes when history is non-empty
   - See [issues.md](docs/issues.md#critical) for details

2. **Missing state argument in fallback** - `select_track()` called without required `state` argument
   - Location: `backend_v2/orchestration/agents.py:582`
   - Impact: TypeError when catalog flow falls back
   - See [issues.md](docs/issues.md#critical) for details

3. **Invalid song features access** - `song.features[0]` used but features is not a list
   - Location: `backend_v2/orchestration/agents.py:630-633`
   - Impact: Crash after successful acquisition
   - See [issues.md](docs/issues.md#critical) for details

### High Priority Issues

4. **Selected song missing features dict** - Features at top level instead of nested
   - Location: `backend_v2/orchestration/agents.py:625-635`
   - Impact: Transition planning loses feature data

5. **Genres/tags as JSON strings** - Stored as JSON but treated as lists
   - Location: `backend_v2/services/preference_bundle.py:952-960`
   - Impact: Genre filtering silently fails

6. **Explicit lyrics filtering never triggers** - `explicit` field missing from song dict
   - Location: `backend_v2/services/preference_bundle.py:747-753`
   - Impact: Users can't avoid explicit tracks

For complete list and suggested fixes, see [docs/issues.md](docs/issues.md).

## ✅ Recent Fixes

### December 2024
- ✅ **Onboarding FK Constraint** - Removed foreign key constraint on `llm_trace.session_id` to allow pre-generation
- ✅ **Infinite Redirect Loop** - Fixed stale auth state after mood generation
- ✅ **Mood Diversity** - Sequential intro generation prevents download conflicts
- ✅ **Stream Startup Silence** - Bounded silence mode prevents audio backlog
- ✅ **iOS PWA Voice Connection** - WebRTC fallback for WebSocket failures

See [FIXES_SUMMARY.md](docs/FIXES_SUMMARY.md) and [release_notes.md](docs/release_notes.md) for details.

## 🎯 Recent Features

### Status Events & Real-Time Updates
- Real-time stage indicators during mood generation and playback
- WebSocket events with versioning and deduplication
- MediaSession API integration for OS media controls

### Global Catalog Integration
- Access to millions of tracks via Deezer API
- MMR (Maximal Marginal Relevance) diversity ranking
- Intent-based acquisition with multi-provider fallback

### Production Features
- Single-origin serving mode (frontend + API)
- PWA support with service worker
- Production-like local testing

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Add tests if applicable
4. Submit a pull request

## 📄 License

[Add your license here]

## 🔗 Links

- [Backend API Docs](http://localhost:8000/docs) (when running)
- [Frontend Dev Server](http://localhost:5173) (when running)
- [GitHub Repository](https://github.com/armoordonjamie-sketch/ai-djv2)
