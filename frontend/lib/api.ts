// Mock API client for Jamify
import type { User, AuthResponse, Mood, Track, HistoryItem } from "./types"

// Simulate network delay
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// Mock user database
const mockUsers: Map<string, { password: string; user: User }> = new Map()

// Mock data
export const mockMoods: Mood[] = [
  { id: "1", name: "Energetic", emoji: "⚡", color: "#f59e0b", isActive: false, createdAt: new Date().toISOString() },
  { id: "2", name: "Chill", emoji: "🌊", color: "#06b6d4", isActive: true, createdAt: new Date().toISOString() },
  { id: "3", name: "Focus", emoji: "🎯", color: "#8b5cf6", isActive: false, createdAt: new Date().toISOString() },
  { id: "4", name: "Party", emoji: "🎉", color: "#ec4899", isActive: false, createdAt: new Date().toISOString() },
  { id: "5", name: "Melancholy", emoji: "🌧️", color: "#6366f1", isActive: false, createdAt: new Date().toISOString() },
]

export const mockTracks: Track[] = [
  {
    id: "1",
    title: "Midnight Dreams",
    artist: "Neon Pulse",
    album: "Electric Nights",
    albumArt: "/album-art-synthwave-neon.jpg",
    duration: 245,
    genres: ["synthwave", "electronic"],
  },
  {
    id: "2",
    title: "Ocean Waves",
    artist: "Ambient Collective",
    album: "Serenity",
    albumArt: "/album-art-ocean-calm-blue.jpg",
    duration: 312,
    genres: ["ambient", "chill"],
  },
  {
    id: "3",
    title: "Urban Groove",
    artist: "City Beats",
    album: "Metropolitan",
    albumArt: "/album-art-city-night-urban.jpg",
    duration: 198,
    genres: ["hip-hop", "electronic"],
  },
]

// Auth API
export async function login(email: string, password: string): Promise<AuthResponse> {
  await delay(800)

  const stored = mockUsers.get(email)
  if (stored && stored.password === password) {
    return {
      success: true,
      user: stored.user,
      token: "mock-jwt-token-" + Date.now(),
    }
  }

  // For demo purposes, allow any login with demo@jamify.app
  if (email === "demo@jamify.app" && password === "demo123") {
    return {
      success: true,
      user: {
        id: "demo-user",
        email: "demo@jamify.app",
        displayName: "Demo User",
        createdAt: new Date().toISOString(),
        preferences: {
          onboardingComplete: true,
          favoriteGenres: ["electronic", "indie"],
          energyLevel: "medium",
          discoveryLevel: "mixed",
        },
      },
      token: "mock-jwt-token-demo",
    }
  }

  return {
    success: false,
    error: "Invalid email or password",
  }
}

export async function register(email: string, password: string, displayName?: string): Promise<AuthResponse> {
  await delay(1000)

  if (mockUsers.has(email)) {
    return {
      success: false,
      error: "An account with this email already exists",
    }
  }

  const newUser: User = {
    id: "user-" + Date.now(),
    email,
    displayName: displayName || email.split("@")[0],
    createdAt: new Date().toISOString(),
    preferences: {
      onboardingComplete: false,
      favoriteGenres: [],
      energyLevel: "medium",
      discoveryLevel: "mixed",
    },
  }

  mockUsers.set(email, { password, user: newUser })

  return {
    success: true,
    user: newUser,
    token: "mock-jwt-token-" + Date.now(),
  }
}

export async function logout(): Promise<void> {
  await delay(300)
  // Clear any stored tokens
}

// Mood API
export async function getMoods(): Promise<Mood[]> {
  await delay(500)
  return mockMoods
}

export async function setActiveMood(moodId: string): Promise<Mood> {
  await delay(300)
  const mood = mockMoods.find((m) => m.id === moodId)
  if (!mood) throw new Error("Mood not found")
  return { ...mood, isActive: true }
}

// Track API
export async function getNextTrack(): Promise<Track> {
  await delay(600)
  const randomIndex = Math.floor(Math.random() * mockTracks.length)
  return mockTracks[randomIndex]
}

export async function submitFeedback(trackId: string, type: "like" | "dislike"): Promise<void> {
  await delay(200)
  // Store feedback in mock database
}

// History API
export async function getHistory(): Promise<HistoryItem[]> {
  await delay(500)
  return mockTracks.map((track, index) => ({
    id: `history-${index}`,
    track,
    playedAt: new Date(Date.now() - index * 3600000).toISOString(),
    feedback: index === 0 ? "like" : undefined,
    mood: mockMoods[index % mockMoods.length],
  }))
}
