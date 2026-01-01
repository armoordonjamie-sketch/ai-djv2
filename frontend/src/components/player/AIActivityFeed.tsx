"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { motion, AnimatePresence, LayoutGroup } from "framer-motion"
import { ChevronDown, Sparkles, Radio, Zap, Check, Loader2, Search, Download, Mic } from "lucide-react"
import { cn } from "@/lib/utils"
import type { StatusEvent } from "@/lib/types"
import { prefersReducedMotion } from "@/lib/motion"

interface AIActivityFeedProps {
    statusHistory: StatusEvent[]
    className?: string
    /** Force expanded state (for desktop) */
    defaultExpanded?: boolean
    /** Callback when expanded state changes (for parent layout adjustments) */
    onExpandedChange?: (expanded: boolean) => void
    /** Maximum expanded height in pixels (calculated from available container space) */
    maxExpandedHeightPx?: number
}

const STORAGE_KEY = "jamify_ai_feed_expanded"

// Map status steps to icons and colors
const statusConfig: Record<string, { icon: React.ElementType; color: string; label: string }> = {
    planning: { icon: Sparkles, color: "text-primary", label: "Planning mix" },
    selecting_track: { icon: Search, color: "text-primary", label: "Finding track" },
    track_selected: { icon: Zap, color: "text-warning", label: "Track found" },
    searching_catalog: { icon: Search, color: "text-info", label: "Searching catalog" },
    acquiring_track: { icon: Download, color: "text-info", label: "Downloading" },
    downloading_track: { icon: Download, color: "text-info", label: "Downloading" },
    generating_intro: { icon: Mic, color: "text-accent", label: "Creating intro" },
    generating_tts: { icon: Mic, color: "text-accent", label: "Generating voice" },
    mixing: { icon: Radio, color: "text-primary", label: "Mixing" },
    queued: { icon: Check, color: "text-success", label: "Ready" },
    ready: { icon: Check, color: "text-success", label: "Ready" },
    feedback_received: { icon: Check, color: "text-success", label: "Got it!" },
    training_started: { icon: Sparkles, color: "text-warning", label: "Learning" },
    training_applied: { icon: Sparkles, color: "text-warning", label: "Applying" },
    training_complete: { icon: Check, color: "text-success", label: "Updated" },
}

function getStatusIcon(step: string): React.ElementType {
    return statusConfig[step]?.icon || Loader2
}

function getStatusColor(step: string): string {
    return statusConfig[step]?.color || "text-muted-foreground"
}

// Animation variants for list container
const listVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.05,
            delayChildren: 0.15, // Increased to allow container to expand first
        },
    },
}

// Animation variants for list items
const itemVariants = {
    hidden: {
        opacity: 0,
        y: 8,
        filter: "blur(4px)",
        scale: 0.95,
    },
    visible: {
        opacity: 1,
        y: 0,
        filter: "blur(0px)",
        scale: 1,
        transition: {
            type: "spring" as const,
            stiffness: 400,
            damping: 30,
        },
    },
    exit: {
        opacity: 0,
        y: -8,
        filter: "blur(4px)",
        scale: 0.95,
        height: 0,
        marginTop: 0,
        marginBottom: 0,
        paddingTop: 0,
        paddingBottom: 0,
        transition: {
            duration: 0.2,
            ease: "easeOut" as const,
        },
    },
}

// Reduced motion variants
const reducedItemVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: { duration: 0.15 },
    },
    exit: {
        opacity: 0,
        transition: { duration: 0.1 },
    },
}

/**
 * AIActivityFeed - A collapsible panel showing real-time AI activity.
 * 
 * Features:
 * - Collapsible with chevron toggle
 * - Persists expanded/collapsed state in localStorage
 * - Shows pulsing indicator when collapsed but active
 * - Smooth premium animations with reduced-motion support
 * - Item enter/exit/layout animations with AnimatePresence
 * - Max height constraint with internal scroll (never grows outer page)
 */
