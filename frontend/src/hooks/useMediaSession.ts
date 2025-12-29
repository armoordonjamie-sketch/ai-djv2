import { useEffect, useCallback, useRef } from 'react'
import type { Track } from '@/lib/types'

export interface MediaSessionMetadata {
    title: string
    artist: string
    album?: string
    artwork?: string
}

export interface MediaSessionHandlers {
    onPlay?: () => void
    onPause?: () => void
    onSeekBackward?: () => void
    onSeekForward?: () => void
    onPreviousTrack?: () => void
    onNextTrack?: () => void
    onSeekTo?: (time: number) => void
}

export interface UseMediaSessionOptions {
    metadata?: MediaSessionMetadata
    handlers?: MediaSessionHandlers
    enabled?: boolean
}

export function useMediaSession(options: UseMediaSessionOptions = {}) {
    const { metadata, handlers, enabled = true } = options
    const handlersRef = useRef(handlers)

    // Keep handlers ref updated
    useEffect(() => {
        handlersRef.current = handlers
    }, [handlers])

    // Check if Media Session API is supported
    const isSupported = typeof navigator !== 'undefined' && 'mediaSession' in navigator

    // Update metadata
    const updateMetadata = useCallback((newMetadata: MediaSessionMetadata) => {
        if (!isSupported || !enabled) return

        const artworkArray = newMetadata.artwork
            ? [
                { src: newMetadata.artwork, sizes: '96x96' },
                { src: newMetadata.artwork, sizes: '128x128' },
                { src: newMetadata.artwork, sizes: '256x256' },
                { src: newMetadata.artwork, sizes: '512x512' },
            ]
            : []

        navigator.mediaSession.metadata = new MediaMetadata({
            title: newMetadata.title,
            artist: newMetadata.artist,
            album: newMetadata.album || '',
            artwork: artworkArray,
        })
    }, [isSupported, enabled])

    // Set playback state
    const setPlaybackState = useCallback((state: 'playing' | 'paused' | 'none') => {
        if (!isSupported || !enabled) return
        navigator.mediaSession.playbackState = state
    }, [isSupported, enabled])

    // Set position state (for seek bar in lock screen)
    const setPositionState = useCallback((
        duration: number,
        position: number,
        playbackRate: number = 1
    ) => {
        if (!isSupported || !enabled) return
        if (!isFinite(duration) || duration <= 0) return

        try {
            navigator.mediaSession.setPositionState({
                duration,
                position: Math.min(position, duration),
                playbackRate,
            })
        } catch {
            // Some browsers may not support setPositionState
        }
    }, [isSupported, enabled])

    // Update metadata from Track object
    const updateFromTrack = useCallback((track: Track | null) => {
        if (!track) return

        updateMetadata({
            title: track.title,
            artist: track.artist,
            album: track.album,
            artwork: (track as any).artworkUrl || track.albumArt,
        })
    }, [updateMetadata])

    // Set up action handlers
    useEffect(() => {
        if (!isSupported || !enabled) return

        const actions: Array<[MediaSessionAction, () => void]> = [
            ['play', () => handlersRef.current?.onPlay?.()],
            ['pause', () => handlersRef.current?.onPause?.()],
            ['seekbackward', () => handlersRef.current?.onSeekBackward?.()],
            ['seekforward', () => handlersRef.current?.onSeekForward?.()],
            ['previoustrack', () => handlersRef.current?.onPreviousTrack?.()],
            ['nexttrack', () => handlersRef.current?.onNextTrack?.()],
        ]

        // Register handlers
        actions.forEach(([action, handler]) => {
            try {
                navigator.mediaSession.setActionHandler(action, handler)
            } catch {
                // Action not supported in this browser
            }
        })

        // Register seek handler separately (needs event parameter)
        try {
            navigator.mediaSession.setActionHandler('seekto', (event) => {
                if (event.seekTime !== undefined) {
                    handlersRef.current?.onSeekTo?.(event.seekTime)
                }
            })
        } catch {
            // seekto not supported
        }

        // Cleanup
        return () => {
            actions.forEach(([action]) => {
                try {
                    navigator.mediaSession.setActionHandler(action, null)
                } catch {
                    // Ignore
                }
            })
        }
    }, [isSupported, enabled])

    // Update metadata when it changes
    useEffect(() => {
        if (metadata) {
            updateMetadata(metadata)
        }
    }, [metadata, updateMetadata])

    return {
        isSupported,
        updateMetadata,
        updateFromTrack,
        setPlaybackState,
        setPositionState,
    }
}
