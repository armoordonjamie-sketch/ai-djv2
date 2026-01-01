"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Music, Sparkles, Check, AlertCircle, Loader2 } from "lucide-react"
import { StatusTimeline } from "@/components/ui/StatusTimeline"
import { SkeletonMoodCard } from "@/components/ui/Skeleton"
import { useAuth } from "@/providers/AuthProvider"
import * as api from "@/lib/jamifyApi"
import type { StatusEvent, StatusStep } from "@/lib/types"

interface GenerationStatus {
  status: "pending" | "generating" | "complete" | "failed"
  moods_created: number
  moods_total: number
  current_step: string
  intros_ready: number
  error: string | null
}

// Mood names and colors for animation
const MOODS = [
  { name: "Flow", color: "#ec4899", emoji: "🎵" },
  { name: "Energy", color: "#f59e0b", emoji: "⚡" },
  { name: "Chill", color: "#06b6d4", emoji: "🌊" },
  { name: "Party", color: "#8b5cf6", emoji: "🎉" },
  { name: "Late Night", color: "#64748b", emoji: "🌙" },
]

const moodCreationSteps = [
  { id: "voice_processing" as StatusStep, label: "Analyzing", description: "Understanding your taste" },
  { id: "mood_parsing" as StatusStep, label: "Parsing", description: "Extracting preferences" },
  { id: "mood_creating" as StatusStep, label: "Creating", description: "Building your moods" },
  { id: "intro_generating" as StatusStep, label: "Finishing", description: "Preparing experience" },
]

