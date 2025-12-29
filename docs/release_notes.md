# Release Notes - December 2024

## Overview

This release brings significant improvements to the Jamify AI DJ experience, focusing on real-time feedback, audio performance, and production deployment readiness.

---

## 🎵 Status Events + UX Overhaul

### Real-Time Stage Updates
The app now shows what the AI is doing in real-time during mood generation and playback:
- **Generating intro** → **Downloading songs** → **Mixing** → **Playing**
- Error states display with friendly messages and retry options

### Backend Event System
- New `StatusEventLog` model persists events to database
- Events correlated with LLM traces for debugging
- WebSocket events include version (`v: 1`), type, timestamp, and deduplication IDs

### Frontend Integration
- `PlayerProvider` subscribes to WebSocket events
- Stage indicators on VoiceOnboardingPage and PlayerPage
- Automatic reconnection with event replay (last 60 seconds)
- Client-side deduplication prevents duplicate toasts

### MediaSession API
- Now Playing info displayed in OS media controls (Windows, Android)
- Play/pause/skip controls work from lock screen and notification shade
- Artwork shown in media controls (when available)

---

## ⚡ Phase 1 Audio Performance

### Profiling & Optimization
- Identified and resolved FFmpeg subprocess bottlenecks
- Reduced segment render time with smarter audio processing
- Memory-efficient chunk streaming for long mixes

### Caching Layer
- `MediaCache` with expiry and LRU eviction
- Songs cached after download to avoid re-fetching
- Intro audio pre-generated and cached per mood

### Seeking Support (Groundwork)
- Segment metadata includes `handoff_at` timestamps
- Frontend tracks playback position for future seek implementation

### Test Coverage
- `test_mix_performance.py` - benchmarks for mix rendering
- `test_stream_integration.py` - WebSocket and pipeline tests
- `test_backend_v2.py` - auth, moods, contexts integration

---

## 🌐 Production-Like Local Serving

### Single-Origin Mode
Built frontend now served by backend on port 5173:
```powershell
$env:SERVE_FRONTEND="true"
uvicorn backend_v2.main:app --port 5173
```

### Benefits
- No CORS issues (frontend + API on same origin)
- Matches production Cloudflare tunnel setup
- Proper cache headers for hashed assets
- SPA fallback for client-side routing

### Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `SERVE_FRONTEND` | `false` | Enable frontend serving |
| `FRONTEND_DIST_DIR` | `../frontend/dist` | Path to built frontend |
| `APP_PORT` | `8000` (or `5173` if SERVE_FRONTEND) | Server bind port |

---

## 📱 PWA Improvements

### Service Worker
- Precaches static assets (JS, CSS, HTML, icons)
- Network-only for API routes (no stale data)
- Network-only for audio streams (no caching live audio)

### Install Experience
- Add to Home Screen works on iOS Safari and Chrome
- Standalone display mode with custom theme color
- App icon with maskable variant for Android

### Known Limitations (iOS)
| Limitation | Workaround |
|------------|------------|
| No background audio | "Tap to Resume" sheet shown on return |
| Limited MediaSession | Basic now-playing info works |
| No push notifications | Polling or passive updates only |

---

## 📁 Files Changed

### New Files
- `backend_v2/spa_serving.py` - SPA static file middleware
- `docs/ship_checklist.md` - Dev and prod-like testing workflows
- `docs/release_notes.md` - This file

### Modified Files
- `backend_v2/config.py` - Added `SERVE_FRONTEND`, `FRONTEND_DIST_DIR`, `APP_PORT`
- `backend_v2/main.py` - Conditional SPA middleware mount
- `frontend/vite.config.ts` - PWA config, code splitting

---

## 🔜 Coming Next

- **Phase 2 Audio**: Crossfade improvements, dynamic transitions
- **Seeking**: Jump to position in current segment
- **History**: View and replay past mixes
- **Sharing**: Share mood links with friends
