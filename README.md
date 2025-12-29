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

- [API Documentation](docs/README.md)
- [Implementation Notes](docs/IMPLEMENTATION_COMPLETE.md)
- [Frontend Guide](docs/frontend-guide.md)

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
