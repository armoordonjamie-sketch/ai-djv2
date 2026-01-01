"use client"

import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ThumbsDown, Heart } from "lucide-react"
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
  /** Compact mode for inline layout */
  compact?: boolean
}

export function LikeDislike({ onLike, onDislike, currentFeedback, disabled = false, status, compact = false }: LikeDislikeProps) {
  const [feedbackState, setFeedbackState] = useState<"idle" | "received" | "training" | "complete">("idle")
  const [showConfetti, setShowConfetti] = useState(false)

  // Watch for training status events
  useEffect(() => {
    if (!status) return

    if (status.step === "feedback_received") {
      setFeedbackState("received")
    } else if (status.step === "training_started" || status.step === "training_applied") {
      setFeedbackState("training")
    } else if (status.step === "training_complete") {
      setFeedbackState("complete")
      const timer = setTimeout(() => setFeedbackState("idle"), 2500)
      return () => clearTimeout(timer)
    }
  }, [status])

  // Reset feedback state when track changes
  useEffect(() => {
    if (currentFeedback === null) {
      setFeedbackState("idle")
    }
  }, [currentFeedback])

  const handleLike = () => {
    if (disabled) return
    triggerHaptic("medium")
    setShowConfetti(true)
    setTimeout(() => setShowConfetti(false), 800)
    onLike()
    setFeedbackState("received")
  }

  const handleDislike = () => {
    if (disabled) return
    triggerHaptic("light")
    onDislike()
    setFeedbackState("received")
  }

  // Generate confetti particles
  const confettiParticles = Array.from({ length: 12 }, (_, i) => ({
    id: i,
    angle: (i / 12) * 360,
    delay: i * 0.03,
    size: 4 + Math.random() * 4,
    color: i % 2 === 0 ? "#22c55e" : "#4ade80",
  }))

  return (
    <div className={cn("flex items-center", compact ? "gap-3" : "flex-col gap-2")}>
      {/* Buttons row */}
      <div className={cn("flex items-center justify-center", compact ? "gap-3" : "gap-6")}>
        {/* Dislike button */}
        <motion.button
          whileTap={{ scale: 0.85 }}
          onClick={handleDislike}
          disabled={disabled}
          className={cn(
            "relative w-12 h-12 rounded-full flex items-center justify-center",
            "border-2 transition-all duration-300",
            currentFeedback === "dislike"
              ? "bg-destructive/20 border-destructive text-destructive shadow-lg shadow-destructive/20"
              : "border-white/20 hover:border-destructive/50 hover:bg-destructive/10 text-foreground",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          aria-label="Dislike this track"
          aria-pressed={currentFeedback === "dislike"}
        >
          <motion.div
            animate={
              currentFeedback === "dislike"
                ? { scale: [1, 1.3, 0.9, 1.1, 1], rotate: [0, -10, 10, -5, 0] }
                : {}
            }
            transition={{ duration: 0.4 }}
          >
            <ThumbsDown
              className={cn("w-5 h-5 transition-all", currentFeedback === "dislike" && "fill-current")}
            />
          </motion.div>

          {/* Ripple effect */}
          {currentFeedback === "dislike" && (
            <motion.div
              initial={{ scale: 0, opacity: 0.5 }}
              animate={{ scale: 2, opacity: 0 }}
              transition={{ duration: 0.5 }}
              className="absolute inset-0 rounded-full bg-destructive/30"
            />
          )}
        </motion.button>

        {/* Like button with heart */}
        <motion.button
          whileTap={{ scale: 0.85 }}
          onClick={handleLike}
          disabled={disabled}
          className={cn(
            "relative w-14 h-14 rounded-full flex items-center justify-center",
            "border-2 transition-all duration-300",
            currentFeedback === "like"
              ? "bg-success/20 border-success text-success shadow-lg shadow-success/25"
              : "border-white/20 hover:border-success/50 hover:bg-success/10 text-foreground",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          aria-label="Like this track"
          aria-pressed={currentFeedback === "like"}
        >
          <motion.div
            animate={
              currentFeedback === "like"
                ? { scale: [1, 1.4, 0.8, 1.2, 1] }
                : {}
            }
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <Heart
              className={cn(
                "w-6 h-6 transition-all",
                currentFeedback === "like" && "fill-current"
              )}
            />
          </motion.div>

          {/* Confetti explosion */}
          <AnimatePresence>
            {showConfetti &&
              confettiParticles.map((particle) => (
                <motion.div
                  key={particle.id}
                  initial={{
                    scale: 0,
                    x: 0,
                    y: 0,
                    opacity: 1,
                  }}
                  animate={{
                    scale: [0, 1, 0.5],
                    x: Math.cos((particle.angle * Math.PI) / 180) * 50,
                    y: Math.sin((particle.angle * Math.PI) / 180) * 50 - 20,
                    opacity: [1, 1, 0],
                  }}
                  exit={{ opacity: 0 }}
                  transition={{
                    duration: 0.6,
                    delay: particle.delay,
                    ease: "easeOut",
                  }}
                  className="absolute rounded-full pointer-events-none"
                  style={{
                    width: particle.size,
                    height: particle.size,
                    backgroundColor: particle.color,
                  }}
                />
              ))}
          </AnimatePresence>

          {/* Glow pulse */}
          {currentFeedback === "like" && (
            <motion.div
              initial={{ scale: 1, opacity: 0.6 }}
              animate={{ scale: 1.5, opacity: 0 }}
              transition={{ duration: 0.6 }}
              className="absolute inset-0 rounded-full bg-success/40"
            />
          )}
        </motion.button>
      </div>

      {/* Hint text - hidden in compact mode */}
      {!compact && (
        <div className="h-4 flex items-center justify-center">
          <AnimatePresence mode="wait">
            {!currentFeedback && feedbackState === "idle" && !disabled && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ delay: 2 }}
                className="text-[11px] text-muted-foreground text-center"
              >
                Train your DJ with feedback
              </motion.p>
            )}
            {feedbackState === "training" && (
              <motion.p
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                className="text-[11px] text-warning flex items-center gap-1"
              >
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  ⚡
                </motion.span>
                Learning your taste...
              </motion.p>
            )}
            {feedbackState === "complete" && (
              <motion.p
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="text-[11px] text-success"
              >
                ✓ DJ updated!
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
