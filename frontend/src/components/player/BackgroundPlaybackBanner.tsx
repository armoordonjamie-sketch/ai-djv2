"use client"

import { motion, AnimatePresence } from "framer-motion"
import { Play, AlertCircle, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import { triggerHaptic } from "@/lib/motion"

interface BackgroundPlaybackBannerProps {
  /** Whether playback was paused due to iOS background limitation */
  wasPausedByBackground: boolean
  /** Whether the app is running as iOS PWA */
  isIOSPWA: boolean
  /** Callback to resume playback */
  onResume: () => void
  /** Whether playback is currently loading/buffering */
  isLoading?: boolean
  className?: string
}

/**
 * Banner that appears when iOS Safari/PWA pauses audio in the background.
 * Prompts user to tap to resume playback.
 */
export function BackgroundPlaybackBanner({
  wasPausedByBackground,
  isIOSPWA,
  onResume,
  isLoading,
  className,
}: BackgroundPlaybackBannerProps) {
  const handleResume = () => {
    triggerHaptic("medium")
    onResume()
  }

  // Only show when playback was paused by iOS background limitation
  if (!wasPausedByBackground) return null

  return (
    <AnimatePresence>
      {wasPausedByBackground && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className={cn(
            "fixed top-0 left-0 right-0 z-[60] safe-area-inset-top",
            "bg-warning/95 backdrop-blur-sm",
            className,
          )}
        >
          <button onClick={handleResume} disabled={isLoading} className="w-full px-4 py-3 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-warning-foreground/20 flex items-center justify-center flex-shrink-0">
              {isLoading ? (
                <RefreshCw className="w-5 h-5 text-warning-foreground animate-spin" />
              ) : (
                <Play className="w-5 h-5 text-warning-foreground ml-0.5" />
              )}
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-medium text-warning-foreground">Playback paused</p>
              <p className="text-xs text-warning-foreground/80">{isLoading ? "Resuming..." : "Tap to resume"}</p>
            </div>
            {isIOSPWA && (
              <div className="flex items-center gap-1 text-warning-foreground/60">
                <AlertCircle className="w-4 h-4" />
              </div>
            )}
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
