"use client"

import { NavLink, Outlet, useLocation } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Music2, Sparkles, History, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { MiniPlayer } from "@/components/player/MiniPlayer"
import { BackgroundPlaybackBanner } from "@/components/player/BackgroundPlaybackBanner"
import { usePlayer } from "@/providers/PlayerProvider"
import { durations, easings, prefersReducedMotion } from "@/lib/motion"

const tabs = [
  { path: "/player", label: "Player", icon: Music2 },
  { path: "/moods", label: "Moods", icon: Sparkles },
  { path: "/history", label: "History", icon: History },
  { path: "/settings", label: "Settings", icon: Settings },
]

export function AppShell() {
  const location = useLocation()
  const player = usePlayer()
  const reducedMotion = prefersReducedMotion()

  const isOnPlayerPage = location.pathname === "/player"
  const showMiniPlayer = player.currentTrack && !isOnPlayerPage

  const handleResume = async () => {
    await player.play()
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Background playback banner for iOS */}
      <BackgroundPlaybackBanner
        wasPausedByBackground={player.wasPausedByBackground}
        isIOSPWA={player.isIOSPWA}
        onResume={handleResume}
        isLoading={player.isLoading}
      />

      {/* Main content area with safe area padding and page transitions */}
      <main
        className={cn(
          "flex-1 overflow-auto",
          "pt-safe-top",
          // Add extra padding when mini player is visible
          showMiniPlayer ? "pb-32" : "pb-20",
        )}
      >
        {reducedMotion ? (
          <Outlet />
        ) : (
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{
                duration: durations.fast / 1000,
                ease: easings.out,
              }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        )}
      </main>

      {/* Mini player - shows when not on player page */}
      <MiniPlayer
        track={player.currentTrack}
        isPlaying={player.isPlaying}
        onPlayPause={player.toggle}
        onSkip={player.skip}
        hidden={isOnPlayerPage}
      />

      {/* Bottom tab navigation */}
      <nav
        className={cn(
          "fixed bottom-0 left-0 right-0 z-50",
          "bg-background/90 backdrop-blur-xl border-t border-border/50",
          "pb-safe-bottom",
        )}
      >
        <div className="flex items-center justify-around h-16 max-w-lg mx-auto">
          {tabs.map((tab) => (
            <NavLink
              key={tab.path}
              to={tab.path}
              className="relative flex flex-col items-center justify-center w-full h-full"
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute inset-x-2 top-0 h-0.5 gradient-bg rounded-full"
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                  <motion.div
                    animate={{ scale: isActive ? 1.1 : 1 }}
                    transition={{ type: "spring", stiffness: 400, damping: 20 }}
                    className="flex flex-col items-center gap-1"
                  >
                    <tab.icon
                      className={cn("w-5 h-5 transition-colors", isActive ? "text-primary" : "text-muted-foreground")}
                    />
                    <span
                      className={cn(
                        "text-xs transition-colors",
                        isActive ? "text-primary font-medium" : "text-muted-foreground",
                      )}
                    >
                      {tab.label}
                    </span>
                  </motion.div>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
