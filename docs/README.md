# Jamify - AI DJ

A personalized AI DJ that creates continuous mixes tailored to your music taste.

## Architecture

```
frontend/          # React + Vite + TypeScript PWA
backend_v2/        # FastAPI async backend
  ├── api/         # REST endpoints
  ├── models/      # SQLAlchemy models
  ├── services/    # Business logic
  ├── orchestration/  # Audio pipeline
  └── integrations/   # External APIs (Deezer, etc)
```

## Quick Start

### Backend

```bash
cd backend_v2
pip install -r ../requirements.txt
uvicorn backend_v2.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment

Copy `.env.example` to `.env` and configure:
- `ELEVENLABS_API_KEY` - For voice onboarding
- `ONBOARD_TOOL_SECRET` - Webhook security
- Database and auth settings

## Features

- 🎙️ Voice onboarding with ElevenLabs
- 🎵 5 personalized moods (Flow, Energy, Chill, Party, Late Night)
- 🎧 Continuous audio streaming
- 📊 Feedback-based learning
- 🎤 AI DJ commentary
