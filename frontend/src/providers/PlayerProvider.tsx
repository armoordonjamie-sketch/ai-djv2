import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Howl } from 'howler'
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
    setActiveMood: (moodId: string) => Promise<void>
    submitFeedback: (type: 'like' | 'dislike') => Promise<void>
    startStream: (moodId?: string) => Promise<void>
    stopStream: () => Promise<void>
    // iOS/PWA Status
    hasUserInteracted: boolean
    setHasUserInteracted: (value: boolean) => void
    wasPausedByBackground: boolean
    isIOSPWA: boolean
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
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.disconnect()
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
    const [hasUserInteracted, setHasUserInteracted] = useState(false)

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
    })

    // Detect iOS PWA
    useEffect(() => {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
        const isStandalone = (window.navigator as any).standalone === true || window.matchMedia('(display-mode: standalone)').matches
        const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent)
        setIsIOSPWA(isIOS && (isStandalone || isSafari))
    }, [])

    // Handle visibility changes for background pause detection
    useEffect(() => {
        const handleVisibilityChange = () => {
            const isHidden = document.visibilityState === 'hidden'

            if (isHidden) {
                // Going to background
                if (state.isPlaying) {
                    wasPlayingRef.current = true
                }
            } else {
                // Coming to foreground
                // If we were playing but now we are paused, and we are on iOS PWA, it's a background pause
                if (wasPlayingRef.current && !state.isPlaying && isIOSPWA) {
                    setWasPausedByBackground(true)
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
                // Structured StatusEvent - update currentStatus for UI display
                const statusEvent = data as StatusEvent
                setState(s => ({ ...s, currentStatus: statusEvent }))
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
        if (!soundRef.current) return
        try {
            setHasUserInteracted(true)
            setWasPausedByBackground(false)
            soundRef.current.play()
        } catch (err) {
            console.error('[Player] Play failed:', err)
            setState(s => ({ ...s, error: 'Playback failed' }))
        }
    }, [])

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

    const startStream = useCallback(async (moodId?: string) => {
        setState(s => ({ ...s, isLoading: true, error: null, activeMoodId: moodId || s.activeMoodId }))

        try {
            const result = await api.startStream({ mood_id: moodId })

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
            const sound = new Howl({
                src: [streamUrl],
                html5: true, // Use HTML5 Audio for streaming (better for long files)
                format: ['mp3'], // Hint mechanism
                volume: state.volume,
                autoplay: hasUserInteracted, // Try to autoplay if we have interaction
                onplay: () => {
                    console.log('[Howler] Playing')
                    setState(s => ({ ...s, isPlaying: true, isLoading: false, error: null }))
                    setWasPausedByBackground(false)
                },
                onpause: () => {
                    console.log('[Howler] Paused')
                    setState(s => ({ ...s, isPlaying: false }))
                },
                onend: () => {
                    console.log('[Howler] Ended')
                    setState(s => ({ ...s, isPlaying: false }))
                },
                onstop: () => {
                    setState(s => ({ ...s, isPlaying: false }))
                },
                onload: () => {
                    console.log('[Howler] Loaded')
                    setState(s => ({ ...s, isLoading: false, duration: sound.duration() }))
                },
                onloaderror: (_id, err) => {
                    console.error('[Howler] Load error:', err)
                    setState(s => ({ ...s, isLoading: false, error: 'Stream load failed' }))
                },
                onplayerror: (_id, err) => {
                    console.warn('[Howler] Play error (autoplay blocked?):', err)
                    setState(s => ({ ...s, isPlaying: false }))
                    // Do NOT set error here, just stop playing state so UI shows Play button
                    // If it was an autoplay attempt, silence is fine, user will tap play

                    // Try to unlock audio context just in case
                    sound.once('unlock', () => {
                        sound.play()
                    })
                }
            })

            soundRef.current = sound
            if (hasUserInteracted) {
                sound.play()
            }

            // Map now_playing if provided
            const currentTrack = result.now_playing ? {
                id: result.now_playing.song_uuid,
                title: result.now_playing.title,
                artist: result.now_playing.artist,
                artworkUrl: result.now_playing.artwork_url,
            } : null

            setState(s => ({
                ...s,
                sessionId: result.session_id,
                streamUrl,
                wsUrl,
                currentTrack,
                isLoading: false,
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
    }, [hasUserInteracted, navigate, state.volume])

    const stopStream = useCallback(async () => {
        try {
            await api.stopStream()
        } catch {
            // Ignore errors
        }

        soundRef.current?.unload()
        wsManagerRef.current?.disconnect()

        setState(s => ({
            ...s,
            isPlaying: false,
            sessionId: null,
            streamUrl: null,
            wsUrl: null,
            wsConnected: false,
        }))
    }, [])

    const setActiveMood = useCallback(async (moodId: string) => {
        // Check if we have a saved session for this mood
        const savedSession = moodSessionsRef.current.get(moodId)
        
        // If same mood and session exists, just seek to saved position (resume)
        if (state.activeMoodId === moodId && state.sessionId) {
            if (savedSession && savedSession.position > 0) {
                console.log(`[Player] Resuming mood ${moodId} from position ${savedSession.position}s`)
                soundRef.current?.seek(savedSession.position)
            }
            return
        }

        // Save current position before switching
        if (state.activeMoodId && state.sessionId && soundRef.current) {
            const currentPosition = soundRef.current.seek()
            if (typeof currentPosition === 'number' && currentPosition > 0) {
                const sessions = moodSessionsRef.current
                sessions.set(state.activeMoodId, {
                    moodId: state.activeMoodId,
                    sessionId: state.sessionId,
                    position: currentPosition,
                    timestamp: Date.now(),
                })
                saveMoodSessions(sessions)
                console.log(`[Player] Saved position ${currentPosition}s for mood ${state.activeMoodId}`)
            }
        }

        // Stop current stream before starting new one
        if (state.sessionId && state.activeMoodId !== moodId) {
            console.log('[Player] Stopping current stream before mood switch')
            await stopStream()
        }

        // Start new stream with new mood
        await startStream(moodId)
        
        // After stream starts, seek to saved position if available
        if (savedSession && savedSession.position > 0) {
            // Wait a bit for stream to initialize
            setTimeout(() => {
                console.log(`[Player] Seeking to saved position ${savedSession.position}s for mood ${moodId}`)
                soundRef.current?.seek(savedSession.position)
            }, 1000)
        }
    }, [startStream, stopStream, state.activeMoodId, state.sessionId])

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
