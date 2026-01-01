/**
 * SpotifyConnect Component
 * 
 * Handles Spotify OAuth flow with popup window
 */
import { useState } from 'react'
import { Button } from './ui/button'
import { Loader2, Music2 } from 'lucide-react'
import * as api from '../lib/jamifyApi'

interface SpotifyConnectProps {
    onSuccess?: () => void
    onError?: (error: string) => void
}

export function SpotifyConnect({ onSuccess, onError }: SpotifyConnectProps) {
    const [isConnecting, setIsConnecting] = useState(false)

    const handleConnect = async () => {
        setIsConnecting(true)
        
        try {
            // Get authorization URL (session_id is encoded in the state parameter by backend)
            const { auth_url } = await api.getSpotifyAuthUrl()
            
            // Open OAuth popup
            const width = 600
            const height = 700
            const left = window.screenX + (window.outerWidth - width) / 2
            const top = window.screenY + (window.outerHeight - height) / 2
            
            const popup = window.open(
                auth_url,
                'Spotify Login',
                `width=${width},height=${height},left=${left},top=${top}`
            )
            
            if (!popup) {
                throw new Error('Popup blocked. Please allow popups for this site.')
            }
            
            const handleMessage = (event: MessageEvent) => {
                if (event.origin !== window.location.origin) return
                if (event.data?.type === 'spotify-connected') {
                    try {
                        popup.close()
                    } catch {
                        // Ignore popup close errors
                    }
                }
            }

            window.addEventListener('message', handleMessage)

            // Poll for popup close
            const checkPopup = setInterval(() => {
                if (popup.closed) {
                    clearInterval(checkPopup)
                    window.removeEventListener('message', handleMessage)
                    // Check if connection was successful
                    api.getSpotifyStatus()
                        .then((status) => {
                            if (status.connected) {
                                onSuccess?.()
                            } else {
                                setIsConnecting(false)
                            }
                        })
                        .catch(() => {
                            setIsConnecting(false)
                        })
                }
            }, 500)
            
        } catch (error) {
            console.error('Spotify connect error:', error)
            const message = error instanceof Error ? error.message : 'Failed to connect to Spotify'
            onError?.(message)
            setIsConnecting(false)
        }
    }

    return (
        <Button
            onClick={handleConnect}
            disabled={isConnecting}
            className="w-full h-12 rounded-full bg-[#1DB954] hover:bg-[#1ed760] text-white font-semibold touch-target"
            size="lg"
        >
            {isConnecting ? (
                <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Connecting...
                </>
            ) : (
                <>
                    <Music2 className="mr-2 h-5 w-5" />
                    Connect Spotify
                </>
            )}
        </Button>
    )
}

