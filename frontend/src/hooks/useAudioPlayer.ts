import { useState, useRef, useCallback, useEffect } from 'react'

export interface AudioPlayerState {
    isPlaying: boolean
    isPaused: boolean
    isLoading: boolean
    currentTime: number
    duration: number
    volume: number
    isMuted: boolean
    error: string | null
    hasUserInteracted: boolean
}

export interface AudioPlayerControls {
    play: () => Promise<void>
    pause: () => void
    toggle: () => Promise<void>
    setVolume: (volume: number) => void
    mute: () => void
    unmute: () => void
    toggleMute: () => void
    seek: (time: number) => void
    seekPercent: (percent: number) => void
    setSource: (url: string) => void
}

export interface UseAudioPlayerReturn extends AudioPlayerState, AudioPlayerControls {
    audioRef: React.RefObject<HTMLAudioElement | null>
}

export function useAudioPlayer(initialSrc?: string): UseAudioPlayerReturn {
    const audioRef = useRef<HTMLAudioElement | null>(null)
    const [state, setState] = useState<AudioPlayerState>({
        isPlaying: false,
        isPaused: true,
        isLoading: false,
        currentTime: 0,
        duration: 0,
        volume: 1,
        isMuted: false,
        error: null,
        hasUserInteracted: false,
    })

    // Initialize audio element
    useEffect(() => {
        if (!audioRef.current) {
            audioRef.current = new Audio()
            audioRef.current.preload = 'metadata'
        }

        const audio = audioRef.current

        if (initialSrc) {
            audio.src = initialSrc
        }

        // Event handlers
        const handlePlay = () => {
            setState(prev => ({ ...prev, isPlaying: true, isPaused: false }))
        }

        const handlePause = () => {
            setState(prev => ({ ...prev, isPlaying: false, isPaused: true }))
        }

        const handleTimeUpdate = () => {
            setState(prev => ({ ...prev, currentTime: audio.currentTime }))
        }

        const handleDurationChange = () => {
            setState(prev => ({ ...prev, duration: audio.duration || 0 }))
        }

        const handleVolumeChange = () => {
            setState(prev => ({
                ...prev,
                volume: audio.volume,
                isMuted: audio.muted,
            }))
        }

        const handleLoadStart = () => {
            setState(prev => ({ ...prev, isLoading: true, error: null }))
        }

        const handleCanPlay = () => {
            setState(prev => ({ ...prev, isLoading: false }))
        }

        const handleError = () => {
            const error = audio.error?.message || 'Failed to load audio'
            setState(prev => ({ ...prev, isLoading: false, error }))
        }

        const handleEnded = () => {
            setState(prev => ({ ...prev, isPlaying: false, isPaused: true }))
        }

        // Attach event listeners
        audio.addEventListener('play', handlePlay)
        audio.addEventListener('pause', handlePause)
        audio.addEventListener('timeupdate', handleTimeUpdate)
        audio.addEventListener('durationchange', handleDurationChange)
        audio.addEventListener('volumechange', handleVolumeChange)
        audio.addEventListener('loadstart', handleLoadStart)
        audio.addEventListener('canplay', handleCanPlay)
        audio.addEventListener('error', handleError)
        audio.addEventListener('ended', handleEnded)

        return () => {
            audio.removeEventListener('play', handlePlay)
            audio.removeEventListener('pause', handlePause)
            audio.removeEventListener('timeupdate', handleTimeUpdate)
            audio.removeEventListener('durationchange', handleDurationChange)
            audio.removeEventListener('volumechange', handleVolumeChange)
            audio.removeEventListener('loadstart', handleLoadStart)
            audio.removeEventListener('canplay', handleCanPlay)
            audio.removeEventListener('error', handleError)
            audio.removeEventListener('ended', handleEnded)
        }
    }, [initialSrc])

    // Play (handles iOS autoplay restrictions)
    const play = useCallback(async () => {
        if (!audioRef.current) return

        try {
            setState(prev => ({ ...prev, hasUserInteracted: true }))
            await audioRef.current.play()
        } catch (err) {
            const error = err instanceof Error ? err.message : 'Playback failed'
            setState(prev => ({ ...prev, error }))
        }
    }, [])

    // Pause
    const pause = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause()
        }
    }, [])

    // Toggle play/pause
    const toggle = useCallback(async () => {
        if (state.isPlaying) {
            pause()
        } else {
            await play()
        }
    }, [state.isPlaying, play, pause])

    // Set volume (0-1)
    const setVolume = useCallback((volume: number) => {
        if (audioRef.current) {
            audioRef.current.volume = Math.max(0, Math.min(1, volume))
        }
    }, [])

    // Mute
    const mute = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.muted = true
        }
    }, [])

    // Unmute
    const unmute = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.muted = false
        }
    }, [])

    // Toggle mute
    const toggleMute = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.muted = !audioRef.current.muted
        }
    }, [])

    // Seek to specific time (seconds)
    const seek = useCallback((time: number) => {
        if (audioRef.current && isFinite(audioRef.current.duration)) {
            audioRef.current.currentTime = Math.max(0, Math.min(audioRef.current.duration, time))
        }
    }, [])

    // Seek to percentage (0-100)
    const seekPercent = useCallback((percent: number) => {
        if (audioRef.current && isFinite(audioRef.current.duration)) {
            const time = (percent / 100) * audioRef.current.duration
            audioRef.current.currentTime = time
        }
    }, [])

    // Set audio source
    const setSource = useCallback((url: string) => {
        if (audioRef.current) {
            audioRef.current.src = url
            audioRef.current.load()
        }
    }, [])

    return {
        // State
        ...state,
        // Controls
        play,
        pause,
        toggle,
        setVolume,
        mute,
        unmute,
        toggleMute,
        seek,
        seekPercent,
        setSource,
        // Ref
        audioRef,
    }
}

// Helper to format time in mm:ss
export function formatTime(seconds: number): string {
    if (!isFinite(seconds)) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
}
