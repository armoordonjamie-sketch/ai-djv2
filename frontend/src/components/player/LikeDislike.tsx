"use client"

import type React from "react"

import { useState, useEffect, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ThumbsUp, ThumbsDown, Sparkles, Check } from "lucide-react"
import { cn } from "@/lib/utils"
import { triggerHaptic } from "@/lib/motion"
import type { StatusEvent } from "@/lib/types"

interface LikeDislikeProps {
  onLike: () => void
  onDislike: () => void
  currentFeedback?: "like" | "dislike" | null
  disabled?: boolean
  /** Current status event from PlayerProvider for training feedback */
  status?: StatusEvent | null
}

export function LikeDislike({ onLike, onDislike, currentFeedback, disabled = false, status }: LikeDislikeProps) {
  const [feedbackState, setFeedbackState] = useState<"idle" | "received" | "training" | "complete">("idle")
  const [particles, setParticles] = useState<{ id: number; x: number; y: number; color: string }[]>([])

  // Watch for training status events
  useEffect(() => {
    if (!status) return

    if (status.step === "feedback_received") {
      setFeedbackState("received")
    } else if (status.step === "training_started" || status.step === "training_applied") {
      setFeedbackState("training")
    } else if (status.step === "training_complete") {
      setFeedbackState("complete")
      // Reset after showing completion
      const timer = setTimeout(() => setFeedbackState("idle"), 2500)
      return () => clearTimeout(timer)
    }
  }, [status])

  // Reset feedback state when track changes (currentFeedback becomes null)
  useEffect(() => {
    if (currentFeedback === null) {
      setFeedbackState("idle")
    }
  }, [currentFeedback])

  const createParticles = useCallback((type: "like" | "dislike", buttonRect: DOMRect) => {
    const centerX = buttonRect.width / 2
    const centerY = buttonRect.height / 2
    const color = type === "like" ? "#22c55e" : "#ef4444"

    const newParticles = Array.from({ length: 8 }).map((_, i) => ({
      id: Date.now() + i,
      x: centerX,
      y: centerY,
      color,
    }))

    setParticles(newParticles)
    setTimeout(() => setParticles([]), 600)
  }, [])

  const handleFeedback = (type: "like" | "dislike", event: React.MouseEvent<HTMLButtonElement>) => {
    if (disabled) return

    triggerHaptic("medium")
    createParticles(type, event.currentTarget.getBoundingClientRect())

    if (type === "like") {
      onLike()
    } else {
      onDislike()
    }

    setFeedbackState("received")
  }

  const getFeedbackMessage = () => {
    switch (feedbackState) {
      case "received":
        return "Got it!"
      case "training":
        return "Learning your taste..."
      case "complete":
        return "Updated your DJ"
      default:
        return null
    }
  }

  const feedbackMessage = getFeedbackMessage()

  return (
    <div className="flex flex-col items-center gap-2">
      {/* Buttons row */}
      <div className="flex items-center justify-center gap-6">
        {/* Dislike button */}
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={(e) => handleFeedback("dislike", e)}
          disabled={disabled}
          className={cn(
            "relative w-14 h-14 rounded-full flex items-center justify-center",
            "border-2 transition-all duration-200",
            currentFeedback === "dislike"
              ? "bg-destructive/20 border-destructive text-destructive"
              : "border-border hover:border-destructive/50 hover:bg-destructive/10 text-foreground",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          aria-label="Dislike this track"
          aria-pressed={currentFeedback === "dislike"}
        >
          <motion.div
            animate={currentFeedback === "dislike" ? { scale: [1, 1.2, 1] } : {}}
            transition={{ duration: 0.2 }}
          >
            <ThumbsDown className={cn("w-5 h-5 transition-all", currentFeedback === "dislike" && "fill-current")} />
          </motion.div>

          {/* Selection ring */}
          {currentFeedback === "dislike" && (
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="absolute inset-0 rounded-full border-2 border-destructive/50"
            />
          )}

          {/* Particles */}
          <AnimatePresence>
            {particles.map((particle) => (
              <motion.div
                key={particle.id}
                initial={{ x: particle.x - 3, y: particle.y - 3, opacity: 1, scale: 1 }}
                animate={{
                  x: particle.x + (Math.random() - 0.5) * 60 - 3,
                  y: particle.y - Math.random() * 40 - 20,
                  opacity: 0,
                  scale: 0,
                }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className="absolute w-1.5 h-1.5 rounded-full pointer-events-none"
                style={{ backgroundColor: particle.color }}
              />
            ))}
          </AnimatePresence>
        </motion.button>

        {/* Like button */}
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={(e) => handleFeedback("like", e)}
          disabled={disabled}
          className={cn(
            "relative w-14 h-14 rounded-full flex items-center justify-center",
            "border-2 transition-all duration-200",
            currentFeedback === "like"
              ? "bg-success/20 border-success text-success"
              : "border-border hover:border-success/50 hover:bg-success/10 text-foreground",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          aria-label="Like this track"
          aria-pressed={currentFeedback === "like"}
        >
          <motion.div animate={currentFeedback === "like" ? { scale: [1, 1.2, 1] } : {}} transition={{ duration: 0.2 }}>
            <ThumbsUp className={cn("w-5 h-5 transition-all", currentFeedback === "like" && "fill-current")} />
          </motion.div>

          {/* Selection ring */}
          {currentFeedback === "like" && (
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="absolute inset-0 rounded-full border-2 border-success/50"
            />
          )}

          {/* Particles */}
          <AnimatePresence>
            {particles.map((particle) => (
              <motion.div
                key={particle.id}
                initial={{ x: particle.x - 3, y: particle.y - 3, opacity: 1, scale: 1 }}
                animate={{
                  x: particle.x + (Math.random() - 0.5) * 60 - 3,
                  y: particle.y - Math.random() * 40 - 20,
                  opacity: 0,
                  scale: 0,
                }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className="absolute w-1.5 h-1.5 rounded-full pointer-events-none"
                style={{ backgroundColor: particle.color }}
              />
            ))}
          </AnimatePresence>
        </motion.button>
      </div>

      {/* Feedback status indicator - now in normal flow, above controls */}
      <div className="h-6 flex items-center justify-center">
        <AnimatePresence mode="wait">
          {feedbackMessage ? (
            <motion.div
              key={feedbackState}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.2 }}
              className="flex items-center gap-2"
            >
              {feedbackState === "complete" ? (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 15 }}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-success/15 text-success text-xs"
                >
                  <Check className="w-3 h-3" />
                  <span>{feedbackMessage}</span>
                </motion.div>
              ) : feedbackState === "training" ? (
                <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-warning/15 text-warning text-xs">
                  <motion.div
                    animate={{ rotate: [0, 15, -15, 0] }}
                    transition={{ duration: 0.5, repeat: Number.POSITIVE_INFINITY }}
                  >
                    <Sparkles className="w-3 h-3" />
                  </motion.div>
                  <span>{feedbackMessage}</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/15 text-primary text-xs">
                  <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring" }}>
                    <Check className="w-3 h-3" />
                  </motion.div>
                  <span>{feedbackMessage}</span>
                </div>
              )}
            </motion.div>
          ) : !currentFeedback && feedbackState === "idle" && !disabled ? (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2 }}
              className="text-xs text-muted-foreground text-center"
            >
              Train your DJ with feedback
            </motion.p>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  )
}

