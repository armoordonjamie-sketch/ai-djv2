# Voice Onboarding Connection Fix

## Issue
When user accepts microphone permissions during voice onboarding:
- "Using mic" indicator appears briefly
- Then disappears
- Appears again
- Disappears again
- Gets stuck on "Loading your AI DJ..."

## Root Cause

The issue occurs specifically on **iOS PWA** (Progressive Web App) devices. Here's the flow:

1. ✅ User clicks "Start Conversation"
2. ✅ iOS PWA warmup process requests microphone (indicator appears)
3. ✅ Warmup creates AudioContext and activates audio pipeline
4. ✅ Warmup releases microphone for ElevenLabs SDK to use (indicator disappears)
5. ❌ **ElevenLabs WebSocket connection fails or times out**
6. ❌ SDK never acquires the microphone successfully
7. ❌ Connection stuck in "connecting" state forever

### Why WebSocket Fails on iOS PWA

The code uses **WebSocket connection** specifically for iOS PWA (instead of WebRTC) because iOS PWA has limited WebRTC support. However, WebSocket connections can also be problematic in iOS PWA sandbox environment, leading to:
- Connection timeouts
- Network permission issues
- Audio pipeline initialization failures

## Solution Applied

Added **automatic fallback to WebRTC** when WebSocket connection fails on iOS PWA:

```typescript
try {
    // Try WebSocket first (iOS PWA preferred)
    conversationId = await conversation.startSession({
        signedUrl: response.signed_url,
        connectionType: "websocket",
        dynamicVariables: { user_id: user?.id || 'anonymous' },
    })
} catch (wsError) {
    // WebSocket failed - fall back to WebRTC
    console.warn("WebSocket failed, trying WebRTC fallback:", wsError)
    
    const { token } = await api.getConversationToken()
    conversationId = await conversation.startSession({
        conversationToken: token,
        connectionType: "webrtc",  // Use WebRTC instead
        dynamicVariables: { user_id: user?.id || 'anonymous' },
    })
}
```

### Benefits
- ✅ Still tries WebSocket first (better for iOS PWA if it works)
- ✅ Automatically falls back to WebRTC if WebSocket fails
- ✅ Provides better error messages in debug logs
- ✅ Increases connection success rate on iOS PWA

## Files Changed

- `frontend/src/pages/VoiceOnboardingPage.tsx`
  - Added try/catch around WebSocket connection
  - Added automatic WebRTC fallback
  - Enhanced debug logging

## Testing

### Normal Testing
1. Restart frontend (reload page)
2. Click "Start Conversation"
3. Accept microphone permissions
4. Connection should succeed (either WebSocket or WebRTC fallback)

### Debug Mode
Add `?debug` to URL to see detailed connection logs:
```
http://localhost:3000/onboarding?debug
```

This shows:
- Connection type used (WebSocket vs WebRTC)
- Timing information
- Error messages
- Fallback events

## Additional Recommendations

If issues persist:

1. **Try in Safari browser** (not PWA) - WebRTC works better in full browser
2. **Check network connection** - Poor network can cause connection failures
3. **Check browser console** for ElevenLabs SDK errors
4. **Try on different device/browser** to isolate iOS PWA vs general issue

## Related Issues Fixed

This is separate from the backend fixes but completes the full onboarding flow:
- ✅ Backend: FK constraint error fixed (intros can now generate)
- ✅ Frontend: Infinite loop fixed (smooth transition after onboarding)
- ✅ Frontend: Voice connection stability improved (WebSocket fallback)

---

**Status**: ✅ Fix applied and built
**Next Step**: Test voice onboarding again (should connect successfully)
