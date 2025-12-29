"use client"

import type React from "react"

import { motion, AnimatePresence } from "framer-motion"
import { Music, Radio } from "lucide-react"
import { cn } from "@/lib/utils"
import { SkeletonPlayer } from "@/components/ui/Skeleton"
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
  className?: string
}

export function NowPlaying({
  track,
  moodColor = "#8b5cf6",
  moodName,
  status,
  isLoading,
  className,
}: NowPlayingProps) {
  // Show skeleton when loading and no track yet
  if (isLoading && !track) {
    return (
      <div className={cn("text-center", className)}>
        <SkeletonPlayer />
      </div>
    )
  }

  if (!track) {
    return (
      <div className={cn("text-center space-y-6", className)}>
        {/* Empty state with animated gradient */}
        <div className="relative w-56 h-56 mx-auto">
          <motion.div
            animate={{
              scale: [1, 1.05, 1],
              opacity: [0.3, 0.5, 0.3],
            }}
            transition={{ duration: 3, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
            className="absolute inset-0 rounded-3xl gradient-bg opacity-20 blur-2xl"
          />
          <div className="relative w-full h-full rounded-3xl bg-surface-2 border border-border flex flex-col items-center justify-center gap-4">
            <motion.div
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
            >
              <div className="w-20 h-20 rounded-2xl gradient-bg flex items-center justify-center">
                <Music className="w-10 h-10 text-white" />
              </div>
            </motion.div>
            <div className="space-y-1 px-6">
              <p className="text-lg font-semibold">Ready to play</p>
              <p className="text-sm text-muted-foreground">Tap play to start your AI DJ</p>
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

  return (
    <div className={cn("text-center space-y-3", className)}>
      {/* Artwork with dynamic glow */}
      <motion.div
        key={track.id}
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 25 }}
        className="relative w-56 h-56 mx-auto"
        style={{ "--mood-color": `${moodColor}60` } as React.CSSProperties}
      >
        {/* Animated glow effect */}
        <motion.div
          animate={{
            scale: [1, 1.1, 1],
            opacity: [0.4, 0.6, 0.4],
          }}
          transition={{ duration: 4, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
          className="absolute inset-0 rounded-3xl blur-3xl"
          style={{
            background: `linear-gradient(135deg, ${moodColor} 0%, var(--gradient-end) 100%)`,
            opacity: 0.4,
          }}
        />

        {/* Main artwork card */}
        <div className="relative w-full h-full rounded-3xl overflow-hidden shadow-2xl ring-1 ring-white/10">
          {track.artworkUrl ? (
            <img
              src={track.artworkUrl || "/placeholder.svg"}
              alt={`${track.title} by ${track.artist}`}
              className="w-full h-full object-cover"
            />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center"
              style={{
                background: `linear-gradient(135deg, ${moodColor} 0%, var(--gradient-end) 50%, var(--warning) 100%)`,
              }}
            >
              {/* Pattern overlay */}
              <div className="absolute inset-0 opacity-20">
                <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent" />
                <div className="absolute bottom-0 left-0 right-0 h-1/2 bg-gradient-to-t from-black/40 to-transparent" />
              </div>
              <Music className="w-20 h-20 text-white/80" />
            </div>
          )}

          {/* Equalizer overlay when playing */}
          <div className="absolute bottom-3 right-3 flex items-end gap-0.5 h-4">
            {[1, 2, 3, 4].map((i) => (
              <motion.div
                key={i}
                animate={{
                  height: ["30%", "100%", "50%", "80%", "30%"],
                }}
                transition={{
                  duration: 1,
                  repeat: Number.POSITIVE_INFINITY,
                  delay: i * 0.1,
                  ease: "easeInOut",
                }}
                className="w-1 bg-white/80 rounded-full"
                style={{ originY: 1 }}
              />
            ))}
          </div>
        </div>
      </motion.div>

      {/* Track info */}
      <motion.div
        key={track.title}
        initial={{ y: 10, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="space-y-1"
      >
        <h2 className="text-xl font-bold truncate px-4 text-balance">{track.title}</h2>
        <p className="text-muted-foreground truncate px-4">{track.artist}</p>
      </motion.div>

      {/* AI status micro-line */}
      <AnimatePresence mode="wait">
        {aiStatusLine && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="flex items-center justify-center gap-2 text-xs text-muted-foreground"
          >
            <Radio className="w-3 h-3 animate-pulse" />
            <span>{aiStatusLine}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* DJ Caption removed to save space on mobile */}

      {/* Current mood indicator */}
      {moodName && (
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: moodColor }} />
          <span>Playing {moodName}</span>
        </div>
      )}
    </div>
  )
}
