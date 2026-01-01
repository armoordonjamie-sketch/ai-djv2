import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Howl, Howler } from 'howler'
import { useMediaSession } from '@/hooks/useMediaSession'
import * as api from '@/lib/jamifyApi'
import type { StatusEvent } from '@/lib/types'

// ============ Types ============

export interface Track {
    id: string
    title: string
    artist: string
    artworkUrl?: string
}

interface PlayerState {
    currentTrack: Track | null
    queue: Track[]
    activeMoodId: string | null
    sessionId: string | null
    isPlaying: boolean
    isLoading: boolean
    position: number
    duration: number
    volume: number
    isMuted: boolean
    feedback: 'like' | 'dislike' | null
    error: string | null
    streamUrl: string | null
    wsUrl: string | null
    wsConnected: boolean
    djCaption: string
    // Status event state
    currentStatus: StatusEvent | null
    // Status history for AIActivityFeed (last 10 events)
    statusHistory: StatusEvent[]
}

interface PlayerContextType extends PlayerState {
    // Actions
    play: () => Promise<void>
    pause: () => void
    toggle: () => Promise<void>
    skip: () => void
    setVolume: (volume: number) => void
    toggleMute: () => void
    seek: (time: number) => void
    setActiveMood: (moodId: string, moodName?: string, moodColor?: string) => Promise<void>
    submitFeedback: (type: 'like' | 'dislike') => Promise<void>
    startStream: (moodId?: string, resume?: boolean) => Promise<void>
    stopStream: () => Promise<void>
    // iOS/PWA Status
    hasUserInteracted: boolean
    setHasUserInteracted: (value: boolean) => void
    wasPausedByBackground: boolean
    isIOSPWA: boolean
    // Mood switch dialog
    moodSwitchDialog: {
        open: boolean
        moodId: string | null
        moodName: string
        moodColor: string
        savedPosition: number
        savedTrack: { title: string; artist: string; artworkUrl?: string } | null
    }
    confirmMoodSwitch: (resume: boolean) => void
    cancelMoodSwitch: () => void
}

const PlayerContext = createContext<PlayerContextType | null>(null)

// ============ WebSocket Manager ============

class WSManager {
    private ws: WebSocket | null = null
    private url: string | null = null
    private reconnectAttempts = 0
    private maxReconnectAttempts = 5
    private reconnectDelay = 1000
    private pingInterval: NodeJS.Timeout | null = null
    private onMessage: (event: api.NowPlaying | { script: string } | { status: string } | StatusEvent, type: string) => void
    private onStatusChange: (connected: boolean) => void
    private isIntentionalDisconnect = false

    constructor(
        onMessage: (event: api.NowPlaying | { script: string } | { status: string } | StatusEvent, type: string) => void,
        onStatusChange: (connected: boolean) => void
    ) {
        this.onMessage = onMessage
        this.onStatusChange = onStatusChange
    }

    connect(url: string) {
        // Close any existing connection (including ones still connecting)
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            console.log('[WS] Closing existing connection before reconnecting')
            this.ws.close()
            this.ws = null
        }

