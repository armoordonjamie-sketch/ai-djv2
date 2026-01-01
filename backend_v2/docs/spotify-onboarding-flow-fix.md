# Spotify Onboarding Flow Fix - December 30, 2025

## Issue
After user registration, the app was navigating directly to voice onboarding, skipping the Spotify connection page. This prevented users from connecting their Spotify account before the voice onboarding step.

## Root Cause
1. The `/api/v1/onboard/status` endpoint didn't include Spotify connection status
2. The registration form navigated directly to `/onboarding` instead of `/connect-spotify`
3. The frontend didn't track or check whether users had connected Spotify
4. The onboarding flow routing didn't enforce the Spotify → Voice Onboarding sequence

## Changes Made

### Backend Changes

#### 1. Updated `OnboardStatusResponse` Schema
**File**: `backend_v2/api/onboard.py`

Added `has_spotify` field to the response model:
```python
class OnboardStatusResponse(BaseModel):
    """Response for onboarding status check."""
    onboarded: bool
    has_profile: bool
    has_spotify: bool  # ← NEW
    display_name: Optional[str] = None
```

#### 2. Updated `/api/v1/onboard/status` Endpoint
**File**: `backend_v2/api/onboard.py`

Modified the endpoint to check for Spotify connection:
- Queries `SpotifyUserContext` table to check if user has connected Spotify
- Returns `has_spotify: true` if connection exists, `false` otherwise
- Updated docstring to reflect new requirement

### Frontend Changes

#### 1. Updated API Type Definition
**File**: `frontend/src/lib/jamifyApi.ts`

Added `has_spotify` field to the TypeScript interface:
```typescript
export interface OnboardStatus {
    onboarded: boolean
    has_profile: boolean
    has_spotify: boolean  // ← NEW
    display_name: string | null
}
```

#### 2. Enhanced AuthProvider
**File**: `frontend/src/providers/AuthProvider.tsx`

- Added `hasSpotify: boolean` state variable
- Updated `AuthContextType` interface to include `hasSpotify`
- Modified all onboard status checks to update `hasSpotify` state:
  - `loadOnboardingStatus()`
  - `refreshAuth()`
  - `checkOnboarding()`
  - `login()`
  - `register()` - sets to `false` for new users
  - `logout()` - resets to `false`
- Exposed `hasSpotify` in context value

#### 3. Enhanced ProtectedRoute
**File**: `frontend/src/components/ProtectedRoute.tsx`

- Added `requireSpotify?: boolean` prop
- Added routing logic to check Spotify connection:
  ```typescript
  // If Spotify is required but user hasn't connected it
  if (requireSpotify && !hasSpotify) {
      return <Navigate to="/connect-spotify" />
  }
  
  // If onboarding required but not onboarded
  if (requireOnboarding && !isOnboarded) {
      // First check if they need to connect Spotify
      if (!hasSpotify) {
          return <Navigate to="/connect-spotify" />
      }
      return <Navigate to="/onboarding" />
  }
  ```

#### 4. Updated VoiceOnboardingPage
**File**: `frontend/src/pages/VoiceOnboardingPage.tsx`

Modified the initial status check to redirect to Spotify connect page if not connected:
```typescript
const status = await api.getOnboardStatus()

// Check if user has connected Spotify first
if (!status.has_spotify) {
    navigate("/connect-spotify", { replace: true })
    return
}
```

#### 5. Fixed Registration Flow
**File**: `frontend/src/components/auth/register-form.tsx`

Changed navigation after successful registration:
```typescript
// Before
navigate("/onboarding")

// After  
navigate("/connect-spotify")  // ← Go to Spotify connect first
```

## New Onboarding Flow

### For New Users (Registration)
1. **Register** → Creates account
2. **Spotify Connect Page** (`/connect-spotify`)
   - User can connect Spotify account
   - User can skip and continue to voice onboarding
3. **Voice Onboarding** (`/onboarding`) 
   - If no Spotify connection, redirected back to step 2
   - Interactive voice conversation with ElevenLabs AI
4. **Mood Creation** (`/creating-moods`)
   - AI generates 5 personalized moods
5. **Player** (`/player`) - Fully onboarded!

### For Returning Users (Login)
- Protected routes automatically check onboarding status
- Users without Spotify connection are redirected to `/connect-spotify`
- Users without voice onboarding are redirected to `/onboarding`
- Users without moods see `/creating-moods` page
- Fully onboarded users can access `/player` directly

## Benefits

1. **Consistent Flow**: All new users see the Spotify connect page
2. **Better UX**: Clear progression through onboarding steps
3. **Data Collection**: Encourages Spotify connection for better personalization
4. **Flexible**: Users can still skip Spotify if they prefer
5. **Type-Safe**: Full TypeScript typing for `has_spotify` flag

## Testing Checklist

- [x] Backend returns `has_spotify` in `/api/v1/onboard/status`
- [x] Register → navigates to `/connect-spotify`
- [x] Spotify connect → navigates to `/onboarding`
- [x] Voice onboarding checks for Spotify and redirects if missing
- [x] Protected routes enforce onboarding sequence
- [x] Login flow respects incomplete onboarding steps

## Notes

- The Spotify connection is **optional** (users can skip)
- The backend now tracks Spotify connection status separately from onboarding status
- The `has_spotify` flag is distinct from `has_profile` and `onboarded`
- All state management properly handles Spotify connection status across auth flows

