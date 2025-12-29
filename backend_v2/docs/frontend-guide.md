# Jamify Frontend Integration Guide

Complete guide for connecting a frontend application to the Jamify AI DJ backend.

## Quick Start

```typescript
// 1. Register/Login
const auth = await fetch('/api/v1/auth/login', { 
  method: 'POST', body: JSON.stringify({ email, password }), 
  credentials: 'include' 
});

// 2. Check onboarding
const status = await fetch('/api/v1/onboard/status', { credentials: 'include' });
if (!status.has_profile) { /* Show onboarding UI */ }

// 3. Start stream
const stream = await fetch('/api/v1/stream/start', { 
  method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrfToken }
});

// 4. Connect WebSocket
const ws = new WebSocket('/api/v1/ws');

// 5. Play audio
const audio = new Audio('/api/v1/stream');
audio.play();
```

---

## Authentication

All API calls require authentication. The backend uses **HttpOnly cookies** (preferred) + **CSRF tokens**.

### Register
```typescript
POST /api/v1/auth/register
{
  "email": "user@example.com",
  "password": "securepass123",
  "display_name": "Jamie"
}
```

### Login
```typescript
POST /api/v1/auth/login
{ "email": "...", "password": "..." }

// Response sets cookies: access_token, refresh_token, csrf_token
// Also returns tokens in body for API clients
```

### CSRF Protection
For state-changing requests (POST/PUT/PATCH/DELETE), include the CSRF token:
```typescript
headers: { 'X-CSRF-Token': getCookie('csrf_token') }
```

### Token Refresh
```typescript
POST /api/v1/auth/refresh
// Reads refresh_token from cookie, issues new tokens
```

### Logout
```typescript
POST /api/v1/auth/logout
// Clears all auth cookies
```

---

## Onboarding (Voice Profile)

Users must complete voice onboarding before streaming.

### Check Status
```typescript
GET /api/v1/onboard/status
// Response: { has_profile: boolean, conversation_hint: string }
```

### Get Widget URL
```typescript
GET /api/v1/onboard/start
// Response: { signed_url, agent_id, user_id }
```

### Embed Widget
```html
<elevenlabs-convai 
  agent-id="AGENT_ID"
  dynamic-variables='{"user_id":"USER_UUID"}'
></elevenlabs-convai>
<script src="https://elevenlabs.io/convai-widget/index.js" async></script>
```

---

## Streaming

### Start Stream
```typescript
POST /api/v1/stream/start
{ "mood_id": "uuid", "context_name": "workout" }  // Both optional

// Response: { session_id, stream_url, ws_url, now_playing }
```

**Error 409**: User needs onboarding first
```json
{ "detail": { "code": "onboarding_required", "next": "/api/v1/onboard/start" } }
```

### Get Status
```typescript
GET /api/v1/stream/status
// Response: { session_id, active, now_playing, started_at }
```

### Stop Stream
```typescript
POST /api/v1/stream/stop
```

### Play Audio
```typescript
const audio = new Audio('/api/v1/stream');
audio.crossOrigin = 'use-credentials'; // Enable cookie auth
audio.play();
```

**Important**: The stream is an MP3 stream that requires cookie authentication.

---

## WebSocket Events

Connect to `/api/v1/ws` for real-time updates.

### Connection
```typescript
const ws = new WebSocket(`${baseUrl.replace('http', 'ws')}/api/v1/ws`);
// Cookie auth is automatic
```

### Event Format
```json
{
  "v": 1,
  "type": "event_type",
  "data": { ... },
  "ts": "2025-12-21T00:00:00Z"
}
```

### Event Types

| Event | Data | Description |
|-------|------|-------------|
| `connected` | `{ user_id, message }` | Connection established |
| `now_playing` | `{ song_uuid, title, artist, artwork_url }` | Song changed |
| `segment_ready` | `{ segment_index, duration_sec, song_uuid }` | New audio segment |
| `dj_says` | `{ script }` | DJ speech text (for UI display) |
| `decision_trace` | `{ agent, decision, rationale }` | AI decision (debug) |
| `stream_status` | `{ status, session_id }` | Stream started/stopped |
| `pong` | `{}` | Keepalive response |

### Sending Messages
```typescript
ws.send(JSON.stringify({ type: 'ping', data: {} }));
ws.send(JSON.stringify({ type: 'get_status', data: {} }));
```

---

## Moods

Moods control the music selection algorithm (energy, genres, DJ personality).

### List Moods
```typescript
GET /api/v1/moods
// Response: [{ id, name, color, energy_target, valence_target, genres, dj_personality, is_default }]
```

### Create Mood
```typescript
POST /api/v1/moods
{
  "name": "Workout",
  "color": "#FF5733",
  "energy_target": 0.9,
  "valence_target": 0.7,
  "genres": ["edm", "hip-hop"],
  "dj_personality": "hype_energetic",
  "is_default": false
}
```

