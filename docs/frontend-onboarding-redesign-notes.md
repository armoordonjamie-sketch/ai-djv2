# Frontend Onboarding Redesign - Implementation Notes

## What Was Implemented

This implementation redesigns the voice onboarding experience with professional audio handling, better preview UI, fixed mood creation flow, and iOS PWA optimizations.

### Files Created

1. **`frontend/src/hooks/useDucking.ts`**
   - Professional audio ducking hook with sidechain-style attack/release curves
   - Uses Web Audio API `exponentialRampToValueAtTime` for smooth volume transitions
   - Configurable attack (50ms), release (300ms), and level parameters
   - Properly handles iOS AudioContext unlocking requirements

2. **`frontend/src/components/player/PreviewCard.tsx`**
   - Floating mini-card showing current song preview during onboarding
   - Displays album artwork, track title, artist name
   - Animated waveform indicator for playback status
   - Visual indicator when audio is ducked (agent speaking)
   - Progress bar showing preview position

### Files Modified

1. **`frontend/src/pages/VoiceOnboardingPage.tsx`**
   - Replaced manual volume toggling with professional ducking system
   - Integrated PreviewCard component for better preview UX
   - Track preview progress and current track info
   - Removed Howler.js dependency for preview playback
   - Uses ducking AudioContext for all preview audio

2. **`frontend/src/pages/MoodCreationPage.tsx`**
   - **Fixed premature completion bug**: Now waits for `intros_ready >= moods_total`
   - Added "Almost there..." finishing phase when moods created but intros pending
   - Minimum 2-second completion display time for better animation UX
   - Enhanced progress calculation: 70% moods + 30% intros
   - Better status messaging with loader during finishing phase

3. **`frontend/index.html`**
   - Additional iOS-specific meta tags for format detection
   - Multiple Apple touch icon sizes (152x152, 180x180)
   - Apple splash screen links for various iOS devices
   - Touch callout prevention meta tag

4. **`frontend/src/index.css`**
   - `touch-action: manipulation` on all interactive elements
   - Minimum 44x44pt touch target utilities
   - `overscroll-behavior: contain` for scroll containers
   - Comprehensive safe area utilities (`safe-x`, `safe-y`, `safe-all`)
   - Standalone mode detection styles
   - Tap highlight prevention and subtle feedback

5. **`frontend/vite.config.ts`**
   - Additional iOS icon sizes in manifest
   - PWA shortcuts for Play Music and My Moods
   - `prefer_related_applications: false` for proper iOS launch
   - Categories for app store metadata

6. **`backend_v2/api/deezer_tools.py`**
   - Added `artwork_url` to PlayPreviewResponse schema
   - Extracts album cover (preferring xl/big sizes) from Deezer track response

7. **`frontend/src/lib/jamifyApi.ts`**
   - Added `artwork_url` to PlayPreviewResponse interface

## How to Run Locally

```bash
# Frontend
cd frontend
pnpm install
pnpm dev

# Backend
cd backend_v2
pip install -r requirements.txt
uvicorn backend_v2.main:app --reload
```

## Interfaces & Contracts

### DuckingConfig Interface

```typescript
interface DuckingConfig {
  attackTime: number;   // ms to fade down (default: 50)
  releaseTime: number;  // ms to fade up (default: 300)
  duckLevel: number;    // volume when ducked (default: 0.25)
  fullLevel: number;    // volume when not ducked (default: 1.0)
}
```

### PreviewTrack Interface

```typescript
interface PreviewTrack {
  title: string;
  artist: string;
  artworkUrl?: string;
  previewUrl?: string;
  duration?: number;
}
```

### Updated PlayPreviewResponse

```typescript
interface PlayPreviewResponse {
  played: boolean;
  track_title?: string;
  artist_name?: string;
  preview_url?: string;
  artwork_url?: string;  // NEW: Album artwork from Deezer
  duration_seconds?: number;
  message?: string;
  error?: string;
}
```

## Architecture Decisions

### Ducking Implementation

**Choice**: Web Audio API with `exponentialRampToValueAtTime`

**Rationale**: 
- `linearRampToValueAtTime` sounds unnatural for volume changes
- Exponential curves match human perception of loudness
- 50ms attack is fast enough to not clip the agent's speech
- 300ms release provides a "breathing" effect that feels professional

**Official Docs**: [MDN Web Audio API - GainNode](https://developer.mozilla.org/en-US/docs/Web/API/GainNode)

### MoodCreationPage Completion Logic

**Problem**: Backend marks generation `complete` when moods are created, but intros take additional time.

**Solution**: Two-phase completion check:
```typescript
const isActuallyComplete = data.status === "complete" && 
  data.intros_ready >= data.moods_total;
```

Plus minimum 2-second display time for completion animation.

### iOS PWA Audio

**Challenge**: iOS PWA sandbox has strict AudioContext requirements.

**Solution**:
- Create AudioContext inside ducking hook (lazy initialization)
- Unlock context during user gesture (handleStart button click)
- Keep single AudioContext alive for entire session
- All preview audio routed through ducking gain node

## TODOs & Known Limitations

1. **Apple touch icons**: Need to actually generate the various iOS icon sizes
2. **Splash screens**: Referenced but not yet generated
3. **Offline mode**: Preview playback requires network
4. **iOS 16.4+ shortcuts**: May not work on older iOS versions

## Dependencies Added

No new dependencies added. Uses existing:
- `framer-motion` for PreviewCard animations
- Web Audio API (browser native)
- CSS env() safe-area-inset (browser native)

