"use client"

import { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { Music, Volume2, X, RotateCcw } from "lucide-react"
import { cn } from "@/lib/utils"

interface PreviewTrack {
  title: string
  artist: string
  artworkUrl?: string
  previewUrl?: string
}

interface PreviewCardProps {
  track: PreviewTrack | null
  isPlaying?: boolean
  progress?: number
  isDucked?: boolean
  onDismiss?: () => void
  onReplay?: () => void
  className?: string
}

/**
 * Floating mini-card showing the currently playing song preview during onboarding.
 *
 * Features:
 * - Album art thumbnail
 * - Track title and artist
 * - Animated waveform indicating playback
 * - Visual indicator when audio is ducked
 * - Auto-shows/hides based on track prop
 */
export function PreviewCard({
  track,
  isPlaying = true,
  progress = 0,
  isDucked = false,
  onDismiss,
  onReplay,
  className,
}: PreviewCardProps) {
  const [artworkFailed, setArtworkFailed] = useState(false)

  useEffect(() => {
    setArtworkFailed(false)
  }, [track?.title, track?.artist])

  if (!track) return null

  return (
    <div className={cn("w-full rounded-2xl bg-surface-2/80 border border-white/5 overflow-hidden", className)}>
      <div className="flex items-center gap-3 p-3">
        {/* Album Art */}
        <div className="relative w-12 h-12 rounded-xl overflow-hidden flex-shrink-0 bg-surface-3">
          {track.artworkUrl && !artworkFailed ? (
            <img
              src={track.artworkUrl || "/placeholder.svg"}
              alt={`${track.title} artwork`}
              className="w-full h-full object-cover"
              onError={() => setArtworkFailed(true)}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center gradient-bg">
              <Music className="w-5 h-5 text-white/80" />
            </div>
          )}

          {/* Playing indicator overlay */}
          {isPlaying && (
            <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
              <MiniWaveform isPlaying={isPlaying} isDucked={isDucked} />
            </div>
          )}
        </div>

        {/* Track Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium truncate text-foreground">{track.title}</p>
            {isDucked && <Volume2 className="flex-shrink-0 w-3 h-3 text-muted-foreground animate-pulse" />}
          </div>
          <p className="text-xs text-muted-foreground truncate">{track.artist}</p>

          {/* Progress bar */}
          <div className="mt-2 h-1 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              className="h-full gradient-bg"
              style={{ width: `${progress * 100}%` }}
              transition={{ duration: 0.1 }}
            />
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1">
          {onReplay && (
            <button
              onClick={onReplay}
              className="flex-shrink-0 w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 
                         flex items-center justify-center transition-colors"
              aria-label="Replay preview"
              title="Replay preview"
            >
              <RotateCcw className="w-4 h-4 text-muted-foreground" />
            </button>
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="flex-shrink-0 w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 
                         flex items-center justify-center transition-colors"
              aria-label="Dismiss preview"
            >
              <X className="w-4 h-4 text-muted-foreground" />
            </button>
          )}
        </div>
      </div>

      {/* Now previewing label */}
      <div className="flex items-center justify-center gap-1.5 px-3 pb-2">
        <motion.div
          animate={{ scale: [1, 1.3, 1] }}
          transition={{ duration: 1.5, repeat: Number.POSITIVE_INFINITY }}
          className="w-1 h-1 rounded-full bg-primary"
        />
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
          {isDucked ? "Listening..." : "Now previewing"}
        </span>
      </div>
    </div>
  )
}

/**
 * Mini waveform visualizer for the preview card.
 * Shows animated bars when playing, reduced animation when ducked.
 */
function MiniWaveform({
  isPlaying,
  isDucked,
}: {
  isPlaying: boolean
  isDucked: boolean
}) {
  return (
    <div className="flex items-end justify-center gap-0.5 h-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <motion.div
          key={i}
          className="w-0.5 bg-white rounded-full"
          animate={{
            height: isPlaying ? (isDucked ? [4, 6, 4] : [4, 12, 6, 10, 4]) : [4],
            opacity: isDucked ? 0.5 : 1,
          }}
          transition={{
            duration: isDucked ? 1.5 : 0.8,
            repeat: Number.POSITIVE_INFINITY,
            delay: i * 0.1,
            ease: "easeInOut",
          }}
          style={{ minHeight: 4 }}
        />
      ))}
    </div>
  )
}

export default PreviewCard
