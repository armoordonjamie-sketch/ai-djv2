import { useState, useEffect, useRef } from 'react'
import type React from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
    Headphones,
    Sparkles,
    Smartphone,
    LogOut,
    ChevronRight,
    Share2,
    AlertTriangle,
    Loader2,
    Volume2,
    Palette,
    Info,
    Mail,
    FileText,
    Lock,
    Music2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { LogoMark } from '@/components/branding/Logo'
import { HelperCard } from '@/components/ui/HelperCard'
import { useFirstRunHint } from '@/hooks/useFirstRunHint'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useAuth } from '@/providers/AuthProvider'
import * as api from '@/lib/jamifyApi'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

export default function SettingsPage() {
    const navigate = useNavigate()
    const { user, logout } = useAuth()
    const [audioQuality, setAudioQuality] = useState('standard')
    const [crossfade, setCrossfade] = useState(true)
    const [loudnessNormalize, setLoudnessNormalize] = useState(true)
    const [defaultMoodName, setDefaultMoodName] = useState<string | null>(null)
    const [isLoggingOut, setIsLoggingOut] = useState(false)
    const [spotifyStatus, setSpotifyStatus] = useState<{ connected: boolean; spotify_id?: string } | null>(null)
    const [isDisconnectingSpotify, setIsDisconnectingSpotify] = useState(false)
    const firstRunHint = useFirstRunHint('jamify_hint_settings')
    const installRef = useRef<HTMLDivElement | null>(null)

    // Load default mood name
    useEffect(() => {
        async function loadDefaultMood() {
            try {
                const moods = await api.getMoods()
                const defaultMood = moods.find(m => m.is_default)
                if (defaultMood) {
                    setDefaultMoodName(defaultMood.name)
                }
            } catch {
                // Ignore errors
            }
        }
        loadDefaultMood()
    }, [])

    // Load Spotify status
    useEffect(() => {
        async function loadSpotifyStatus() {
            try {
                const status = await api.getSpotifyStatus()
                setSpotifyStatus(status)
            } catch {
                // Ignore errors
            }
        }
        loadSpotifyStatus()
    }, [])

    async function handleDisconnectSpotify() {
        setIsDisconnectingSpotify(true)
        try {
            await api.disconnectSpotify()
            setSpotifyStatus({ connected: false })
            toast.success('Spotify disconnected')
        } catch {
            toast.error('Failed to disconnect Spotify')
        } finally {
            setIsDisconnectingSpotify(false)
        }
    }

    async function handleLogout() {
        setIsLoggingOut(true)
        try {
            await logout()
            navigate('/login')
        } catch {
            toast.error('Failed to log out')
        } finally {
            setIsLoggingOut(false)
        }
    }

    // Get user initials for avatar
    const userInitials = user?.displayName
        ? user.displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
        : user?.email?.[0]?.toUpperCase() || '?'

    return (
        <div className="h-full bg-background relative overflow-hidden">
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute -top-32 right-[-10%] h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
                <div className="absolute top-32 left-[-15%] h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
                <div className="absolute bottom-[-20%] right-[10%] h-72 w-72 rounded-full bg-success/15 blur-3xl" />
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_55%)]" />
            </div>

            <div className="relative h-full flex flex-col px-4 pt-3 pb-3 gap-3">
                {/* Header */}
                <div className="glass-subtle rounded-3xl border border-white/10 px-4 py-2.5 shadow-lg shadow-black/20 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <LogoMark size={28} />
                        <div>
                            <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Settings</p>
                            <h1 className="text-base font-semibold">Account</h1>
                        </div>
                    </div>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto scroll-container scrollbar-hide pt-3 pb-2 space-y-4">
                    {firstRunHint.isVisible && (
                    <HelperCard
                        eyebrow="First session"
                        title="Make it feel like an app"
                        description="Install Jamify for a faster, more reliable iOS experience."
                        icon={<LogoMark size={20} />}
                        actionLabel="See install steps"
                        onAction={() => installRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                        onDismiss={firstRunHint.dismiss}
                    >
                        <ul className="text-xs text-muted-foreground space-y-1">
                            <li>Use Safari for the best install flow.</li>
                            <li>Enable notifications to stay in the loop.</li>
                            <li>Adjust playback preferences below.</li>
                        </ul>
                    </HelperCard>
                )}

                {/* User Profile Hero */}
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="relative overflow-hidden rounded-3xl glass border border-white/10 p-4"
                >
                    {/* Background decoration */}
                    <div className="absolute -top-10 -right-10 w-40 h-40 bg-primary/20 rounded-full blur-3xl" />
                    <div className="absolute -bottom-10 -left-10 w-32 h-32 bg-primary/10 rounded-full blur-2xl" />
                    <div className="absolute top-4 right-4 opacity-20">
                        <LogoMark size={60} />
                    </div>

                    <div className="relative flex items-center gap-4">
                        {/* Avatar */}
                        <div className="relative">
                            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center text-xl font-bold text-primary-foreground shadow-lg">
                                {userInitials}
                            </div>
                            <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-white/20 to-transparent" />
                        </div>

                        {/* User info */}
                        <div className="flex-1 min-w-0">
                            <h1 className="text-lg font-bold truncate">
                                {user?.displayName || 'Jamify User'}
                            </h1>
                            <p className="text-sm text-muted-foreground truncate flex items-center gap-1.5">
                                <Mail className="w-3.5 h-3.5" />
                                {user?.email || 'Unknown'}
                            </p>
                        </div>
                    </div>
                </motion.div>

                {/* Playback Section */}
                <SettingsSection title="Playback" icon={Headphones} delay={0.1}>
                    <SettingsItem
                        icon={Volume2}
                        label="Audio Quality"
                        description="Higher quality uses more data"
                    >
                        <Select value={audioQuality} onValueChange={setAudioQuality}>
                            <SelectTrigger className="w-28 bg-surface-2/50 border-white/10">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="low">Low</SelectItem>
                                <SelectItem value="standard">Standard</SelectItem>
                                <SelectItem value="high">High</SelectItem>
                            </SelectContent>
                        </Select>
                    </SettingsItem>

                    <SettingsToggle
                        icon={Sparkles}
                        label="Crossfade"
                        description="Smooth transitions between tracks"
                        checked={crossfade}
                        onCheckedChange={setCrossfade}
                    />

                    <SettingsToggle
                        icon={Volume2}
                        label="Loudness Normalization"
                        description="Keep volume consistent across tracks"
                        checked={loudnessNormalize}
                        onCheckedChange={setLoudnessNormalize}
                    />
                </SettingsSection>

                {/* Personalization Section */}
                <SettingsSection title="Personalization" icon={Palette} delay={0.15}>
                    <SettingsLink
                        icon={Sparkles}
                        label="Default Mood"
                        value={defaultMoodName || 'None'}
                        onClick={() => navigate('/moods')}
                    />

                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <button className="w-full flex items-center gap-3 py-3 group">
                                <div className="w-9 h-9 rounded-xl bg-destructive/10 flex items-center justify-center">
                                    <AlertTriangle className="w-4 h-4 text-destructive" />
                                </div>
                                <div className="flex-1 text-left">
                                    <p className="font-medium text-destructive">Reset Training</p>
                                    <p className="text-sm text-muted-foreground">Clear all AI preferences</p>
                                </div>
                                <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                            </button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Reset All Training?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    This will clear all your likes, dislikes, and personalization data. Your AI DJ will need to learn your preferences again. This action cannot be undone.
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                                    Reset
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                </SettingsSection>

                {/* Spotify Integration Section */}
                <SettingsSection title="Spotify Integration" icon={Music2} delay={0.175}>
                    {spotifyStatus?.connected ? (
                        <>
                            <div className="py-3">
                                <div className="flex items-center gap-3 p-3 rounded-xl bg-green-500/10 border border-green-500/20">
                                    <div className="w-9 h-9 rounded-full bg-[#1DB954] flex items-center justify-center">
                                        <Music2 className="w-5 h-5 text-white" />
                                    </div>
                                    <div className="flex-1">
                                        <p className="font-medium text-green-400">Spotify Connected</p>
                                        <p className="text-sm text-muted-foreground">
                                            Your DJ is using your Spotify listening data
                                        </p>
                                    </div>
                                </div>
                            </div>
                            <AlertDialog>
                                <AlertDialogTrigger asChild>
                                    <button className="w-full flex items-center gap-3 py-3 group">
                                        <div className="w-9 h-9 rounded-xl bg-destructive/10 flex items-center justify-center">
                                            <AlertTriangle className="w-4 h-4 text-destructive" />
                                        </div>
                                        <div className="flex-1 text-left">
                                            <p className="font-medium text-destructive">Disconnect Spotify</p>
                                            <p className="text-sm text-muted-foreground">Remove Spotify data</p>
                                        </div>
                                        <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                                    </button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                    <AlertDialogHeader>
                                        <AlertDialogTitle>Disconnect Spotify?</AlertDialogTitle>
                                        <AlertDialogDescription>
                                            This will remove all your Spotify listening data. Your DJ will no longer be able to reference your Spotify top tracks and artists. This action cannot be undone.
                                        </AlertDialogDescription>
                                    </AlertDialogHeader>
                                    <AlertDialogFooter>
                                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                                        <AlertDialogAction
                                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                            onClick={handleDisconnectSpotify}
                                            disabled={isDisconnectingSpotify}
                                        >
                                            {isDisconnectingSpotify ? (
                                                <>
                                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                    Disconnecting...
                                                </>
                                            ) : (
                                                'Disconnect'
                                            )}
                                        </AlertDialogAction>
                                    </AlertDialogFooter>
                                </AlertDialogContent>
                            </AlertDialog>
                        </>
                    ) : (
                        <div className="py-3">
                            <div className="p-3 rounded-xl bg-slate-800/50 border border-slate-700">
                                <p className="text-sm text-muted-foreground mb-3">
                                    Connect your Spotify account to let your AI DJ know your real music taste and reference your listening history.
                                </p>
                                <Button
                                    onClick={() => navigate('/connect-spotify')}
                                    className="w-full bg-[#1DB954] hover:bg-[#1ed760] text-white"
                                >
                                    <Music2 className="mr-2 h-4 w-4" />
                                    Connect Spotify
                                </Button>
                            </div>
                        </div>
                    )}
                </SettingsSection>

                {/* Install App Section */}
                <div ref={installRef}>
                    <SettingsSection title="Install App" icon={Smartphone} delay={0.2}>
                        <div className="py-3">
                            <div className="relative overflow-hidden p-3 rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 border border-primary/20">
                                {/* Decorative elements */}
                                <div className="absolute top-0 right-0 w-20 h-20 bg-primary/20 rounded-full blur-2xl" />

                                <div className="relative flex items-start gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center flex-shrink-0">
                                        <Share2 className="w-5 h-5 text-primary" />
                                    </div>
                                    <div className="space-y-2">
                                        <p className="font-semibold text-sm">Install Jamify on iOS</p>
                                        <ol className="text-xs text-muted-foreground space-y-1.5 list-decimal list-inside">
                                            <li>Tap the <strong className="text-foreground">Share</strong> button in Safari</li>
                                            <li>Scroll down and tap <strong className="text-foreground">Add to Home Screen</strong></li>
                                            <li>Tap <strong className="text-foreground">Add</strong> to install</li>
                                        </ol>
                                    </div>
                                </div>
                            </div>
                            <p className="text-xs text-muted-foreground text-center mt-3">
                                Get the full app experience with background playback
                            </p>
                        </div>
                    </SettingsSection>
                </div>

                {/* Legal & Info Section */}
                <SettingsSection title="Legal & Info" icon={Info} delay={0.25}>
                    <SettingsLink
                        icon={FileText}
                        label="Terms of Service"
                        onClick={() => navigate('/terms')}
                    />
                    <SettingsLink
                        icon={Lock}
                        label="Privacy Policy"
                        onClick={() => navigate('/privacy')}
                    />
                </SettingsSection>

                {/* Logout Button */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                    className="pt-2"
                >
                    <Button
                        variant="outline"
                        className={cn(
                            "w-full h-12 rounded-2xl",
                            "bg-destructive/5 border-destructive/20 text-destructive",
                            "hover:bg-destructive/10 hover:border-destructive/30",
                            "transition-all"
                        )}
                        onClick={handleLogout}
                        disabled={isLoggingOut}
                    >
                        {isLoggingOut ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <LogOut className="w-4 h-4 mr-2" />
                        )}
                        Log Out
                    </Button>
                </motion.div>

                {/* Version info */}
                <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.35 }}
                    className="text-xs text-muted-foreground/50 text-center"
                >
                    Jamify v1.0.0 - Made with care
                </motion.p>
                </div>
            </div>
        </div>
    )

}

