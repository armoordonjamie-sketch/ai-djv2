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
