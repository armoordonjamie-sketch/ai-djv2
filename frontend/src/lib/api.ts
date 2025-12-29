// Jamify API Client with mock fallback
import type { User, AuthResponse, Mood, Track, HistoryItem } from './types'

// API Configuration
export const API_BASE_URL = 'http://localhost:8000/api'

// Simulate network delay for mock responses
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// Track if we're in demo/mock mode
let isUsingMockData = false
export const getIsMockMode = () => isUsingMockData

// Helper for API calls with mock fallback
async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {},
  mockFallback: () => Promise<T>
): Promise<T> {
  try {
    const token = localStorage.getItem('jamify-token')
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`)
    }

    isUsingMockData = false
    return response.json()
  } catch {
    // Fallback to mock data
    isUsingMockData = true
    return mockFallback()
  }
}

// ============ Mock Data ============

const mockUsers: Map<string, { password: string; user: User }> = new Map()

export const mockMoods: Mood[] = [
  { id: '1', name: 'Energetic', emoji: '⚡', color: '#f59e0b', isActive: false, createdAt: new Date().toISOString() },
  { id: '2', name: 'Chill', emoji: '🌊', color: '#06b6d4', isActive: true, createdAt: new Date().toISOString() },
  { id: '3', name: 'Focus', emoji: '🎯', color: '#8b5cf6', isActive: false, createdAt: new Date().toISOString() },
  { id: '4', name: 'Party', emoji: '🎉', color: '#ec4899', isActive: false, createdAt: new Date().toISOString() },
  { id: '5', name: 'Melancholy', emoji: '🌧️', color: '#6366f1', isActive: false, createdAt: new Date().toISOString() },
]

export const mockTracks: Track[] = [
  {
    id: '1',
    title: 'Midnight Dreams',
    artist: 'Neon Pulse',
    album: 'Electric Nights',
    albumArt: '/album-art-placeholder.svg',
    duration: 245,
    genres: ['synthwave', 'electronic'],
  },
  {
    id: '2',
    title: 'Ocean Waves',
    artist: 'Ambient Collective',
    album: 'Serenity',
    albumArt: '/album-art-placeholder.svg',
    duration: 312,
    genres: ['ambient', 'chill'],
  },
  {
    id: '3',
    title: 'Urban Groove',
    artist: 'City Beats',
    album: 'Metropolitan',
    albumArt: '/album-art-placeholder.svg',
    duration: 198,
    genres: ['hip-hop', 'electronic'],
  },
]

// ============ Auth API ============

export async function login(email: string, password: string): Promise<AuthResponse> {
  return apiCall(
    '/auth/login',
    {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    },
    async () => {
      await delay(800)
      const stored = mockUsers.get(email)
      if (stored && stored.password === password) {
        return { success: true, user: stored.user, token: 'mock-jwt-' + Date.now() }
      }
      if (email === 'demo@jamify.app' && password === 'demo123') {
        return {
          success: true,
          user: {
            id: 'demo-user',
            email: 'demo@jamify.app',
            displayName: 'Demo User',
            createdAt: new Date().toISOString(),
            preferences: {
              onboardingComplete: true,
              favoriteGenres: ['electronic', 'indie'],
              energyLevel: 'medium',
              discoveryLevel: 'mixed',
            },
          },
          token: 'mock-jwt-demo',
        }
      }
      return { success: false, error: 'Invalid email or password' }
    }
  )
}

export async function register(email: string, password: string, displayName?: string): Promise<AuthResponse> {
  return apiCall(
    '/auth/register',
    {
      method: 'POST',
      body: JSON.stringify({ email, password, displayName }),
    },
    async () => {
      await delay(1000)
      if (mockUsers.has(email)) {
        return { success: false, error: 'An account with this email already exists' }
      }
      const newUser: User = {
        id: 'user-' + Date.now(),
        email,
        displayName: displayName || email.split('@')[0],
        createdAt: new Date().toISOString(),
        preferences: {
          onboardingComplete: false,
          favoriteGenres: [],
          energyLevel: 'medium',
          discoveryLevel: 'mixed',
        },
      }
      mockUsers.set(email, { password, user: newUser })
      return { success: true, user: newUser, token: 'mock-jwt-' + Date.now() }
    }
  )
}

export async function getMe(): Promise<User | null> {
  return apiCall(
    '/me',
    { method: 'GET' },
    async () => {
      await delay(300)
      const storedUser = localStorage.getItem('jamify-user')
      return storedUser ? JSON.parse(storedUser) : null
    }
  )
}

export async function logout(): Promise<void> {
  await delay(300)
  localStorage.removeItem('jamify-token')
  localStorage.removeItem('jamify-user')
}

// ============ Moods API ============

export async function getMoods(): Promise<Mood[]> {
  return apiCall('/moods', { method: 'GET' }, async () => {
    await delay(500)
    return mockMoods
  })
}

export async function createMood(mood: Omit<Mood, 'id' | 'createdAt'>): Promise<Mood> {
  return apiCall(
    '/moods',
    {
      method: 'POST',
      body: JSON.stringify(mood),
    },
    async () => {
      await delay(500)
      const newMood: Mood = {
        ...mood,
        id: 'mood-' + Date.now(),
        createdAt: new Date().toISOString(),
      }
      mockMoods.push(newMood)
      return newMood
    }
  )
}

export async function updateMood(id: string, updates: Partial<Mood>): Promise<Mood> {
  return apiCall(
    `/moods/${id}`,
    {
      method: 'PATCH',
      body: JSON.stringify(updates),
    },
    async () => {
      await delay(300)
      const mood = mockMoods.find((m) => m.id === id)
      if (!mood) throw new Error('Mood not found')
      Object.assign(mood, updates)
      return mood
    }
  )
}

export async function deleteMood(id: string): Promise<void> {
  return apiCall(
    `/moods/${id}`,
    { method: 'DELETE' },
    async () => {
      await delay(300)
      const index = mockMoods.findIndex((m) => m.id === id)
      if (index !== -1) mockMoods.splice(index, 1)
    }
  )
}

export async function setActiveMood(moodId: string): Promise<Mood> {
  return apiCall(
    `/moods/${moodId}/activate`,
    { method: 'POST' },
    async () => {
      await delay(300)
      const mood = mockMoods.find((m) => m.id === moodId)
      if (!mood) throw new Error('Mood not found')
      mockMoods.forEach((m) => (m.isActive = false))
      mood.isActive = true
      return mood
    }
  )
}

// ============ Stream API ============

interface StreamResponse {
  streamUrl: string
  currentTrack: Track
  queue: Track[]
}

export async function startStream(moodId: string): Promise<StreamResponse> {
  return apiCall(
    '/stream/start',
    {
      method: 'POST',
      body: JSON.stringify({ moodId }),
    },
    async () => {
      await delay(800)
      console.log(`[Mock] Starting stream for mood ${moodId}`)
      return {
        streamUrl: 'https://stream.jamify.uk/live',
        currentTrack: mockTracks[0],
        queue: mockTracks.slice(1),
      }
    }
  )
}

export async function getNextTrack(): Promise<Track> {
  return apiCall('/stream/next', { method: 'GET' }, async () => {
    await delay(600)
    const randomIndex = Math.floor(Math.random() * mockTracks.length)
    return mockTracks[randomIndex]
  })
}

// ============ Feedback API ============

export async function submitFeedback(trackId: string, type: 'like' | 'dislike'): Promise<void> {
  return apiCall(
    '/feedback',
    {
      method: 'POST',
      body: JSON.stringify({ trackId, value: type }),
    },
    async () => {
      await delay(200)
      console.log(`[Mock] Feedback: ${type} for track ${trackId}`)
    }
  )
}

// ============ History API ============

export async function getHistory(): Promise<HistoryItem[]> {
  return apiCall('/history', { method: 'GET' }, async () => {
    await delay(500)
    return mockTracks.map((track, index) => ({
      id: `history-${index}`,
      track,
      playedAt: new Date(Date.now() - index * 3600000).toISOString(),
      feedback: index === 0 ? ('like' as const) : undefined,
      mood: mockMoods[index % mockMoods.length],
    }))
  })
}
