# Ship Checklist

Pre-flight checklist for development and production-like testing.

---

## Dev Mode (Separate Processes)

Frontend running via Vite dev server, backend as separate API server.

### Backend (Port 8000)
```powershell
cd c:\Users\JamiePC\Desktop\ai-djv2
.\.venv\Scripts\Activate
uvicorn backend_v2.main:app --host 0.0.0.0 --port 8000
```

### Frontend (Port 5173)
```powershell
cd c:\Users\JamiePC\Desktop\ai-djv2\frontend
npm run dev
```

### Verification
- [ ] Backend health: `curl http://localhost:8000/health`
- [ ] Frontend loads at `http://localhost:5173`
- [ ] API calls work (login, moods, etc.)
- [ ] WebSocket connects and receives events
- [ ] Audio stream plays

---

## Prod-Like Mode (Single Process)

Built frontend served by backend from same origin. Matches production behavior.

### Build Frontend
```powershell
cd c:\Users\JamiePC\Desktop\ai-djv2\frontend
npm ci
npm run build
```
- [ ] Build completes without errors
- [ ] `dist/` contains `index.html`, `assets/`, service worker files

### Start Backend with Frontend Serving
```powershell
cd c:\Users\JamiePC\Desktop\ai-djv2
.\.venv\Scripts\Activate
$env:SERVE_FRONTEND="true"
uvicorn backend_v2.main:app --host 0.0.0.0 --port 5173
```

### Verification
- [ ] `http://localhost:5173` loads built SPA
- [ ] Navigate to `/moods` → page loads (not 404)
- [ ] Refresh on `/moods` → SPA fallback works
- [ ] `/health` returns JSON
- [ ] `/api/v1/me` requires auth (API still working)
- [ ] Assets load with cache headers (check DevTools Network)
- [ ] Service worker registers
- [ ] WebSocket connects (`ws://localhost:5173/api/v1/ws/events`)
- [ ] Audio stream plays

---

## Cloudflare Tunnel Setup (Production)

| Subdomain | Local Port | Purpose |
|-----------|------------|---------|
| `jamify.jamiearmoordon.co.uk` | 8000 | Backend API only |
| `app.jamiearmoordon.co.uk` | 5173 | Frontend + API (prod-like) |

For production, run backend in prod-like mode on port 5173:
```powershell
$env:SERVE_FRONTEND="true"
uvicorn backend_v2.main:app --host 0.0.0.0 --port 5173
```

---

## PWA Checklist

- [ ] Service worker registered (Application tab → Service Workers)
- [ ] Manifest loaded (Application tab → Manifest)
- [ ] Add to Home Screen works (iOS: Share → Add to Home Screen)
- [ ] Offline: static assets cached, API calls show appropriate errors
- [ ] Audio streams NOT cached by service worker (NetworkOnly handler)

### iOS PWA Limitations
- No background audio when app is backgrounded
- `navigator.mediaSession` has limited support
- "Tap to Resume" sheet shown when returning to app

---

## Quick Smoke Test

```powershell
# Build and test
cd c:\Users\JamiePC\Desktop\ai-djv2\frontend
npm run build

cd c:\Users\JamiePC\Desktop\ai-djv2
$env:SERVE_FRONTEND="true"
uvicorn backend_v2.main:app --port 5173

# In another terminal:
curl http://localhost:5173/         # Should return HTML
curl http://localhost:5173/moods    # Should return HTML (SPA fallback)
curl http://localhost:5173/health   # Should return JSON
```
