/**
 * SpotifyConnectedPage
 * 
 * Simple success page shown after Spotify OAuth completes
 * Closes the popup window so parent can detect success
 */
import { useEffect } from 'react'
import { CheckCircle, Loader2 } from 'lucide-react'

export function SpotifyConnectedPage() {
    useEffect(() => {
        if (window.opener) {
            window.opener.postMessage({ type: 'spotify-connected' }, window.location.origin)
        }

        // Close the popup window after a short delay
        const timer = setTimeout(() => {
            window.close()
        }, 1500)

        return () => clearTimeout(timer)
    }, [])

    return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
            <div className="text-center space-y-6">
                <div className="flex justify-center">
                    <div className="w-20 h-20 rounded-full bg-[#1DB954]/20 flex items-center justify-center">
                        <CheckCircle className="w-12 h-12 text-[#1DB954]" />
                    </div>
                </div>
                
                <div className="space-y-2">
                    <h1 className="text-2xl font-semibold">Spotify Connected!</h1>
                    <p className="text-muted-foreground">
                        Your account has been successfully linked.
                    </p>
                </div>

                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Closing window...</span>
                </div>
            </div>
        </div>
    )
}

