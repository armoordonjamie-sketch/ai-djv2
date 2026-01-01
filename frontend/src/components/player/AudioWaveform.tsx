"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"

interface AudioWaveformProps {
    /** Number of bars to display */
    barCount?: number
    /** Whether the waveform is animating (playing) */
    isPlaying?: boolean
    /** Color of the waveform bars (defaults to gradient) */
    color?: string
    /** Height of the waveform container */
    height?: number
    /** Compact mode for mini-player */
    compact?: boolean
    className?: string
}

/**
 * Animated audio waveform visualizer with bars that pulse to simulate audio activity.
 * Uses Framer Motion for smooth, performant animations.
 */
export function AudioWaveform({
    barCount = 24,
    isPlaying = true,
    color,
    height = 48,
    compact = false,
    className,
}: AudioWaveformProps) {
    const bars = Array.from({ length: barCount }, (_, i) => i)
    const barWidth = compact ? 2 : 3
    const gap = compact ? 2 : 3

    return (
        <div
            className={cn(
                "flex items-end justify-center",
                className
            )}
            style={{ height }}
        >
            {bars.map((i) => {
                // Create varied animation delays and heights for organic look
                const delay = (i * 0.05) % 0.8
                const baseHeight = 0.3 + Math.sin(i * 0.5) * 0.2
                const maxHeight = 0.5 + Math.cos(i * 0.3) * 0.5

                return (
                    <motion.div
                        key={i}
                        className="rounded-full"
                        style={{
                            width: barWidth,
                            marginLeft: i === 0 ? 0 : gap,
                            background: color || `linear-gradient(to top, var(--gradient-start), var(--gradient-end))`,
                        }}
                        initial={{ height: `${baseHeight * 100}%` }}
                        animate={
                            isPlaying
                                ? {
                                    height: [
                                        `${baseHeight * 100}%`,
                                        `${maxHeight * 100}%`,
                                        `${(baseHeight + 0.1) * 100}%`,
                                        `${(maxHeight - 0.2) * 100}%`,
                                        `${baseHeight * 100}%`,
                                    ],
                                }
                                : { height: `${baseHeight * 50}%` }
                        }
                        transition={
                            isPlaying
                                ? {
                                    duration: 0.8 + Math.random() * 0.4,
                                    repeat: Infinity,
                                    delay,
                                    ease: "easeInOut",
                                }
                                : { duration: 0.3, ease: "easeOut" }
                        }
                    />
                )
            })}
        </div>
    )
}
