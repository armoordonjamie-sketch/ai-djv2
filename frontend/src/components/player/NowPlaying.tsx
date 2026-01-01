"use client"

import type React from "react"
import { useState, useEffect, useMemo } from "react"

import { motion, AnimatePresence } from "framer-motion"
import { Music, Radio } from "lucide-react"
import { cn } from "@/lib/utils"
import { SkeletonPlayer } from "@/components/ui/Skeleton"
import { AudioWaveform } from "./AudioWaveform"
import { prefersReducedMotion } from "@/lib/motion"
import type { StatusEvent } from "@/lib/types"

interface Track {
  id: string
  title: string
  artist: string
  artworkUrl?: string
}

interface NowPlayingProps {
  track: Track | null
  moodColor?: string
  moodName?: string
  status?: StatusEvent | null
  isLoading?: boolean
  isPlaying?: boolean
  /** When true, AI feed is expanded and vinyl should scale down */
  feedExpanded?: boolean
  /** Available height from parent container (for dynamic sizing) */
  availableHeight?: number
  className?: string
}

/**
 * Clamp a value between min and max
 */
function clamp(min: number, value: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function NowPlaying({
  track,
  moodColor = "#8b5cf6",
  moodName,
  status,
  isLoading,
  isPlaying = true,
  feedExpanded = false,
  availableHeight = 0,
  className,
}: NowPlayingProps) {
  // Track artwork load failures to show placeholder
  const [artworkFailed, setArtworkFailed] = useState(false)
  const reducedMotion = prefersReducedMotion()

  // Reset artwork failure state when track changes
  useEffect(() => {
    setArtworkFailed(false)
  }, [track?.id])

  /**
   * Dynamic vinyl size based on available height.
   * When feed is expanded, we have less vertical space, so vinyl shrinks.
   * When collapsed, vinyl can be larger.
   * 
   * The formula:
   * - feedExpanded: use ~46-50% of available height
   * - feedCollapsed: use ~58-62% of available height
   * - Minimum 120px, maximum 300px (increased for large screens)
   */
  const vinylSize = useMemo(() => {
    if (availableHeight <= 0) {
      // Fallback to responsive classes if no measurement yet
      return feedExpanded ? 140 : 200
    }
    // Use different percentages based on feed state
    const percentage = feedExpanded ? 0.48 : 0.60
    const computed = Math.floor(availableHeight * percentage)
    return clamp(120, computed, 300)
  }, [availableHeight, feedExpanded])

  // Show skeleton when loading and no track yet
  if (isLoading && !track) {
    return (
      <div className={cn("text-center flex items-center justify-center", className)}>
        <SkeletonPlayer />
      </div>
    )
  }

  if (!track) {
    return (
      <div className={cn("text-center flex flex-col items-center justify-center", className)}>
        {/* Empty state with animated gradient */}
        <div
          className="relative mx-auto"
          style={{ width: vinylSize, height: vinylSize }}
        >
          <motion.div
            animate={{
              scale: [1, 1.05, 1],
              opacity: [0.3, 0.5, 0.3],
            }}
            transition={{ duration: 3, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
            className="absolute inset-0 rounded-full gradient-bg opacity-20 blur-3xl"
          />
          <div className="relative w-full h-full rounded-full bg-surface-2 border border-border flex flex-col items-center justify-center gap-2">
            <motion.div
              animate={{ y: [0, -6, 0] }}
              transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
            >
              <div
                className="rounded-full gradient-bg flex items-center justify-center shadow-lg"
                style={{ width: vinylSize * 0.25, height: vinylSize * 0.25 }}
              >
                <Music className="text-white" style={{ width: vinylSize * 0.12, height: vinylSize * 0.12 }} />
              </div>
            </motion.div>
            <div className="space-y-0.5 px-4 text-center">
              <p className="text-sm font-semibold">Ready to play</p>
              <p className="text-xs text-muted-foreground">Tap play to start your AI DJ</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Get status-based micro-message
  const getAIStatusLine = () => {
    if (!status) return null
    if (status.category === "generation") {
      switch (status.step) {
        case "planning":
          return "AI is planning your next track..."
        case "selecting_track":
          return "AI is finding something perfect..."
        case "mixing":
          return "AI is creating a smooth transition..."
        default:
          return null
      }
    }
    return null
  }

  const aiStatusLine = getAIStatusLine()

  // Calculate proportional sizes based on vinyl size
  const waveformHeight = Math.max(16, Math.floor(vinylSize * 0.1))
  const titleSize = vinylSize > 180 ? "text-base" : "text-sm"
  const artistSize = "text-xs"

  return (
    <div className={cn("w-full h-full flex flex-col items-center justify-center gap-2", className)}>
      <AnimatePresence mode="wait">
        <motion.div
          key={track.id}
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 40, scale: 0.95 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -40, scale: 0.95 }}
          transition={
            reducedMotion
              ? { duration: 0.15 }
              : { type: "spring", stiffness: 300, damping: 30, mass: 0.8 }
          }
          className="flex flex-col items-center gap-2"
        >
          {/* Vinyl disc with album art - dynamically sized */}
          <motion.div
            layout={!reducedMotion}
            transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 350, damping: 35 }}
            className="relative mx-auto"
            style={{
              width: vinylSize,
              height: vinylSize,
              "--mood-color": `${moodColor}60`
            } as React.CSSProperties}
          >
            {/* Animated glow effect */}
            <motion.div
              animate={{
                scale: [1, 1.08, 1],
                opacity: [0.3, 0.5, 0.3],
              }}
              transition={{ duration: 4, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
              className="absolute rounded-full blur-3xl"
              style={{
                inset: -20,
                background: `radial-gradient(circle, ${moodColor}80 0%, ${moodColor}40 40%, transparent 70%)`,
              }}
            />

            {/* Vinyl disc container */}
            <div className="relative w-full h-full">
              {/* Outer vinyl ring */}
              <motion.div
                animate={isPlaying ? { rotate: 360 } : { rotate: 0 }}
                transition={
                  isPlaying
                    ? { duration: 3, repeat: Infinity, ease: "linear" }
                    : { duration: 0.5, ease: "easeOut" }
                }
                className="absolute inset-0 rounded-full"
                style={{
                  background: `
                    radial-gradient(circle at center, 
                      transparent 38%, 
                      rgba(20, 20, 25, 0.95) 39%, 
                      rgba(30, 30, 35, 0.98) 40%, 
                      rgba(25, 25, 30, 0.95) 60%, 
                      rgba(35, 35, 40, 0.98) 75%, 
                      rgba(20, 20, 25, 0.95) 90%, 
                      rgba(10, 10, 15, 1) 100%
                    )
                  `,
                  boxShadow: `
                    inset 0 0 60px rgba(0,0,0,0.6),
                    0 8px 32px rgba(0,0,0,0.4),
                    0 2px 8px rgba(0,0,0,0.3)
                  `,
                }}
              >
                {/* Vinyl grooves */}
                {[45, 55, 65, 75, 85].map((size) => (
                  <div
                    key={size}
                    className="absolute rounded-full border border-white/[0.03]"
                    style={{
                      inset: `${(100 - size) / 2}%`,
                    }}
                  />
                ))}

                {/* Center hole */}
                <div
                  className="absolute rounded-full bg-surface-1"
                  style={{
                    inset: "46%",
                    boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)",
                  }}
                />
              </motion.div>

              {/* Album art label (centered) */}
              <motion.div
                animate={isPlaying ? { rotate: 360 } : { rotate: 0 }}
                transition={
                  isPlaying
                    ? { duration: 3, repeat: Infinity, ease: "linear" }
                    : { duration: 0.5, ease: "easeOut" }
                }
                className="absolute rounded-full overflow-hidden shadow-xl ring-2 ring-white/10"
                style={{
                  inset: "22%",
                }}
              >
                {track.artworkUrl && !artworkFailed ? (
                  <img
                    src={track.artworkUrl}
                    alt={`${track.title} by ${track.artist}`}
                    className="w-full h-full object-cover"
                    onError={() => setArtworkFailed(true)}
                  />
                ) : (
                  <div
                    className="w-full h-full flex items-center justify-center"
                    style={{
                      background: `linear-gradient(135deg, ${moodColor} 0%, var(--gradient-end) 100%)`,
                    }}
                  >
                    <Music className="w-10 h-10 text-white/80" />
                  </div>
                )}
              </motion.div>

              {/* Shine reflection */}
              <div
                className="absolute inset-0 rounded-full pointer-events-none"
                style={{
                  background: `linear-gradient(135deg, rgba(255,255,255,0.1) 0%, transparent 50%, rgba(0,0,0,0.2) 100%)`,
                }}
              />
            </div>
          </motion.div>

          {/* Audio Waveform Visualizer */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="w-full px-4"
          >
            <AudioWaveform isPlaying={isPlaying} color={moodColor} height={waveformHeight} barCount={20} />
          </motion.div>

          {/* Track info */}
          <motion.div
            key={track.title}
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="space-y-0.5 text-center"
          >
            <h2 className={cn(titleSize, "font-semibold truncate px-4 text-balance")}>{track.title}</h2>
            <p className={cn(artistSize, "text-muted-foreground truncate px-4")}>{track.artist}</p>
          </motion.div>
        </motion.div>
      </AnimatePresence>

      {/* AI status micro-line */}
      <AnimatePresence mode="wait">
        {aiStatusLine && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="flex items-center justify-center gap-2 text-[11px] text-muted-foreground"
          >
            <Radio className="w-3 h-3 animate-pulse" />
            <span>{aiStatusLine}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Current mood indicator */}
      {moodName && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-center gap-2 text-xs text-muted-foreground"
        >
          <motion.div
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: moodColor }}
          />
          <span>Playing {moodName}</span>
        </motion.div>
      )}
    </div>
  )
}
