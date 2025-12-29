# Auth Redesign QA Checklist

## Pre-Deployment Verification

### Build & TypeScript
- [ ] `npm run build` completes without errors
- [ ] No TypeScript errors in auth components
- [ ] No linter warnings in modified files

### Component Rendering
- [ ] All auth pages render without console errors
- [ ] No React warnings in browser console
- [ ] Page transitions work smoothly
- [ ] Back buttons navigate correctly

## Mobile-First UX Testing

### iOS Safari (Not Installed)
- [ ] Landing page displays correctly
- [ ] Safe area insets respected (notch/home indicator)
- [ ] Tap targets are >= 44px
- [ ] Input focus doesn't zoom (font-size: 16px working)
- [ ] Keyboard doesn't break layout
- [ ] Page transitions feel smooth (or disabled if reduced motion)
- [ ] Install prompt shows iOS instructions
- [ ] Back button works correctly

### iOS Safari (Installed PWA - Standalone Mode)
- [ ] Safe area paddings correct (no content under notch)
- [ ] Status bar style correct (black-translucent)
- [ ] Full-screen layout works (viewport-fit=cover)
- [ ] Back button navigates within app
- [ ] Keyboard behavior stable
- [ ] No white bars at top/bottom
- [ ] Landscape mode works correctly

### Android Chrome
- [ ] Landing page displays correctly
- [ ] Install prompt button appears (if beforeinstallprompt fires)
- [ ] Install prompt works
- [ ] Tap targets adequate
- [ ] Keyboard behavior stable
- [ ] Page transitions smooth

### Desktop (Chrome/Firefox/Safari)
- [ ] Landing page looks good (centered card)
- [ ] Auth forms centered and readable
- [ ] Hover states work on buttons/links
- [ ] Forms work with mouse and keyboard
- [ ] No layout issues on wide screens

## Form Validation Testing

### Login Form
- [ ] Email validation works (invalid email shows error)
- [ ] Password required validation works
- [ ] Submit disabled while loading
- [ ] Server errors display correctly
- [ ] Success navigates to /player (or redirect path)
- [ ] "Forgot password" link works
- [ ] "Create account" link works
- [ ] Password toggle works
- [ ] Autocomplete="email" works with password managers
- [ ] Autocomplete="current-password" works
- [ ] Error messages don't cause layout shift (fixed height)

### Register Form
- [ ] Email validation works
- [ ] Password minimum 8 characters enforced
- [ ] Password must have uppercase letter
- [ ] Password must have lowercase letter
- [ ] Password must have number
- [ ] Password strength indicator updates correctly
- [ ] Confirm password match validation works
- [ ] Terms checkbox required
- [ ] Submit disabled while loading
- [ ] Server errors display correctly
- [ ] Success navigates to /onboarding
- [ ] "Sign in" link works
- [ ] Password toggle affects both password fields
- [ ] Autocomplete="new-password" works
- [ ] Error messages don't cause layout shift

### Accessibility
- [ ] All inputs have proper labels
- [ ] Error messages announced by screen readers (aria-live)
- [ ] Focus management works (errors focus first invalid field)
- [ ] Keyboard navigation follows visual order
- [ ] Tab order logical
- [ ] All interactive elements keyboard accessible
- [ ] Color contrast meets WCAG AA
- [ ] Reduced motion respected (no animations if prefers-reduced-motion)

## Animation & Motion

### Page Transitions
- [ ] Landing → Login transition smooth
- [ ] Login → Register transition smooth
- [ ] Register → Login transition smooth
- [ ] Back button transition smooth
- [ ] No flickering or visual glitches
- [ ] AnimatePresence mode="wait" working (no overlapping pages)
- [ ] Reduced motion: animations disabled or minimal

### Landing Page Animations
- [ ] Logo animates on load (or static if reduced motion)
- [ ] Background blobs animate (or static if reduced motion)
- [ ] Stagger effect on feature bullets (or instant if reduced motion)
- [ ] No performance issues (smooth 60fps)

### Form Animations
- [ ] Error messages slide in smoothly
- [ ] Password strength indicator animates
- [ ] Button loading state smooth
- [ ] No animation jank

## Install Prompt Behavior

### iOS
- [ ] Shows after 3 second delay (if not dismissed recently)
- [ ] Shows "Add to Home Screen" instructions
- [ ] Share icon displayed correctly
- [ ] Dismiss works and saves to localStorage
- [ ] Doesn't show again for 7 days after dismiss
- [ ] Doesn't show if already installed (display-mode: standalone)

