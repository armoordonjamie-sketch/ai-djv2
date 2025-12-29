"use client"

import { motion, AnimatePresence } from "framer-motion"
import { Music, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import type { StatusEvent } from "@/lib/types"

interface Track {
  id: string
  title: string
  artist: string
  artworkUrl?: string
}

interface NextUpCardProps {
  track?: Track | null
  status?: StatusEvent | null
  className?: string
}

/**
 * Shows the next track in queue with status information.
 * Displays loading state when AI is preparing the next segment.
 */
export function NextUpCard({ track, status, className }: NextUpCardProps) {
  // Determine if we're preparing next track
  const isPreparing =
    status?.category === "generation" && ["planning", "selecting_track", "mixing", "encoding"].includes(status.step)

  // Get status-specific message
  const getStatusMessage = () => {
    if (!status) return null
    switch (status.step) {
      case "planning":
        return "Planning next track..."
      case "selecting_track":
        return "Finding something perfect..."
      case "mixing":
        return "Creating transition..."
      case "encoding":
        return "Preparing audio..."
      case "queued":
        return "Ready to play"
      default:
        return null
    }
  }

  const statusMessage = getStatusMessage()

  // Don't show if nothing to display
  if (!track && !isPreparing) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("rounded-xl bg-surface-1 border border-border overflow-hidden", className)}
    >
      <div className="flex items-center gap-3 p-3">
        {/* Artwork or loading state */}
        <div className="relative w-12 h-12 rounded-lg overflow-hidden flex-shrink-0 bg-surface-2">
          <AnimatePresence mode="wait">
            {track?.artworkUrl ? (
              <motion.img
                key={track.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                src={track.artworkUrl}
                alt=""
                className="w-full h-full object-cover"
              />
            ) : isPreparing ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="w-full h-full flex items-center justify-center"
              >
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                >
                  <Sparkles className="w-5 h-5 text-primary" />
                </motion.div>
              </motion.div>
            ) : (
              <motion.div
                key="placeholder"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="w-full h-full flex items-center justify-center"
              >
                <Music className="w-5 h-5 text-muted-foreground" />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Track info or status */}
        <div className="flex-1 min-w-0">
          <p className="text-xs text-muted-foreground mb-0.5">Next up</p>
          {track ? (
            <>
              <p className="text-sm font-medium truncate">{track.title}</p>
              <p className="text-xs text-muted-foreground truncate">{track.artist}</p>
            </>
          ) : isPreparing && statusMessage ? (
            <p className="text-sm text-primary animate-pulse">{statusMessage}</p>
          ) : (
            <p className="text-sm text-muted-foreground">AI is preparing...</p>
          )}
        </div>

        {/* Status indicator */}
        {isPreparing && (
          <div className="flex-shrink-0">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          </div>
        )}
      </div>
    </motion.div>
  )
}
