# Backend v2 API Reference

> **Base URL**: `https://jamify.jamiearmoordon.co.uk/api/v1`
> **Authentication**: HttpOnly cookies (preferred) or Bearer token
> **CSRF**: Required for POST/PUT/PATCH/DELETE via `X-CSRF-Token` header

---

## Authentication

### POST /auth/register
Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepass123",
  "display_name": "John Doe"
}
```

**Response:** `201 Created`
```json
{
  "user": {
    "id": "0dc3103e-5bf9-4996-ab25-63e27101a4d5",
    "email": "user@example.com",
    "display_name": "John Doe",
    "created_at": "2025-12-21T13:45:37.121452"
  },
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### POST /auth/login
Authenticate and receive tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```

**Response:** Same as register

### POST /auth/refresh
Rotate refresh token and get new access token.

**Request:**
```json
{
  "refresh_token": "eyJhbGci..."
}
```
*Also accepts refresh_token from HttpOnly cookie*

### POST /auth/logout
Revoke refresh token and clear cookies.

---

## User Profile

### GET /me
Get current authenticated user profile.

**Response:**
```json
{
  "id": "0dc3103e-5bf9-4996-ab25-63e27101a4d5",
  "email": "user@example.com",
  "display_name": "John Doe",
  "created_at": "2025-12-21T13:45:37.121452"
}
```

---

## Onboarding

Voice-based onboarding flow using ElevenLabs Conversational AI.

### GET /onboard/status
Check if user has completed onboarding.

**Response:**
```json
{
  "onboarded": false,
  "has_profile": false,
  "display_name": null
}
```

### GET /onboard/start
Get signed URL for ElevenLabs widget.

**Response:**
```json
{
  "signed_url": "https://elevenlabs.io/...",
  "agent_id": "agent_xxx",
  "user_id": "0dc3103e-5bf9-4996-ab25-63e27101a4d5"
}
```

### POST /onboard/submit
Submit structured profile data (called by ElevenLabs webhook).

**Headers:** `X-Onboard-Secret: <tool_secret>`

**Request:**
```json
{
  "user_id": "uuid",
  "display_name": "Jamie",
  "favorite_genres": ["pop", "r&b", "house"],
  "favorite_artists": ["Dua Lipa", "The Weeknd"],
  "favorite_songs": ["Levitating", "Blinding Lights"],
  "no_go": ["country", "heavy metal"],
  "explicit_lyrics": "ok",
  "dj_personality": "casual_funny",
  "age_range": "25-34",
  "location": "London, UK",
  "occupation": "Software Engineer"
}
```

**Enums:**
- `explicit_lyrics`: `"ok"` | `"avoid"` | `"depends"`
- `dj_personality`: `"casual_funny"` | `"minimal_talk"` | `"hype_energetic"` | `"light_roast"` | `"more_talk_between_songs"`

**Response:**
```json
{
  "success": true,
  "user_id": "uuid"
}
```

---

## Streaming

### POST /stream/start
Start or resume a streaming session (idempotent).

**Request:**
```json
{
  "mood_id": "uuid",
  "context_name": "workout"
}
```
*Both fields optional*

**Response:** `200 OK`
```json
{
  "session_id": "uuid",
  "stream_url": "/api/v1/stream",
  "ws_url": "/api/v1/ws",
  "now_playing": null
}
```

**Error:** `409 Conflict` (if not onboarded)
```json
{
  "detail": {
    "code": "onboarding_required",
    "message": "Please complete onboarding before streaming",
    "next": "/api/v1/onboard/start"
  }
}
```

### GET /stream/status
Get current stream status.

**Response:**
```json
{
  "session_id": "uuid",
  "active": true,
  "mood_id": null,
  "context_id": null,
  "started_at": "2025-12-21T00:00:00Z",
  "now_playing": {
    "title": "Blinding Lights",
    "artist": "The Weeknd"
  }
}
```

### POST /stream/stop
Stop the current stream.

**Response:**
```json
{
  "message": "Stream stopped"
}
```

### GET /stream
Audio stream (MP3). Authenticates via cookie.

**Headers returned:**
```
Content-Type: audio/mpeg
Cache-Control: no-cache, no-store
Connection: keep-alive
```

---

## WebSocket

### GET /ws
Real-time events via WebSocket.

**Authentication:** Cookie (access_token) or query param (?token=xxx if enabled)

**Event Format (server → client):**
```json
{
  "v": 1,
  "type": "now_playing",
  "data": { ... },
  "ts": "2025-12-21T00:00:00Z"
}
```

**Event Types:**
| Type | Data |
|------|------|
| `connected` | `{ user_id, message }` |
| `now_playing` | `{ song_uuid, title, artist, artwork_url }` |
| `segment_ready` | `{ segment_index, duration_sec, song_uuid }` |
| `dj_says` | `{ script }` |
| `decision_trace` | `{ agent, decision, rationale }` |
| `stream_status` | `{ status, session_id }` |
| `pong` | `{}` |

**Client Messages:**
```json
{ "type": "ping", "data": {} }
{ "type": "get_status", "data": {} }
```

---

## Moods

### GET /moods
List all moods for current user.

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Workout",
    "color": "#FF5733",
    "energy_target": 0.9,
    "valence_target": 0.7,
    "genres": ["edm", "hip-hop"],
    "dj_personality": "hype_energetic",
    "is_default": true,
    "profile": { "summary_text": "" }
  }
]
```

### POST /moods
Create a new mood.

**Request:**
```json
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

### PATCH /moods/{id}
Update a mood.

### DELETE /moods/{id}
Delete a mood.

### POST /moods/{id}/set-default
Set a mood as default.

---

## Contexts

### GET /contexts
List all contexts.

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "workout",
    "raw_text": "High energy music...",
    "parsed_json": null
  }
]
```

### POST /contexts
Create a new context.

**Request:**
```json
{
  "name": "workout",
  "raw_text": "High energy music for gym sessions"
}
```

### GET /contexts/{name}
Get context by name.

### PUT /contexts/{name}
Update context.

### DELETE /contexts/{name}
Delete context.

---

## Feedback

### POST /feedback
Submit song feedback for training.

**Request:**
```json
{
  "song_uuid": "uuid",
  "track_title": "Song Name",
  "track_artist": "Artist Name",
  "mood_id": "uuid",
  "value": "like",
  "reason_text": "Great tempo for running"
}
```

**Values:** `"like"` | `"dislike"` | `"skip"`

### GET /feedback
List feedback events.

**Query params:** `mood_id`, `limit` (default 50)

---

## Agent Settings

### GET /agent-settings
List all agent settings.

### PUT /agent-settings/{agent_name}
Update agent settings.

**Valid agents:** `track_selector`, `transition_planner`, `speech_writer`, `download_planner`

**Request:**
```json
{
  "settings_json": "{\"thinking_budget\": 3000, \"temperature\": 0.7}"
}
```

---

## Prompt Templates

### GET /prompts
List prompt templates.

**Query param:** `active_only=true`

### PUT /prompts/{name}
Create/update a prompt template.

**Request:**
```json
{
  "scope": "global",
  "role": "system",
  "template_text": "You are a DJ with a chill personality..."
}
```

### POST /prompts/{name}/activate
Activate a specific version.

**Query param:** `version=N`

---

## Error Responses

```json
{
  "detail": "Error message here"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request / validation error |
| 401 | Not authenticated |
| 403 | CSRF token missing/invalid |
| 404 | Resource not found |
| 409 | Onboarding required |
| 422 | Validation error (JSON schema) |
| 503 | Session limit reached |
