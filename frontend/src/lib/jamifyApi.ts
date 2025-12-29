/**
 * Jamify API Client — Real Backend Integration (No Mock Fallbacks)
 * 
 * Uses HttpOnly cookies for auth + CSRF token for state-changing requests.
 * All calls include credentials: 'include' for cookie auth.
 */

// ============ Configuration ============

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
export const API_V1 = API_BASE ? `${API_BASE}/api/v1` : '/api/v1'

// Derive WebSocket base URL from API base
export function getWsBase(): string {
    if (API_BASE) {
        return API_BASE.replace(/^http/, 'ws')
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}`
}

// ============ Helpers ============

/**
 * Get a cookie value by name
 */
export function getCookie(name: string): string | null {
    const value = `; ${document.cookie}`
    const parts = value.split(`; ${name}=`)
    if (parts.length === 2) {
        return parts.pop()?.split(';').shift() ?? null
    }
    return null
}

/**
 * Returns CSRF header for mutating HTTP methods
 */
function csrfHeadersIfNeeded(method: string): HeadersInit {
    const mutatingMethods = ['POST', 'PUT', 'PATCH', 'DELETE']
    if (mutatingMethods.includes(method.toUpperCase())) {
        const csrfToken = getCookie('csrf_token')
        if (csrfToken) {
            return { 'X-CSRF-Token': csrfToken }
        }
    }
    return {}
}

// ============ Error Types ============

export interface ApiError {
    status: number
    code?: string
    message: string
    detail?: unknown
}

export class JamifyApiError extends Error {
    status: number
    code?: string
    detail?: unknown

    constructor(error: ApiError) {
        super(error.message)
        this.name = 'JamifyApiError'
        this.status = error.status
        this.code = error.code
        this.detail = error.detail
    }

    get isOnboardingRequired(): boolean {
        return this.status === 409 && this.code === 'onboarding_required'
    }

    get isUnauthorized(): boolean {
        return this.status === 401
    }

    get isCsrfError(): boolean {
        return this.status === 403
    }
}

// ============ Fetch Wrapper ============

interface JamifyFetchOptions {
    method?: string
    body?: unknown
    headers?: HeadersInit
}

/**
 * Wrapper for fetch with:
 * - credentials: 'include' (cookie auth)
 * - JSON body serialization
 * - CSRF header for mutating requests
 * - Rich error parsing
 */
async function jamifyFetch<T>(path: string, options: JamifyFetchOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options

    const finalHeaders: HeadersInit = {
        ...csrfHeadersIfNeeded(method),
        ...headers,
    }

    // Add Content-Type for JSON body
    if (body !== undefined) {
        (finalHeaders as Record<string, string>)['Content-Type'] = 'application/json'
    }

    // Anti-caching headers
    (finalHeaders as Record<string, string>)['Cache-Control'] = 'no-cache, no-store, must-revalidate';
    (finalHeaders as Record<string, string>)['Pragma'] = 'no-cache';
    (finalHeaders as Record<string, string>)['Expires'] = '0';

    const requestId = Math.random().toString(36).substring(7)
    // Add cache-buster to URL
    const url = new URL(`${API_V1}${path}`, window.location.origin)
    url.searchParams.append('_t', Date.now().toString())

    console.log(`[API] ${requestId} -> ${method} ${url.pathname}`)

    // Robust 15s timeout
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 15000)

    try {
        const response = await fetch(url.toString(), {
            method,
            credentials: 'include',
            headers: finalHeaders,
            body: body !== undefined ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        })
        clearTimeout(timeoutId)

        console.log(`[API] ${requestId} <- Status ${response.status}`)

        // Handle no-content responses
        if (response.status === 204) {
            return undefined as T
        }

        // Try to parse JSON response
        let data: unknown
        try {
            const text = await response.text()
            console.log(`[API] ${requestId} Body len: ${text.length}`)
            try {
                data = JSON.parse(text)
            } catch {
                data = null
            }
        } catch (jsonErr) {
            console.warn(`[API] ${requestId} JSON Parse Error:`, jsonErr)
            data = null
        }

        if (!response.ok) {
            const detail = data as { detail?: string | { code?: string; message?: string } } | null
            let message = `API Error: ${response.status}`
            let code: string | undefined

            if (detail?.detail) {
                if (typeof detail.detail === 'string') {
                    message = detail.detail
                } else if (typeof detail.detail === 'object') {
                    message = detail.detail.message || message
                    code = detail.detail.code
                }
            }

            throw new JamifyApiError({
                status: response.status,
                code,
                message,
                detail: detail?.detail,
            })
        }

        return data as T
    } catch (err) {
        clearTimeout(timeoutId)
        console.error(`[API] ${requestId} Error:`, err)
        throw err
    }
}

// ============ Type Definitions ============

export interface User {
    id: string
    email: string
    display_name: string | null
    created_at: string
}

export interface AuthResponse {
    user: User
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
}

export interface OnboardStatus {
    onboarded: boolean
    has_profile: boolean
    display_name: string | null
}

export interface OnboardStartResponse {
    signed_url: string
    agent_id: string
    conversation_hint: {
        user_id: string
        display_name: string | null
    }
}

export interface OnboardTokenResponse {
    token: string
    agent_id: string
    conversation_hint: {
        user_id: string
        display_name: string | null
    }
}

export interface Mood {
    id: string
    name: string
    color: string
    energy_target: number
    valence_target: number
    genres: string[]
    dj_personality: string
    is_default: boolean
    profile?: { summary_text: string }
}

export interface MoodCreateRequest {
    name: string
    color: string
    energy_target?: number
    valence_target?: number
    genres?: string[]
    dj_personality?: string
    is_default?: boolean
}

export interface Context {
    id: string
    name: string
    raw_text: string
    parsed_json: unknown | null
}

export interface ContextCreateRequest {
    name: string
    raw_text: string
}

export interface StreamStartRequest {
    mood_id?: string
    context_name?: string
}

export interface StreamStartResponse {
    session_id: string
    stream_url: string
    ws_url: string
    now_playing: NowPlaying | null
}

export interface StreamStatusResponse {
    session_id: string | null
    active: boolean
    mood_id: string | null
    context_id: string | null
    started_at: string | null
    now_playing: NowPlaying | null
    loop_state?: unknown
}

export interface NowPlaying {
    song_uuid: string
    title: string
    artist: string
    artwork_url?: string
}

export interface FeedbackRequest {
    song_uuid: string
    track_title?: string
    track_artist?: string
    mood_id?: string
    value: 'like' | 'dislike' | 'skip'
    reason_text?: string
}

export interface FeedbackResponse {
    id: string
    song_uuid: string
    track_title: string
    track_artist: string
    value: string
    created_at: string
}

export interface FeedbackListItem {
    id: string
    song_uuid: string
    track_title: string
    track_artist: string
    mood_id: string | null
    value: string
    reason_text: string | null
    created_at: string
}

// ============ Auth API ============

export async function login(email: string, password: string): Promise<AuthResponse> {
    return jamifyFetch<AuthResponse>('/auth/login', {
        method: 'POST',
        body: { email, password },
    })
}

export async function register(
    email: string,
    password: string,
    displayName?: string
): Promise<AuthResponse> {
    return jamifyFetch<AuthResponse>('/auth/register', {
        method: 'POST',
        body: { email, password, display_name: displayName },
    })
}

export async function logout(): Promise<void> {
    await jamifyFetch<void>('/auth/logout', { method: 'POST' })
}

export async function refreshToken(): Promise<AuthResponse> {
    return jamifyFetch<AuthResponse>('/auth/refresh', { method: 'POST' })
}

export async function getMe(): Promise<User> {
    return jamifyFetch<User>('/me')
}

// ============ Onboarding API ============

export async function getOnboardStatus(): Promise<OnboardStatus> {
    return jamifyFetch<OnboardStatus>('/onboard/status')
}

export async function startOnboarding(): Promise<OnboardStartResponse> {
    return jamifyFetch<OnboardStartResponse>('/onboard/start', { method: 'POST' })
}

export async function getConversationToken(): Promise<OnboardTokenResponse> {
    return jamifyFetch<OnboardTokenResponse>('/onboard/conversation-token')
}

// ============ Moods API ============

export async function getMoods(): Promise<Mood[]> {
    return jamifyFetch<Mood[]>('/moods')
}

export async function createMood(mood: MoodCreateRequest): Promise<Mood> {
    return jamifyFetch<Mood>('/moods', {
        method: 'POST',
        body: mood,
    })
}

export async function updateMood(id: string, updates: Partial<MoodCreateRequest>): Promise<Mood> {
    return jamifyFetch<Mood>(`/moods/${id}`, {
        method: 'PATCH',
        body: updates,
    })
}

export async function deleteMood(id: string): Promise<void> {
    await jamifyFetch<void>(`/moods/${id}`, { method: 'DELETE' })
}

export async function setDefaultMood(id: string): Promise<Mood> {
    return jamifyFetch<Mood>(`/moods/${id}/set-default`, { method: 'POST' })
}

// ============ Contexts API ============

export async function getContexts(): Promise<Context[]> {
    return jamifyFetch<Context[]>('/contexts')
}

export async function createContext(ctx: ContextCreateRequest): Promise<Context> {
    return jamifyFetch<Context>('/contexts', {
        method: 'POST',
        body: ctx,
    })
}

export async function getContext(name: string): Promise<Context> {
    return jamifyFetch<Context>(`/contexts/${encodeURIComponent(name)}`)
}

export async function updateContext(name: string, rawText: string): Promise<Context> {
    return jamifyFetch<Context>(`/contexts/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: { name, raw_text: rawText },
    })
}

