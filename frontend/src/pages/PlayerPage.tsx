"use client"

import { useEffect, useState } from "react"
import { useLocation } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Music2, WifiOff, Wifi, Plus } from "lucide-react"
import { NowPlaying } from "@/components/player/NowPlaying"
import { PlayerControls } from "@/components/player/PlayerControls"
import { LikeDislike } from "@/components/player/LikeDislike"
import { MoodPills } from "@/components/player/MoodPills"
import { QueueList } from "@/components/player/QueueList"
import { NextUpCard } from "@/components/player/NextUpCard"
import { StatusPill } from "@/components/player/StatusPill"
import { StatusOverlay } from "@/components/ui/StatusOverlay"
import { usePlayer } from "@/providers/PlayerProvider"
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
  const incomingMoodId = (location.state as { moodId?: string })?.moodId
  const [moods, setMoods] = useState<Mood[]>([])
  const [moodsLoading, setMoodsLoading] = useState(true)

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
  useEffect(() => {
    if (moodsLoading || player.sessionId || player.streamUrl || player.isLoading) return

    const targetMoodId = incomingMoodId || player.activeMoodId
    if (targetMoodId) {
      player.startStream(targetMoodId)
    } else if (moods.length > 0) {
      const defaultMood = moods.find((m) => m.isActive) || moods[0]
      if (defaultMood) {
        player.startStream(defaultMood.id)
      }
    }
  }, [moodsLoading, moods, incomingMoodId, player.activeMoodId, player.sessionId, player.streamUrl, player.isLoading])

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

  // Handle empty state (no moods)
  if (!moodsLoading && moods.length === 0) {
    return (
      <div className="min-h-full flex flex-col items-center justify-center p-6 text-center space-y-6">
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="w-24 h-24 rounded-2xl gradient-bg flex items-center justify-center shadow-lg shadow-primary/20"
        >
          <Music2 className="w-12 h-12 text-white" />
        </motion.div>
        <div className="space-y-2">
          <h2 className="text-2xl font-bold">Welcome to Jamify!</h2>
          <p className="text-muted-foreground max-w-xs">
            Create your first "Vibe" so your AI DJ knows what to play for you.
          </p>
        </div>
        <a
          href="/moods"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-full gradient-bg text-white font-medium 
                     hover:opacity-90 transition-opacity shadow-lg shadow-primary/20"
        >
          <Plus className="w-5 h-5" />
          Create a Vibe
        </a>
      </div>
    )
  }

  return (
    <div className="min-h-full flex flex-col relative">
      {/* iOS Tap to Start overlay */}
      <AnimatePresence>
        {!player.hasUserInteracted && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm"
            onClick={handleTapToStart}
          >
            <motion.div
              animate={{ scale: [1, 1.02, 1] }}
              transition={{ repeat: Number.POSITIVE_INFINITY, duration: 2, ease: "easeInOut" }}
              className="text-center space-y-4"
            >
              <div className="w-28 h-28 rounded-3xl gradient-bg flex items-center justify-center mx-auto shadow-2xl shadow-primary/30">
                <Music2 className="w-14 h-14 text-white" />
              </div>
              <div className="space-y-1">
                <p className="text-xl font-bold">Tap to Start</p>
                <p className="text-muted-foreground text-sm">Your AI DJ is ready</p>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status Overlay - fullscreen for major state changes */}
      <StatusOverlay
        status={player.currentStatus}
        isLoading={player.isLoading && !player.currentTrack}
        hasStartedPlaying={!!player.currentTrack}
      />

      {/* Header area with connection status */}
      <div className="flex items-center justify-between px-4 py-3">
        <div /> {/* Spacer for centering */}
        {/* Connection status indicator */}
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

      {/* Mood Pills */}
      <div className="mb-2">
        <MoodPills
          moods={moods}
          activeMoodId={player.activeMoodId}
          onMoodSelect={handleMoodSelect}
          disabled={player.isLoading}
        />
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col px-4">
        {/* Status Pill - shows real-time backend updates */}
        <div className="flex justify-center mb-2 relative z-50">
          <StatusPill status={player.currentStatus} compact />
        </div>

        {/* Now Playing Hero */}
        <div className="flex-1 flex flex-col items-center justify-center py-1">
          <NowPlaying
            track={player.currentTrack}
            moodColor={activeMood?.color}
            moodName={activeMood?.name}
            status={player.currentStatus}
            isLoading={player.isLoading && !player.currentTrack}
          />
        </div>

        {/* Like/Dislike */}
        <div className="py-2">
          <LikeDislike
            onLike={() => player.submitFeedback("like")}
            onDislike={() => player.submitFeedback("dislike")}
            currentFeedback={player.feedback}
            disabled={!player.currentTrack}
            status={player.currentStatus}
          />
        </div>

        {/* Player Controls */}
        <div className="py-2">
          <PlayerControls
            isPlaying={player.isPlaying}
            volume={player.volume}
            isMuted={player.isMuted}
            onPlayPause={player.toggle}
            onSkip={player.skip}
            onVolumeChange={player.setVolume}
            onMuteToggle={player.toggleMute}
            disabled={player.isLoading && !player.currentTrack}
          />
        </div>

        {/* Next Up Card - shows when AI is preparing next track */}
        <div className="py-2">
          <NextUpCard track={player.queue[0]} status={player.currentTrack ? player.currentStatus : null} />
        </div>

        {/* Queue List */}
        {player.queue.length > 0 && (
          <div className="py-2 pb-safe-bottom">
            <QueueList tracks={player.queue} />
          </div>
        )}
      </div>
    </div>
  )
}
