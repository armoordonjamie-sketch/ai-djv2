/**
 * SpotifyConnectPage
 *
 * Optional Spotify connection step before voice onboarding
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SpotifyConnect } from '@/components/SpotifyConnect'
import { Button } from '@/components/ui/button'
import { LogoMark } from '@/components/branding/Logo'
import { Sparkles, TrendingUp, MessageSquare, Loader2 } from 'lucide-react'
import * as api from '@/lib/jamifyApi'

export function SpotifyConnectPage() {
    const navigate = useNavigate()
    const [isFetching, setIsFetching] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const handleSuccess = async () => {
        setIsFetching(true)
        setError(null)
        
        try {
            // Fetch and enrich Spotify data
            await api.fetchSpotifyData()
            
            // Navigate to voice onboarding
            navigate('/onboarding')
        } catch (err) {
            console.error('Failed to fetch Spotify data:', err)
            setError('Failed to fetch your Spotify data. Please try again.')
            setIsFetching(false)
        }
    }

    const handleSkip = () => {
        // Skip Spotify and go directly to voice onboarding
        navigate('/onboarding')
    }

    const handleError = (errorMessage: string) => {
        setError(errorMessage)
    }

    return (
        <div className="min-h-dvh bg-background relative overflow-hidden">
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute -top-32 right-[-10%] h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
                <div className="absolute top-32 left-[-15%] h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
                <div className="absolute bottom-[-20%] right-[10%] h-72 w-72 rounded-full bg-success/15 blur-3xl" />
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_55%)]" />
            </div>

            <div className="relative min-h-dvh flex flex-col px-4 pt-safe-top pb-safe-bottom">
                <header className="glass-subtle rounded-3xl border border-white/10 px-4 py-3 shadow-lg shadow-black/20 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <LogoMark size={28} />
                        <div>
                            <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Spotify</p>
                            <h1 className="text-base font-semibold">Connect</h1>
                        </div>
                    </div>
                    <Button variant="ghost" size="sm" onClick={handleSkip} className="text-muted-foreground hover:text-foreground">
                        Skip
                    </Button>
                </header>

                <main className="flex-1 flex flex-col items-center justify-center py-6">
                    <div className="w-full max-w-xl space-y-6">
                        <div className="glass rounded-3xl border border-white/10 px-6 py-6">
                            <div className="flex items-center gap-4">
                                <div className="w-14 h-14 rounded-2xl gradient-bg flex items-center justify-center shadow-lg shadow-primary/30">
                                    <LogoMark size={28} />
                                </div>
                                <div>
                                    <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Optional</p>
                                    <h2 className="text-2xl font-semibold">Connect your Spotify</h2>
                                    <p className="text-sm text-muted-foreground">
                                        Let your AI DJ start with real listening data.
                                    </p>
                                </div>
                            </div>

                            <div className="grid gap-3 mt-6">
                                <div className="flex items-start gap-3 p-3 rounded-2xl bg-white/5 border border-white/10">
                                    <Sparkles className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                                    <div>
                                        <h3 className="font-semibold text-sm">Personalized selections</h3>
                                        <p className="text-xs text-muted-foreground">
                                            Your DJ uses your favorite artists, genres, and tracks.
                                        </p>
                                    </div>
                                </div>

                                <div className="flex items-start gap-3 p-3 rounded-2xl bg-white/5 border border-white/10">
                                    <TrendingUp className="h-5 w-5 text-success flex-shrink-0 mt-0.5" />
                                    <div>
                                        <h3 className="font-semibold text-sm">Smarter recommendations</h3>
                                        <p className="text-xs text-muted-foreground">
                                            Discover new music based on your real listening habits.
                                        </p>
                                    </div>
                                </div>

                                <div className="flex items-start gap-3 p-3 rounded-2xl bg-white/5 border border-white/10">
                                    <MessageSquare className="h-5 w-5 text-info flex-shrink-0 mt-0.5" />
                                    <div>
                                        <h3 className="font-semibold text-sm">Personal DJ banter</h3>
                                        <p className="text-xs text-muted-foreground">
                                            Your DJ can reference tracks you played on repeat.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {error && (
                            <div className="p-4 rounded-2xl border border-destructive/30 bg-destructive/10 text-destructive text-sm">
                                {error}
                            </div>
                        )}

                        {isFetching ? (
                            <div className="glass-subtle rounded-2xl border border-white/10 p-4 text-center space-y-2">
                                <div className="flex items-center justify-center gap-3">
                                    <Loader2 className="h-5 w-5 animate-spin text-primary" />
                                    <p className="text-sm font-medium">Analyzing your listening data...</p>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    This may take a moment while we enrich your profile.
                                </p>
                            </div>
                        ) : (
                            <div className="flex flex-col sm:flex-row gap-3">
                                <div className="flex-1">
                                    <SpotifyConnect onSuccess={handleSuccess} onError={handleError} />
                                </div>
                                <Button
                                    onClick={handleSkip}
                                    variant="outline"
                                    size="lg"
                                    className="h-12 rounded-full border-white/10 hover:bg-white/5"
                                >
                                    Skip for now
                                </Button>
                            </div>
                        )}

                        <p className="text-xs text-muted-foreground text-center">
                            Your Spotify data stays private and is only used to personalize your DJ.
                        </p>
                    </div>
                </main>
            </div>
        </div>
    )
}