export default function MoodCreationPage() {
  const navigate = useNavigate()
  const { refreshAuth } = useAuth()
  const [status, setStatus] = useState<GenerationStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [wsStatus, setWsStatus] = useState<StatusEvent | null>(null)
  const [completedSteps, setCompletedSteps] = useState<StatusStep[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const isNavigatingRef = useRef(false)
  const completionTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Track when we first saw completion to ensure minimum display time
  const completionSeenAtRef = useRef<number | null>(null)
  const MIN_COMPLETION_DISPLAY_MS = 2000 // Show completion animation for at least 2 seconds

  useEffect(() => {
    const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/v1/ws`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === "status") {
          const statusEvent = msg.data as StatusEvent
          if (statusEvent.category === "onboarding") {
            setWsStatus(statusEvent)

            // Track completed steps based on status progression
            const stepOrder: StatusStep[] = ["voice_processing", "mood_parsing", "mood_creating", "intro_generating"]
            const currentIndex = stepOrder.indexOf(statusEvent.step as StatusStep)
            if (currentIndex > 0) {
              setCompletedSteps(stepOrder.slice(0, currentIndex))
            }
          }
        }
      } catch {
        // Ignore parse errors
      }
    }

    return () => {
      ws.close()
      if (completionTimerRef.current) {
        clearTimeout(completionTimerRef.current)
      }
    }
  }, [])

  const checkStatus = useCallback(async () => {
    // Prevent checking status if we're already navigating
    if (isNavigatingRef.current) {
      return
    }

    try {
      const response = await fetch(`${api.API_V1}/onboard/generation-status`, {
        credentials: "include",
      })

      if (!response.ok) {
        throw new Error("Failed to get status")
      }

      const data: GenerationStatus = await response.json()
      setStatus(data)

      // Check if ACTUALLY complete:
      // - Backend status is "complete"
      // - At least the default mood's intro is ready (intros_ready >= 1)
      const isActuallyComplete = data.status === "complete" &&
        data.intros_ready >= 1

      if (isActuallyComplete && !isNavigatingRef.current) {
        // Mark all steps complete immediately for visual feedback
        setCompletedSteps(["voice_processing", "mood_parsing", "mood_creating", "intro_generating"])

        // Track when we first saw completion
        if (!completionSeenAtRef.current) {
          completionSeenAtRef.current = Date.now()
        }

        // Calculate remaining time to show completion animation
        const timeSinceCompletion = Date.now() - completionSeenAtRef.current
        const remainingDisplayTime = Math.max(0, MIN_COMPLETION_DISPLAY_MS - timeSinceCompletion)

        // Navigate after minimum display time
        if (remainingDisplayTime === 0 && !completionTimerRef.current) {
          isNavigatingRef.current = true

          // Refresh auth state to update isOnboarded flag
          await refreshAuth()

          // Navigate to moods page
          navigate("/moods", { replace: true })
        } else if (!completionTimerRef.current) {
          // Schedule navigation after remaining display time
          completionTimerRef.current = setTimeout(async () => {
            if (!isNavigatingRef.current) {
              isNavigatingRef.current = true
              await refreshAuth()
              navigate("/moods", { replace: true })
            }
          }, remainingDisplayTime)
        }
      } else if (data.status === "failed") {
        setError(data.error || "Something went wrong")
      } else if (data.status === "complete" && data.intros_ready < 1) {
        // Moods created but default mood intro still generating - show "Finishing touches" phase
        setCompletedSteps(["voice_processing", "mood_parsing", "mood_creating"])
      }
    } catch (err) {
      console.error("[MoodCreation] Status check failed:", err)
    }
  }, [navigate, refreshAuth])

  useEffect(() => {
    checkStatus()
    const interval = setInterval(checkStatus, 1000)
    return () => clearInterval(interval)
  }, [checkStatus])

  // Calculate progress including intro generation
  const calculateProgress = () => {
    if (!status) return 0

    // If no moods yet, show 0
    if (status.moods_total === 0) return 0

    // Mood creation is 70% of the progress
    const moodProgress = (status.moods_created / status.moods_total) * 70

    // Intro generation is 30% of the progress
    const introProgress = (status.intros_ready / status.moods_total) * 30

    return Math.min(100, moodProgress + introProgress)
  }

  const progress = calculateProgress()
  const isComplete = status?.status === "complete" && (status?.intros_ready ?? 0) >= 1
  const isFinishing = status?.status === "complete" && (status?.intros_ready ?? 0) < 1

  // Dynamic status message
  const getStatusMessage = () => {
    if (wsStatus?.user_message) return wsStatus.user_message
    if (isFinishing) return "Finishing touches..."
    if (status?.current_step) return status.current_step
    return "Setting things up..."
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background px-4 relative overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div
          className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full"
          style={{
            background: "radial-gradient(circle, rgba(139, 92, 246, 0.15) 0%, transparent 70%)",
          }}
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{ duration: 4, repeat: Number.POSITIVE_INFINITY }}
        />
        <motion.div
          className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full"
          style={{
            background: "radial-gradient(circle, rgba(236, 72, 153, 0.15) 0%, transparent 70%)",
          }}
          animate={{
            scale: [1.2, 1, 1.2],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{ duration: 4, repeat: Number.POSITIVE_INFINITY, delay: 2 }}
        />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative z-10 text-center max-w-md w-full"
      >
        {/* Main icon with completion state */}
        <motion.div
          animate={{
            rotate: isComplete ? 0 : 360,
            scale: isComplete ? [1, 1.1, 1] : 1,
          }}
          transition={{
            rotate: { duration: 3, repeat: isComplete ? 0 : Number.POSITIVE_INFINITY, ease: "linear" },
            scale: { duration: 0.5 },
          }}
          className="w-24 h-24 mx-auto mb-6 rounded-3xl gradient-bg flex items-center justify-center shadow-lg shadow-primary/20"
        >
          {isComplete ? (
            <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300 }}>
              <Check className="w-12 h-12 text-white" />
            </motion.div>
          ) : (
            <Music className="w-12 h-12 text-white" />
          )}
        </motion.div>

        {/* Title */}
        <h1 className="text-2xl font-bold mb-2">
          {isComplete ? "You're all set!" : isFinishing ? "Almost there..." : "Creating your vibes..."}
        </h1>

        {/* Status message with more detail */}
        <p className="text-muted-foreground mb-2">
          {getStatusMessage()}
        </p>

        {/* Show intro generation progress during finishing phase */}
        {isFinishing && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center justify-center gap-2 mb-4"
          >
            <Loader2 className="w-4 h-4 animate-spin text-primary" />
            <span className="text-sm text-muted-foreground/70">
              Preparing intros: {status?.intros_ready}/{status?.moods_total}
            </span>
          </motion.div>
        )}

        <div className="mb-8">
          <StatusTimeline
            steps={moodCreationSteps}
            currentStatus={wsStatus}
            completedSteps={completedSteps}
            orientation="horizontal"
          />
        </div>

        {/* Mood cards animation */}
        <div className="flex justify-center gap-3 mb-8">
          {MOODS.map((mood, i) => {
            const isCreated = status && i < status.moods_created
            const hasIntro = status && i < status.intros_ready
            const isCreating = status && i === status.moods_created

            return (
              <motion.div
                key={mood.name}
                initial={{ opacity: 0, scale: 0, y: 20 }}
                animate={{
                  opacity: isCreated ? (hasIntro ? 1 : 0.8) : isCreating ? 0.7 : 0.3,
                  scale: isCreated ? (hasIntro ? 1 : 0.95) : isCreating ? 0.9 : 0.8,
                  y: 0,
                }}
                transition={{
                  delay: i * 0.1,
                  duration: 0.3,
                  type: "spring",
                  stiffness: 200,
                }}
                className="relative w-14 h-14 rounded-xl flex items-center justify-center text-xl shadow-lg"
                style={{
                  backgroundColor: mood.color,
                  boxShadow: hasIntro ? `0 8px 20px ${mood.color}40` : "none",
                  opacity: isCreated ? (hasIntro ? 1 : 0.6) : 0.3,
                }}
                title={`${mood.name}${hasIntro ? ' ✓' : isCreated ? ' (preparing intro...)' : ''}`}
              >
                {mood.emoji}
                {hasIntro && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-success flex items-center justify-center"
                  >
                    <Check className="w-3 h-3 text-success-foreground" />
                  </motion.div>
                )}
                {isCreated && !hasIntro && (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                    className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center"
                  >
                    <Sparkles className="w-3 h-3 text-primary" />
                  </motion.div>
                )}
              </motion.div>
            )
          })}
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 bg-surface-2 rounded-full overflow-hidden mb-3">
          <motion.div
            className="h-full gradient-bg"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>

        {/* Progress text */}
        <p className="text-sm text-muted-foreground">
          {status ? (
            isFinishing
              ? `${status.moods_created} moods created, preparing ${status.moods_total - status.intros_ready} intros...`
              : `${status.moods_created} of ${status.moods_total} moods created`
          ) : "Starting..."}
        </p>

        {!isComplete && !isFinishing && status && status.moods_created === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1 }} className="mt-8">
            <p className="text-xs text-muted-foreground mb-3">Preview of your moods:</p>
            <div className="flex gap-3 overflow-hidden">
              {[1, 2].map((i) => (
                <SkeletonMoodCard key={i} className="w-32 flex-shrink-0" />
              ))}
            </div>
          </motion.div>
        )}

        {/* Error state */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="mt-6 p-4 bg-destructive/10 border border-destructive/20 rounded-xl"
            >
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-destructive text-sm font-medium">Something went wrong</p>
                  <p className="text-destructive/80 text-xs mt-1">{error}</p>
                  <p className="text-destructive/80 text-xs mt-2">
                    We need at least one mood intro before playback can start. This usually resolves within a minute.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-col gap-2">
                <button
                  onClick={checkStatus}
                  className="w-full text-sm font-medium rounded-lg border border-destructive/30 text-destructive py-2 hover:bg-destructive/10 transition-colors"
                >
                  Retry status check
                </button>
                <button
                  onClick={() => navigate("/moods", { replace: true })}
                  className="w-full text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Go to moods (playback may still be unavailable)
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Sparkles decoration */}
        <motion.div
          className="absolute -top-4 -right-4"
          animate={{ rotate: 360 }}
          transition={{ duration: 20, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
        >
          <Sparkles className="w-6 h-6 text-warning/50" />
        </motion.div>
      </motion.div>
    </div>
  )
}