// Helper Components

function SettingsSection({
    title,
    icon: Icon,
    children,
    delay = 0,
}: {
    title: string
    icon: React.ElementType
    children: React.ReactNode
    delay?: number
}) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay }}
            className="space-y-1.5"
        >
            <div className="flex items-center gap-2 px-1">
                <Icon className="w-4 h-4 text-primary" />
                <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                    {title}
                </h2>
            </div>
            <div className="rounded-2xl glass-subtle border border-white/10 divide-y divide-white/5 px-3">
                {children}
            </div>
        </motion.div>
    )
}

function SettingsItem({
    icon: Icon,
    label,
    description,
    children,
}: {
    icon: React.ElementType
    label: string
    description?: string
    children: React.ReactNode
}) {
    return (
        <div className="flex items-center gap-3 py-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Icon className="w-4 h-4 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
                <p className="font-medium">{label}</p>
                {description && <p className="text-sm text-muted-foreground">{description}</p>}
            </div>
            {children}
        </div>
    )
}

function SettingsToggle({
    icon: Icon,
    label,
    description,
    checked,
    onCheckedChange,
}: {
    icon: React.ElementType
    label: string
    description?: string
    checked: boolean
    onCheckedChange: (checked: boolean) => void
}) {
    return (
        <div className="flex items-center gap-3 py-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Icon className="w-4 h-4 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
                <p className="font-medium">{label}</p>
                {description && <p className="text-sm text-muted-foreground">{description}</p>}
            </div>
            <Switch checked={checked} onCheckedChange={onCheckedChange} />
        </div>
    )
}

function SettingsLink({
    icon: Icon,
    label,
    value,
    onClick,
}: {
    icon: React.ElementType
    label: string
    value?: string
    onClick: () => void
}) {
    return (
        <button
            onClick={onClick}
            className="w-full flex items-center gap-3 py-3 group"
        >
            <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Icon className="w-4 h-4 text-primary" />
            </div>
            <div className="flex-1 text-left min-w-0">
                <p className="font-medium">{label}</p>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
                {value && <span className="text-sm">{value}</span>}
                <ChevronRight className="w-4 h-4 group-hover:text-foreground transition-colors" />
            </div>
        </button>
    )
}
