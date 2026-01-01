"use client"

import type React from "react"
import { useState, useEffect } from "react"

import { motion, AnimatePresence } from "framer-motion"
import { Play, Pause, SkipForward } from "lucide-react"
import { Link } from "react-router-dom"
import { cn } from "@/lib/utils"
import { triggerHaptic } from "@/lib/motion"
import { AudioWaveform } from "./AudioWaveform"
import { LogoMark } from "@/components/branding/Logo"

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
  /** Progress 0-1 for the progress bar */
  progress?: number
  moodColor?: string
  className?: string
}

/**
 * Premium compact mini-player with glassmorphism that appears above bottom navigation.
 */
export function MiniPlayer({
  track,
  isPlaying,
  onPlayPause,
  onSkip,
  hidden,
  progress = 0,
  moodColor = "#8b5cf6",
  className,
}: MiniPlayerProps) {
  const [artworkFailed, setArtworkFailed] = useState(false)
  
  // Reset artwork failure when track changes
  useEffect(() => {
    setArtworkFailed(false)
  }, [track?.id])
  
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
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        className={cn(
          "fixed bottom-[calc(72px+env(safe-area-inset-bottom,0px))] left-4 right-4 z-40",
          "glass-strong rounded-3xl border border-white/10 shadow-xl shadow-black/30",
          "pb-safe-bottom",
          className,
        )}
      >
        {/* Progress bar at top */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-white/10 rounded-t-3xl overflow-hidden">
          <motion.div
            className="h-full"
            style={{ background: `linear-gradient(to right, ${moodColor}, var(--gradient-end))` }}
            initial={{ width: 0 }}
            animate={{ width: `${progress * 100}%` }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          />
        </div>

        <Link to="/player" className="flex items-center gap-3 px-4 py-3">
          {/* Artwork with vinyl-like styling */}
          <motion.div
            className="relative w-12 h-12 rounded-xl overflow-hidden flex-shrink-0 shadow-lg"
            whileTap={{ scale: 0.95 }}
          >
            {/* Spinning ring when playing */}
            {isPlaying && (
              <motion.div
                className="absolute inset-[-2px] rounded-xl"
                style={{
                  background: `conic-gradient(from 0deg, ${moodColor}60, transparent, ${moodColor}60)`,
                }}
                animate={{ rotate: 360 }}
                transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
              />
            )}
          <div className="absolute inset-0 rounded-xl overflow-hidden bg-surface-2">
            <AnimatePresence mode="wait">
              <motion.div
                key={track.id}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.02 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
                className="absolute inset-0"
              >
                {track.artworkUrl && !artworkFailed ? (
                  <img
                    src={track.artworkUrl}
                    alt={`${track.title} artwork`}
                    className="w-full h-full object-cover"
                    onError={() => setArtworkFailed(true)}
                  />
                ) : (
                  <div
                    className="w-full h-full flex items-center justify-center"
                    style={{ background: `linear-gradient(135deg, ${moodColor}, var(--gradient-end))` }}
                  >
                    <LogoMark size={24} />
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </div>
          </motion.div>

          {/* Track info */}
          <div className="flex-1 min-w-0">
            <AnimatePresence mode="wait">
              <motion.div
                key={track.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                <p className="text-sm font-medium truncate">{track.title}</p>
                <p className="text-xs text-muted-foreground truncate">{track.artist}</p>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Mini waveform */}
          <div className="hidden sm:block w-16">
            <AudioWaveform isPlaying={isPlaying} compact height={24} barCount={8} color={moodColor} />
          </div>

          {/* Controls with larger touch targets */}
          <div className="flex items-center gap-1">
            <motion.button
              whileTap={{ scale: 0.85 }}
              onClick={handlePlayPause}
              className={cn(
                "w-11 h-11 rounded-full flex items-center justify-center",
                "hover:bg-white/10 active:bg-white/15 transition-colors",
              )}
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
                    <Pause className="w-5 h-5" fill="currentColor" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="play"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    transition={{ duration: 0.1 }}
                  >
                    <Play className="w-5 h-5 ml-0.5" fill="currentColor" />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.button>

            <motion.button
              whileTap={{ scale: 0.85 }}
              onClick={handleSkip}
              className={cn(
                "w-11 h-11 rounded-full flex items-center justify-center",
                "hover:bg-white/10 active:bg-white/15 transition-colors",
              )}
              aria-label="Skip"
            >
              <SkipForward className="w-5 h-5" />
            </motion.button>
          </div>
        </Link>
      </motion.div>
    </AnimatePresence>
  )
}