export async function deleteContext(name: string): Promise<void> {
    await jamifyFetch<void>(`/contexts/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

// ============ Stream API ============

export async function startStream(request: StreamStartRequest = {}): Promise<StreamStartResponse> {
    return jamifyFetch<StreamStartResponse>('/stream/start', {
        method: 'POST',
        body: request,
    })
}

export async function getStreamStatus(): Promise<StreamStatusResponse> {
    return jamifyFetch<StreamStatusResponse>('/stream/status')
}

export async function stopStream(): Promise<{ message: string }> {
    return jamifyFetch<{ message: string }>('/stream/stop', { method: 'POST' })
}

/**
 * Get the stream audio URL (for use with <audio> element)
 */
export function getStreamUrl(): string {
    return `${API_V1}/stream`
}

/**
 * Get the WebSocket URL for real-time events
 */
export function getWebSocketUrl(): string {
    return `${getWsBase()}${API_V1.replace(API_BASE, '')}/ws`
}

// ============ Feedback API ============

export async function submitFeedback(feedback: FeedbackRequest): Promise<FeedbackResponse> {
    return jamifyFetch<FeedbackResponse>('/feedback', {
        method: 'POST',
        body: feedback,
    })
}

export async function getFeedback(
    moodId?: string,
    limit: number = 50
): Promise<FeedbackListItem[]> {
    const params = new URLSearchParams()
    if (moodId) params.set('mood_id', moodId)
    params.set('limit', limit.toString())
    return jamifyFetch<FeedbackListItem[]>(`/feedback?${params.toString()}`)
}

// ============ History API ============

/**
 * Get listening history.
 * Note: This endpoint may not be implemented server-side.
 * If so, returns an empty array and logs a warning.
 */
export async function getHistory(): Promise<unknown[]> {
    try {
        return await jamifyFetch<unknown[]>('/history')
    } catch (error) {
        if (error instanceof JamifyApiError && error.status === 404) {
            console.warn('[JamifyAPI] GET /history not implemented server-side')
            return []
        }
        throw error
    }
}

// ============ Profile API ============

export interface ProfileUpdateRequest {
    display_name?: string
}

export async function updateProfile(updates: ProfileUpdateRequest): Promise<User> {
    return jamifyFetch<User>('/me', {
        method: 'PATCH',
        body: updates,
    })
}

// ============ Training Reset ============

/**
 * Reset all training data (delete all feedback and reset mood weights)
 */
export async function resetTraining(): Promise<void> {
    await jamifyFetch<void>('/feedback/all', { method: 'DELETE' })
}
// ============ Skip API ============

export async function skipTrack(): Promise<{ message: string }> {
    return jamifyFetch<{ message: string }>('/stream/skip', { method: 'POST' })
}


// ============ Deezer Tools API ============

export interface PlayPreviewResponse {
    played: boolean
    track_title?: string
    artist_name?: string
    preview_url?: string
    duration_seconds?: number
    message?: string
    error?: string
}

export async function playPreview(artist_name: string, track_title: string): Promise<PlayPreviewResponse> {
    return jamifyFetch<PlayPreviewResponse>('/deezer/play-preview', {
        method: 'POST',
        body: { artist_name, track_title }
    })
}
