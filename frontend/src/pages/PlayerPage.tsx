"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { WifiOff, Wifi, Plus } from "lucide-react"
import { prefersReducedMotion } from "@/lib/motion"
import { LogoMark } from "@/components/branding/Logo"
import { NowPlaying } from "@/components/player/NowPlaying"
import { PlayerControls } from "@/components/player/PlayerControls"
import { LikeDislike } from "@/components/player/LikeDislike"
import { MoodPills } from "@/components/player/MoodPills"
import { StatusPill } from "@/components/player/StatusPill"
import { AIActivityFeed } from "@/components/player/AIActivityFeed"
import { StatusOverlay } from "@/components/ui/StatusOverlay"
import { HelperCard } from "@/components/ui/HelperCard"
import { usePlayer } from "@/providers/PlayerProvider"
import { useFirstRunHint } from "@/hooks/useFirstRunHint"
import * as api from "@/lib/jamifyApi"
import type { Mood } from "@/lib/types"

// Map API mood to frontend Mood type
function mapApiMood(apiMood: api.Mood): Mood {
  return {
    id: apiMood.id,
    name: apiMood.name,
    emoji: "🎵",
    color: apiMood.color,
    isActive: apiMood.is_default,
    createdAt: "",
  }
}

export default function PlayerPage() {
  const player = usePlayer()
  const location = useLocation()
  const navigate = useNavigate()
  const { moodId: incomingMoodId, streamStarted } = (location.state as { moodId?: string; streamStarted?: boolean }) || {}
  const [moods, setMoods] = useState<Mood[]>([])
  const [moodsLoading, setMoodsLoading] = useState(true)
  const [resumeCheckComplete, setResumeCheckComplete] = useState(
    sessionStorage.getItem('resume_check_complete') === 'true'
  )
  const hasAutoStartedRef = useRef(false)

  // Track feed expanded state for dynamic vinyl sizing
  const [feedExpanded, setFeedExpanded] = useState(false)
  const reducedMotion = prefersReducedMotion()

  // Ref to measure middle content area for dynamic vinyl sizing
  const middleContentRef = useRef<HTMLDivElement>(null)
  const [availableHeight, setAvailableHeight] = useState(0)

  // Ref to measure interaction region (feed + now playing wrapper) for feed max height
  const interactionRef = useRef<HTMLDivElement>(null)
  const [interactionHeight, setInteractionHeight] = useState(0)

  // Callback when feed expands/collapses
  const handleFeedExpandedChange = useCallback((expanded: boolean) => {
    setFeedExpanded(expanded)
  }, [])

  // Measure available height for dynamic vinyl sizing
  useEffect(() => {
    const el = middleContentRef.current
    if (!el) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setAvailableHeight(entry.contentRect.height)
      }
    })

    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Measure interaction region height for dynamic feed max height
  useEffect(() => {
    const el = interactionRef.current
    if (!el) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setInteractionHeight(entry.contentRect.height)
      }
    })

    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Poll for resume check completion if not already done
  useEffect(() => {
    if (resumeCheckComplete) return

    const interval = setInterval(() => {
      if (sessionStorage.getItem('resume_check_complete') === 'true') {
        setResumeCheckComplete(true)
        clearInterval(interval)
      }
    }, 100) // Check every 100ms

    return () => clearInterval(interval)
  }, [resumeCheckComplete])

  // Load moods from API
  useEffect(() => {
    async function loadMoods() {
      try {
        const apiMoods = await api.getMoods()
        setMoods(apiMoods.map(mapApiMood))
      } catch (err) {
        console.error("[PlayerPage] Failed to load moods:", err)
      } finally {
        setMoodsLoading(false)
      }
    }
    loadMoods()
  }, [])

  // Initialize stream on mount if no track
  // Note: If navigated from MoodsPage, stream is already started there
  useEffect(() => {
    // Only run once
    if (hasAutoStartedRef.current) return

    // Wait for moods to load before auto-starting
    if (moodsLoading) return

    // Wait for resume check to complete (state updated by polling effect)
    if (!resumeCheckComplete) {
      console.log('[PlayerPage] Waiting for resume check to complete...')
      return
    }

    // If there's a resumable session, let the resume dialog handle it
    if (sessionStorage.getItem('has_resumable_session') === 'true') {
      console.log('[PlayerPage] Resumable session exists - letting dialog handle it')
      hasAutoStartedRef.current = true
      return
    }

    // Don't start if already loading, has session, or has stream URL
    if (player.sessionId || player.streamUrl || player.isLoading || player.isPlaying) return

    // Don't start if we have a current track (stream already playing)
    if (player.currentTrack) return

    // Only auto-start if we don't have an incoming mood or streamStarted flag (which means MoodsPage handled it)
    // If there's an incomingMoodId or streamStarted flag, MoodsPage already started the stream
    if (incomingMoodId || streamStarted) {
      console.log('[PlayerPage] Stream already started from MoodsPage, skipping auto-start')
      hasAutoStartedRef.current = true
      return
    }

    // Auto-start with active mood or default mood
    const targetMoodId = player.activeMoodId
    if (targetMoodId) {
      console.log('[PlayerPage] Auto-starting stream with mood:', targetMoodId)
      hasAutoStartedRef.current = true
      player.startStream(targetMoodId)
    } else if (moods.length > 0) {
      const defaultMood = moods.find((m) => m.isActive) || moods[0]
      if (defaultMood) {
        console.log('[PlayerPage] Auto-starting stream with default mood:', defaultMood.id)
        hasAutoStartedRef.current = true
        player.startStream(defaultMood.id)
      }
    }
  }, [moodsLoading, moods, incomingMoodId, resumeCheckComplete, player.activeMoodId, player.sessionId, player.streamUrl, player.isLoading, player.currentTrack, player.isPlaying])

  const handleTapToStart = async () => {
    player.setHasUserInteracted(true)
    if (!player.currentTrack && moods.length > 0) {
      const defaultMood = moods.find((m) => m.isActive) || moods[0]
      if (defaultMood) {
        await player.startStream(defaultMood.id)
      }
    }
    await player.play()
  }

  const handleMoodSelect = async (moodId: string) => {
    await player.setActiveMood(moodId)
  }

  const activeMood = moods.find((m) => m.id === player.activeMoodId) || moods[0]
  const firstRunHint = useFirstRunHint("jamify_hint_player")

  // Handle empty state (no moods)
  if (!moodsLoading && moods.length === 0) {
    return (
      <div className="h-full bg-background relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 right-[-10%] h-56 w-56 rounded-full bg-primary/20 blur-3xl" />
          <div className="absolute bottom-[-20%] left-[10%] h-64 w-64 rounded-full bg-accent/20 blur-3xl" />
        </div>
        <div className="relative flex h-full flex-col items-center justify-center px-6 text-center">
          <div className="glass rounded-3xl border border-white/10 px-6 py-6 max-w-sm w-full space-y-4">
            <LogoMark size={48} className="mx-auto" />
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Welcome to Jamify</h2>
              <p className="text-sm text-muted-foreground">
                Create your first vibe so your AI DJ knows what to play.
              </p>
            </div>
            <Link
              to="/moods"
              className="inline-flex items-center justify-center w-full h-12 rounded-full gradient-bg text-white font-medium shadow-lg shadow-primary/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              Create a vibe
            </Link>
          </div>
        </div>
      </div>
    )
  }


  return (
    /* Root: fill AppShell main container, no overflow (no outer scroll) */
    <div className="h-full min-h-0 bg-background relative overflow-hidden">
      {/* Background gradients */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-32 right-[-10%] h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute top-32 left-[-15%] h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <div className="absolute bottom-[-20%] right-[10%] h-72 w-72 rounded-full bg-success/15 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_55%)]" />
      </div>

      {/* 3-row CSS Grid layout: header (auto) | content (1fr) | controls (auto) */}
      <div className="relative h-full grid grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
        {/* iOS Tap to Start overlay */}
        <AnimatePresence>
          {!player.hasUserInteracted && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-50 flex items-center justify-center bg-background/90 backdrop-blur-xl"
              onClick={handleTapToStart}
            >
              <motion.div
                animate={{ scale: [1, 1.02, 1] }}
                transition={{ repeat: Number.POSITIVE_INFINITY, duration: 2, ease: "easeInOut" }}
                className="glass rounded-3xl border border-white/10 px-6 py-6 text-center space-y-4"
              >
                <LogoMark size={64} className="mx-auto" />
                <div className="space-y-1">
                  <p className="text-lg font-semibold">Tap to start</p>
                  <p className="text-sm text-muted-foreground">Your DJ is ready</p>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Status Overlay - fullscreen for major state changes */}
        <StatusOverlay
          status={player.currentStatus}
          isLoading={player.isLoading && !player.isPlaying}
          hasStartedPlaying={player.isPlaying}
        />

        {/* ROW 1: Header (auto height) */}
        <header className="shrink-0 px-4 pt-2">
          <div className="glass-subtle rounded-3xl border border-white/10 px-4 py-2.5 shadow-lg shadow-black/20">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <LogoMark size={28} />
                <div>
                  <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Now playing</p>
                  <h1 className="text-base font-semibold">AI DJ</h1>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {player.wsConnected ? (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-success/15 text-success text-xs font-medium"
                  >
                    <Wifi className="w-3 h-3" />
                    <span>Live</span>
                  </motion.div>
                ) : player.error ? (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-warning/15 text-warning text-xs font-medium"
                  >
                    <WifiOff className="w-3 h-3" />
                    <span>Reconnecting</span>
                  </motion.div>
                ) : null}
              </div>
            </div>
          </div>
        </header>

        {/* ROW 2: Middle content (minmax(0, 1fr)) - this is the flexible area */}
        <main className="min-h-0 flex flex-col gap-2 px-3 sm:px-4 pt-2 overflow-hidden">
          {/* Helper card (only shows on first run) */}
          {firstRunHint.isVisible && moods.length > 0 && (
            <HelperCard
              eyebrow="First session"
              title="Welcome to your DJ"
              description="Pick a mood, then hit play. Use like or dislike to train your mix."
              icon={<LogoMark size={20} />}
              actionLabel="Explore moods"
              onAction={() => navigate("/moods")}
              onDismiss={firstRunHint.dismiss}
            >
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>Choose a mood to set the vibe.</li>
                <li>Tap play to start streaming.</li>
                <li>Use likes and skips to tune recommendations.</li>
              </ul>
            </HelperCard>
          )}

          {/* Mood pills - shrink-0 so they don't compress */}
          <div className="glass-subtle rounded-2xl border border-white/10 px-2 py-1.5 shrink-0">
            <MoodPills
              moods={moods}
              activeMoodId={player.activeMoodId}
              onMoodSelect={handleMoodSelect}
              disabled={player.isLoading}
            />
          </div>

          {/* Interaction Region: AIActivityFeed + NowPlaying wrapper for height constraint */}
          <div ref={interactionRef} className="flex-1 min-h-0 flex flex-col gap-2 overflow-hidden">
            {/* AI Activity Feed - shrink-0, has internal scroll, container-relative max height */}
            <AIActivityFeed
              statusHistory={player.statusHistory}
              onExpandedChange={handleFeedExpandedChange}
              maxExpandedHeightPx={
                interactionHeight > 0
                  ? Math.max(
                    160,
                    Math.min(
                      Math.floor(interactionHeight * 0.42),
                      Math.max(160, interactionHeight - 260) // NOW_PLAYING_MIN = 260
                    )
                  )
                  : undefined
              }
              className="shrink-0"
            />

            {/* Now Playing area - flex-1 min-h-0 to take remaining space */}
            <motion.div
              ref={middleContentRef}
              layout={!reducedMotion}
              transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 350, damping: 35 }}
              className="flex-1 min-h-0 glass rounded-3xl border border-white/10 px-3 py-2 flex items-center justify-center relative overflow-hidden"
            >
              {player.currentStatus && (
                <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10">
                  <StatusPill status={player.currentStatus} compact />
                </div>
              )}
              <NowPlaying
                track={player.currentTrack}
                moodColor={activeMood?.color}
                moodName={activeMood?.name}
                status={player.currentStatus}
                isLoading={player.isLoading && !player.currentTrack}
                isPlaying={player.isPlaying}
                feedExpanded={feedExpanded}
                availableHeight={availableHeight}
                className="w-full h-full"
              />
            </motion.div>
          </div>
        </main>

        {/* ROW 3: Controls - unified single row, clears fixed nav */}
        <footer className="shrink-0 px-3 sm:px-4 pt-2 pb-[calc(env(safe-area-inset-bottom,0px)+68px)]">
          <div className="glass-subtle rounded-2xl border border-white/10 px-3 py-2.5 flex items-center justify-between gap-2">
            {/* Left: Like/Dislike (inline) */}
            <LikeDislike
              onLike={() => player.submitFeedback("like")}
              onDislike={() => player.submitFeedback("dislike")}
              currentFeedback={player.feedback}
              disabled={!player.currentTrack}
              status={player.currentStatus}
              compact
            />

            {/* Center: Player Controls (inline) */}
            <PlayerControls
              isPlaying={player.isPlaying}
              volume={player.volume}
              isMuted={player.isMuted}
              onPlayPause={player.toggle}
              onSkip={player.skip}
              onVolumeChange={player.setVolume}
              onMuteToggle={player.toggleMute}
              disabled={player.isLoading && !player.currentTrack}
              moodColor={activeMood?.color}
              compact
            />
          </div>
        </footer>
      </div>
    </div>
  )
}
