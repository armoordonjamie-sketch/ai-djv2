"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Mic, MicOff, Loader2, CheckCircle, AlertCircle, ChevronLeft, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/providers/AuthProvider"
import { useConversation } from "@elevenlabs/react"
import { PreviewCard } from "@/components/player/PreviewCard"
import { useDucking } from "@/hooks/useDucking"
import * as api from "@/lib/jamifyApi"
import type { StatusEvent, StatusStep } from "@/lib/types"

type OnboardingState = "loading" | "ready" | "connecting" | "active" | "complete" | "error"

interface Message {
    id: string
    role: "user" | "agent"
    text: string
    isFinal: boolean
}

interface PreviewTrack {
    title: string
    artist: string
    artworkUrl?: string
    previewUrl?: string
    duration?: number
}

const voiceOnboardingSteps: StatusStep[] = [
    "mic_permission",
    "voice_capture",
    "voice_processing",
    "onboarding_complete",
]

export default function VoiceOnboardingPage() {
    const navigate = useNavigate()
    const { isOnboarded, user, checkOnboarding } = useAuth()
    const [state, setState] = useState<OnboardingState>("loading")
    const [error, setError] = useState<string | null>(null)
    const [messages, setMessages] = useState<Message[]>([])
    const pollingRef = useRef<NodeJS.Timeout | null>(null)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const messagesContainerRef = useRef<HTMLDivElement>(null)
    const isActiveRef = useRef(false)
    const wsRef = useRef<WebSocket | null>(null)
    const [wsStatus, setWsStatus] = useState<StatusEvent | null>(null)
    const [_completedSteps, setCompletedSteps] = useState<StatusStep[]>([])

    const [currentPreview, setCurrentPreview] = useState<PreviewTrack | null>(null)
    const [previewProgress, setPreviewProgress] = useState(0)
    const previewProgressRef = useRef<NodeJS.Timeout | null>(null)
    const isPreviewPlayingRef = useRef(false)
    const isSpeakingRef = useRef(false)
    const previewPlaybackPromiseRef = useRef<Promise<void> | null>(null)
    const conversationModeRef = useRef<{ mode: "speaking" | "listening" }>({ mode: "listening" })

    const ducking = useDucking({
        attackTime: 50,
        releaseTime: 300,
        duckLevel: 0.2,
        fullLevel: 1.0,
    })

    const [debugLogs, setDebugLogs] = useState<string[]>([])
    const isIOSRef = useRef(false)
    const isPWARef = useRef(false)

    const addLog = useCallback((msg: string) => {
        const time = new Date().toISOString().split("T")[1].slice(0, -1)
        setDebugLogs((prev) => [...prev.slice(-49), `[${time}] ${msg}`])
    }, [])

    const handleRetry = () => {
        handleStart()
    }

    const warmupCtxRef = useRef<AudioContext | null>(null)
    const warmupStreamRef = useRef<MediaStream | null>(null)
    const vadStreamRef = useRef<MediaStream | null>(null)
    const playbackSourceRef = useRef<AudioBufferSourceNode | null>(null)

    const isIOSDevice = typeof navigator !== "undefined" && /iPad|iPhone|iPod/.test(navigator.userAgent)
    const isStandalone =
        typeof window !== "undefined" &&
        (window.matchMedia("(display-mode: standalone)").matches || (window.navigator as any).standalone === true)
    const isIOSPWA = isIOSDevice && isStandalone
    const USE_TEXT_ONLY_FOR_IOS_PWA = false

    const stopPreview = useCallback((clearUI = true) => {
        const sourceToStop = playbackSourceRef.current
        playbackSourceRef.current = null

        if (sourceToStop) {
            try {
                sourceToStop.stop()
            } catch {
                // Already stopped
            }
        }
        if (previewProgressRef.current) {
            clearInterval(previewProgressRef.current)
            previewProgressRef.current = null
        }
        if (clearUI) {
            setCurrentPreview(null)
            setPreviewProgress(0)
        }
        isPreviewPlayingRef.current = false
        previewPlaybackPromiseRef.current = null
    }, [])

    /**
     * Internal function to play a preview from a URL.
     * Returns a Promise that resolves after a listening window (default 12s),
     * allowing the agent to ask for feedback while preview continues playing.
     */
    const playPreviewFromUrl = useCallback(async (
        previewUrl: string,
        trackTitle: string,
        artistName: string,
        artworkUrl?: string,
        listenWindowSeconds: number = 12
    ): Promise<void> => {
        // Stop any existing preview
        stopPreview(false)
        
        // CRITICAL: Wait for agent to finish speaking before starting preview
        if (isSpeakingRef.current || conversationModeRef.current.mode === "speaking") {
            console.log("[VoiceOnboarding] Agent is speaking, waiting for speech to finish...")
            const startWait = Date.now()
            const maxWait = 15000 // Increased max wait
            const minSilentMs = 600 // Increased silence requirement (600ms)
            
            // Wait for agent to enter listening mode
            while (Date.now() - startWait < maxWait) {
                const currentMode = conversationModeRef.current.mode
                if (!isSpeakingRef.current && currentMode === "listening") {
                    // Agent stopped speaking, wait for silence period
                    const silentStart = Date.now()
                    let silentDuration = 0
                    
                    while (Date.now() - startWait < maxWait && silentDuration < minSilentMs) {
                        await new Promise((resolve) => setTimeout(resolve, 50))
                        
                        // Check fresh state each iteration
                        const freshMode = conversationModeRef.current.mode
                        if (isSpeakingRef.current || freshMode === "speaking") {
                            // Agent started speaking again, reset
                            break
                        }
                        silentDuration = Date.now() - silentStart
                    }
                    
                    if (silentDuration >= minSilentMs) {
                        console.log("[VoiceOnboarding] Agent finished speaking, proceeding with preview")
                        break
                    }
                }
                await new Promise((resolve) => setTimeout(resolve, 100))
            }
            
            // Additional small pause after TTS to ensure audio buffers are clear
            await new Promise((resolve) => setTimeout(resolve, 300))
        }

        const ctx = ducking.getContext()
        const duckingGain = ducking.getGainNode()

        if (!ctx || ctx.state === "closed") {
            throw new Error("Audio system not initialized")
        }

        console.log(`[VoiceOnboarding] Using ducking AudioContext (state: ${ctx.state})`)

        if (ctx.state === "suspended") {
            console.log("[VoiceOnboarding] Resuming suspended context...")
            await ctx.resume()
        }

        // Set preview volume to match agent voice level (75% for balanced mix)
        // Music previews should be slightly quieter than speech for clarity
        const previewVolume = 0.90 // 75% volume to match agent voice level
        const duckingGainNode = ducking.getGainNode()
        if (duckingGainNode && ctx) {
            // Cancel any scheduled ramps and set to balanced volume
            duckingGainNode.gain.cancelScheduledValues(ctx.currentTime)
            duckingGainNode.gain.setValueAtTime(previewVolume, ctx.currentTime)
            console.log(`[VoiceOnboarding] Set ducking gain to ${previewVolume} (75%) for balanced preview volume`)
        } else {
            // Fallback: use release() method, then adjust
            ducking.release()
            console.log("[VoiceOnboarding] Released ducking, will adjust volume")
            // Wait for ducking release to complete, then set to preview volume
            await new Promise((resolve) => setTimeout(resolve, 350))
            if (duckingGainNode && ctx) {
                duckingGainNode.gain.cancelScheduledValues(ctx.currentTime)
                duckingGainNode.gain.setValueAtTime(previewVolume, ctx.currentTime)
            }
        }

        setCurrentPreview({
            title: trackTitle,
            artist: artistName,
            artworkUrl,
            previewUrl,
        })
        isPreviewPlayingRef.current = true

        console.log("[VoiceOnboarding] Fetching audio data...")
        const response = await fetch(previewUrl)
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`)
        }
        const arrayBuffer = await response.arrayBuffer()
        console.log(`[VoiceOnboarding] Got ${arrayBuffer.byteLength} bytes, decoding...`)

        const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
        const duration = audioBuffer.duration
        
        // Use full 30s preview (Spotify previews are typically 30s)
        const previewDuration = Math.min(duration, 30)
        console.log(
            `[VoiceOnboarding] Decoded: ${duration.toFixed(1)}s, ${audioBuffer.numberOfChannels}ch, playing ${previewDuration.toFixed(1)}s`,
        )

        if ((ctx.state as string) === "closed") {
            throw new Error("Context was closed during fetch/decode")
        }

        setCurrentPreview((prev) => (prev ? { ...prev, duration: previewDuration } : null))

        const source = ctx.createBufferSource()
        source.buffer = audioBuffer

        // Connect preview through ducking gain node (so it can be ducked when agent speaks)
        if (duckingGain) {
            source.connect(duckingGain)
        } else {
            source.connect(ctx.destination)
        }

        playbackSourceRef.current = source

        // Progress tracking
        const startTime = ctx.currentTime
        previewProgressRef.current = setInterval(() => {
            if (ctx && playbackSourceRef.current) {
                const elapsed = ctx.currentTime - startTime
                const progress = previewDuration > 0 ? Math.min(elapsed / previewDuration, 1) : 1
                setPreviewProgress(progress)
            }
        }, 100)

        // Set up playback completion handler (for cleanup when preview ends)
        const thisSource = source
        source.onended = () => {
            if (playbackSourceRef.current === thisSource) {
                console.log("[VoiceOnboarding] Preview finished naturally")
                stopPreview()
            } else {
                console.log("[VoiceOnboarding] Old preview stopped (switching songs)")
            }
        }

        // Suppress agent audio during initial preview playback
        ducking.setAgentSpeaking(false) // Ensure agent doesn't speak during preview

        console.log("[VoiceOnboarding] Starting playback...")
        source.start(0, 0, previewDuration)
        console.log("[VoiceOnboarding] Playback started, will return after listening window...")

        // Wait for listening window (e.g., 12 seconds) then return
        // This allows agent to ask for feedback while preview continues playing
        const actualListenWindow = Math.min(listenWindowSeconds, previewDuration)
        await new Promise((resolve) => setTimeout(resolve, actualListenWindow * 1000))
        
        console.log(`[VoiceOnboarding] Listening window complete (${actualListenWindow}s), returning to agent`)
        // Preview continues playing in background - agent can now ask for feedback
    }, [ducking, stopPreview])

    const conversation = useConversation({
        textOnly: USE_TEXT_ONLY_FOR_IOS_PWA && isIOSPWA,
        preferHeadphonesForIosDevices: isIOSDevice,
        connectionDelay: {
            ios: 1500,
            android: 3000,
            default: 0,
        },
        onConnect: async () => {
            timestampsRef.current.onConnectTime = Date.now()
            const connectDelay = timestampsRef.current.onConnectTime - (timestampsRef.current.startSessionTime || 0)
            addLog(`EVENT: onConnect (ElevenLabs, delay: ${connectDelay}ms)`)
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current)
                timeoutRef.current = null
            }
            isActiveRef.current = true
            setState("active")
            setCompletedSteps((prev) => [...prev, "mic_permission" as StatusStep])
            startPolling()

            try {
                const vadStream = await navigator.mediaDevices.getUserMedia({
                    audio: { echoCancellation: true, noiseSuppression: true },
                    video: false,
                })
                vadStreamRef.current = vadStream
                ducking.startVAD(vadStream)
                addLog("EVENT: VAD started for user speech detection")
            } catch (vadErr) {
                addLog(`EVENT: VAD start failed (non-critical): ${vadErr}`)
            }

            setTimeout(() => {
                if (warmupStreamRef.current) {
                    warmupStreamRef.current.getTracks().forEach((t) => t.stop())
                    warmupStreamRef.current = null
                    addLog("EVENT: Released warmup stream (delayed)")
                }
                if (warmupCtxRef.current) {
                    warmupCtxRef.current.close().catch(() => { })
                    warmupCtxRef.current = null
                    addLog("EVENT: Closed warmup AudioContext (delayed)")
                }
            }, 3000)
        },
        onDisconnect: () => {
            addLog("EVENT: onDisconnect")
            stopPreview()
            ducking.stopVAD()
            if (vadStreamRef.current) {
                vadStreamRef.current.getTracks().forEach((t) => t.stop())
                vadStreamRef.current = null
            }
            if (isActiveRef.current || state === "connecting") {
                isActiveRef.current = false
                setError("Connection lost. Please try again.")
                setState("error")
            }
        },
        onMessage: (message) => {
            const msgStr = typeof message === "string" ? message : JSON.stringify(message)
            addLog(`EVENT: onMessage (${msgStr.length} chars)`)

            if (typeof message === "object" && message !== null && "message" in message) {
                const msg = message as { source?: string; message: string }
                const role = msg.source === "user" ? "user" : "agent"

                setMessages((prev) => {
                    return [
                        ...prev,
                        {
                            id: `${Date.now()}-${role}`,
                            role,
                            text: msg.message,
                            isFinal: true,
                        },
                    ]
                })
            }
        },
        onError: (error) => {
            addLog(`EVENT: onError: ${JSON.stringify(error)}`)
            const errorMsg = typeof error === "string" ? error : "Connection error"
            if (state !== "error") {
                setError(errorMsg)
                isActiveRef.current = false
                setState("error")
            }
        },
        onModeChange: (mode) => {
            addLog(`EVENT: onModeChange: ${JSON.stringify(mode)}`)
            setConversationMode(mode)
            conversationModeRef.current = mode
            // Only set agent speaking if preview is not playing
            // During preview playback, we want to suppress agent audio
            if (!isPreviewPlayingRef.current) {
                ducking.setAgentSpeaking(mode.mode === "speaking")
            }
            isSpeakingRef.current = mode.mode === "speaking"
        },
        onStatusChange: (status) => {
            console.log("[VoiceOnboarding] onStatusChange:", status)
            if (!timestampsRef.current.firstStatusChangeTime) {
                timestampsRef.current.firstStatusChangeTime = Date.now()
                const statusDelay = timestampsRef.current.firstStatusChangeTime - (timestampsRef.current.startSessionTime || 0)
                addLog(`EVENT: onStatusChange (first, delay: ${statusDelay}ms): ${JSON.stringify(status)}`)
            } else {
                addLog(`EVENT: onStatusChange: ${JSON.stringify(status)}`)
            }
        },
        onDebug: (info) => {
            console.log("[VoiceOnboarding] SDK_DEBUG:", info)
            addLog(`SDK_DEBUG: ${typeof info === "string" ? info : JSON.stringify(info)}`)
        },
        clientTools: {
            play_song_preview: async ({ artist_name, track_title }: { artist_name: string; track_title: string }) => {
                console.log(`[VoiceOnboarding] play_song_preview called: ${track_title} by ${artist_name}`)
                try {
                    const res = await api.playPreview(artist_name, track_title)

                    if (res.preview_url) {
                        const previewUrl = res.preview_url
                        console.log(`[VoiceOnboarding] Got preview URL: ${previewUrl}`)
                        console.log(`[VoiceOnboarding] Got artwork URL: ${res.artwork_url}`)

                        try {
                            // Use the shared playback function with 12-second listening window
                            await playPreviewFromUrl(
                                previewUrl,
                                res.track_title || track_title,
                                res.artist_name || artist_name,
                                res.artwork_url,
                                12 // 12-second listening window before agent can ask
                            )
                            
                            return `Previewed "${res.track_title}" for 12 seconds. Ask the user what they think.`
                        } catch (playError: any) {
                            console.error(
                                "[VoiceOnboarding] Play error:",
                                playError?.name || playError?.constructor?.name,
                                playError?.message,
                            )
                            stopPreview()
                            return `I tried to play ${res.track_title} by ${res.artist_name}, but audio playback failed. Let's continue.`
                        }
                    } else {
                        return `Could not find a preview for ${track_title}.`
                    }
                } catch (err) {
                    console.error("[VoiceOnboarding] API error:", err)
                    return "Error trying to play preview."
                }
            },

            wait_for_listening: async ({ seconds }: { seconds: number }) => {
                console.log(`[VoiceOnboarding] wait_for_listening called: ${seconds} seconds`)
                const waitTime = Math.min(Math.max(seconds, 3), 30) * 1000
                await new Promise((resolve) => setTimeout(resolve, waitTime))
                console.log(`[VoiceOnboarding] wait_for_listening complete`)
                return `Waited ${seconds} seconds. The user has had time to listen. Now ask for their feedback.`
            },
        },
    })

    const [conversationMode, setConversationMode] = useState<{ mode: "speaking" | "listening" }>({ mode: "listening" })

    useEffect(() => {
        return () => {
            stopPreview()
            ducking.stopVAD()
            if (vadStreamRef.current) {
                vadStreamRef.current.getTracks().forEach((t) => t.stop())
                vadStreamRef.current = null
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    const initialCheckDoneRef = useRef(false)

    useEffect(() => {
        if (initialCheckDoneRef.current) return
        initialCheckDoneRef.current = true

        async function checkStatus() {
            if (isOnboarded) {
                navigate("/player", { replace: true })
                return
            }

            try {
                const status = await api.getOnboardStatus()
                if (!status.has_spotify) {
                    navigate("/connect-spotify", { replace: true })
                    return
                }

                if (status.onboarded) {
                    navigate("/player", { replace: true })
                } else if (status.has_profile) {
                    navigate("/creating-moods", { replace: true })
                } else {
                    setState("ready")
                }
            } catch {
                setError("Failed to check onboarding status")
                setState("error")
            }
        }
        checkStatus()
    }, [isOnboarded, navigate])

    const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null)

    useEffect(() => {
        // Clear any pending scroll
        if (scrollTimeoutRef.current) {
            clearTimeout(scrollTimeoutRef.current)
        }

        // Debounce scroll to allow animation to complete
        scrollTimeoutRef.current = setTimeout(() => {
            requestAnimationFrame(() => {
                if (messagesEndRef.current) {
                    messagesEndRef.current.scrollIntoView({
                        behavior: "smooth",
                        block: "end",
                    })
                }
            })
        }, 100) // Small delay to let animation start

        return () => {
            if (scrollTimeoutRef.current) {
                clearTimeout(scrollTimeoutRef.current)
            }
        }
    }, [messages])

    const wsInitializedRef = useRef(false)

    useEffect(() => {
        if (wsInitializedRef.current) return
        wsInitializedRef.current = true

        const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/v1/ws`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => addLog("WS: Connected to Backend")
        ws.onerror = () => addLog("WS: Error")

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data)
                if (msg.type === "status") {
                    const statusEvent = msg.data as StatusEvent
                    if (statusEvent.category === "onboarding") {
                        setWsStatus(statusEvent)
                        if (statusEvent.step === "voice_processing") {
                            setCompletedSteps((prev) =>
                                prev.includes("voice_capture") ? prev : [...prev, "voice_capture" as StatusStep],
                            )
                        }
                        if (statusEvent.step === "onboarding_complete") {
                            setCompletedSteps((prev) => [
                                ...new Set([...prev, "voice_capture" as StatusStep, "voice_processing" as StatusStep]),
                            ])
                        }
                    }
                }
            } catch {
                // Ignore parse errors
            }
        }

        return () => {
            ws.close()
            wsInitializedRef.current = false
        }
    }, [addLog])

    useEffect(() => {
        const handleDeviceChange = () => {
            addLog("EVENT: navigator.mediaDevices.ondevicechange")
            if (isActiveRef.current || state === "connecting") {
                addLog("WARNING: Device change detection during active session")
            }
        }

        navigator.mediaDevices.addEventListener("devicechange", handleDeviceChange)
        return () => {
            navigator.mediaDevices.removeEventListener("devicechange", handleDeviceChange)
        }
    }, [addLog, state])

    const timeoutRef = useRef<NodeJS.Timeout | null>(null)

    const timestampsRef = useRef<{
        clickTime?: number
        permissionTime?: number
        startSessionTime?: number
        firstStatusChangeTime?: number
        onConnectTime?: number
    }>({})

    const cleanupResources = useCallback(() => {
        addLog("CLEANUP: Starting resource cleanup")

        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current)
            timeoutRef.current = null
        }

        stopPreview()

        if (warmupStreamRef.current) {
            warmupStreamRef.current.getTracks().forEach((t) => t.stop())
            warmupStreamRef.current = null
            addLog("CLEANUP: Released warmup stream")
        }
        if (warmupCtxRef.current) {
            warmupCtxRef.current.close().catch(() => { })
            warmupCtxRef.current = null
            addLog("CLEANUP: Closed warmup AudioContext")
        }

        conversation.endSession().catch(() => { })
    }, [conversation, addLog, stopPreview])

    const handleStart = async () => {
        try {
            timestampsRef.current = { clickTime: Date.now() }
            setError(null)
            setState("connecting")

            isIOSRef.current = isIOSDevice
            isPWARef.current = isStandalone
            addLog(`START: iOS=${isIOSDevice}, PWA=${isStandalone}, isIOSPWA=${isIOSPWA}`)

            if (isIOSPWA) {
                addLog("iOS PWA: Starting audio warmup sequence...")
                try {
                    const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
                    warmupCtxRef.current = audioCtx
                    addLog(`iOS PWA: Created warmup AudioContext (state: ${audioCtx.state})`)

                    if (audioCtx.state === "suspended") {
                        await audioCtx.resume()
                        addLog(`iOS PWA: Resumed warmup AudioContext (state: ${audioCtx.state})`)
                    }

                    const oscillator = audioCtx.createOscillator()
                    const silentGain = audioCtx.createGain()
                    silentGain.gain.value = 0
                    oscillator.connect(silentGain)
                    silentGain.connect(audioCtx.destination)
                    oscillator.start()
                    oscillator.stop(audioCtx.currentTime + 0.001)
                    addLog("iOS PWA: Played silent audio to unlock AudioContext")

                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true,
                        },
                        video: false,
                    })
                    warmupStreamRef.current = stream
                    timestampsRef.current.permissionTime = Date.now()
                    addLog(`iOS PWA: Got warmup microphone stream (${stream.getAudioTracks().length} tracks)`)
                } catch (warmupErr: any) {
                    addLog(`iOS PWA: Warmup error (continuing anyway): ${warmupErr?.message || warmupErr}`)
                }

                addLog("iOS PWA: Starting ElevenLabs session with warmup complete...")
            }

            timestampsRef.current.startSessionTime = Date.now()
            addLog(`Calling conversation.startSession()...`)

            timeoutRef.current = setTimeout(() => {
                if (state === "connecting" && !isActiveRef.current) {
                    addLog("ERROR: Connection timeout after 30s")
                    setError("Connection timed out. Check your network and try again.")
                    setState("error")
                    cleanupResources()
                }
            }, 30000)

            if (isIOSPWA) {
                const tokenResp = await api.getConversationToken()
                addLog(`Got conversation token (${tokenResp.token.length} chars), calling startSession...`)
                await conversation.startSession({
                    conversationToken: tokenResp.token,
                    dynamicVariables: {
                        user_id: user?.id || 'anonymous',
                    },
                })
            } else {
                const onboardResp = await api.startOnboarding()
                addLog(`Got signed URL (${onboardResp.signed_url.length} chars), calling startSession...`)
                await conversation.startSession({
                    signedUrl: onboardResp.signed_url,
                    dynamicVariables: {
                        user_id: user?.id || 'anonymous',
                    },
                })
            }
            addLog(`startSession() returned successfully`)
        } catch (err: any) {
            addLog(`ERROR in handleStart: ${err?.message || err}`)
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current)
                timeoutRef.current = null
            }
            cleanupResources()
            setError(err?.message || "Failed to start conversation")
            setState("error")
        }
    }

    const handleEnd = useCallback(async () => {
        try {
            addLog("USER: Ending conversation")
            isActiveRef.current = false
            cleanupResources()
            setState("complete")
        } catch {
            // Ignore errors on end
        }
    }, [addLog, cleanupResources])

    const pollingStartedRef = useRef(false)
    const completedRef = useRef(false)

    const startPolling = useCallback(() => {
        if (pollingStartedRef.current) return
        pollingStartedRef.current = true

        let attempts = 0
        const maxAttempts = 60
        let currentInterval = 3000

        const poll = async () => {
            try {
                if (completedRef.current || state === "error") {
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                        pollingRef.current = null
                    }
                    return
                }

                const status = await api.getOnboardStatus()

                if (status.has_profile) {
                    completedRef.current = true
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                        pollingRef.current = null
                    }
                    setCompletedSteps(voiceOnboardingSteps)
                    await checkOnboarding()

                    setTimeout(async () => {
                        try {
                            await conversation.endSession()
                        } catch { }
                        stopPreview()
                        navigate("/creating-moods", { replace: true })
                    }, 2000)
                    return
                }

                attempts++
                if (attempts >= maxAttempts) {
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                        pollingRef.current = null
                    }
                    return
                }

                if (attempts === 10) {
                    currentInterval = 10000
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                    }
                    pollingRef.current = setInterval(poll, currentInterval)
                } else if (attempts === 20) {
                    currentInterval = 15000
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                    }
                    pollingRef.current = setInterval(poll, currentInterval)
                }
            } catch {
                // Continue polling on errors
            }
        }

        pollingRef.current = setInterval(poll, currentInterval)
    }, [navigate, conversation, checkOnboarding, stopPreview])

    useEffect(() => {
        return () => {
            if (pollingRef.current) {
                clearInterval(pollingRef.current)
                pollingRef.current = null
            }
            pollingStartedRef.current = false
            completedRef.current = false
        }
    }, [])

    const isSpeaking = conversation.isSpeaking

    const showDebug = typeof window !== "undefined" && new URLSearchParams(window.location.search).has("debug")

    return (
        <div
            className="min-h-screen bg-background text-foreground relative overflow-hidden"
            style={{ minHeight: "var(--app-height)", height: "var(--app-height)" }}
        >
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute -top-32 right-[-10%] h-64 w-64 rounded-full bg-primary/15 blur-3xl" />
                <div className="absolute bottom-[-10%] left-[-10%] h-72 w-72 rounded-full bg-accent/10 blur-3xl" />
            </div>

            <div
                className="relative h-full flex flex-col"
                style={{
                    paddingTop: "calc(env(safe-area-inset-top, 0px) + 8px)",
                    paddingBottom: "env(safe-area-inset-bottom, 0px)",
                }}
            >
                <header className="flex-shrink-0 z-30 px-4 pt-2">
                    <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                            {state === "active" ? (
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={handleEnd}
                                    className="w-10 h-10 rounded-full bg-surface-2/80 hover:bg-surface-3 border border-white/5"
                                    aria-label="End conversation"
                                >
                                    <ChevronLeft className="w-5 h-5" />
                                </Button>
                            ) : (
                                <div className="w-10 h-10 rounded-full gradient-bg flex items-center justify-center shadow-lg shadow-primary/20">
                                    <Mic className="w-5 h-5 text-white" />
                                </div>
                            )}
                            <div>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Voice Setup</p>
                                <h1 className="text-base font-semibold">AI DJ Onboarding</h1>
                            </div>
                        </div>

                        <AnimatePresence mode="wait">
                            {state === "active" && (
                                <motion.div
                                    key={isSpeaking ? "speaking" : "listening"}
                                    initial={{ opacity: 0, scale: 0.9 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.9 }}
                                    className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${isSpeaking ? "bg-primary/15 text-primary" : "bg-success/15 text-success"
                                        }`}
                                >
                                    {isSpeaking ? (
                                        <>
                                            <VoiceWaveform />
                                            <span className="text-xs font-medium">DJ Speaking</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="relative flex h-2 w-2">
                                                <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-75 animate-ping" />
                                                <span className="relative inline-flex rounded-full h-2 w-2 bg-success" />
                                            </span>
                                            <span className="text-xs font-medium">Listening</span>
                                        </>
                                    )}
                                </motion.div>
                            )}
                            {state === "connecting" && (
                                <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-warning/15 text-warning"
                                >
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                    <span className="text-xs font-medium">Connecting</span>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </header>

                {/* Content */}
                <main className="relative flex-1 overflow-hidden min-h-0 flex flex-col">
                    {/* DEBUG CONSOLE OVERLAY */}
                    {showDebug && (
                        <div className="absolute top-0 left-0 right-0 h-64 bg-black/90 text-[10px] font-mono text-green-400 p-2 overflow-y-auto z-50 opacity-90 border-b border-green-900">
                            <div className="flex justify-between border-b border-green-800 pb-1 mb-1">
                                <span>DEBUG LOG</span>
                                <span className="text-gray-400">
                                    iOS:{String(isIOSRef.current)} PWA:{String(isPWARef.current)}
                                </span>
                            </div>
                            {timestampsRef.current.clickTime && (
                                <div className="border-b border-green-800 pb-1 mb-1 text-yellow-400">
                                    <div>Timestamps:</div>
                                    <div>
                                        Click → Permission:{" "}
                                        {timestampsRef.current.permissionTime
                                            ? `${timestampsRef.current.permissionTime - timestampsRef.current.clickTime}ms`
                                            : "pending"}
                                    </div>
                                    <div>
                                        Permission → startSession:{" "}
                                        {timestampsRef.current.startSessionTime
                                            ? `${timestampsRef.current.startSessionTime - (timestampsRef.current.permissionTime || timestampsRef.current.clickTime)}ms`
                                            : "pending"}
                                    </div>
                                    <div>
                                        startSession → statusChange:{" "}
                                        {timestampsRef.current.firstStatusChangeTime
                                            ? `${timestampsRef.current.firstStatusChangeTime - (timestampsRef.current.startSessionTime || 0)}ms`
                                            : "pending"}
                                    </div>
                                    <div>
                                        startSession → onConnect:{" "}
                                        {timestampsRef.current.onConnectTime
                                            ? `${timestampsRef.current.onConnectTime - (timestampsRef.current.startSessionTime || 0)}ms`
                                            : "pending"}
                                    </div>
                                </div>
                            )}
                            {debugLogs.map((log, i) => (
                                <div key={i} className="whitespace-pre-wrap mb-1">
                                    {log}
                                </div>
                            ))}
                        </div>
                    )}

                    {state === "loading" && (
                        <div className="flex-1 flex items-center justify-center px-6">
                            <div className="flex items-center gap-3 px-5 py-4 rounded-2xl bg-surface-2/50 border border-white/5">
                                <Loader2 className="w-5 h-5 animate-spin text-primary" />
                                <div className="text-left">
                                    <p className="text-sm font-medium">Preparing session</p>
                                    <p className="text-xs text-muted-foreground">Checking your profile</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {state === "ready" && (
                        <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="flex-1 flex flex-col items-center justify-center px-6 pb-8"
                        >
                            <div className="w-full max-w-sm space-y-8">
                                {/* Hero visual */}
                                <div className="relative flex justify-center">
                                    <motion.div
                                        className="absolute -inset-8 rounded-full bg-primary/10 blur-2xl"
                                        animate={{ scale: [1, 1.1, 1], opacity: [0.3, 0.5, 0.3] }}
                                        transition={{ duration: 4, repeat: Number.POSITIVE_INFINITY }}
                                    />
                                    <motion.div
                                        animate={{ scale: [1, 1.02, 1] }}
                                        transition={{ duration: 2.5, repeat: Number.POSITIVE_INFINITY }}
                                        className="relative w-28 h-28 rounded-full gradient-bg flex items-center justify-center shadow-xl shadow-primary/30"
                                    >
                                        <Mic className="w-12 h-12 text-white" />
                                    </motion.div>
                                </div>

                                {/* Copy */}
                                <div className="text-center space-y-2">
                                    <h2 className="text-2xl font-semibold text-balance">Tell us your taste</h2>
                                    <p className="text-muted-foreground text-sm text-pretty leading-relaxed">
                                        Have a quick conversation with your AI DJ about your favorite artists, genres, and the vibe you
                                        want.
                                    </p>
                                </div>

                                {/* Steps preview - minimal */}
                                <div className="flex items-center justify-center gap-3 py-3">
                                    {["Mic access", "Conversation", "Profile created"].map((step, i) => (
                                        <div key={step} className="flex items-center gap-2">
                                            <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" />
                                            <span className="text-xs text-muted-foreground">{step}</span>
                                            {i < 2 && <div className="w-4 h-px bg-border" />}
                                        </div>
                                    ))}
                                </div>

                                {/* CTA */}
                                <div className="space-y-3">
                                    <Button
                                        onClick={handleStart}
                                        className="w-full h-14 text-base font-semibold gradient-bg shadow-lg shadow-primary/20 touch-target rounded-2xl"
                                    >
                                        <Mic className="w-5 h-5 mr-2" />
                                        Start Conversation
                                    </Button>
                                    <p className="text-center text-[11px] text-muted-foreground">Takes about 1-2 minutes</p>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {state === "connecting" && (
                        <div className="flex-1 flex items-center justify-center px-6">
                            <motion.div
                                initial={{ opacity: 0, scale: 0.98 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="text-center space-y-6 max-w-xs"
                            >
                                <div className="relative w-20 h-20 mx-auto">
                                    <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl animate-pulse" />
                                    <div className="relative w-full h-full rounded-full bg-surface-2 border border-white/10 flex items-center justify-center">
                                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-sm font-medium">Connecting to your AI DJ</p>
                                    <p className="text-xs text-muted-foreground">This may take a moment...</p>
                                </div>
                            </motion.div>
                        </div>
                    )}

                    {state === "active" && (
                        <div className="flex-1 flex flex-col min-h-0 px-4 pt-4 gap-3">
                            {/* Chat container - takes remaining space */}
                            <div className="flex-1 min-h-0 rounded-2xl bg-surface-1/50 border border-white/5 overflow-hidden flex flex-col">
                                <div
                                    ref={messagesContainerRef}
                                    className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scroll-container scrollbar-hide"
                                >
                                    {messages.length === 0 && (
                                        <div className="flex items-center justify-center h-full">
                                            <div className="text-center space-y-2 py-8">
                                                <Sparkles className="w-8 h-8 mx-auto text-muted-foreground/50" />
                                                <p className="text-sm text-muted-foreground">Your AI DJ will start speaking soon...</p>
                                            </div>
                                        </div>
                                    )}
                                    {messages
                                        .filter((m) => m.isFinal)
                                        .map((msg) => (
                                            <motion.div
                                                key={msg.id}
                                                initial={{ opacity: 0, y: 8 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                transition={{ duration: 0.2 }}
                                                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                                            >
                                                <div
                                                    className={`max-w-[80%] px-4 py-3 text-sm leading-relaxed ${msg.role === "user"
                                                        ? "bg-primary text-primary-foreground rounded-2xl rounded-br-md"
                                                        : "bg-surface-2 border border-white/5 rounded-2xl rounded-bl-md"
                                                        }`}
                                                >
                                                    {msg.text}
                                                </div>
                                            </motion.div>
                                        ))}
                                    {wsStatus && (
                                        <motion.div
                                            key={wsStatus.id}
                                            initial={{ opacity: 0, y: 5 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="flex justify-center"
                                        >
                                            <div className="px-3 py-1.5 rounded-full bg-surface-2/80 border border-white/5 text-primary text-xs flex items-center gap-2">
                                                <Loader2 className="w-3 h-3 animate-spin" />
                                                {wsStatus.user_message}
                                            </div>
                                        </motion.div>
                                    )}
                                    <div ref={messagesEndRef} className="h-1" />
                                </div>
                            </div>

                            {/* Preview card - fixed position above control bar */}
                            <AnimatePresence>
                                {currentPreview && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: 10 }}
                                    >
                                        <PreviewCard
                                            track={currentPreview}
                                            isPlaying={isPreviewPlayingRef.current}
                                            progress={previewProgress}
                                            isDucked={conversationMode.mode === "speaking"}
                                            onDismiss={stopPreview}
                                            onReplay={currentPreview?.previewUrl ? async () => {
                                                // Replay the same preview
                                                if (currentPreview.previewUrl) {
                                                    console.log(`[VoiceOnboarding] Replay requested for ${currentPreview.title} by ${currentPreview.artist}`)
                                                    try {
                                                        await playPreviewFromUrl(
                                                            currentPreview.previewUrl,
                                                            currentPreview.title,
                                                            currentPreview.artist,
                                                            currentPreview.artworkUrl,
                                                            12 // 12-second listening window
                                                        )
                                                    } catch (err) {
                                                        console.error("[VoiceOnboarding] Replay error:", err)
                                                    }
                                                }
                                            } : undefined}
                                        />
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            <div className="flex-shrink-0 pb-4">
                                <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-2xl bg-surface-2/50 border border-white/5">
                                    <p className="text-xs text-muted-foreground">
                                        Say <span className="text-foreground font-medium">"I'm done"</span> when finished
                                    </p>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleEnd}
                                        className="rounded-full text-destructive hover:text-destructive hover:bg-destructive/10 px-4"
                                    >
                                        <MicOff className="w-4 h-4 mr-2" />
                                        End
                                    </Button>
                                </div>
                            </div>
                        </div>
                    )}

                    {state === "complete" && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="flex-1 flex items-center justify-center px-6"
                        >
                            <div className="text-center max-w-xs space-y-6">
                                <motion.div
                                    initial={{ scale: 0 }}
                                    animate={{ scale: 1 }}
                                    transition={{ type: "spring", stiffness: 200, damping: 15 }}
                                    className="w-20 h-20 rounded-full bg-success/20 flex items-center justify-center mx-auto"
                                >
                                    <CheckCircle className="w-10 h-10 text-success" />
                                </motion.div>
                                <div className="space-y-2">
                                    <h2 className="text-xl font-semibold">All set!</h2>
                                    <p className="text-muted-foreground text-sm">Creating your personalized moods...</p>
                                </div>
                                <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                                    <span>Building your first mix</span>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {state === "error" && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="flex-1 flex items-center justify-center px-6"
                        >
                            <div className="text-center max-w-sm w-full space-y-6">
                                <div className="w-16 h-16 rounded-full bg-destructive/20 flex items-center justify-center mx-auto">
                                    <AlertCircle className="w-8 h-8 text-destructive" />
                                </div>
                                <div className="space-y-2">
                                    <h2 className="text-lg font-semibold">Something went wrong</h2>
                                    <p className="text-muted-foreground text-sm">{error}</p>
                                </div>
                                <div className="flex flex-col gap-3">
                                    <Button onClick={handleRetry} className="gradient-bg w-full touch-target rounded-xl">
                                        Try Again
                                    </Button>
                                    {isPWARef.current && isIOSRef.current && (
                                        <Button
                                            variant="ghost"
                                            className="text-xs text-muted-foreground hover:text-primary"
                                            onClick={() => window.open(window.location.href, "_system")}
                                        >
                                            Open in Safari (More Stable)
                                        </Button>
                                    )}

                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => {
                                            window.location.reload()
                                        }}
                                        className="text-xs text-muted-foreground"
                                    >
                                        Force Reload
                                    </Button>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </main>
            </div>
        </div>
    )
}

function VoiceWaveform() {
    return (
        <div className="flex items-center gap-0.5 h-3">
            {[0, 1, 2, 3].map((i) => (
                <motion.div
                    key={i}
                    className="w-0.5 bg-primary rounded-full"
                    animate={{
                        height: [4, 12, 4],
                    }}
                    transition={{
                        duration: 0.6,
                        repeat: Number.POSITIVE_INFINITY,
                        delay: i * 0.1,
                        ease: "easeInOut",
                    }}
                />
            ))}
        </div>
    )
}
