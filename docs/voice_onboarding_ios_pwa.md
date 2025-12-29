# Voice Onboarding iOS PWA Fix Strategy

## 1. Research Findings

### iOS Safari vs. PWA Standalone Constraints
*   **`getUserMedia` in Standalone:** Historically buggy (Webkit Bug 185448), though largely fixed in iOS 13.4+. However, it remains strict about **User Gesture**.
*   **The "Gesture Token":** iOS grants a short window (< 1s) after a tap to:
    1.  Resume an `AudioContext`.
    2.  Call `getUserMedia`.
    3.  Play an `<audio>` element.
*   **The Conflict:** If `conversation.startSession()` performs an async network call (e.g., fetching a token or strict-mode checks) *before* requesting the mic, the "gesture token" expires. When the SDK finally calls `getUserMedia`, it fails silently or throws `NotAllowedError` without a prompt.
*   **Audio Session Interruption:** On iOS, putting the PWA in the background or even locking screen can kill the `AudioContext`. Resuming it requires *another* user gesture.

    *   `websocket` (Default): Uses a WebSocket for audio streaming. Reliable on desktop, can be flaky on mobile networks or strict firewalls. Requires `signedUrl` for private agents.
    *   `webrtc`: Uses WebRTC Data Channels / Media Streams. Often more robust for real-time audio (echo cancellation, latency). **Requires `conversationToken` (not `signedUrl`) for private agents.**
        *   **API Endpoint**: `GET https://api.elevenlabs.io/v1/convai/conversation/token` (Headers: `xi-api-key`). Returns `{ "token": "..." }`.
        *   **SDK Usage**: `conversation.startSession({ conversationToken: "...", connectionType: "webrtc" })`.
    *   **Mic Handling:** The SDK manages `getUserMedia` internally. It does not natively support "injecting" an existing MediaStream (unless using the lower-level `client` methods directly).

### Hypothesis
The current "Hang" on "Connecting..." is likely due to:
1.  **Gesture Expiry:** The SDK does async work (internal setup) between the `handleStart` click and the actual `getUserMedia` call.
2.  **WebSocket Flakiness:** The WebSocket connection opens, but audio context initialization fails silently due to PWA restrictions.

## 2. Diagnostics Plan (Make it Observable)

We cannot "guess" anymore. We need on-device visibility.

### 2.1 Debug Panel Requirements
*   **Platform Info:** `isIOS`, `isPWA`, `userAgent`.
*   **State Machine:** Track exact transitions (e.g., `ready` -> `connecting` -> `active`).
*   **Timestamps:**
    *   `Start Clicked`
    *   `Signed URL Ready`
    *   `conversation.startSession Called`
    *   `onConnect / onError`
*   **Console Capture:** Intercept `console.log/warn/error` to on-screen overlay.
*   **Hard Timeout:** If state stays `connecting` for > 15s, force Error state with "Retry" or "Text Mode" fallback.

## 3. Fix Strategy (Prioritized)

### FIX A: "Single User Gesture" (Frontend Optimist)
*   **Goal:** Ensure `startSession` happens *immediately* (sync) in the click handler.
*   **Implementation:**
    *   Pre-fetch `signedUrl` (Already done, but verify freshness).
    *   **Monkey-patch `getUserMedia`:** (Extreme safety)
        1.  In `handleStart`: Call `navigator.mediaDevices.getUserMedia` *immediately* to get a stream.
        2.  Cache this stream.
        3.  Temporarily replace `navigator.mediaDevices.getUserMedia` with a function that returns this cached stream.
        4.  Call `conversation.startSession`.
        5.  Restore original function after connection.
    *   **Force Audio Context Resume:** Call `Howler.ctx.resume()` (or create a dummy buffer) immediately in the click handler.

### FIX B: WebRTC Switch (Backend + Frontend)
*   **Goal:** Use the more robust WebRTC protocol.
*   **Implementation:**
    *   **Backend:** New endpoint `POST /api/v1/onboard/token` that calls ElevenLabs API to get a `conversation_token` (not signed URL).
    *   **Frontend:**
        *   Pre-fetch this token.
        *   Call `conversation.startSession({ connectionType: "webrtc", conversationToken: ... })`.

### FIX C: Fallback Paths (UX Safety)
*   If connection takes > 15s:
    *   Show "Connection failed."
    *   Button: "Try Text-Only Mode" (Uses `textOnly: true` in SDK).
    *   Button: "Open in Safari" (Deep link to browser version).

## 4. Testing Criteria
1.  **iOS PWA (Standalone):** Click start -> Mic Prompt -> "Connected" within 5s.
2.  **Failure Case:** Airplane mode -> Click start -> Error message within 15s (not infinite spinner).
