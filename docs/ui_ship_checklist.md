# UI Ship Checklist

Manual QA checklist for the AI DJ frontend before shipping.

## Desktop Checklist
- [ ] Landing page loads and looks polished
- [ ] Login/Register flows work
- [ ] Player page loads and shows "Tap to Start" overlay
- [ ] Audio stream starts after first interaction
- [ ] WebSocket connection shows "Live" indicator
- [ ] Mood switching works without audio interruption
- [ ] Like/Dislike buttons show training progression feedback
- [ ] Status pills update in real-time during generation

## Mobile / iOS Checklist
- [ ] No content hidden under notch (top safe area)
- [ ] No content hidden under home indicator (bottom safe area)
- [ ] Player controls fully visible and tappable
- [ ] Mini-player visible when navigating away from Player page
- [ ] Bottom tab navigation fully visible
- [ ] Touch targets are at least 44x44px

## PWA Install Checklist
- [ ] InstallHint component appears for eligible browsers
- [ ] "Add to Home Screen" prompt works on iOS Safari
- [ ] Installed PWA opens in standalone mode
- [ ] Theme color matches app (dark purple `#0a0a0f`)
- [ ] Splash screen shows correctly during launch

## Reconnect / Network Checklist
- [ ] WebSocket reconnects automatically after network drop
- [ ] No duplicate toasts or status messages on reconnect
- [ ] "Reconnecting" status shows during reconnect attempt
- [ ] Playback continues after reconnect (if still streaming)

## Background Pause/Resume Checklist (iOS)
- [ ] Audio pauses when app goes to background (expected iOS behavior)
- [ ] "Tap to Resume" banner appears when returning to app
- [ ] Tapping banner resumes playback
- [ ] Banner dismisses after resume
- [ ] Works in both Safari and installed PWA

## Commands to Verify

```bash
# TypeScript check
npx tsc --noEmit

# Production build
npm run build

# Preview production build locally
npm run preview
```
