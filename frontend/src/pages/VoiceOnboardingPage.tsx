"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Mic, MicOff, Loader2, CheckCircle, AlertCircle, Volume2, ChevronLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/providers/AuthProvider"
import { useConversation } from "@elevenlabs/react"
import { StatusTimeline } from "@/components/ui/StatusTimeline"
import * as api from "@/lib/jamifyApi"
import type { StatusEvent, StatusStep } from "@/lib/types"

type OnboardingState = "loading" | "ready" | "connecting" | "active" | "complete" | "error"

interface Message {
    id: string
    role: "user" | "agent"
    text: string
    isFinal: boolean
}

const voiceOnboardingSteps = [
    { id: "mic_permission" as StatusStep, label: "Microphone", description: "Grant access" },
    { id: "voice_capture" as StatusStep, label: "Conversation", description: "Tell us your taste" },
    { id: "voice_processing" as StatusStep, label: "Processing", description: "Analyzing preferences" },
    { id: "onboarding_complete" as StatusStep, label: "Complete", description: "Profile created" },
]

export default function VoiceOnboardingPage() {
    const navigate = useNavigate()
    const { isOnboarded, user } = useAuth()
    const [state, setState] = useState<OnboardingState>("loading")
    const [error, setError] = useState<string | null>(null)
    const [messages, setMessages] = useState<Message[]>([])
    const pollingRef = useRef<NodeJS.Timeout | null>(null)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const isActiveRef = useRef(false)
    const wsRef = useRef<WebSocket | null>(null)
    const [wsStatus, setWsStatus] = useState<StatusEvent | null>(null)
    const [completedSteps, setCompletedSteps] = useState<StatusStep[]>([])

    // Debugging state
    const [debugLogs, setDebugLogs] = useState<string[]>([])
    const isIOSRef = useRef(false)
    const isPWARef = useRef(false)

    // Capture logs immediately
    const addLog = useCallback((msg: string) => {
        const time = new Date().toISOString().split('T')[1].slice(0, -1)
        setDebugLogs(prev => [...prev.slice(-49), `[${time}] ${msg}`])
    }, [])

    const handleRetry = () => {
        handleStart()
    }

        const VOL_MAX = 1.0      // Full volume when agent is listening
        const VOL_DUCKED = 0.45  // Background volume when agent is speaking (increased from 0.25)

    // Track current sound for cleanup
    const currentSoundRef = useRef<Howl | null>(null)
    
    // Track active audio element for instant volume changes (bypasses React state batching)
    const activeAudioRef = useRef<HTMLAudioElement | null>(null)
    
    // iOS PWA audio warmup resources - kept alive until connection established
    const warmupCtxRef = useRef<AudioContext | null>(null)
    const warmupStreamRef = useRef<MediaStream | null>(null)
    
    // Dedicated AudioContext for playback - unlocked once during user gesture, stays unlocked
    const playbackCtxRef = useRef<AudioContext | null>(null)
    const playbackSourceRef = useRef<AudioBufferSourceNode | null>(null)

    // Detect iOS PWA once for hook config
    const isIOSDevice = typeof navigator !== 'undefined' && /iPad|iPhone|iPod/.test(navigator.userAgent)
    const isStandalone = typeof window !== 'undefined' && (
        window.matchMedia('(display-mode: standalone)').matches || 
        (window.navigator as any).standalone === true
    )
    const isIOSPWA = isIOSDevice && isStandalone
    
    // DIAGNOSTIC: Use text-only mode for iOS PWA to test if connection works without audio
    // Set to false to disable this diagnostic and use full audio mode
    const USE_TEXT_ONLY_FOR_IOS_PWA = false
    
    const conversation = useConversation({
        // Text-only mode bypasses all audio setup - useful for diagnosing connection issues
        textOnly: USE_TEXT_ONLY_FOR_IOS_PWA && isIOSPWA,
        // iOS-specific audio routing preference
        preferHeadphonesForIosDevices: isIOSDevice,
        // Connection delay to allow audio mode switching (critical for iOS PWA)
        connectionDelay: {
            ios: 1500,  // Give iOS time to set up audio after mic activation
            android: 3000,
            default: 0,
        },
        onConnect: () => {
            timestampsRef.current.onConnectTime = Date.now()
            const connectDelay = timestampsRef.current.onConnectTime - (timestampsRef.current.startSessionTime || 0)
            addLog(`EVENT: onConnect (ElevenLabs, delay: ${connectDelay}ms)`)
            isActiveRef.current = true
            setState("active")
            setCompletedSteps((prev) => [...prev, "mic_permission" as StatusStep])
            startPolling()
            
            // Release iOS PWA warmup resources AFTER a delay to let SDK fully take over
            // Releasing too soon can disrupt iOS audio session
            setTimeout(() => {
                if (warmupStreamRef.current) {
                    warmupStreamRef.current.getTracks().forEach(t => t.stop())
                    warmupStreamRef.current = null
                    addLog("EVENT: Released warmup stream (delayed)")
                }
                if (warmupCtxRef.current) {
                    warmupCtxRef.current.close().catch(() => {})
                    warmupCtxRef.current = null
                    addLog("EVENT: Closed warmup AudioContext (delayed)")
                }
            }, 3000) // Wait 3 seconds for SDK audio to stabilize
        },
        onDisconnect: () => {
            addLog("EVENT: onDisconnect")
            // Stop HTMLAudioElement if playing
            if (activeAudioRef.current) {
                activeAudioRef.current.pause()
                activeAudioRef.current = null
                setActiveAudio(null)
            }
            // Stop Web Audio playback if playing
            if (playbackSourceRef.current) {
                try {
                    playbackSourceRef.current.stop()
                } catch (e) {
                    // Already stopped
                }
                playbackSourceRef.current = null
            }

            if (isActiveRef.current) {
                isActiveRef.current = false
                setError("Connection lost. Please try again.")
                setState("error")
            }
        },
        onMessage: (message) => {
            // Log truncated message for brevity
            const msgStr = typeof message === 'string' ? message : JSON.stringify(message)
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
            // Only set error if we haven't manually handled it (e.g., timeout)
            if (state !== 'error') {
                setError(errorMsg)
                isActiveRef.current = false
                setState("error")
            }
        },
        onModeChange: (mode) => {
            addLog(`EVENT: onModeChange: ${JSON.stringify(mode)}`)
            setConversationMode(mode)
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
            // Log SDK internal debug info for troubleshooting
            console.log("[VoiceOnboarding] SDK_DEBUG:", info)
            addLog(`SDK_DEBUG: ${typeof info === 'string' ? info : JSON.stringify(info)}`)
        },
        clientTools: {
            play_song_preview: async ({ artist_name, track_title }: { artist_name: string; track_title: string }) => {
                console.log(`[VoiceOnboarding] play_song_preview called: ${track_title} by ${artist_name}`)
                try {
                    const res = await api.playPreview(artist_name, track_title)

                    if (res.preview_url) {
                        const previewUrl = res.preview_url
                        console.log(`[VoiceOnboarding] Got preview URL: ${previewUrl}`)
                        
                        try {
                            // Stop any previous audio
                            if (playbackSourceRef.current) {
                                try {
                                    playbackSourceRef.current.stop()
                                } catch (e) {
                                    // Ignore - may already be stopped
                                }
                                playbackSourceRef.current = null
                            }
                            if (activeAudio) {
                                activeAudio.pause()
                                activeAudio.currentTime = 0
                            }
                            if (currentSoundRef.current) {
                                currentSoundRef.current.stop()
                                currentSoundRef.current = null
                            }
                            
                            // Use Web Audio API with pre-unlocked context (more reliable on iOS PWA)
                            const ctx = playbackCtxRef.current
                            if (!ctx || ctx.state === 'closed') {
                                console.error("[VoiceOnboarding] No playback context available")
                                return `Audio system not initialized. Let's continue without music.`
                            }
                            
                            console.log(`[VoiceOnboarding] Using Web Audio API (context state: ${ctx.state})`)
                            
                            // Ensure context is running
                            if (ctx.state === 'suspended') {
                                console.log("[VoiceOnboarding] Resuming suspended context...")
                                await ctx.resume()
                            }
                            
                            // Fetch audio data
                            console.log("[VoiceOnboarding] Fetching audio data...")
                            const response = await fetch(previewUrl)
                            if (!response.ok) {
                                throw new Error(`HTTP ${response.status}`)
                            }
                            const arrayBuffer = await response.arrayBuffer()
                            console.log(`[VoiceOnboarding] Got ${arrayBuffer.byteLength} bytes, decoding...`)
                            
                            // Decode audio
                            const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
                            console.log(`[VoiceOnboarding] Decoded: ${audioBuffer.duration.toFixed(1)}s, ${audioBuffer.numberOfChannels}ch`)
                            
                            // Create gain node for volume control
                            const gainNode = ctx.createGain()
                            const targetVol = conversationMode.mode === "speaking" ? VOL_DUCKED : VOL_MAX
                            gainNode.gain.value = targetVol
                            gainNode.connect(ctx.destination)
                            
                            // Create source and play
                            const source = ctx.createBufferSource()
                            source.buffer = audioBuffer
                            source.connect(gainNode)
                            
                            // Store for later cleanup/control
                            playbackSourceRef.current = source
                            
                            // Track gain node for ducking (store on source for access)
                            ;(source as any)._gainNode = gainNode
                            
                            source.onended = () => {
                                console.log("[VoiceOnboarding] Web Audio preview finished")
                                playbackSourceRef.current = null
                            }
                            
                            console.log("[VoiceOnboarding] Starting Web Audio playback...")
                            source.start(0)
                            console.log("[VoiceOnboarding] Web Audio playback started!")
                            
                            // Wait a moment for audio to be audible
                            await new Promise(resolve => setTimeout(resolve, 800))

                            return `The music is now playing. Ask the user if they like this song.`
                        } catch (playError: any) {
                            console.error("[VoiceOnboarding] Play error:", playError?.name || playError?.constructor?.name, playError?.message)
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
        },
    })

    // Local state for volume control
    const [conversationMode, setConversationMode] = useState<{ mode: "speaking" | "listening" }>({ mode: "listening" })
    const [activeAudio, setActiveAudio] = useState<HTMLAudioElement | null>(null)

    // Ducking - adjust volume when agent speaks/listens
    useEffect(() => {
        const targetVol = conversationMode.mode === "speaking" ? VOL_DUCKED : VOL_MAX
        
        // Adjust Howler global volume (for any Howler sounds)
        Howler.volume(targetVol)
        
        // Adjust HTMLAudioElement if playing (use ref for instant access)
        const audio = activeAudioRef.current || activeAudio
        if (audio && !audio.paused) {
            audio.volume = targetVol
        }
        
        // Adjust Web Audio gain node if playing
        const source = playbackSourceRef.current
        if (source) {
            const gainNode = (source as any)._gainNode as GainNode | undefined
            if (gainNode) {
                gainNode.gain.value = targetVol
            }
        }
    }, [conversationMode, activeAudio])

    useEffect(() => {
        return () => {
            // Stop howler sounds on unmount
            Howler.unload()
        }
    }, [])


    useEffect(() => {
        async function checkStatus() {
            if (isOnboarded) {
                navigate("/player", { replace: true })
                return
            }

            try {
                const status = await api.getOnboardStatus()
                if (status.has_profile) {
                    navigate("/player", { replace: true })
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

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    useEffect(() => {
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
                        // Track completed steps
                        if (statusEvent.step === "voice_processing") {
                            setCompletedSteps((prev) => (prev.includes("voice_capture") ? prev : [...prev, "voice_capture" as StatusStep]))
                        }
                        if (statusEvent.step === "onboarding_complete") {
                            setCompletedSteps((prev) => [...new Set([...prev, "voice_capture" as StatusStep, "voice_processing" as StatusStep])])
                        }
                    }
                }
            } catch {
                // Ignore parse errors
            }
        }

        return () => {
            ws.close()
        }
    }, [addLog])

    useEffect(() => {
        // Monitor device changes (often triggers stream death on iOS)
        const handleDeviceChange = () => {
            addLog("EVENT: navigator.mediaDevices.ondevicechange")
            // If we are active/connecting, this is dangerous
            if (isActiveRef.current || state === "connecting") {
                addLog("WARNING: Device change detection during active session")
            }
        }

        navigator.mediaDevices.addEventListener('devicechange', handleDeviceChange)
        return () => {
            navigator.mediaDevices.removeEventListener('devicechange', handleDeviceChange)
        }
    }, [addLog, state])

    const timeoutRef = useRef<NodeJS.Timeout | null>(null)
    
    // Timestamps for debug overlay
    const timestampsRef = useRef<{
        clickTime?: number
        permissionTime?: number
        startSessionTime?: number
        firstStatusChangeTime?: number
        onConnectTime?: number
    }>({})

    // Simplified cleanup - just clear timeout and end session
    const cleanupResources = useCallback(() => {
        addLog("CLEANUP: Starting resource cleanup")
        
        // Clear timeout if exists
        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current)
            timeoutRef.current = null
        }
        
        // Clean up iOS PWA warmup resources if still held
        if (warmupStreamRef.current) {
            warmupStreamRef.current.getTracks().forEach(t => t.stop())
            warmupStreamRef.current = null
            addLog("CLEANUP: Released warmup stream")
        }
        if (warmupCtxRef.current) {
            warmupCtxRef.current.close().catch(() => {})
            warmupCtxRef.current = null
            addLog("CLEANUP: Closed warmup AudioContext")
        }
        
        // End session (SDK handles its own stream cleanup)
        conversation.endSession().catch(() => {})
    }, [conversation, addLog])

    const handleStart = async () => {
        try {
            // Reset timestamps
            timestampsRef.current = { clickTime: Date.now() }
            addLog("ACTION: handleStart clicked")
            setState("connecting")
            setError(null)
            setMessages([])

            // Environment Detection
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream
            const isPWA = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true
            // Use WebSocket for iOS PWA (more stable than WebRTC in sandbox)
            const useWebSocket = isIOS && isPWA

            isIOSRef.current = isIOS
            isPWARef.current = isPWA

            addLog(`ENV: iOS=${isIOS}, PWA=${isPWA} => Mode=${useWebSocket ? 'WebSocket' : 'WebRTC'}`)

            // CRITICAL: Unlock playback AudioContext FIRST (before any mic operations)
            // This must happen in user gesture context. Once unlocked, it stays unlocked for the page session.
            if (!playbackCtxRef.current || playbackCtxRef.current.state === 'closed') {
                addLog("STEP 0: Creating playback AudioContext...")
                const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
                playbackCtxRef.current = new AudioContextClass()
            }
            
            if (playbackCtxRef.current.state === 'suspended') {
                addLog("STEP 0: Unlocking playback AudioContext...")
                try {
                    await playbackCtxRef.current.resume()
                    addLog(`STEP 0: Playback AudioContext unlocked (state: ${playbackCtxRef.current.state})`)
                } catch (e: any) {
                    addLog(`STEP 0: Playback unlock failed: ${e.message}`)
                }
            } else {
                addLog(`STEP 0: Playback AudioContext already unlocked (state: ${playbackCtxRef.current.state})`)
            }

            // STEP 1: Prepare for SDK (user gesture context)
            addLog("STEP 1: Preparing for SDK...")
            
            // Unlock Howler's AudioContext in user gesture (needed for audio playback later)
            // IMPORTANT: On iOS PWA, AudioContext.resume() can hang indefinitely, so we use a timeout
            // @ts-ignore
            if (typeof Howler !== 'undefined' && Howler.ctx && Howler.ctx.state === 'suspended') {
                try {
                    addLog("STEP 1: Resuming Howler AudioContext...")
                    // @ts-ignore
                    const resumePromise = Howler.ctx.resume()
                    const timeoutPromise = new Promise((_, reject) => 
                        setTimeout(() => reject(new Error('AudioContext resume timeout')), 2000)
                    )
                    await Promise.race([resumePromise, timeoutPromise])
                    addLog("STEP 1: Howler AudioContext resumed")
                } catch (howlerErr: any) {
                    // Don't fail on Howler issues - SDK can still work
                    addLog(`STEP 1: Howler resume skipped (${howlerErr.message})`)
                }
            } else {
                addLog("STEP 1: Howler not suspended or not loaded")
            }

            addLog("STEP 1: Audio prep done, checking mic...")
            
            // For non-iOS-PWA: Pre-check mic permission (recommended by SDK docs)
            // For iOS PWA: Skip this - let SDK handle it directly to avoid interference
            if (!useWebSocket) {
                try {
                    addLog("STEP 1: Pre-checking mic permission (non-iOS)...")
                    
                    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                        throw new Error("getUserMedia not supported")
                    }

                    const testStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
                    timestampsRef.current.permissionTime = Date.now()
                    const permissionDelay = timestampsRef.current.permissionTime - (timestampsRef.current.clickTime || 0)
                    addLog(`STEP 1: Permission OK (${permissionDelay}ms)`)
                    
                    // Release immediately
                    testStream.getTracks().forEach(t => t.stop())
                    addLog("STEP 1: Test stream released")

                } catch (micErr: any) {
                    addLog(`STEP 1: Mic error: ${micErr.name}: ${micErr.message}`)
                    setState("error")
                    if (micErr.name === 'NotAllowedError') {
                        setError("Microphone access denied. Please allow microphone.")
                    } else if (micErr.name === 'NotFoundError') {
                        setError("No microphone found.")
                    } else {
                        setError(`Microphone error: ${micErr.message}`)
                    }
                    return
                }
            } else {
                // iOS PWA: Pre-activate audio system to work around Safari sandbox issues
                // The SDK will still acquire its own stream, but this "warms up" iOS audio
                // CRITICAL: Keep audio resources alive until SDK connects to maintain iOS audio session
                addLog("STEP 1: iOS PWA - warming up audio system...")
                
                try {
                    // Request mic permission in user gesture context
                    const warmupStream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                        }, 
                        video: false 
                    })
                    warmupStreamRef.current = warmupStream // Keep alive!
                    addLog("STEP 1: iOS PWA - got warmup stream")
                    
                    // Create AudioContext and briefly process audio to activate iOS audio session
                    const warmupCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
                    warmupCtxRef.current = warmupCtx // Keep alive!
                    addLog(`STEP 1: iOS PWA - AudioContext state: ${warmupCtx.state}`)
                    
                    if (warmupCtx.state === 'suspended') {
                        try {
                            const resumePromise = warmupCtx.resume()
                            const timeoutPromise = new Promise((_, reject) => 
                                setTimeout(() => reject(new Error('resume timeout')), 1500)
                            )
                            await Promise.race([resumePromise, timeoutPromise])
                            addLog("STEP 1: iOS PWA - AudioContext resumed")
                        } catch (resumeErr: any) {
                            addLog(`STEP 1: iOS PWA - AudioContext resume failed: ${resumeErr.message}`)
                            // Continue anyway - having the stream might be enough
                        }
                    }
                    
                    // Connect stream to AudioContext to fully activate audio pipeline
                    const source = warmupCtx.createMediaStreamSource(warmupStream)
                    const gain = warmupCtx.createGain()
                    gain.gain.value = 0 // Silent
                    source.connect(gain)
                    gain.connect(warmupCtx.destination)
                    addLog("STEP 1: iOS PWA - audio pipeline activated")
                    
                    // Brief delay to let iOS audio system settle
                    await new Promise(resolve => setTimeout(resolve, 300))
                    
                    // Disconnect nodes and RELEASE the stream (SDK needs exclusive mic access)
                    // But KEEP the AudioContext alive to maintain iOS audio session
                    source.disconnect()
                    gain.disconnect()
                    
                    // Release mic stream so SDK can acquire it
                    warmupStream.getTracks().forEach(t => t.stop())
                    warmupStreamRef.current = null
                    addLog("STEP 1: iOS PWA - released mic for SDK, keeping AudioContext alive")
                    
                    timestampsRef.current.permissionTime = Date.now()
                    
                } catch (warmupErr: any) {
                    addLog(`STEP 1: iOS PWA warmup error: ${warmupErr.name}: ${warmupErr.message}`)
                    // Continue anyway - SDK might still work
                    timestampsRef.current.permissionTime = Date.now()
                }
            }

            // STEP 2: Fetch Token/URL & Start Session
            addLog("STEP 2: Authenticating...")

            let conversationId: string

            try {
                if (useWebSocket) {
                    // WebSocket Flow (iOS PWA)
                    addLog("Mode: WebSocket (via /onboard/start)")
                    console.log("[VoiceOnboarding] Fetching signed URL...")
                    
                    try {
                        const response = await api.startOnboarding()
                        if (!response.signed_url) throw new Error("No signed_url returned")

                        addLog(`Got Signed URL. Agent: ${response.agent_id}`)
                        console.log("[VoiceOnboarding] Got signed URL, agent:", response.agent_id)

                        timestampsRef.current.startSessionTime = Date.now()
                        addLog("STEP 2: Calling startSession (WebSocket)...")
                        console.log("[VoiceOnboarding] Calling startSession with WebSocket...")
                        
                        conversationId = await conversation.startSession({
                            signedUrl: response.signed_url,
                            connectionType: "websocket",
                            dynamicVariables: {
                                user_id: user?.id || 'anonymous',
                            },
                        })
                        
                        const startDelay = Date.now() - timestampsRef.current.startSessionTime
                        addLog(`STEP 2: startSession returned (took: ${startDelay}ms)`)
                        console.log("[VoiceOnboarding] startSession returned, took:", startDelay, "ms")
                    } catch (wsError: any) {
                        // WebSocket failed - fall back to WebRTC
                        addLog(`WebSocket failed: ${wsError.message}, falling back to WebRTC...`)
                        console.warn("[VoiceOnboarding] WebSocket failed, trying WebRTC fallback:", wsError)
                        
                        // Use WebRTC as fallback
                        const { token, agent_id } = await api.getConversationToken()
                        addLog(`Fallback: Got Token. Agent: ${agent_id}`)
                        
                        timestampsRef.current.startSessionTime = Date.now()
                        conversationId = await conversation.startSession({
                            conversationToken: token,
                            connectionType: "webrtc",
                            dynamicVariables: {
                                user_id: user?.id || 'anonymous',
                            },
                        })
                        
                        const startDelay = Date.now() - timestampsRef.current.startSessionTime
                        addLog(`Fallback: startSession returned (took: ${startDelay}ms)`)
                    }

                } else {
                    // WebRTC Flow (Default for non-iOS-PWA)
                    addLog("Mode: WebRTC (via /conversation-token)")
                    console.log("[VoiceOnboarding] Fetching conversation token...")
                    const { token, agent_id } = await api.getConversationToken()
                    addLog(`Got Token. Agent: ${agent_id}`)
                    console.log("[VoiceOnboarding] Got token, agent:", agent_id)

                    timestampsRef.current.startSessionTime = Date.now()
                    addLog("STEP 2: Calling startSession (WebRTC)...")
                    console.log("[VoiceOnboarding] Calling startSession with WebRTC...")
                    
                    conversationId = await conversation.startSession({
                        conversationToken: token,
                        connectionType: "webrtc",
                        dynamicVariables: {
                            user_id: user?.id || 'anonymous',
                        },
                    })
                    
                    const startDelay = Date.now() - timestampsRef.current.startSessionTime
                    addLog(`STEP 2: startSession returned (took: ${startDelay}ms)`)
                    console.log("[VoiceOnboarding] startSession returned, took:", startDelay, "ms")
                }
            } catch (sessionErr: any) {
                console.error("[VoiceOnboarding] startSession error:", sessionErr)
                addLog(`STEP 2: startSession FAILED: ${sessionErr.message || sessionErr}`)
                throw sessionErr // Re-throw to be caught by outer handler
            }

            addLog(`STEP 3: Session Started (ID: ${conversationId})`)

            // HARD TIMEOUT (25s - slightly longer to account for connectionDelay)
            timeoutRef.current = setTimeout(() => {
                // Check if we are still connecting (not active, not error)
                if (!isActiveRef.current && state === "connecting") {
                    addLog("TIMEOUT: Connection took too long (>25s)")
                    cleanupResources()
                    setState("error")
                    
                    // More specific error for iOS PWA
                    if (isIOS && isPWA) {
                        setError("Connection timed out. iOS PWA has limited WebRTC support. Try opening in Safari browser instead.")
                    } else {
                        setError("Connection timed out. Please check your network and try again.")
                    }
                }
            }, 25000)

        } catch (err: any) {
            console.error("Failed to start conversation:", err)
            addLog(`FATAL ERROR: ${err.message || err}`)

            cleanupResources()

            setState("error")
            
            // More specific error messages
            const errMsg = err.message || String(err)
            if (errMsg.includes('microphone') || errMsg.includes('getUserMedia')) {
                setError("Microphone access failed. Please grant permission and try again.")
            } else if (errMsg.includes('network') || errMsg.includes('fetch')) {
                setError("Network error. Please check your connection.")
            } else {
                setError("Failed to connect to AI Agent. Please try again.")
            }
        }
    }

    const handleEnd = async () => {
        addLog("ACTION: handleEnd clicked")
        try {
            // Clear any pending timeout
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current)
                timeoutRef.current = null
            }
            await conversation.endSession()
        } catch {
            // Ignore errors on end
        }
        isActiveRef.current = false
        setState("ready")
    }

    const startPolling = useCallback(() => {
        let attempts = 0
        const maxAttempts = 90

        const poll = async () => {
            try {
                const status = await api.getOnboardStatus()
                if (status.has_profile) {
                    setState("complete")
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                    }
                    try {
                        await conversation.endSession()
                    } catch {
                        /* ignore */
                    }
                    setTimeout(() => {
                        navigate("/creating-moods", { replace: true })
                    }, 1000)
                    return
                }

                attempts++
                if (attempts >= maxAttempts) {
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                    }
                }
            } catch {
                // Continue polling on errors
            }
        }

        pollingRef.current = setInterval(poll, 2000)
    }, [navigate, conversation])

    useEffect(() => {
        return () => {
            if (pollingRef.current) {
                clearInterval(pollingRef.current)
            }
        }
    }, [])

    const isSpeaking = conversation.isSpeaking
    const isConnected = conversation.status === "connected"

    // Debug mode only via URL param (for development)
    const showDebug = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('debug')

    return (
        <div className="min-h-screen flex flex-col bg-background">
            {/* Header */}
            <header className="px-4 pt-safe-top py-4 border-b border-border flex items-center gap-4">
                {state === "active" && (
                    <Button variant="ghost" size="icon" onClick={handleEnd} className="flex-shrink-0">
                        <ChevronLeft className="w-5 h-5" />
                    </Button>
                )}
                <div className="flex-1 text-center">
                    <h1 className="text-xl font-bold gradient-text">Let's get to know you</h1>
                    <p className="text-muted-foreground text-sm">Have a quick chat with your AI DJ</p>
                </div>
                {state === "active" && <div className="w-10" />}
            </header>

            {/* Content */}
            <main className="flex-1 flex flex-col overflow-hidden relative">
                {/* DEBUG CONSOLE OVERLAY - only with ?debug URL param */}
                {showDebug && (
                    <div className="absolute top-0 left-0 right-0 h-64 bg-black/90 text-[10px] font-mono text-green-400 p-2 overflow-y-auto z-50 opacity-90 border-b border-green-900">
                        <div className="flex justify-between border-b border-green-800 pb-1 mb-1">
                            <span>DEBUG LOG</span>
                            <span className="text-gray-400">iOS:{String(isIOSRef.current)} PWA:{String(isPWARef.current)}</span>
                        </div>
                        {/* Timestamps Summary */}
                        {timestampsRef.current.clickTime && (
                            <div className="border-b border-green-800 pb-1 mb-1 text-yellow-400">
                                <div>Timestamps:</div>
                                <div>Click → Permission: {timestampsRef.current.permissionTime ? `${timestampsRef.current.permissionTime - timestampsRef.current.clickTime}ms` : 'pending'}</div>
                                <div>Permission → startSession: {timestampsRef.current.startSessionTime ? `${timestampsRef.current.startSessionTime - (timestampsRef.current.permissionTime || timestampsRef.current.clickTime)}ms` : 'pending'}</div>
                                <div>startSession → statusChange: {timestampsRef.current.firstStatusChangeTime ? `${timestampsRef.current.firstStatusChangeTime - (timestampsRef.current.startSessionTime || 0)}ms` : 'pending'}</div>
                                <div>startSession → onConnect: {timestampsRef.current.onConnectTime ? `${timestampsRef.current.onConnectTime - (timestampsRef.current.startSessionTime || 0)}ms` : 'pending'}</div>
                            </div>
                        )}
                        {debugLogs.map((log, i) => (
                            <div key={i} className="whitespace-pre-wrap mb-1">{log}</div>
                        ))}
                    </div>
                )}

                {state === "loading" && (
                    <div className="flex-1 flex items-center justify-center">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                )}

                {state === "ready" && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex-1 flex flex-col items-center justify-center gap-8 px-6 text-center"
                    >
                        {/* Animated mic icon */}
                        <motion.div
                            animate={{
                                scale: [1, 1.05, 1],
                                boxShadow: [
                                    "0 0 0 0 rgba(139, 92, 246, 0.4)",
                                    "0 0 0 20px rgba(139, 92, 246, 0)",
                                    "0 0 0 0 rgba(139, 92, 246, 0)",
                                ],
                            }}
                            transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY }}
                            className="w-28 h-28 rounded-3xl gradient-bg flex items-center justify-center"
                        >
                            <Mic className="w-14 h-14 text-white" />
                        </motion.div>

                        <div className="space-y-3 max-w-sm">
                            <h2 className="text-2xl font-semibold">Voice Onboarding</h2>
                            <p className="text-muted-foreground">
                                Tell your AI DJ about your music taste, favorite artists, and what kind of experience you want. It only
                                takes a minute.
                            </p>
                        </div>

                        <div className="w-full max-w-xs">
                            <StatusTimeline
                                steps={voiceOnboardingSteps}
                                currentStatus={null}
                                completedSteps={[]}
                                orientation="horizontal"
                            />
                        </div>

                        <Button onClick={handleStart} className="gradient-bg px-8 py-6 text-lg shadow-lg shadow-primary/20">
                            <Mic className="w-5 h-5 mr-2" />
                            Start Conversation
                        </Button>
                    </motion.div>
                )}

                {state === "connecting" && (
                    <div className="flex-1 flex items-center justify-center">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="text-center space-y-4"
                        >
                            <div className="relative w-20 h-20 mx-auto">
                                <Loader2 className="w-full h-full animate-spin text-primary" />
                                <motion.div
                                    className="absolute inset-0 rounded-full border-2 border-primary/20"
                                    animate={{ scale: [1, 1.3, 1], opacity: [0.5, 0, 0.5] }}
                                    transition={{ duration: 1.5, repeat: Number.POSITIVE_INFINITY }}
                                />
                            </div>
                            <p className="text-muted-foreground">Connecting to your AI DJ...</p>
                        </motion.div>
                    </div>
                )}

                {state === "active" && (
                    <div className="flex-1 flex flex-col">
                        {/* Status bar with timeline */}
                        <div className="px-4 py-3 border-b border-border bg-surface-1">
                            <div className="flex items-center justify-between mb-3">
                                <div className="flex items-center gap-2">
                                    <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-success" : "bg-warning"}`} />
                                    <span className="text-sm text-muted-foreground">{isConnected ? "Connected" : "Connecting..."}</span>
                                </div>
                                <AnimatePresence>
                                    {isSpeaking && (
                                        <motion.div
                                            initial={{ opacity: 0, scale: 0.9 }}
                                            animate={{ opacity: 1, scale: 1 }}
                                            exit={{ opacity: 0, scale: 0.9 }}
                                            className="flex items-center gap-1.5 text-primary"
                                        >
                                            <Volume2 className="w-4 h-4" />
                                            <span className="text-sm">Speaking</span>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                            <StatusTimeline
                                steps={voiceOnboardingSteps}
                                currentStatus={wsStatus}
                                completedSteps={completedSteps}
                                orientation="horizontal"
                            />
                        </div>

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
                            {messages
                                .filter((m) => m.isFinal)
                                .map((msg) => (
                                    <motion.div
                                        key={msg.id}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                                    >
                                        <div
                                            className={`max-w-[80%] px-4 py-2.5 rounded-2xl ${msg.role === "user"
                                                ? "bg-primary text-primary-foreground rounded-br-sm"
                                                : "bg-surface-2 border border-border rounded-bl-sm"
                                                }`}
                                        >
                                            <p className="text-sm leading-relaxed">{msg.text}</p>
                                        </div>
                                    </motion.div>
                                ))}
                            {/* Real-time status from WebSocket */}
                            {wsStatus && (
                                <motion.div
                                    key={wsStatus.id}
                                    initial={{ opacity: 0, y: 5 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex justify-center"
                                >
                                    <div className="px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs flex items-center gap-2">
                                        <Loader2 className="w-3 h-3 animate-spin" />
                                        {wsStatus.user_message}
                                    </div>
                                </motion.div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Controls */}
                        <div className="px-4 py-4 border-t border-border bg-surface-1">
                            <div className="flex items-center justify-center gap-4">
                                <Button
                                    variant="outline"
                                    size="lg"
                                    onClick={handleEnd}
                                    className="text-destructive border-destructive/30 bg-transparent"
                                >
                                    <MicOff className="w-5 h-5 mr-2" />
                                    End Conversation
                                </Button>
                            </div>
                            <p className="text-center text-xs text-muted-foreground mt-2">
                                Just speak naturally — say "I'm done" when finished
                            </p>
                        </div>
                    </div>
                )}

                {state === "complete" && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-6"
                    >
                        <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            transition={{ type: "spring", stiffness: 200, damping: 15 }}
                            className="w-24 h-24 rounded-full bg-success/20 flex items-center justify-center"
                        >
                            <CheckCircle className="w-12 h-12 text-success" />
                        </motion.div>
                        <div className="space-y-2">
                            <h2 className="text-2xl font-semibold">All set!</h2>
                            <p className="text-muted-foreground">Creating your personalized moods...</p>
                        </div>
                        <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    </motion.div>
                )}

                {state === "error" && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-6"
                    >
                        <div className="w-20 h-20 rounded-full bg-destructive/20 flex items-center justify-center">
                            <AlertCircle className="w-10 h-10 text-destructive" />
                        </div>
                        <div className="space-y-2">
                            <h2 className="text-xl font-semibold">Something went wrong</h2>
                            <p className="text-muted-foreground text-sm max-w-xs">{error}</p>
                        </div>
                        <div className="flex flex-col gap-3 w-full max-w-xs">
                            <Button onClick={handleRetry} className="gradient-bg w-full">
                                Try Again
                            </Button>
                            <Button variant="outline" onClick={() => navigate("/text-onboarding")} className="w-full">
                                Use Text Mode
                            </Button>

                            {/* iOS PWA Fallback */}
                            {isPWARef.current && isIOSRef.current && (
                                <Button
                                    variant="ghost"
                                    className="text-xs text-muted-foreground hover:text-primary"
                                    onClick={() => window.open(window.location.href, '_system')}
                                >
                                    Open in Safari (More Stable)
                                </Button>
                            )}

                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                    // FORCE RELOAD
                                    window.location.reload()
                                }}
                                className="text-xs text-muted-foreground"
                            >
                                Force Reload
                            </Button>
                        </div>
                    </motion.div>
                )}

            </main>
        </div>
    )
}