### Update Mood
```typescript
PATCH /api/v1/moods/{id}
{ "energy_target": 0.8 }  // Partial update
```

### Delete Mood
```typescript
DELETE /api/v1/moods/{id}
```

### Set Default
```typescript
POST /api/v1/moods/{id}/set-default
```

---

## Contexts

Contexts provide additional personalization (e.g., workout mode, party mode).

### CRUD Operations
```typescript
GET    /api/v1/contexts                  // List all
POST   /api/v1/contexts                  // Create
GET    /api/v1/contexts/{name}           // Get by name
PUT    /api/v1/contexts/{name}           // Update
DELETE /api/v1/contexts/{name}           // Delete
```

### Create Context
```typescript
{
  "name": "workout",
  "raw_text": "High energy music for gym sessions. No slow songs."
}
```

---

## Feedback

Provide like/dislike feedback to train the AI.

### Submit Feedback
```typescript
POST /api/v1/feedback
{
  "song_uuid": "uuid",
  "track_title": "Song Name",
  "track_artist": "Artist Name",
  "mood_id": "uuid",           // Optional
  "value": "like",             // "like" | "dislike" | "skip"
  "reason_text": "Great beat!" // Optional
}
```

### List Feedback
```typescript
GET /api/v1/feedback?mood_id=xxx&limit=50
```

---

## User Profile

### Get Current User
```typescript
GET /api/v1/me
// Response: { id, email, display_name, created_at }
```

---

## Agent Settings (Advanced)

Customize AI agent behavior per-user.

### List Settings
```typescript
GET /api/v1/agent-settings
```

### Update Agent
```typescript
PUT /api/v1/agent-settings/{agent_name}
{ "settings_json": "{\"thinking_budget\": 3000, \"temperature\": 0.8}" }
```

**Agent Names**: `track_selector`, `transition_planner`, `speech_writer`, `download_planner`

---

## Complete React Integration Example

```tsx
// hooks/useJamify.ts
import { useState, useEffect, useRef, useCallback } from 'react';

interface NowPlaying {
  title: string;
  artist: string;
  artwork_url?: string;
}

export function useJamify() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [djScript, setDjScript] = useState<string>('');
  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Connect WebSocket
  useEffect(() => {
    const ws = new WebSocket('/api/v1/ws');
    
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      
      switch (msg.type) {
        case 'now_playing':
          setNowPlaying(msg.data);
          break;
        case 'dj_says':
          setDjScript(msg.data.script);
          break;
        case 'stream_status':
          setIsStreaming(msg.data.status === 'started');
          break;
      }
    };
    
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  // Start streaming
  const startStream = useCallback(async (moodId?: string) => {
    const res = await fetch('/api/v1/stream/start', {
      method: 'POST',
      credentials: 'include',
      headers: { 
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCookie('csrf_token') 
      },
      body: JSON.stringify({ mood_id: moodId }),
    });
    
    if (res.status === 409) {
      throw new Error('ONBOARDING_REQUIRED');
    }
    
    if (!res.ok) throw new Error('Failed to start stream');
    
    // Start audio playback
    const audio = new Audio('/api/v1/stream');
    audio.play();
    audioRef.current = audio;
    setIsStreaming(true);
  }, []);

  // Stop streaming
  const stopStream = useCallback(async () => {
    await fetch('/api/v1/stream/stop', { 
      method: 'POST', 
      credentials: 'include',
      headers: { 'X-CSRF-Token': getCookie('csrf_token') }
    });
    
    audioRef.current?.pause();
    setIsStreaming(false);
  }, []);

  // Submit feedback
  const submitFeedback = useCallback(async (
    songUuid: string, 
    value: 'like' | 'dislike' | 'skip'
  ) => {
    await fetch('/api/v1/feedback', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCookie('csrf_token'),
      },
      body: JSON.stringify({ song_uuid: songUuid, value }),
    });
  }, []);

  return { 
    isStreaming, 
    nowPlaying, 
    djScript, 
    startStream, 
    stopStream,
    submitFeedback,
  };
}

function getCookie(name: string): string {
  return document.cookie.match(`(^|;)\\s*${name}\\s*=\\s*([^;]+)`)?.pop() || '';
}
```

---

## Error Handling

| Status | Meaning | Action |
|--------|---------|--------|
| 400 | Validation error | Check request body |
| 401 | Not authenticated | Redirect to login |
| 403 | CSRF token invalid | Refresh page, get new token |
| 404 | Resource not found | Handle gracefully |
| 409 | Onboarding required | Redirect to onboarding |
| 503 | Server at capacity | Show "try again later" |

---

## Environment Setup

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Configure fetch defaults
const api = (path: string, options: RequestInit = {}) => 
  fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
```
