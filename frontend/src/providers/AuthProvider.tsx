import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import * as api from '@/lib/jamifyApi'

export interface User {
    id: string
    email: string
    displayName: string | null
    createdAt: string
}

interface AuthContextType {
    user: User | null
    isLoading: boolean
    isAuthenticated: boolean
    isOnboarded: boolean
    hasSpotify: boolean
    login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>
    register: (email: string, password: string, displayName?: string) => Promise<{ success: boolean; error?: string }>
    logout: () => Promise<void>
    refreshAuth: () => Promise<void>
    checkOnboarding: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextType | null>(null)

function mapApiUser(apiUser: api.User): User {
    return {
        id: apiUser.id,
        email: apiUser.email,
        displayName: apiUser.display_name,
        createdAt: apiUser.created_at,
    }
}

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [isOnboarded, setIsOnboarded] = useState(false)
    const [hasSpotify, setHasSpotify] = useState(false)

    // Check auth state on mount by calling GET /me
    useEffect(() => {
        async function checkAuth() {
            try {
                // Try to get user
                const apiUser = await api.getMe()
                setUser(mapApiUser(apiUser))
                await loadOnboardingStatus()
            } catch (err) {
                // If 401, try to refresh token
                if (err instanceof api.JamifyApiError && err.isUnauthorized) {
                    try {
                        // Check if we have a refresh token cookie before attempting refresh
                        // (Note: HttpOnly cookies can't be checked from JS, so we try and handle gracefully)
                        await api.refreshToken()
                        // Retry get user
                        const apiUser = await api.getMe()
                        setUser(mapApiUser(apiUser))
                        await loadOnboardingStatus()
                    } catch (refreshErr) {
                        // Refresh failed - this is expected when not logged in
                        // If it's a 400 "Refresh token required", that's normal for logged-out users
                        if (refreshErr instanceof api.JamifyApiError && 
                            refreshErr.status === 400 && 
                            refreshErr.message.toLowerCase().includes('refresh token')) {
                            // Expected: no refresh token means user is not logged in
                            setUser(null)
                            setIsOnboarded(false)
                            setHasSpotify(false)
                        } else {
                            // Other error during refresh - also means logged out
                            setUser(null)
                            setIsOnboarded(false)
                            setHasSpotify(false)
                        }
                    }
                } else {
                    // Not a 401, just failed
                    setUser(null)
                    setIsOnboarded(false)
                    setHasSpotify(false)
                }
            } finally {
                setIsLoading(false)
            }
        }

        async function loadOnboardingStatus() {
            try {
                const onboardStatus = await api.getOnboardStatus()
                setIsOnboarded(onboardStatus.onboarded)
                setHasSpotify(onboardStatus.has_spotify)
            } catch {
                setIsOnboarded(false)
                setHasSpotify(false)
            }
        }

        checkAuth()
    }, [])

    const refreshAuth = useCallback(async () => {
        try {
            const apiUser = await api.getMe()
            setUser(mapApiUser(apiUser))

            const onboardStatus = await api.getOnboardStatus()
            setIsOnboarded(onboardStatus.onboarded)
            setHasSpotify(onboardStatus.has_spotify)
        } catch {
            setUser(null)
            setIsOnboarded(false)
            setHasSpotify(false)
        }
    }, [])

    const checkOnboarding = useCallback(async (): Promise<boolean> => {
        try {
            const status = await api.getOnboardStatus()
            setIsOnboarded(status.onboarded)
            setHasSpotify(status.has_spotify)
            return status.onboarded
        } catch {
            return false
        }
    }, [])

    const login = useCallback(async (email: string, password: string) => {
        try {
            const response = await api.login(email, password)
            setUser(mapApiUser(response.user))

            // Check onboarding after login
            try {
                const onboardStatus = await api.getOnboardStatus()
                setIsOnboarded(onboardStatus.onboarded)
                setHasSpotify(onboardStatus.has_spotify)
            } catch {
                setIsOnboarded(false)
                setHasSpotify(false)
            }

            return { success: true }
        } catch (err) {
            const message = err instanceof api.JamifyApiError
                ? err.message
                : 'Login failed'
            return { success: false, error: message }
        }
    }, [])

    const register = useCallback(async (email: string, password: string, displayName?: string) => {
        try {
            const response = await api.register(email, password, displayName)
            setUser(mapApiUser(response.user))
            setIsOnboarded(false) // New users need onboarding
            setHasSpotify(false) // New users haven't connected Spotify yet

            return { success: true }
        } catch (err) {
            const message = err instanceof api.JamifyApiError
                ? err.message
                : 'Registration failed'
            return { success: false, error: message }
        }
    }, [])

    const logout = useCallback(async () => {
        try {
            await api.logout()
        } catch {
            // Ignore errors, clear state anyway
        }
        setUser(null)
        setIsOnboarded(false)
        setHasSpotify(false)
    }, [])

    return (
        <AuthContext.Provider
            value={{
                user,
                isLoading,
                isAuthenticated: !!user,
                isOnboarded,
                hasSpotify,
                login,
                register,
                logout,
                refreshAuth,
                checkOnboarding,
            }}
        >
            {children}
        </AuthContext.Provider>
    )
}

export function useAuth() {
    const context = useContext(AuthContext)
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider')
    }
    return context
}
