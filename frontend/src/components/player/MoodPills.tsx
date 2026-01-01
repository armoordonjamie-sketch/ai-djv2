"use client"

import { useRef, useEffect } from "react"
import { motion } from "framer-motion"
import type { Mood } from "@/lib/types"
import { cn } from "@/lib/utils"
import { triggerHaptic } from "@/lib/motion"

interface MoodPillsProps {
  moods: Mood[]
  activeMoodId: string | null
  onMoodSelect: (moodId: string, name?: string, color?: string) => void
  disabled?: boolean
}

export function MoodPills({ moods, activeMoodId, onMoodSelect, disabled }: MoodPillsProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLButtonElement>(null)

  // Scroll active mood into view on mount
  useEffect(() => {
    if (activeRef.current && scrollRef.current) {
      const container = scrollRef.current
      const active = activeRef.current
      const containerRect = container.getBoundingClientRect()
      const activeRect = active.getBoundingClientRect()

      const scrollLeft = activeRect.left - containerRect.left - containerRect.width / 2 + activeRect.width / 2

      container.scrollBy({ left: scrollLeft, behavior: "smooth" })
    }
  }, [activeMoodId])

  const handleSelect = (mood: Mood) => {
    if (disabled || mood.id === activeMoodId) return
    triggerHaptic("light")
    onMoodSelect(mood.id, mood.name, mood.color)
  }

  return (
    <div ref={scrollRef} className="overflow-x-auto scrollbar-hide px-4">
      <div className="flex gap-2 py-1 min-w-max">
        {moods.map((mood) => {
          const isActive = activeMoodId === mood.id
          return (
            <motion.button
              key={mood.id}
              ref={isActive ? activeRef : null}
              whileTap={{ scale: 0.95 }}
              onClick={() => handleSelect(mood)}
              disabled={disabled}
              className={cn(
                "relative flex items-center gap-2 px-4 py-2.5 rounded-full",
                "text-sm font-medium transition-all duration-200",
                "border focus:outline-none focus:ring-2 focus:ring-primary/50",
                isActive ? "border-transparent shadow-md" : "border-border hover:border-primary/30 hover:bg-surface-2",
                disabled && "opacity-50 cursor-not-allowed",
              )}
              style={{
                backgroundColor: isActive ? `${mood.color}25` : undefined,
                borderColor: isActive ? mood.color : undefined,
                color: isActive ? mood.color : undefined,
              }}
              aria-pressed={isActive}
            >
              <span className="text-base">{mood.emoji}</span>
              <span>{mood.name}</span>

              {/* Active indicator dot */}
              {isActive && (
                <motion.div
                  layoutId="activeMoodDot"
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: mood.color }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                />
              )}

              {/* Selection ring animation */}
              {isActive && (
                <motion.div
                  layoutId="activeMoodRing"
                  className="absolute inset-0 rounded-full"
                  style={{
                    boxShadow: `0 0 0 2px ${mood.color}40`,
                  }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                />
              )}
            </motion.button>
          )
        })}
      </div>
    </div>
  )
}
