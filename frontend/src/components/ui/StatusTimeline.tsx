"use client"

import { motion, AnimatePresence } from "framer-motion"
import { Check, Loader2, Circle, AlertCircle } from "lucide-react"
import type { StatusEvent, StatusStep } from "@/lib/types"
import { cn } from "@/lib/utils"

interface TimelineStep {
  id: StatusStep
  label: string
  description?: string
}

interface StatusTimelineProps {
  steps: TimelineStep[]
  currentStatus: StatusEvent | null
  completedSteps: StatusStep[]
  className?: string
  /** Vertical or horizontal layout */
  orientation?: "vertical" | "horizontal"
}

/**
 * Visual timeline showing progress through multi-step processes.
 * Used during onboarding and generation flows to show where the user is.
 */
export function StatusTimeline({
  steps,
  currentStatus,
  completedSteps,
  className = "",
  orientation = "vertical",
}: StatusTimelineProps) {
  const getStepState = (step: TimelineStep): "completed" | "current" | "upcoming" | "error" => {
    if (currentStatus?.step === step.id && currentStatus.severity === "error") {
      return "error"
    }
    if (completedSteps.includes(step.id)) return "completed"
    if (currentStatus?.step === step.id) return "current"
    return "upcoming"
  }

  const getStepIcon = (state: "completed" | "current" | "upcoming" | "error") => {
    switch (state) {
      case "completed":
        return (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 400, damping: 15 }}
            className="w-6 h-6 rounded-full bg-success flex items-center justify-center"
          >
            <Check className="w-3.5 h-3.5 text-success-foreground" />
          </motion.div>
        )
      case "current":
        return (
          <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
            <Loader2 className="w-3.5 h-3.5 text-primary-foreground animate-spin" />
          </div>
        )
      case "error":
        return (
          <div className="w-6 h-6 rounded-full bg-destructive flex items-center justify-center">
            <AlertCircle className="w-3.5 h-3.5 text-destructive-foreground" />
          </div>
        )
      default:
        return (
          <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center">
            <Circle className="w-2 h-2 text-muted-foreground" />
          </div>
        )
    }
  }

  if (orientation === "horizontal") {
    return (
      <div className={cn("flex items-center justify-between", className)}>
        {steps.map((step, index) => {
          const state = getStepState(step)
          const isLast = index === steps.length - 1

          return (
            <div key={step.id} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                {getStepIcon(state)}
                <span
                  className={cn(
                    "text-xs mt-2 text-center max-w-16",
                    state === "completed" && "text-success",
                    state === "current" && "text-primary font-medium",
                    state === "error" && "text-destructive",
                    state === "upcoming" && "text-muted-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>
              {!isLast && (
                <div className="flex-1 h-0.5 mx-2 bg-muted relative overflow-hidden">
                  <motion.div
                    className="absolute inset-y-0 left-0 bg-success"
                    initial={{ width: 0 }}
                    animate={{
                      width: state === "completed" || (state === "current" && currentStatus?.progress) ? "100%" : 0,
                    }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col gap-0", className)}>
      {steps.map((step, index) => {
        const state = getStepState(step)
        const isLast = index === steps.length - 1

        return (
          <div key={step.id} className="flex gap-3">
            {/* Icon and connector line */}
            <div className="flex flex-col items-center">
              {getStepIcon(state)}
              {!isLast && (
                <div className="w-0.5 flex-1 min-h-8 bg-muted relative overflow-hidden">
                  <motion.div
                    className="absolute inset-x-0 top-0 bg-success"
                    initial={{ height: 0 }}
                    animate={{
                      height: state === "completed" ? "100%" : 0,
                    }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              )}
            </div>

            {/* Content */}
            <div className={cn("pb-6", isLast && "pb-0")}>
              <h4
                className={cn(
                  "text-sm font-medium",
                  state === "completed" && "text-success",
                  state === "current" && "text-primary",
                  state === "error" && "text-destructive",
                  state === "upcoming" && "text-muted-foreground",
                )}
              >
                {step.label}
              </h4>
              {step.description && <p className="text-xs text-muted-foreground mt-0.5">{step.description}</p>}
              {/* Show current status message if this is the active step */}
              <AnimatePresence>
                {state === "current" && currentStatus && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="text-xs text-primary mt-1"
                  >
                    {currentStatus.user_message}
                  </motion.p>
                )}
              </AnimatePresence>
              {/* Progress bar for current step */}
              {state === "current" && currentStatus?.progress !== undefined && (
                <div className="w-32 h-1 bg-muted rounded-full overflow-hidden mt-2">
                  <motion.div
                    className="h-full bg-primary rounded-full"
                    animate={{ width: `${currentStatus.progress * 100}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Preset timeline configurations
export const onboardingSteps: TimelineStep[] = [
  { id: "voice_capture", label: "Voice", description: "Record your preferences" },
  { id: "voice_processing", label: "Processing", description: "Analyzing your taste" },
  { id: "mood_creating", label: "Moods", description: "Creating personalized moods" },
  { id: "onboarding_complete", label: "Ready", description: "All set!" },
]

export const generationSteps: TimelineStep[] = [
  { id: "planning", label: "Planning", description: "Selecting style" },
  { id: "selecting_track", label: "Finding", description: "Searching tracks" },
  { id: "mixing", label: "Mixing", description: "Creating transition" },
  { id: "ready", label: "Ready", description: "Queued to play" },
]
