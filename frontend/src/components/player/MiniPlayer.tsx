"use client"

import type React from "react"

import { motion, AnimatePresence } from "framer-motion"
import { Play, Pause, SkipForward, Music } from "lucide-react"
import { Link } from "react-router-dom"
import { cn } from "@/lib/utils"
import { triggerHaptic } from "@/lib/motion"

interface Track {
  id: string
  title: string
  artist: string
  artworkUrl?: string
}

interface MiniPlayerProps {
  track: Track | null
  isPlaying: boolean
  onPlayPause: () => void
  onSkip: () => void
  /** Hide mini player (e.g., when on player page) */
  hidden?: boolean
  className?: string
}

/**
 * Compact mini-player that appears above the bottom navigation
 * when music is playing and user is not on the player page.
 */
export function MiniPlayer({ track, isPlaying, onPlayPause, onSkip, hidden, className }: MiniPlayerProps) {
  if (!track || hidden) return null

  const handlePlayPause = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    triggerHaptic("light")
    onPlayPause()
  }

  const handleSkip = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    triggerHaptic("light")
    onSkip()
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 100, opacity: 0 }}
        className={cn(
          "fixed bottom-16 left-0 right-0 z-40",
          "bg-surface-1/95 backdrop-blur-xl border-t border-border",
          "pb-safe-bottom",
          className,
        )}
      >
        <Link to="/player" className="flex items-center gap-3 px-4 py-2">
          {/* Artwork */}
          <div className="w-12 h-12 rounded-lg overflow-hidden flex-shrink-0 bg-surface-2">
            {track.artworkUrl ? (
              <img
                src={track.artworkUrl || "/placeholder.svg"}
                alt={`${track.title} artwork`}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center gradient-bg">
                <Music className="w-5 h-5 text-white" />
              </div>
            )}
          </div>

          {/* Track info */}
          <div className="flex-1 min-w-0">
            <motion.p
              key={track.id}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm font-medium truncate"
            >
              {track.title}
            </motion.p>
            <p className="text-xs text-muted-foreground truncate">{track.artist}</p>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-1">
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={handlePlayPause}
              className="w-10 h-10 rounded-full flex items-center justify-center hover:bg-surface-3 transition-colors"
              aria-label={isPlaying ? "Pause" : "Play"}
            >
              <AnimatePresence mode="wait">
                {isPlaying ? (
                  <motion.div
                    key="pause"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    transition={{ duration: 0.1 }}
                  >
                    <Pause className="w-5 h-5" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="play"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    transition={{ duration: 0.1 }}
                  >
                    <Play className="w-5 h-5 ml-0.5" />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.button>

            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={handleSkip}
              className="w-10 h-10 rounded-full flex items-center justify-center hover:bg-surface-3 transition-colors"
              aria-label="Skip"
            >
              <SkipForward className="w-5 h-5" />
            </motion.button>
          </div>
        </Link>

        {/* Playing indicator bar */}
        {isPlaying && (
          <motion.div
            layoutId="miniPlayerProgress"
            className="absolute bottom-0 left-0 right-0 h-0.5 gradient-bg"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.3 }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  )
}
