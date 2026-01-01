"use client"

import { useEffect, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import { motion } from "framer-motion"
import { Music2, Sparkles, History, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { MiniPlayer } from "@/components/player/MiniPlayer"
import { BackgroundPlaybackBanner } from "@/components/player/BackgroundPlaybackBanner"
import { ResumeSessionDialog } from "@/components/ResumeSessionDialog"
import { MoodSwitchDialog } from "@/components/MoodSwitchDialog"
import { usePlayer } from "@/providers/PlayerProvider"
import { durations, easings, prefersReducedMotion } from "@/lib/motion"
import * as api from "@/lib/jamifyApi"

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
  const [resumableSession, setResumableSession] = useState<api.ResumableSession | null>(null)

  const isOnPlayerPage = location.pathname === "/player"
  const reserveMiniPlayerSpace = !isOnPlayerPage

  // Check for resumable session on mount
  useEffect(() => {
    const checkResumable = async () => {
      try {
        const session = await api.checkResumableSession()
        setResumableSession(session)
        // Store in sessionStorage so PlayerPage knows a resume check happened
        if (session?.resumable) {
          sessionStorage.setItem('has_resumable_session', 'true')
        } else {
          sessionStorage.removeItem('has_resumable_session')
        }
      } catch (err) {
        console.warn('[AppShell] Failed to check resumable session:', err)
      } finally {
        sessionStorage.setItem('resume_check_complete', 'true')
      }
    }

    checkResumable()
  }, [])

  const handleResume = async () => {
    await player.play()
  }

  const handleResumeSession = async () => {
    console.log('[AppShell] User chose to resume session')
    sessionStorage.removeItem('has_resumable_session') // Clear flag so it doesn't block future auto-starts

    // If stream is already started (e.g., from MoodsPage), just dismiss the dialog
    if (player.sessionId || player.isLoading) {
      console.log('[AppShell] Stream already started, dismissing resume dialog')
      player.setHasUserInteracted(true)
      return
    }

    // Mark as user interaction so "Tap to Start" overlay doesn't show
    player.setHasUserInteracted(true)
    await player.startStream(undefined, true)
  }

  const handleStartFresh = async () => {
    console.log('[AppShell] User chose to start fresh')
    sessionStorage.removeItem('has_resumable_session') // Clear flag so it doesn't block future auto-starts

    // If stream is already started (e.g., from MoodsPage), just dismiss the dialog
    if (player.sessionId || player.isLoading) {
      console.log('[AppShell] Stream already started, dismissing resume dialog')
      player.setHasUserInteracted(true)
      return
    }

    // Mark as user interaction so "Tap to Start" overlay doesn't show
    player.setHasUserInteracted(true)
    await player.startStream(undefined, false)
  }

  return (
    <div className="min-h-screen h-[var(--app-height)] overflow-hidden flex flex-col bg-background">
      {/* Resume session dialog */}
      <ResumeSessionDialog
        resumableSession={resumableSession}
        onResume={handleResumeSession}
        onStartFresh={handleStartFresh}
      />

      {/* Mood switch dialog */}
      <MoodSwitchDialog
        open={player.moodSwitchDialog.open}
        switchInfo={player.moodSwitchDialog.moodId ? {
          moodId: player.moodSwitchDialog.moodId,
          moodName: player.moodSwitchDialog.moodName,
          moodColor: player.moodSwitchDialog.moodColor,
          currentTrack: player.moodSwitchDialog.savedTrack || undefined,
          position: player.moodSwitchDialog.savedPosition,
        } : null}
        onResume={() => player.confirmMoodSwitch(true)}
        onStartFresh={() => player.confirmMoodSwitch(false)}
        onCancel={player.cancelMoodSwitch}
      />

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
          "flex-1 min-h-0 overflow-hidden",
          "pt-safe-top",
          // Add extra padding when mini player is visible, none for player page
          reserveMiniPlayerSpace ? "pb-32" : "pb-0",
        )}
      >
        {reducedMotion ? (
          <div className="h-full">
            <Outlet />
          </div>
        ) : (
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              duration: durations.fast / 1000,
              ease: easings.out,
            }}
            className="h-full"
          >
            <Outlet />
          </motion.div>
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
