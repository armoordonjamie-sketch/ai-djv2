"use client"

import { motion, AnimatePresence } from "framer-motion"
import { Loader2, Check, AlertCircle, Music, Sparkles, Radio, Zap } from "lucide-react"
import type { StatusEvent } from "@/lib/types"
import { cn } from "@/lib/utils"

interface StatusPillProps {
  status: StatusEvent | null
  className?: string
  /** Compact mode for inline display */
  compact?: boolean
}

const statusMessages: Partial<Record<string, string>> = {
  planning: "Planning your mix...",
  selecting_track: "Finding the perfect track...",
  track_selected: "Track found!",
  downloading_track: "Loading audio...",
  generating_intro: "Creating intro...",
  generating_tts: "Generating voice...",
  mixing: "Creating smooth transition...",
  encoding: "Encoding audio...",
  queued: "Ready to play",
  ready: "Ready",
  switching_mood: "Switching moods...",
  buffering: "Buffering...",
  recovering: "Reconnecting...",
  feedback_received: "Got it!",
  training_started: "Learning your taste...",
  training_applied: "Applying changes...",
  training_complete: "Updated your DJ",
  retrying: "Retrying...",
  failed: "Something went wrong",
}

/**
 * Compact status indicator for showing real-time backend progress.
 * Displays user-friendly messages from StatusEvents with enhanced visual feedback.
 */
export function StatusPill({ status, className = "", compact = false }: StatusPillProps) {
  if (!status) return null

  // Don't show certain statuses (they're ephemeral or handled elsewhere)
  const hiddenSteps = ["ready", "playing", "connected", "paused", "stopped"]
  if (hiddenSteps.includes(status.step)) return null

  const getIcon = () => {
    // Error states
    if (status.severity === "error") {
      return <AlertCircle className="w-4 h-4 text-destructive" />
    }

    // Success/completion states
    if (status.step === "training_complete" || status.step === "feedback_received") {
      return (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 400, damping: 15 }}
        >
          <Check className="w-4 h-4 text-success" />
        </motion.div>
      )
    }

    // Track found
    if (status.step === "track_selected") {
      return <Zap className="w-4 h-4 text-warning" />
    }

    // Generation states
    if (status.category === "generation") {
      if (status.step === "mixing") {
        return <Radio className="w-4 h-4 text-primary animate-pulse" />
      }
      return <Music className="w-4 h-4 text-primary animate-pulse" />
    }

    // Training states
    if (status.category === "training") {
      return (
        <motion.div
          animate={{ rotate: [0, 15, -15, 0] }}
          transition={{ duration: 0.5, repeat: Number.POSITIVE_INFINITY, repeatDelay: 1 }}
        >
          <Sparkles className="w-4 h-4 text-warning" />
        </motion.div>
      )
    }

    // Default: loading spinner
    return <Loader2 className="w-4 h-4 text-primary animate-spin" />
  }

  const getBackground = () => {
    if (status.severity === "error") return "bg-destructive/15 border-destructive/30"
    if (status.severity === "warn") return "bg-warning/15 border-warning/30"
    if (status.step === "feedback_received" || status.step === "training_complete") {
      return "bg-success/15 border-success/30"
    }
    if (status.category === "training") return "bg-warning/15 border-warning/30"
    return "bg-primary/10 border-primary/20"
  }

  const getMessage = () => {
    return statusMessages[status.step] || status.user_message
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={status.id}
        initial={{ opacity: 0, y: -10, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.95 }}
        transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border text-sm",
          compact ? "px-2 py-1" : "px-3 py-1.5",
          getBackground(),
          className,
        )}
      >
        {getIcon()}
        <span className={cn("text-foreground/90", compact && "text-xs")}>{getMessage()}</span>
        {status.progress !== undefined && status.progress !== null && (
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1 bg-muted/50 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-primary rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${status.progress * 100}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
            <span className="text-xs text-muted-foreground tabular-nums">{Math.round(status.progress * 100)}%</span>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  )
}
