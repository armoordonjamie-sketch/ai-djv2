import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/providers/AuthProvider'

interface ProtectedRouteProps {
    children: React.ReactNode
    /** If true, also requires user to have completed onboarding */
    requireOnboarding?: boolean
    /** If true, requires Spotify connection before accessing */
    requireSpotify?: boolean
}

export function ProtectedRoute({ 
    children, 
    requireOnboarding = false,
    requireSpotify = false 
}: ProtectedRouteProps) {
    const { isAuthenticated, isLoading, isOnboarded, hasSpotify } = useAuth()
    const location = useLocation()

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
        )
    }

    if (!isAuthenticated) {
        // Save the attempted URL for redirecting after login
        return <Navigate to="/login" state={{ from: location }} replace />
    }

    // If Spotify is required but user hasn't connected it, redirect to Spotify connect
    if (requireSpotify && !hasSpotify) {
        return <Navigate to="/connect-spotify" state={{ from: location }} replace />
    }

    // If onboarding is required but user hasn't completed it, redirect to onboarding flow
    if (requireOnboarding && !isOnboarded) {
        // First check if they need to connect Spotify
        if (!hasSpotify) {
            return <Navigate to="/connect-spotify" state={{ from: location }} replace />
        }
        return <Navigate to="/onboarding" state={{ from: location }} replace />
    }

    return <>{children}</>
}
