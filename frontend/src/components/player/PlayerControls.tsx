"use client"

import { useState, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Play, Pause, SkipForward, Volume2, VolumeX, ChevronDown } from "lucide-react"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"
import { triggerHaptic } from "@/lib/motion"

interface PlayerControlsProps {
  isPlaying: boolean
  volume: number
  isMuted: boolean
  onPlayPause: () => void
  onSkip: () => void
  onVolumeChange: (value: number) => void
  onMuteToggle: () => void
  disabled?: boolean
}

export function PlayerControls({
  isPlaying,
  volume,
  isMuted,
  onPlayPause,
  onSkip,
  onVolumeChange,
  onMuteToggle,
  disabled = false,
}: PlayerControlsProps) {
  const [showVolume, setShowVolume] = useState(false)
  const [isSkipping, setIsSkipping] = useState(false)
  const playButtonRef = useRef<HTMLButtonElement>(null)

  const handlePlayPause = () => {
    triggerHaptic("medium")
    onPlayPause()
  }

  const handleSkip = () => {
    triggerHaptic("light")
    setIsSkipping(true)
    onSkip()
    setTimeout(() => setIsSkipping(false), 300)
  }

  return (
    <div className="space-y-2">
      {/* Main controls */}
      <div className="flex items-center justify-center gap-8">
        {/* Volume toggle (mobile-friendly) */}
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={() => setShowVolume(!showVolume)}
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center",
            "bg-surface-2 border border-border",
            "hover:bg-surface-3 transition-colors",
            "focus:outline-none focus:ring-2 focus:ring-primary/50",
          )}
          aria-label="Toggle volume control"
        >
          {showVolume ? <ChevronDown className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
        </motion.button>

        {/* Play/Pause button with ripple effect */}
        <motion.button
          ref={playButtonRef}
          whileTap={{ scale: 0.92 }}
          onClick={handlePlayPause}
          disabled={disabled}
          className={cn(
            "relative w-16 h-16 rounded-full flex items-center justify-center",
            "gradient-bg text-white shadow-lg shadow-primary/25",
            "hover:shadow-xl hover:shadow-primary/30 transition-shadow",
            "focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 focus:ring-offset-background",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          style={{ width: 64, height: 64 }}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          <AnimatePresence mode="wait">
            {isPlaying ? (
              <motion.div
                key="pause"
                initial={{ scale: 0, rotate: -90 }}
                animate={{ scale: 1, rotate: 0 }}
                exit={{ scale: 0, rotate: 90 }}
                transition={{ duration: 0.15 }}
              >
                <Pause className="w-7 h-7" fill="currentColor" />
              </motion.div>
            ) : (
              <motion.div
                key="play"
                initial={{ scale: 0, rotate: 90 }}
                animate={{ scale: 1, rotate: 0 }}
                exit={{ scale: 0, rotate: -90 }}
                transition={{ duration: 0.15 }}
              >
                <Play className="w-7 h-7 ml-1" fill="currentColor" />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Pulse ring when playing */}
          {isPlaying && (
            <motion.div
              className="absolute inset-0 rounded-full border-2 border-primary/30"
              animate={{
                scale: [1, 1.2, 1],
                opacity: [0.5, 0, 0.5],
              }}
              transition={{
                duration: 2,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }}
            />
          )}
        </motion.button>

        {/* Skip button */}
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={handleSkip}
          disabled={disabled}
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center",
            "bg-surface-2 border border-border",
            "hover:bg-surface-3 hover:border-primary/30 transition-all",
            "focus:outline-none focus:ring-2 focus:ring-primary/50",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          aria-label="Skip to next track"
        >
          <motion.div animate={isSkipping ? { x: [0, 4, 0] } : {}} transition={{ duration: 0.2 }}>
            <SkipForward className="w-5 h-5" />
          </motion.div>
        </motion.button>
      </div>

      {/* Collapsible volume control */}
      <AnimatePresence>
        {showVolume && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-3 max-w-xs mx-auto px-4 py-2 rounded-xl bg-surface-1 border border-border">
              <button
                onClick={onMuteToggle}
                className="p-2 rounded-lg hover:bg-surface-3 transition-colors"
                aria-label={isMuted ? "Unmute" : "Mute"}
              >
                {isMuted || volume === 0 ? (
                  <VolumeX className="w-5 h-5 text-muted-foreground" />
                ) : (
                  <Volume2 className="w-5 h-5" />
                )}
              </button>
              <Slider
                value={[isMuted ? 0 : volume * 100]}
                onValueChange={([v]) => onVolumeChange(v / 100)}
                max={100}
                step={1}
                className="flex-1"
                aria-label="Volume"
              />
              <span className="text-xs text-muted-foreground w-8 text-right tabular-nums">
                {Math.round(isMuted ? 0 : volume * 100)}%
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