### Android
- [ ] Shows after 3 second delay
- [ ] "Install App" button appears if beforeinstallprompt available
- [ ] Button triggers native install prompt
- [ ] Dismiss works and saves to localStorage
- [ ] Doesn't show if already installed

### General
- [ ] Prompt is subtle and non-blocking
- [ ] Doesn't interfere with auth flow
- [ ] Position is mobile-friendly (bottom, not covering content)

## Safe Area & Viewport

### CSS Variables
- [ ] env(safe-area-inset-top) applied correctly
- [ ] env(safe-area-inset-bottom) applied correctly
- [ ] env(safe-area-inset-left) applied correctly (landscape)
- [ ] env(safe-area-inset-right) applied correctly (landscape)
- [ ] Fallback to 0 works on non-iOS devices

### Viewport Units
- [ ] min-h-dvh works on supported browsers
- [ ] Fallback to min-h-screen works on older browsers
- [ ] No content cutoff on any device
- [ ] Keyboard doesn't cause content to jump

## Cross-Browser Compatibility

### Modern Browsers (Last 2 versions)
- [ ] Chrome/Edge (Desktop & Android)
- [ ] Safari (Desktop & iOS)
- [ ] Firefox (Desktop & Android)

### PWA Features
- [ ] beforeinstallprompt event handled (Chrome/Edge)
- [ ] Add to Home Screen works (iOS Safari 11.3+)
- [ ] Standalone mode detected correctly
- [ ] Web app manifest loads

## Performance

### Load Times
- [ ] Landing page loads quickly (<2s on 3G)
- [ ] No bundle size regression (check build output)
- [ ] Code splitting working (auth pages separate chunk)
- [ ] No unnecessary re-renders (React DevTools Profiler)

### Runtime
- [ ] Form validation responsive (<100ms)
- [ ] Page transitions smooth (60fps)
- [ ] No memory leaks (test with DevTools Memory profiler)
- [ ] No console warnings/errors

## Security

### Password Handling
- [ ] Password never logged to console
- [ ] Password toggle client-side only
- [ ] No plaintext passwords in network tab
- [ ] Autocomplete helps password managers

### Validation
- [ ] Client-side validation works
- [ ] Server-side validation respected
- [ ] Error messages don't expose sensitive info
- [ ] No XSS vulnerabilities (React auto-escaping working)

## Edge Cases

### Network
- [ ] Offline: graceful error handling
- [ ] Slow network: loading states work
- [ ] Failed request: error messages clear
- [ ] Retry after error works

### Form Edge Cases
- [ ] Very long email (200+ chars) handled
- [ ] Special characters in password work
- [ ] Copy/paste password works
- [ ] Autofill from password manager works
- [ ] Back button during form submission works
- [ ] Double-submit prevented (button disabled)

### Navigation
- [ ] Direct URL access works (/login, /register)
- [ ] Browser back/forward work correctly
- [ ] Redirect after login works
- [ ] Logout redirects to landing

## Regression Testing

### Existing Features Still Work
- [ ] Voice onboarding flow works
- [ ] Player page loads after login
- [ ] Protected routes still protected
- [ ] Logout works
- [ ] Session persistence works (refresh token)
- [ ] Privacy/Terms pages accessible

## Documentation

- [x] Research doc created (docs/auth_redesign_research.md)
- [ ] Plan doc reviewed (plan file)
- [x] QA checklist created (this file)
- [ ] Key changes summarized (see PR description below)

---

## PR Description / Summary

### What Changed

**Auth Pages Redesign (Mobile-First PWA)**

This PR redesigns the Landing, Login, and Register pages to feel like a native mobile PWA app rather than a website, following best practices for iOS and Android.

#### Key Changes:

1. **New Components**
   - `AuthShell.tsx`: Mobile-first auth container with safe-area support
   - `AuthField.tsx`: Reusable form field with iOS-friendly inputs (16px font-size)
   - Added PWA viewport utilities (min-h-dvh, safe-area CSS)

2. **Landing Page Redesign**
   - Replaced multi-section marketing site with single-screen app welcome
   - Centered logo, tagline, and CTAs
   - 3 concise feature bullets
   - Integrated install prompt
   - Feels like opening an app, not visiting a website

