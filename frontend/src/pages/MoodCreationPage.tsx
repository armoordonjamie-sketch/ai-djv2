"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Music, Sparkles, Check, AlertCircle } from "lucide-react"
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

      if (data.status === "complete" && !isNavigatingRef.current) {
        // Mark all steps complete
        setCompletedSteps(["voice_processing", "mood_parsing", "mood_creating", "intro_generating"])
        isNavigatingRef.current = true
        
        // Refresh auth state to update isOnboarded flag
        await refreshAuth()
        
        // Navigate to moods page
        setTimeout(() => {
          navigate("/moods", { replace: true })
        }, 1500)
      } else if (data.status === "failed") {
        setError(data.error || "Something went wrong")
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

  const progress = status ? (status.moods_created / status.moods_total) * 100 : 0
  const isComplete = status?.status === "complete"

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
        <h1 className="text-2xl font-bold mb-2">{isComplete ? "You're all set!" : "Creating your vibes..."}</h1>

        {/* Status message with more detail */}
        <p className="text-muted-foreground mb-2">
          {wsStatus?.user_message || status?.current_step || "Setting things up..."}
        </p>
        
        {/* Show intro generation progress */}
        {status && status.intros_ready > 0 && status.intros_ready < status.moods_total && (
          <p className="text-sm text-muted-foreground/70 mb-4">
            Intros ready: {status.intros_ready}/{status.moods_total}
          </p>
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
          {status ? `${status.moods_created} of ${status.moods_total} moods created` : "Starting..."}
        </p>

        {!isComplete && status && status.moods_created === 0 && (
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
                </div>
              </div>
              <button
                onClick={() => navigate("/moods", { replace: true })}
                className="mt-3 w-full text-sm text-primary hover:underline"
              >
                Continue anyway →
              </button>
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
