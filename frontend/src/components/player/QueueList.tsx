"use client"

import { motion, AnimatePresence } from "framer-motion"
import { ChevronDown, Music } from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils"

interface Track {
  id: string
  title: string
  artist: string
  artworkUrl?: string
}

interface QueueListProps {
  tracks: Track[]
  className?: string
}

export function QueueList({ tracks, className }: QueueListProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (tracks.length === 0) return null

  return (
    <div className={cn("rounded-xl bg-surface-1 border border-border overflow-hidden", className)}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Queue</span>
          <span className="text-xs text-muted-foreground bg-surface-3 px-2 py-0.5 rounded-full">{tracks.length}</span>
        </div>
        <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        </motion.div>
      </button>

      {/* Track list */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-border"
          >
            {tracks.slice(0, 5).map((track, index) => (
              <motion.div
                key={track.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className={cn(
                  "flex items-center gap-3 px-4 py-3",
                  index < Math.min(tracks.length, 5) - 1 && "border-b border-border/50",
                )}
              >
                {/* Track number */}
                <span className="text-xs text-muted-foreground w-4 text-center tabular-nums">{index + 1}</span>

                {/* Artwork */}
                <div className="w-10 h-10 rounded-lg flex-shrink-0 overflow-hidden bg-surface-2">
                  {track.artworkUrl ? (
                    <img src={track.artworkUrl || "/placeholder.svg"} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Music className="w-4 h-4 text-muted-foreground" />
                    </div>
                  )}
                </div>

                {/* Track info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{track.title}</p>
                  <p className="text-xs text-muted-foreground truncate">{track.artist}</p>
                </div>
              </motion.div>
            ))}

            {tracks.length > 5 && (
              <div className="px-4 py-2 text-xs text-muted-foreground text-center">
                +{tracks.length - 5} more tracks
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