export function AIActivityFeed({
    statusHistory,
    className,
    defaultExpanded,
    onExpandedChange,
    maxExpandedHeightPx,
}: AIActivityFeedProps) {
    const reducedMotion = prefersReducedMotion()
    const [isExpanded, setIsExpanded] = useState(() => {
        if (defaultExpanded !== undefined) return defaultExpanded
        try {
            const stored = localStorage.getItem(STORAGE_KEY)
            if (stored !== null) return stored === "true"
        } catch { }
        return false
    })
    const [isVisible, setIsVisible] = useState(false)
    const [showItems, setShowItems] = useState(false) // Two-phase animation: delay items until container opens
    const containerRef = useRef<HTMLDivElement>(null)

    // Show feed when there's activity
    useEffect(() => {
        if (statusHistory.length > 0) {
            setIsVisible(true)
        }
    }, [statusHistory])

    // Persist expanded state
    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, String(isExpanded))
        } catch { }
    }, [isExpanded])

    // Notify parent when expanded state changes
    useEffect(() => {
        onExpandedChange?.(isExpanded)
    }, [isExpanded, onExpandedChange])

    // Two-phase animation: delay showing items until container has opened
    useEffect(() => {
        if (isExpanded) {
            // Wait for container to expand before showing items
            const timer = setTimeout(() => setShowItems(true), reducedMotion ? 0 : 150)
            return () => clearTimeout(timer)
        } else {
            // Hide items immediately when collapsing (they animate out)
            setShowItems(false)
        }
    }, [isExpanded, reducedMotion])

    const toggleExpanded = useCallback(() => {
        setIsExpanded((prev) => !prev)
    }, [])

    // Don't render if no activity ever happened
    if (!isVisible && statusHistory.length === 0) {
        return null
    }

    const latestStatus = statusHistory[0]
    const isActive = latestStatus && !["queued", "ready", "training_complete"].includes(latestStatus.step)

    // Spring transition for expand/collapse
    const springTransition = reducedMotion
        ? { duration: 0 }
        : { type: "spring" as const, stiffness: 350, damping: 35 }

    const variants = reducedMotion ? reducedItemVariants : itemVariants

    return (
        <LayoutGroup>
            <motion.div
                ref={containerRef}
                layout
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={springTransition}
                className={cn(
                    "ai-activity-feed overflow-hidden rounded-xl border border-white/10 bg-black/20 backdrop-blur-sm",
                    isActive && !isExpanded && !reducedMotion && "ai-activity-indicator",
                    className
                )}
            >
                {/* Header - always visible */}
                <button
                    onClick={toggleExpanded}
                    className="w-full flex items-center justify-between px-3 py-2.5 text-left touch-target"
                    aria-expanded={isExpanded}
                    aria-label={isExpanded ? "Collapse AI activity" : "Expand AI activity"}
                >
                    <div className="flex items-center gap-2 overflow-hidden">
                        <motion.div
                            animate={isActive && !reducedMotion ? { scale: [1, 1.2, 1] } : { scale: 1 }}
                            transition={{ duration: 1.5, repeat: isActive ? Infinity : 0 }}
                        >
                            <Sparkles className={cn("w-4 h-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                        </motion.div>
                        <span className="text-sm font-medium text-foreground shrink-0">AI Activity</span>
                        {!isExpanded && latestStatus && (
                            <span className="text-xs text-muted-foreground truncate">
                                • {latestStatus.user_message}
                            </span>
                        )}
                    </div>
                    <motion.div
                        animate={{ rotate: isExpanded ? 180 : 0 }}
                        transition={{ duration: 0.2 }}
                        className="shrink-0"
                    >
                        <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    </motion.div>
                </button>

                {/* Expandable content with layout animation */}
                <AnimatePresence initial={false} mode="sync" presenceAffectsLayout>
                    {isExpanded && (
                        <motion.div
                            key="content"
                            layout
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={springTransition}
                            className="overflow-hidden"
                        >
                            {/* 
                              Max height constraint: calculated from available container space
                              This ensures the feed never pushes NowPlaying off-screen.
                              The list scrolls internally when content exceeds max height.
                            */}
                            <div
                                className="overflow-y-auto scroll-container scrollbar-hide border-t border-white/5"
                                style={{ maxHeight: maxExpandedHeightPx ? `${maxExpandedHeightPx}px` : "320px" }}
                            >
                                {statusHistory.length === 0 ? (
                                    <div className="ai-activity-item text-muted-foreground/60">
                                        <Loader2 className="ai-activity-item-icon animate-spin" />
                                        <span>Waiting for activity...</span>
                                    </div>
                                ) : showItems ? (
                                    <motion.ul
                                        layout
                                        variants={listVariants}
                                        initial="hidden"
                                        animate="visible"
                                        className="py-1"
                                    >
                                        <AnimatePresence mode="popLayout" initial={false}>
                                            {statusHistory.slice(0, 8).map((status, index) => {
                                                const Icon = getStatusIcon(status.step)
                                                const color = getStatusColor(status.step)
                                                const isLatest = index === 0

                                                return (
                                                    <motion.li
                                                        key={status.id}
                                                        layout
                                                        variants={variants}
                                                        initial="hidden"
                                                        animate="visible"
                                                        exit="exit"
                                                        style={{ overflow: "hidden" }}
                                                        className={cn(
                                                            "ai-activity-item",
                                                            isLatest && "text-foreground font-medium"
                                                        )}
                                                    >
                                                        <Icon
                                                            className={cn(
                                                                "ai-activity-item-icon shrink-0",
                                                                color,
                                                                isLatest && !reducedMotion && "animate-pulse"
                                                            )}
                                                        />
                                                        <span
                                                            className="truncate flex-1"
                                                            style={{ opacity: isLatest ? 1 : 0.6 - (index * 0.06) }}
                                                        >
                                                            {status.user_message}
                                                        </span>
                                                        {status.progress !== undefined && status.progress !== null && (
                                                            <span className="text-xs text-muted-foreground tabular-nums ml-auto shrink-0">
                                                                {Math.round(status.progress * 100)}%
                                                            </span>
                                                        )}
                                                    </motion.li>
                                                )
                                            })}
                                        </AnimatePresence>
                                    </motion.ul>
                                ) : (
                                    // Placeholder while container is expanding
                                    <div className="py-1" />
                                )}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </motion.div>
        </LayoutGroup>
    )
}