3. **Auth Forms (Login/Register)**
   - Migrated to react-hook-form + Zod for validation
   - Added proper autocomplete attributes (email, current-password, new-password)
   - Fixed-height error containers (no layout shift)
   - Input font-size: 16px (prevents iOS zoom)
   - Password strength indicator on register
   - Better loading/error states

4. **Page Transitions**
   - Added AnimatePresence for smooth transitions between auth pages
   - 150ms slide + fade animations
   - Respects prefers-reduced-motion
   - Feels app-like, not website-like

5. **Safe Area & iOS Support**
   - viewport-fit=cover already present
   - Safe area insets applied to auth shell
   - Fixed iOS keyboard issues
   - Stable layout on notched devices

#### Technical Details:

- **Bundle impact**: 0 KB (uses existing dependencies)
- **Packages used**: react-hook-form, zod, framer-motion (all already installed)
- **Backend changes**: None (API contracts unchanged)
- **Breaking changes**: None (all routes still work)

#### How to Test:

1. **Desktop**: Visit http://localhost:5173
   - Landing page should show centered welcome screen
   - Forms should validate correctly
   - Page transitions smooth

2. **iOS Safari** (recommended for full PWA experience):
   - Open in Safari on iPhone
   - Check safe area padding (no content under notch)
   - Try "Add to Home Screen"
   - Test installed PWA (standalone mode)
   - Verify keyboard doesn't cause zoom or layout jump

3. **Android Chrome**:
   - Install prompt should appear
   - Test installed PWA

#### Files Changed:

**Created:**
- `frontend/src/components/auth/AuthShell.tsx`
- `frontend/src/components/auth/AuthField.tsx`
- `frontend/docs/auth_redesign_research.md`
- `frontend/docs/auth_redesign_checklist.md` (this file)

**Modified:**
- `frontend/src/pages/LandingPage.tsx` (complete redesign)
- `frontend/src/pages/LoginPage.tsx` (use AuthShell)
- `frontend/src/pages/RegisterPage.tsx` (use AuthShell)
- `frontend/src/components/auth/login-form.tsx` (react-hook-form + zod)
- `frontend/src/components/auth/register-form.tsx` (react-hook-form + zod)
- `frontend/src/App.tsx` (AnimatePresence for transitions)
- `frontend/src/index.css` (dvh utilities, 16px input rule)

**Deprecated (but not deleted):**
- `frontend/src/components/auth/auth-layout.tsx` (replaced by AuthShell)

---

## Post-Deployment Monitoring

### Metrics to Watch
- [ ] Install prompt conversion rate (Google Analytics or similar)
- [ ] Form submission success rate
- [ ] Error rate on auth endpoints
- [ ] Bounce rate on landing page
- [ ] Time to first interaction
- [ ] Mobile vs desktop usage split

### User Feedback
- [ ] Monitor support tickets for auth issues
- [ ] Check for iOS zoom complaints (should be gone)
- [ ] Check for layout complaints on notched devices (should be gone)
- [ ] Monitor install prompt dismiss rate

---

## Known Limitations & Future Improvements

### Current Limitations
1. Password strength indicator is simple (could add more sophisticated checks)
2. "Forgot password" link present but route not implemented (existing behavior)
3. Social login buttons removed (were disabled anyway)
4. Install prompt timing hardcoded (3s delay, 7d dismissal)

### Future Improvements
1. Add biometric authentication (Face ID / Touch ID)
2. Add "Continue with Google/Apple" (when backend ready)
3. Add password visibility persistence (localStorage)
4. Add form autosave (localStorage)
5. Add A/B testing for install prompt timing
6. Add telemetry for install prompt conversion
7. Add haptic feedback on form errors (mobile)
8. Add skeleton loaders for better perceived performance

---

## Sign-Off

**QA Tested By**: _______________ Date: _______________

**Approved By**: _______________ Date: _______________

**Deployed To Production**: _______________ Date: _______________

---

## Rollback Plan

If issues arise:

1. **Immediate**: Revert to previous commit (no DB changes, safe to rollback)
2. **Auth still works**: Old auth-layout.tsx still in codebase as fallback
3. **No backend changes**: API unchanged, can rollback frontend only
4. **User data**: No user data affected (only UI changes)

Rollback command:
```bash
git revert <this-commit-hash>
npm run build
# Deploy
```

