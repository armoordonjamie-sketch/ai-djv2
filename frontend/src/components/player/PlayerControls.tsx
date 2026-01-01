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
  moodColor?: string
  /** Compact mode for inline layout - removes internal glass wrapper */
  compact?: boolean
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
  moodColor = "#8b5cf6",
  compact = false,
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
    <div className={compact ? "" : "space-y-3"}>
      {/* Main controls - no internal glass wrapper in compact mode */}
      <div className={cn(
        "flex items-center justify-center gap-4",
        compact ? "" : "py-3 px-4 rounded-2xl glass-subtle mx-auto max-w-xs"
      )}>
        {/* Volume toggle (iOS 44pt minimum touch target) */}
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={() => setShowVolume(!showVolume)}
          className={cn(
            "w-11 h-11 rounded-full flex items-center justify-center",
            "bg-surface-2/80 border border-border/50",
            "hover:bg-surface-3 active:bg-surface-3 transition-colors",
            "focus:outline-none focus:ring-2 focus:ring-primary/50",
          )}
          aria-label="Toggle volume control"
        >
          {showVolume ? <ChevronDown className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
        </motion.button>

        {/* Play/Pause button - Large and prominent */}
        <motion.button
          ref={playButtonRef}
          whileTap={{ scale: 0.92 }}
          onClick={handlePlayPause}
          disabled={disabled}
          className={cn(
            "relative w-16 h-16 rounded-full flex items-center justify-center",
            "text-white shadow-xl",
            "focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 focus:ring-offset-background",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          style={{
            background: `linear-gradient(135deg, ${moodColor} 0%, var(--gradient-end) 100%)`,
            boxShadow: `0 8px 32px ${moodColor}40, 0 4px 12px rgba(0,0,0,0.3)`,
          }}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {/* Animated gradient ring */}
          <motion.div
            className="absolute inset-[-3px] rounded-full opacity-60"
            style={{
              background: `conic-gradient(from 0deg, ${moodColor}, var(--gradient-end), ${moodColor})`,
            }}
            animate={isPlaying ? { rotate: 360 } : {}}
            transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
          />

          {/* Inner button circle */}
          <div
            className="absolute inset-[3px] rounded-full flex items-center justify-center"
            style={{
              background: `linear-gradient(135deg, ${moodColor} 0%, var(--gradient-end) 100%)`,
            }}
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
                  <Play className="w-7 h-7 ml-0.5" fill="currentColor" />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Pulse rings when playing */}
          {isPlaying && (
            <>
              <motion.div
                className="absolute inset-0 rounded-full"
                style={{ border: `2px solid ${moodColor}40` }}
                animate={{
                  scale: [1, 1.3, 1.3],
                  opacity: [0.6, 0, 0],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeOut",
                }}
              />
              <motion.div
                className="absolute inset-0 rounded-full"
                style={{ border: `2px solid ${moodColor}30` }}
                animate={{
                  scale: [1, 1.5, 1.5],
                  opacity: [0.4, 0, 0],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeOut",
                  delay: 0.5,
                }}
              />
            </>
          )}
        </motion.button>

        {/* Skip button (iOS 44pt minimum) */}
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={handleSkip}
          disabled={disabled}
          className={cn(
            "w-11 h-11 rounded-full flex items-center justify-center",
            "bg-surface-2/80 border border-border/50",
            "hover:bg-surface-3 active:bg-surface-3 transition-all",
            "focus:outline-none focus:ring-2 focus:ring-primary/50",
            disabled && "opacity-50 cursor-not-allowed",
          )}
          aria-label="Skip to next track"
        >
          <motion.div
            animate={isSkipping ? { x: [0, 6, 0] } : {}}
            transition={{ duration: 0.25, ease: "easeOut" }}
          >
            <SkipForward className="w-5 h-5" />
          </motion.div>
        </motion.button>
      </div>

      {/* Collapsible volume control - hidden in compact mode */}
      <AnimatePresence>
        {showVolume && !compact && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-3 max-w-xs mx-auto px-4 py-2.5 rounded-xl glass-subtle">
              <button
                onClick={onMuteToggle}
                className="p-2 rounded-lg hover:bg-surface-3 active:bg-surface-3 transition-colors"
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