        this.url = url
        this.reconnectAttempts = 0
        this.isIntentionalDisconnect = false
        this.createConnection()
    }

    private createConnection() {
        if (!this.url) return

        try {
            this.ws = new WebSocket(this.url)

            this.ws.onopen = () => {
                console.log('[WS] Connected')
                this.onStatusChange(true)
                this.reconnectAttempts = 0
                this.startPingInterval()
            }

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data) as { type: string; data: unknown }
                    this.handleMessage(data)
                } catch {
                    console.warn('[WS] Failed to parse message:', event.data)
                }
            }

            this.ws.onclose = (event) => {
                const cleanClose = this.isIntentionalDisconnect || event.code === 1000 || event.code === 1005
                console.log(`[WS] Disconnected (${cleanClose ? 'clean' : 'unexpected'}):`, event.code, event.reason)
                this.onStatusChange(false)
                this.stopPingInterval()

                if (!this.isIntentionalDisconnect) {
                    this.attemptReconnect()
                }
            }

            this.ws.onerror = (error) => {
                console.error('[WS] Error:', error)
            }
        } catch (error) {
            console.error('[WS] Failed to connect:', error)
            this.attemptReconnect()
        }
    }

    private handleMessage(msg: { type: string; data: unknown }) {
        switch (msg.type) {
            case 'now_playing':
                this.onMessage(msg.data as api.NowPlaying, 'now_playing')
                break
            case 'dj_says':
                this.onMessage(msg.data as { script: string }, 'dj_says')
                break
            case 'stream_status':
                this.onMessage(msg.data as { status: string }, 'stream_status')
                break
            case 'status':
                // Structured StatusEvent - forward to handler
                this.onMessage(msg.data as StatusEvent, 'status')
                break
            case 'segment_ready':
                // Could update queue indicator here
                break
            case 'pong':
                // Keepalive response
                break
            case 'connected':
                console.log('[WS] Server acknowledged connection')
                break
            case 'ping':
                // Server keepalive - just ignore
                break
            default:
                console.log('[WS] Unknown event:', msg.type)
        }
    }

    private attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[WS] Max reconnect attempts reached')
            return
        }

        this.reconnectAttempts++
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`)

        setTimeout(() => {
            if (this.url) {
                this.createConnection()
            }
        }, delay)
    }

    private startPingInterval() {
        this.stopPingInterval()
        this.pingInterval = setInterval(() => {
            this.send({ type: 'ping', data: {} })
        }, 30000)
    }

    private stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval)
            this.pingInterval = null
        }
    }

    send(message: { type: string; data: unknown }) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message))
        }
    }

    disconnect() {
        this.isIntentionalDisconnect = true
        this.stopPingInterval()
        this.url = null
        if (this.ws) {
            this.ws.close()
            this.ws = null
        }
    }
}

// ============ Provider ============

// Session storage for mood playback resumption
interface MoodSession {
    moodId: string
    sessionId: string
    position: number
    timestamp: number
    // Track info for resume dialog
    trackTitle?: string
    trackArtist?: string
    trackArtwork?: string
}

const STORAGE_KEY = 'jamify_mood_sessions'
const SESSION_TTL = 30 * 60 * 1000 // 30 minutes

function loadMoodSessions(): Map<string, MoodSession> {
    try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (!stored) return new Map()

        const sessions: MoodSession[] = JSON.parse(stored)
        const now = Date.now()

        // Filter out expired sessions
        const validSessions = sessions.filter(s => (now - s.timestamp) < SESSION_TTL)
        return new Map(validSessions.map(s => [s.moodId, s]))
    } catch {
        return new Map()
    }
}

function saveMoodSessions(sessions: Map<string, MoodSession>) {
    try {
        const sessionsArray = Array.from(sessions.values())
        localStorage.setItem(STORAGE_KEY, JSON.stringify(sessionsArray))
    } catch {
        // Ignore localStorage errors
    }
}

export function PlayerProvider({ children }: { children: ReactNode }) {
    const navigate = useNavigate()
    const soundRef = useRef<Howl | null>(null)
    const wsManagerRef = useRef<WSManager | null>(null)
    const positionIntervalRef = useRef<NodeJS.Timeout | null>(null)
    const [hasUserInteracted, setHasUserInteractedState] = useState(false)
    const hasUserInteractedRef = useRef(false) // Ref for synchronous access in callbacks

    // Wrapper to update both state and ref
    const setHasUserInteracted = useCallback((value: boolean) => {
        hasUserInteractedRef.current = value
        setHasUserInteractedState(value)
    }, [])

    // Background playback state
    const [wasPausedByBackground, setWasPausedByBackground] = useState(false)
    const [isIOSPWA, setIsIOSPWA] = useState(false)
    const wasPlayingRef = useRef(false) // Track if we were playing before backgrounding

    // Session tracking for mood resumption
    const moodSessionsRef = useRef<Map<string, MoodSession>>(loadMoodSessions())

    const [state, setState] = useState<PlayerState>({
        currentTrack: null,
        queue: [],
        activeMoodId: null,
        sessionId: null,
        isPlaying: false,
        isLoading: false,
        position: 0,
        duration: 0,
        volume: 1,
        isMuted: false,
        feedback: null,
        error: null,
        streamUrl: null,
        wsUrl: null,
        wsConnected: false,
        djCaption: '',
        currentStatus: null,
        statusHistory: [],
    })

    // Mood switch dialog state
    const [moodSwitchDialog, setMoodSwitchDialog] = useState<{
        open: boolean
        moodId: string | null
        moodName: string
        moodColor: string
        savedPosition: number
        savedTrack: { title: string; artist: string; artworkUrl?: string } | null
    }>({
        open: false,
        moodId: null,
        moodName: '',
        moodColor: '#888',
        savedPosition: 0,
        savedTrack: null,
    })

    // Detect iOS PWA
    useEffect(() => {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
        const isStandalone = (window.navigator as any).standalone === true || window.matchMedia('(display-mode: standalone)').matches
        const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent)
        setIsIOSPWA(isIOS && (isStandalone || isSafari))
    }, [])

    // Handle visibility changes for background pause detection and iOS resume
    useEffect(() => {
        const handleVisibilityChange = () => {
            const isHidden = document.visibilityState === 'hidden'

            if (isHidden) {
                // Going to background
                if (state.isPlaying) {
                    wasPlayingRef.current = true
                    console.log('[Player] Going to background, was playing:', true)
                }
            } else {
                // Coming to foreground
                console.log('[Player] Coming to foreground, wasPlaying:', wasPlayingRef.current, 'isPlaying:', state.isPlaying)

                // If we were playing but now we are paused, and we are on iOS PWA, it's a background pause
                if (wasPlayingRef.current && !state.isPlaying && isIOSPWA) {
                    setWasPausedByBackground(true)

                    // iOS PWA: Attempt to automatically resume playback
                    // This requires that the user has already interacted with the page
                    if (hasUserInteractedRef.current && soundRef.current) {
                        console.log('[Player] iOS PWA - attempting to resume playback after background')
                        // Small delay to let iOS settle
                        setTimeout(() => {
                            if (soundRef.current && !soundRef.current.playing()) {
                                try {
                                    soundRef.current.play()
                                    console.log('[Player] iOS PWA - resume attempt made')
                                } catch (err) {
                                    console.warn('[Player] iOS PWA - resume failed:', err)
                                }
                            }
                        }, 100)
                    }
                }

                // Reset flag if we weren't paused by background or we resolved it
                if (state.isPlaying) {
                    setWasPausedByBackground(false)
                    wasPlayingRef.current = false
                }
            }
        }
        document.addEventListener('visibilitychange', handleVisibilityChange)
        return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
    }, [state.isPlaying, isIOSPWA])

    // Handle WS messages
    const handleWSMessage = useCallback((data: api.NowPlaying | { script: string } | { status: string } | StatusEvent, type: string) => {
        switch (type) {
            case 'now_playing': {
                const np = data as api.NowPlaying
                console.log('[WS] Now playing:', np.title, 'by', np.artist)
                setState(s => ({
                    ...s,
                    currentTrack: {
                        id: np.song_uuid,
                        title: np.title,
                        artist: np.artist,
                        artworkUrl: np.artwork_url,
                    },
                    feedback: null, // Reset feedback for new track
                }))
                break
            }
            case 'dj_says': {
                const dj = data as { script: string }
                setState(s => ({ ...s, djCaption: dj.script }))
                break
            }
            case 'stream_status': {
                const status = data as { status: string }
                if (status.status === 'stopped') {
                    setState(s => ({ ...s, isPlaying: false }))
                }
                break
            }
            case 'status': {
                // Structured StatusEvent - update currentStatus and maintain history
                const statusEvent = data as StatusEvent
                setState(s => {
                    // Deduplicate by ID - only add if not already in history
                    const alreadyExists = s.statusHistory.some(e => e.id === statusEvent.id)
                    const newHistory = alreadyExists
                        ? s.statusHistory
                        : [statusEvent, ...s.statusHistory].slice(0, 10)
                    return {
                        ...s,
                        currentStatus: statusEvent,
                        statusHistory: newHistory,
                    }
                })
                console.log('[WS] Status:', statusEvent.user_message, statusEvent.step)
                break
            }
        }
    }, [])

    const handleWSStatusChange = useCallback((connected: boolean) => {
        setState(s => ({ ...s, wsConnected: connected }))
    }, [])

    // Initialize WS and cleanup
    useEffect(() => {
        // Initialize WS manager only once
        wsManagerRef.current = new WSManager(handleWSMessage, handleWSStatusChange)

        return () => {
            wsManagerRef.current?.disconnect()
            // Cleanup Howler
            if (soundRef.current) {
                soundRef.current.unload()
            }
            if (positionIntervalRef.current) {
                clearInterval(positionIntervalRef.current)
            }
        }
    }, [handleWSMessage, handleWSStatusChange])

    // Update position polling and save to session storage
    useEffect(() => {
        if (state.isPlaying) {
            positionIntervalRef.current = setInterval(() => {
                const sound = soundRef.current
                if (sound && sound.playing()) {
                    const position = sound.seek()
                    setState(s => ({ ...s, position }))

                    // Save position to session storage for resumption
                    if (state.activeMoodId && state.sessionId) {
                        const sessions = moodSessionsRef.current
                        sessions.set(state.activeMoodId, {
                            moodId: state.activeMoodId,
                            sessionId: state.sessionId,
                            position,
                            timestamp: Date.now(),
                        })
                        saveMoodSessions(sessions)
                    }
                }
            }, 1000)
        } else {
            if (positionIntervalRef.current) {
                clearInterval(positionIntervalRef.current)
            }
        }
        return () => {
            if (positionIntervalRef.current) {
                clearInterval(positionIntervalRef.current)
            }
        }
    }, [state.isPlaying, state.activeMoodId, state.sessionId])

    // Send heartbeat to backend every 10 seconds
    useEffect(() => {
        if (!state.isPlaying || !state.sessionId) return

        const heartbeatInterval = setInterval(async () => {
            const sound = soundRef.current
            if (sound && sound.playing()) {
                const position = sound.seek()
                if (typeof position === 'number') {
                    try {
                        await api.sendHeartbeat(position)
                    } catch (err) {
                        console.warn('[Player] Heartbeat failed:', err)
                    }
                }
            }
        }, 10000) // Every 10 seconds

        return () => clearInterval(heartbeatInterval)
    }, [state.isPlaying, state.sessionId])

    // Media Session integration
    const mediaSession = useMediaSession({
        handlers: {
            onPlay: () => soundRef.current?.play(),
            onPause: () => soundRef.current?.pause(),
            onSeekTo: (time) => {
                if (soundRef.current) soundRef.current.seek(time)
            },
        },
    })

    // Update media session when track changes
    useEffect(() => {
        if (state.currentTrack) {
            mediaSession.updateMetadata({
                title: state.currentTrack.title,
                artist: state.currentTrack.artist,
                artwork: state.currentTrack.artworkUrl,
            })
            mediaSession.setPlaybackState(state.isPlaying ? 'playing' : 'paused')
        }
    }, [state.currentTrack, state.isPlaying, mediaSession])

    const play = useCallback(async () => {
        console.log('[Player] play() called, soundRef exists:', !!soundRef.current, 'isIOSPWA:', isIOSPWA)
        if (!soundRef.current) {
            console.warn('[Player] Cannot play - no sound instance')
            return
        }
        try {
            setHasUserInteracted(true)
            setWasPausedByBackground(false)

            // iOS: Try to unlock Howler's audio context first
            // @ts-ignore - Howler global context access
            const ctx = Howler.ctx
            if (ctx && ctx.state === 'suspended') {
                console.log('[Player] Audio context suspended, attempting resume...')
                try {
                    await ctx.resume()
                    console.log('[Player] Audio context resumed successfully')
                } catch (resumeErr) {
                    console.warn('[Player] Audio context resume failed:', resumeErr)
                }
            }

            console.log('[Player] Calling sound.play()')
            soundRef.current.play()
        } catch (err) {
            console.error('[Player] Play failed:', err)
            setState(s => ({ ...s, error: 'Playback failed' }))
        }
    }, [isIOSPWA])

    const pause = useCallback(() => {
        soundRef.current?.pause()
    }, [])

    const toggle = useCallback(async () => {
        if (state.isPlaying) {
            pause()
        } else {
            await play()
        }
    }, [state.isPlaying, play, pause])

    const skip = useCallback(() => {
        // Call skip API to advance to next segment
        // Note: Skip is NOT feedback - it just advances playback
        // The backend uses skip events separately from like/dislike training
        api.skipTrack().catch(err => {
            console.error('[Player] Skip failed:', err)
        })
    }, [])

    const setVolume = useCallback((volume: number) => {
        if (soundRef.current) {
            const vol = Math.max(0, Math.min(1, volume))
            soundRef.current.volume(vol)
            setState(s => ({ ...s, volume: vol }))
        }
    }, [])

    const toggleMute = useCallback(() => {
        if (soundRef.current) {
            const newMute = !state.isMuted
            soundRef.current.mute(newMute)
            setState(s => ({ ...s, isMuted: newMute }))
        }
    }, [state.isMuted])

    const seek = useCallback((time: number) => {
        if (soundRef.current) {
            const duration = soundRef.current.duration()
            const seekTime = Math.max(0, Math.min(duration, time))
            soundRef.current.seek(seekTime)
            setState(s => ({ ...s, position: seekTime }))
        }
    }, [])

    const startStream = useCallback(async (moodId?: string, resume = false) => {
        // When starting fresh (not resuming), clear the current track to avoid showing stale data
        if (!resume) {
            setState(s => ({
                ...s,
                isLoading: true,
                error: null,
                activeMoodId: moodId || s.activeMoodId,
                currentTrack: null, // Clear old track when starting fresh
            }))
        } else {
            setState(s => ({ ...s, isLoading: true, error: null, activeMoodId: moodId || s.activeMoodId }))
        }

        try {
            // Get saved position if resuming a mood
            let position_sec: number | undefined
            if (resume && moodId) {
                const savedSession = moodSessionsRef.current.get(moodId)
                if (savedSession && savedSession.position > 0) {
                    position_sec = savedSession.position
                    console.log(`[Player] Resuming mood ${moodId} at position ${position_sec}s`)
                }
            }

            const result = await api.startStream({ mood_id: moodId, resume, position_sec })

            // Determine stream URL
            const streamUrl = result.stream_url?.startsWith('/')
                ? `${api.API_V1.replace('/api/v1', '')}${result.stream_url}`
                : result.stream_url || api.getStreamUrl()

            // Determine WS URL
            const wsUrl = result.ws_url?.startsWith('/')
                ? `${api.getWsBase()}${result.ws_url}`
                : result.ws_url || api.getWebSocketUrl()

            // Connect WebSocket
            wsManagerRef.current?.connect(wsUrl)

            // Setup new Howl
            if (soundRef.current) {
                soundRef.current.unload()
            }

            console.log('[Player] Creating new Howl for:', streamUrl)

            // Track if we've already handled initial load (HTML5 streaming can fire onload multiple times)
            let initialLoadHandled = false

            // Determine if we should autoplay (user must have interacted)
            const shouldAutoplay = hasUserInteractedRef.current
            console.log('[Player] Creating Howl, autoplay:', shouldAutoplay, 'isIOSPWA:', isIOSPWA)

            // iOS PWA needs special handling for streaming audio
            // Howler's HTML5 mode can have issues on iOS, so we configure it carefully
            const initialNowPlaying = result.now_playing ? {
                id: result.now_playing.song_uuid,
                title: result.now_playing.title,
                artist: result.now_playing.artist,
                artworkUrl: result.now_playing.artwork_url,
            } : null

            const sound = new Howl({
                src: [streamUrl],
                html5: true, // Use HTML5 Audio for streaming (required for live streams)
                format: ['mp3'], // Hint mechanism
                volume: state.volume,
                autoplay: shouldAutoplay, // Autoplay if user has interacted
                preload: true, // Start loading immediately
                pool: 1, // Only create one audio element (helps iOS)
                xhr: {
                    // iOS Safari may need credentials for CORS
                    withCredentials: true,
                },
                onplay: () => {
                    console.log('[Howler] Playing')
                    setState(s => ({
                        ...s,
                        isPlaying: true,
                        isLoading: false,
                        error: null,
                        currentTrack: s.currentTrack ?? initialNowPlaying,
                    }))
                    setWasPausedByBackground(false)
                },
                onpause: () => {
                    console.log('[Howler] Paused')
                    setState(s => ({ ...s, isPlaying: false }))
                },
                onend: () => {
                    console.log('[Howler] Ended')
                    // For streaming audio, 'end' usually means stream was interrupted
                    // Don't set isPlaying to false, as the stream might restart
                    // Only set to false if we're explicitly stopping
                    if (!soundRef.current?.playing()) {
                        setState(s => ({ ...s, isPlaying: false }))
                    }
                },
                onstop: () => {
                    setState(s => ({ ...s, isPlaying: false }))
                },
                onload: () => {
                    // HTML5 streaming audio can fire onload multiple times as the buffer refills
                    // Only handle resume/initial play on the first load event
                    if (initialLoadHandled) {
                        console.log('[Howler] Loaded (buffer refill, ignoring)')
                        return
                    }
                    initialLoadHandled = true

                    console.log('[Howler] Loaded (initial)')
                    console.log('[Player] Resume check:', { resume, position_sec: result.position_sec })

                    // If resuming, update state with position for UI display
                    // Note: Backend handles the actual seek via FFmpeg, so we don't seek here
                    if (resume && result.position_sec !== undefined && result.position_sec > 0) {
                        console.log(`[Player] Resumed at position ${result.position_sec}s (backend handled seek)`)
                        setState(s => ({ ...s, isLoading: false, duration: sound.duration(), currentTime: result.position_sec }))
                    } else {
                        setState(s => ({ ...s, isLoading: false, duration: sound.duration() }))
                    }

                    // Ensure we're playing (autoplay should have started, but force if needed)
                    if (!sound.playing() && hasUserInteractedRef.current) {
                        console.log('[Player] Ensuring playback (autoplay may have been blocked)')
                        sound.play()
                    }
                },
                onloaderror: (_id, err) => {
                    console.error('[Howler] Load error:', err)
                    // On iOS, load errors can happen due to background restrictions
                    // Don't immediately show error, try to recover
                    if (isIOSPWA) {
                        console.log('[Player] iOS load error - will retry on user interaction')
                        setState(s => ({ ...s, isLoading: false, isPlaying: false }))
                    } else {
                        setState(s => ({ ...s, isLoading: false, error: 'Stream load failed' }))
                    }
                },
                onplayerror: (_id, err) => {
                    console.warn('[Howler] Play error (autoplay blocked?):', err)
                    setState(s => ({ ...s, isPlaying: false }))
                    // Do NOT set error here, just stop playing state so UI shows Play button
                    // If it was an autoplay attempt, silence is fine, user will tap play

                    // Try to unlock audio context just in case
                    sound.once('unlock', () => {
                        console.log('[Howler] Audio unlocked, attempting play')
                        sound.play()
                    })
                }
            })

            // iOS PWA: Set playsInline on the underlying audio element for better compatibility
            // @ts-ignore - Access internal Howler audio nodes
            const nodes = sound._sounds?.[0]?._node
            if (nodes && isIOSPWA) {
                console.log('[Player] Configuring iOS audio element')
                nodes.playsInline = true
                nodes.setAttribute('playsinline', '')
                nodes.setAttribute('webkit-playsinline', '')
            }


            soundRef.current = sound

            setState(s => ({
                ...s,
                sessionId: result.session_id,
                activeMoodId: result.mood_id || moodId || s.activeMoodId,
                streamUrl,
                wsUrl,
            }))

        } catch (err) {
            if (err instanceof api.JamifyApiError) {
                if (err.isOnboardingRequired) {
                    // Redirect to onboarding
                    navigate('/onboarding')
                    return
                }
                setState(s => ({ ...s, isLoading: false, error: err.message }))
            } else {
                setState(s => ({ ...s, isLoading: false, error: 'Failed to start stream' }))
            }
        }
    }, [navigate, state.volume])

    const stopStream = useCallback(async () => {
        console.log('[Player] Stopping stream...')

        // Stop the audio first
        if (soundRef.current) {
            soundRef.current.stop()
            soundRef.current.unload()
            soundRef.current = null
        }

        // Disconnect WebSocket
        wsManagerRef.current?.disconnect()

        // Tell backend to stop
        try {
            await api.stopStream()
        } catch {
            // Ignore errors
        }

        setState(s => ({
            ...s,
            isPlaying: false,
            sessionId: null,
            streamUrl: null,
            wsUrl: null,
            wsConnected: false,
            currentTrack: null,
        }))

        console.log('[Player] Stream stopped')
    }, [])

    // Internal function to execute mood switch (called by dialog confirm/cancel or directly)
    const executeMoodSwitch = useCallback(async (moodId: string, resume: boolean = false) => {
        console.log(`[Player] Executing mood switch to ${moodId}, resume=${resume}`)

        // Immediately update UI to show new mood is selected and we're loading
        setState(s => ({
            ...s,
            isLoading: true,
            error: null,
            activeMoodId: moodId,
            currentTrack: null,
            queue: [],
            feedback: null,
            currentStatus: null,
        }))

        // Save current position before switching (if playing)
        if (state.activeMoodId && state.sessionId && soundRef.current) {
            const currentPosition = soundRef.current.seek()
            if (typeof currentPosition === 'number' && currentPosition > 0) {
                const sessions = moodSessionsRef.current
                sessions.set(state.activeMoodId, {
                    moodId: state.activeMoodId,
                    sessionId: state.sessionId,
                    position: currentPosition,
                    timestamp: Date.now(),
                    trackTitle: state.currentTrack?.title,
                    trackArtist: state.currentTrack?.artist,
                    trackArtwork: state.currentTrack?.artworkUrl,
                })
                saveMoodSessions(sessions)
                console.log(`[Player] Saved position ${currentPosition}s for mood ${state.activeMoodId}`)
            }
        }

        // Stop current audio and WebSocket
        if (soundRef.current) {
            console.log('[Player] Stopping current audio for mood switch')
            soundRef.current.stop()
            soundRef.current.unload()
            soundRef.current = null
        }

        // Disconnect WebSocket
        wsManagerRef.current?.disconnect()

        // Tell backend to stop current stream
        if (state.sessionId) {
            api.stopStream().catch(() => { })
        }

        // Small delay to ensure cleanup is complete
        await new Promise(resolve => setTimeout(resolve, 150))

        // Start new stream with new mood
        console.log(`[Player] Starting new stream for mood: ${moodId}`)
        await startStream(moodId, resume)
    }, [startStream, state.activeMoodId, state.sessionId, state.currentTrack])

    const setActiveMood = useCallback(async (moodId: string, moodName?: string, moodColor?: string) => {
        console.log(`[Player] Switching to mood: ${moodId}`)

        // Clicking a mood pill is a user interaction!
        hasUserInteractedRef.current = true
        setHasUserInteractedState(true)

        // If same mood and session exists, just resume
        if (state.activeMoodId === moodId && state.sessionId) {
            console.log(`[Player] Same mood, resuming`)
            if (soundRef.current && !soundRef.current.playing()) {
                soundRef.current.play()
            }
            return
        }

        // Check if target mood has a saved session
        const savedSession = moodSessionsRef.current.get(moodId)
        if (savedSession && savedSession.position > 5) {
            // Show dialog to ask user if they want to resume or start fresh
            console.log(`[Player] Found saved session for mood ${moodId} at position ${savedSession.position}s`)
            setMoodSwitchDialog({
                open: true,
                moodId,
                moodName: moodName || 'this mood',
                moodColor: moodColor || '#888',
                savedPosition: savedSession.position,
                savedTrack: savedSession.trackTitle ? {
                    title: savedSession.trackTitle,
                    artist: savedSession.trackArtist || 'Unknown',
                    artworkUrl: savedSession.trackArtwork,
                } : null,
            })
            return
        }

        // No saved session, switch directly
        await executeMoodSwitch(moodId, false)
    }, [executeMoodSwitch, state.activeMoodId, state.sessionId])

    const confirmMoodSwitch = useCallback((resume: boolean) => {
        const { moodId } = moodSwitchDialog
        if (!moodId) return

        console.log(`[Player] User confirmed mood switch, resume=${resume}`)

        // Close dialog
        setMoodSwitchDialog(s => ({ ...s, open: false }))

        // Execute the switch
        executeMoodSwitch(moodId, resume)
    }, [moodSwitchDialog, executeMoodSwitch])

    const cancelMoodSwitch = useCallback(() => {
        console.log('[Player] User cancelled mood switch')
        setMoodSwitchDialog(s => ({ ...s, open: false }))
    }, [])

    const submitFeedback = useCallback(async (type: 'like' | 'dislike') => {
        if (!state.currentTrack) return

        setState(s => ({ ...s, feedback: type }))

        try {
            await api.submitFeedback({
                song_uuid: state.currentTrack.id,
                track_title: state.currentTrack.title,
                track_artist: state.currentTrack.artist,
                mood_id: state.activeMoodId || undefined,
                value: type,
            })
        } catch {
            // Silently fail - feedback is optimistic
        }
    }, [state.currentTrack, state.activeMoodId])

    return (
        <PlayerContext.Provider
            value={{
                ...state,
                play,
                pause,
                toggle,
                skip,
                setVolume,
                toggleMute,
                seek,
                setActiveMood,
                submitFeedback,
                startStream,
                stopStream,
                hasUserInteracted,
                setHasUserInteracted,
                wasPausedByBackground,
                isIOSPWA,
                moodSwitchDialog,
                confirmMoodSwitch,
                cancelMoodSwitch,
            }}
        >
            {children}
        </PlayerContext.Provider>
    )
}

export function usePlayer() {
    const context = useContext(PlayerContext)
    if (!context) {
        throw new Error('usePlayer must be used within a PlayerProvider')
    }
    return context
}
