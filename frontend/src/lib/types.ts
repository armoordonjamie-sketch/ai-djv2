// Jamify TypeScript Types

export interface User {
  id: string
  email: string
  displayName?: string
  avatarUrl?: string
  createdAt: string
  preferences?: UserPreferences
}

export interface UserPreferences {
  onboardingComplete: boolean
  favoriteGenres: string[]
  energyLevel: "low" | "medium" | "high"
  discoveryLevel: "familiar" | "mixed" | "adventurous"
}

export interface Mood {
  id: string
  name: string
  emoji: string
  color: string
  description?: string
  isActive: boolean
  createdAt: string
}

export interface Track {
  id: string
  title: string
  artist: string
  album?: string
  albumArt: string
  duration: number // in seconds
  previewUrl?: string
  genres: string[]
}

export interface PlaybackState {
  currentTrack: Track | null
  isPlaying: boolean
  progress: number // 0-100
  volume: number // 0-100
  queue: Track[]
}

export interface Feedback {
  trackId: string
  type: "like" | "dislike"
  timestamp: string
  moodId?: string
}

export interface HistoryItem {
  id: string
  track: Track
  playedAt: string
  feedback?: "like" | "dislike"
  mood?: Mood
}

export interface AuthResponse {
  success: boolean
  user?: User
  token?: string
  error?: string
}

export interface ApiError {
  message: string
  code: string
  status: number
}

// === StatusEvent Types (matches backend schema) ===

export type StatusCategory =
  | 'onboarding'
  | 'playback'
  | 'generation'
  | 'training'
  | 'network'
  | 'error'

export type StatusStep =
  // Generation
  | 'planning'
  | 'selecting_track'
  | 'track_selected'
  | 'downloading_track'
  | 'generating_intro'
  | 'generating_tts'
  | 'mixing'
  | 'encoding'
  | 'queued'
  | 'ready'
  // Playback
  | 'starting'
  | 'playing'
  | 'paused'
  | 'skipping'
  | 'stopped'
  | 'switching_mood'
  | 'buffering'
  | 'recovering'
  // Training
  | 'feedback_received'
  | 'training_started'
  | 'training_applied'
  | 'training_complete'
  // Onboarding
  | 'mic_permission'
  | 'voice_capture'
  | 'voice_processing'
  | 'mood_parsing'
  | 'mood_creating'
  | 'intro_generating'
  | 'onboarding_complete'
  // Network
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  // Error
  | 'retrying'
  | 'failed'

export type StatusSeverity = 'info' | 'warn' | 'error'

export interface StatusEventPayload {
  track_id?: string
  track_title?: string
  track_artist?: string
  artwork_url?: string
  segment_index?: number
  queue_depth?: number
  mood_id?: string
  mood_name?: string
  feedback_value?: string
  error_code?: string
  retry_count?: number
}

export interface StatusEvent {
  id: string
  ts: string
  user_id: string
  session_id?: string
  correlation_id?: string
  category: StatusCategory
  step: StatusStep
  progress?: number
  eta_seconds?: number
  user_message: string
  debug_message?: string
  payload?: StatusEventPayload
  severity: StatusSeverity
}
