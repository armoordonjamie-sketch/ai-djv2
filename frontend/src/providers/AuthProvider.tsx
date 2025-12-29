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
                        console.log('[Auth] Access token expired, attempting refresh...')
                        await api.refreshToken()
                        // Retry get user
                        const apiUser = await api.getMe()
                        setUser(mapApiUser(apiUser))
                        await loadOnboardingStatus()
                        console.log('[Auth] Session refreshed successfully')
                    } catch {
                        // Refresh failed or other error - truly logged out
                        setUser(null)
                        setIsOnboarded(false)
                    }
                } else {
                    // Not a 401, just failed
                    setUser(null)
                    setIsOnboarded(false)
                }
            } finally {
                setIsLoading(false)
            }
        }

        async function loadOnboardingStatus() {
            try {
                const onboardStatus = await api.getOnboardStatus()
                setIsOnboarded(onboardStatus.has_profile)
            } catch {
                setIsOnboarded(false)
            }
        }

        checkAuth()
    }, [])

    const refreshAuth = useCallback(async () => {
        try {
            const apiUser = await api.getMe()
            setUser(mapApiUser(apiUser))

            const onboardStatus = await api.getOnboardStatus()
            setIsOnboarded(onboardStatus.has_profile)
        } catch {
            setUser(null)
            setIsOnboarded(false)
        }
    }, [])

    const checkOnboarding = useCallback(async (): Promise<boolean> => {
        try {
            const status = await api.getOnboardStatus()
            setIsOnboarded(status.has_profile)
            return status.has_profile
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
                setIsOnboarded(onboardStatus.has_profile)
            } catch {
                setIsOnboarded(false)
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
    }, [])

    return (
        <AuthContext.Provider
            value={{
                user,
                isLoading,
                isAuthenticated: !!user,
                isOnboarded,
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
