"use client"

import { motion, AnimatePresence } from "framer-motion"
import { Loader2, Music, RefreshCw, AlertCircle, Radio } from "lucide-react"
import type { StatusEvent, StatusStep } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Skeleton } from "./Skeleton"

interface StatusOverlayProps {
  status: StatusEvent | null
  isLoading?: boolean
  /** If true, a track is playing - hide overlay for generation states */
  hasStartedPlaying?: boolean
  className?: string
}

const overlayMessages: Partial<Record<StatusStep, { title: string; subtitle: string }>> = {
  planning: { title: "Planning your mix", subtitle: "Analyzing your preferences..." },
  selecting_track: { title: "Finding the perfect track", subtitle: "Searching our library..." },
  downloading_track: { title: "Preparing audio", subtitle: "Loading track data..." },
  mixing: { title: "Creating your mix", subtitle: "Crafting smooth transitions..." },
  switching_mood: { title: "Switching moods", subtitle: "Changing the vibe..." },
  buffering: { title: "Buffering", subtitle: "Loading audio stream..." },
  recovering: { title: "Reconnecting", subtitle: "Restoring your session..." },
  failed: { title: "Something went wrong", subtitle: "Please try again" },
  starting: { title: "Starting playback", subtitle: "Just a moment..." },
}

const stepLabelMap: Partial<Record<StatusStep, string>> = {
  planning: "Analyzing",
  selecting_track: "Selecting",
  downloading_track: "Downloading",
  mixing: "Mixing",
  switching_mood: "Switching mood",
  buffering: "Buffering",
  recovering: "Reconnecting",
  failed: "Failed",
  starting: "Starting",
}

const tipMap: Partial<Record<StatusStep, string>> = {
  planning: "Scanning your likes and recent listens.",
  selecting_track: "Balancing energy, mood, and variety.",
  downloading_track: "Optimizing audio for smooth playback.",
  mixing: "Building a seamless transition.",
  buffering: "Getting the stream ready to play.",
  recovering: "Trying to reconnect to your session.",
  starting: "Warming up the stream.",
}

/**
 * Fullscreen overlay for major state changes (mood switching, initial loading, errors).
 * Only shows during significant transitions, not during normal playback.
 */
export function StatusOverlay({
  status,
  isLoading = false,
  hasStartedPlaying = false,
  className = "",
}: StatusOverlayProps) {
  // Steps that trigger fullscreen overlay ONLY before playback starts
  const prePlaybackSteps: StatusStep[] = [
    "planning",
    "selecting_track",
    "downloading_track",
    "mixing",
    "starting",
    "buffering",
  ]

  // Steps that ALWAYS show overlay (even during playback)
  const alwaysShowSteps: StatusStep[] = ["switching_mood", "recovering", "failed"]

  // Determine if overlay should be visible
  const shouldShow = (() => {
    if (isLoading && !hasStartedPlaying) return true
    if (!status) return false
    if (alwaysShowSteps.includes(status.step)) return true
    if (prePlaybackSteps.includes(status.step) && !hasStartedPlaying) return true
    return false
  })()

  if (!shouldShow) return null

  const getIcon = () => {
    if (!status) return <Loader2 className="w-12 h-12 text-primary animate-spin" />

    if (status.severity === "error") {
      return <AlertCircle className="w-12 h-12 text-destructive" />
    }

    if (status.step === "switching_mood") {
      return <RefreshCw className="w-12 h-12 text-primary animate-spin" />
    }

    if (status.step === "mixing") {
      return <Radio className="w-12 h-12 text-primary animate-pulse" />
    }

    return <Music className="w-12 h-12 text-primary animate-pulse" />
  }

  const getMessages = () => {
    if (!status) return { title: "Loading...", subtitle: "Please wait" }
    const messages = overlayMessages[status.step]
    if (messages) return messages
    return { title: status.user_message, subtitle: "Just a moment..." }
  }

  const { title, subtitle } = getMessages()
  const stepLabel = status ? stepLabelMap[status.step] : "Loading"
  const tip = status ? tipMap[status.step] : undefined

  return (
    <AnimatePresence>
      {shouldShow && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className={cn(
            "fixed inset-0 z-50 bg-background/95 backdrop-blur-xl",
            "flex flex-col items-center justify-center",
            className,
          )}
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0, y: 8 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            transition={{ delay: 0.08, type: "spring", stiffness: 220, damping: 22 }}
            className="relative flex flex-col items-center gap-7 text-center px-8 max-w-sm"
          >
            <div className="absolute inset-0 -z-10 rounded-3xl bg-gradient-to-b from-white/5 via-transparent to-transparent" />

            {/* Status chip */}
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.25em] text-muted-foreground"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              {stepLabel}
            </motion.div>

            {/* Icon with animated rings */}
            <div className="relative">
              {getIcon()}
              {/* Pulsing rings */}
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-primary/20"
                animate={{ scale: [1, 1.4, 1], opacity: [0.4, 0, 0.4] }}
                transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
              />
              <motion.div
                className="absolute inset-0 rounded-full border border-primary/10"
                animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0.3 }}
              />
            </div>

            {/* Message */}
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-foreground">{title}</h2>
              <p className="text-sm text-muted-foreground">{subtitle}</p>
              {tip && (
                <p className="text-xs text-muted-foreground/80">{tip}</p>
              )}
            </div>

            {status?.progress !== undefined && status.progress !== null && (
              <div className="w-full max-w-xs space-y-2">
                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                  <motion.div
                    className="h-full gradient-bg rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(1, Math.max(0, status.progress)) * 100}%` }}
                    transition={{ duration: 0.35 }}
                  />
                </div>
                <p className="text-xs text-muted-foreground tabular-nums">
                  {Math.round(Math.min(1, Math.max(0, status.progress)) * 100)}% complete
                </p>
              </div>
            )}

            {status?.step === "selecting_track" && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="w-full max-w-xs"
              >
                <p className="text-xs text-muted-foreground mb-3">Coming up:</p>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-surface-2">
                  <Skeleton variant="rounded" width={48} height={48} />
                  <div className="flex-1 space-y-2">
                    <Skeleton variant="text" width="70%" height={14} />
                    <Skeleton variant="text" width="50%" height={12} />
                  </div>
                </div>
              </motion.div>
            )}

            {status?.payload?.track_title && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25 }}
                className="w-full max-w-xs"
              >
                <p className="text-xs text-muted-foreground mb-3">Next up:</p>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-surface-2">
                  {status.payload.artwork_url ? (
                    <img
                      src={status.payload.artwork_url || "/placeholder.svg"}
                      alt=""
                      className="w-12 h-12 rounded-lg object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-lg bg-surface-3 flex items-center justify-center">
                      <Music className="w-5 h-5 text-muted-foreground" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{status.payload.track_title}</p>
                    <p className="text-xs text-muted-foreground truncate">{status.payload.track_artist}</p>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Error retry button */}
            {status?.severity === "error" && (
              <motion.button
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
                onClick={() => window.location.reload()}
                className="px-6 py-2 rounded-full gradient-bg text-white font-medium text-sm hover:opacity-90 transition-opacity"
              >
                Try Again
              </motion.button>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
