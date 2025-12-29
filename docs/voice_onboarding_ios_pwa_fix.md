# Voice Onboarding iOS PWA Fix - Research Findings & Implementation

## Problem Summary

iOS PWA users experience a persistent "Connecting..." hang during voice onboarding. Debug logs show:
- SDK status changes to `"connecting"` but never fires `onConnect`
- 20s timeout hit with no connection established
- Multiple `getUserMedia` calls from SDK with complex constraints

## Root Cause Analysis (Updated - v2)

### A. SDK Internal Audio Pipeline Conflicts

**Critical Discovery**: The ElevenLabs SDK uses **LiveKit** (`livekit-client` package) under the hood for WebRTC connections. Our monkey-patching approach conflicted with LiveKit's internal audio pipeline management.

**Evidence from SDK inspection**:
- SDK creates its own `AudioContext` and `MediaStream` via `Input` class
- SDK has built-in iOS handling: `preferHeadphonesForIosDevices`, `connectionDelay`
- SDK documentation explicitly recommends calling `getUserMedia()` before `startSession()` **only to prompt the permission dialog**, not to pass a stream

**Why our approach failed**:
1. We acquired a stream and monkey-patched `getUserMedia` to return clones
2. LiveKit's `Room` connection expected to control the media track lifecycle
3. Cloned tracks from our pre-acquired stream may not integrate properly with LiveKit's connection establishment

### B. Safari ICE Candidate Restrictions

**Critical WebKit Behavior** (from webkit.org/blog/7763/a-closer-look-into-webrtc/):
- Safari implements "mode 3" ICE candidate gathering - the strictest policy
- Safari ONLY provides host ICE candidates AFTER `getUserMedia()` is called and approved
- Safari fails to establish WebRTC data channel connections unless `getUserMedia` is called first

**Why this matters for WebRTC mode**:
- LiveKit requires ICE candidates to establish peer connection
- If we interfered with `getUserMedia`, ICE candidate gathering may have failed
- This explains why `onConnect` never fires despite `startSession` returning

### C. Previous Issues (Addressed but not root cause)

**Hidden Media Element Track Death**:
- WebKit has issues with hidden/offscreen media elements killing tracks
- We fixed this with WebAudio keep-alive, but this wasn't the root cause

**Stream Cloning Issues**:
- Returning cloned tracks could break SDK's internal stream tracking
- SDK's `Input` class stores stream reference and may have issues with clones

## Solution: Trust the SDK

### Key Insight

The ElevenLabs SDK is designed for cross-browser compatibility and has:
1. Built-in iOS Safari handling
2. LiveKit integration with proper WebRTC management
3. Platform-specific delays and options

**We should not fight the SDK - we should let it handle microphone acquisition.**

### Implementation (v2)

**Changes Made**:

1. **Removed monkey-patching of `getUserMedia`** - No longer intercept SDK's calls
2. **Removed stream pre-acquisition** - Just check permission, release immediately
3. **Removed WebAudio keep-alive** - SDK handles its own audio pipeline
4. **Added SDK-specific options**:
   - `preferHeadphonesForIosDevices: true` for iOS
   - `connectionDelay: { ios: 1000, android: 3000, default: 0 }` for device settling
5. **Added `onDebug` callback** - Better visibility into SDK internal events
6. **Improved error messages** - iOS PWA-specific timeout message

### Code Structure (v2)

```typescript
const handleStart = async () => {
  // STEP 1: Permission Check Only
  try {
    const testStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    testStream.getTracks().forEach(t => t.stop()) // Release immediately
  } catch (err) {
    // Handle permission denied
    return
  }

  // STEP 2: Let SDK handle everything
  await conversation.startSession({
    signedUrl: response.signed_url,
    connectionType: "websocket", // or "webrtc"
    preferHeadphonesForIosDevices: isIOS,
    connectionDelay: { ios: 1000, android: 3000, default: 0 },
  })
}
```

## ElevenLabs SDK Architecture

### Dependencies
- `@elevenlabs/client`: Core conversation management
- `livekit-client`: WebRTC implementation for WebRTC mode
- Internal AudioContext for WebSocket mode

### Connection Types

**WebSocket Mode** (used for iOS PWA):
- Simpler, more reliable in restrictive environments
- SDK creates `AudioContext` + `MediaStreamSource` internally
- Uses `WebSocketConnection` class

**WebRTC Mode** (default):
- Uses LiveKit for peer-to-peer audio
- More complex ICE candidate exchange
- Uses `WebRTCConnection` + LiveKit `Room`

### SDK Options

| Option | Description |
|--------|-------------|
| `preferHeadphonesForIosDevices` | Force headphone audio routing on iOS when available |
| `connectionDelay` | Platform-specific delays before connection starts |
| `textOnly` | Skip microphone entirely for text-only agents |

## Citations

1. **ElevenLabs React SDK Documentation**: https://elevenlabs.io/docs/agents-platform/libraries/react
2. **ElevenLabs Client SDK README**: https://www.npmjs.com/package/@elevenlabs/client
3. **WebKit Blog - WebRTC ICE Policies**: https://webkit.org/blog/7763/a-closer-look-into-webrtc/
4. **StackOverflow - Safari ICE Candidates**: https://stackoverflow.com/questions/46605141/ios-safari-11-webrtc-does-not-gather-stun-turn-trickle-ice-candidates
5. **LiveKit Documentation**: https://docs.livekit.io/home/client/connect/
6. **GitHub - ElevenLabs Packages**: https://github.com/elevenlabs/packages

## Testing Checklist

1. **Build Verification**: `npm run build` must pass ✓
2. **iOS Safari (non-PWA)**: WebRTC flow should work
3. **iOS PWA (Standalone)**: WebSocket flow should work, no hang
4. **Desktop Chrome**: Regression test WebRTC
5. **Android Chrome**: Test with connectionDelay
6. **Timeout Test**: Disable network mid-connection, should error within 25s
7. **Permission Denied**: Clear error message, option to retry

## Debug Overlay

Access debug logs by adding `?debug` to URL:
- Shows iOS/PWA detection
- Shows timestamps for each step
- Shows SDK debug events (`onDebug` callback)
- Visible on error state automatically
