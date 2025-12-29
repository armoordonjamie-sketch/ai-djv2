import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
    User,
    Headphones,
    Sparkles,
    Smartphone,
    Shield,
    LogOut,
    ChevronRight,
    Share2,
    AlertTriangle,
    Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
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

export default function SettingsPage() {
    const navigate = useNavigate()
    const { user, logout } = useAuth()
    const [audioQuality, setAudioQuality] = useState('standard')
    const [crossfade, setCrossfade] = useState(true)
    const [loudnessNormalize, setLoudnessNormalize] = useState(true)
    const [defaultMoodName, setDefaultMoodName] = useState<string | null>(null)
    const [isLoggingOut, setIsLoggingOut] = useState(false)

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

    return (
        <div className="min-h-full px-4 py-6 pt-safe-top space-y-6 pb-20">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold">Settings</h1>
                <p className="text-muted-foreground text-sm">Customize your experience</p>
            </div>

            {/* Profile Section */}
            <SettingsSection title="Profile" icon={User}>
                <SettingsRow
                    label="Display Name"
                    value={user?.displayName || 'Not set'}
                />
                <SettingsRow
                    label="Email"
                    value={user?.email || 'Unknown'}
                />
            </SettingsSection>

            {/* Playback Section */}
            <SettingsSection title="Playback" icon={Headphones}>
                <div className="flex items-center justify-between py-3">
                    <div>
                        <p className="font-medium">Audio Quality</p>
                        <p className="text-sm text-muted-foreground">Higher quality uses more data</p>
                    </div>
                    <Select value={audioQuality} onValueChange={setAudioQuality}>
                        <SelectTrigger className="w-28">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="low">Low</SelectItem>
                            <SelectItem value="standard">Standard</SelectItem>
                            <SelectItem value="high">High</SelectItem>
                        </SelectContent>
                    </Select>
                </div>

                <SettingsToggle
                    label="Crossfade"
                    description="Smooth transitions between tracks"
                    checked={crossfade}
                    onCheckedChange={setCrossfade}
                />

                <SettingsToggle
                    label="Loudness Normalization"
                    description="Keep volume consistent across tracks"
                    checked={loudnessNormalize}
                    onCheckedChange={setLoudnessNormalize}
                />
            </SettingsSection>

            {/* Personalization Section */}
            <SettingsSection title="Personalization" icon={Sparkles}>
                <SettingsLink
                    label="Default Mood"
                    value={defaultMoodName || 'None'}
                    onClick={() => navigate('/moods')}
                />

                <AlertDialog>
                    <AlertDialogTrigger asChild>
                        <button className="w-full flex items-center justify-between py-3 text-destructive hover:opacity-80">
                            <div className="flex items-center gap-2">
                                <AlertTriangle className="w-4 h-4" />
                                <span className="font-medium">Reset Training</span>
                            </div>
                            <ChevronRight className="w-4 h-4" />
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

            {/* PWA Section */}
            <SettingsSection title="Install App" icon={Smartphone}>
                <div className="py-3 space-y-3">
                    <div className="p-4 rounded-xl bg-primary/10 border border-primary/20">
                        <div className="flex items-start gap-3">
                            <Share2 className="w-5 h-5 text-primary mt-0.5 flex-shrink-0" />
                            <div className="space-y-1">
                                <p className="font-medium text-sm">Install Jamify on iOS</p>
                                <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
                                    <li>Tap the <strong>Share</strong> button in Safari</li>
                                    <li>Scroll down and tap <strong>Add to Home Screen</strong></li>
                                    <li>Tap <strong>Add</strong> to install</li>
                                </ol>
                            </div>
                        </div>
                    </div>
                    <p className="text-xs text-muted-foreground text-center">
                        Get the full app experience with offline support
                    </p>
                </div>
            </SettingsSection>

            {/* Privacy Section */}
            <SettingsSection title="Privacy" icon={Shield}>
                <SettingsLink label="Terms of Service" onClick={() => navigate('/terms')} />
                <SettingsLink label="Privacy Policy" onClick={() => navigate('/privacy')} />
            </SettingsSection>

            {/* Logout */}
            <div className="pt-4">
                <Button
                    variant="outline"
                    className="w-full text-destructive border-destructive/30 hover:bg-destructive/10"
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
            </div>
        </div>
    )
}

// Helper Components
function SettingsSection({
    title,
    icon: Icon,
    children,
}: {
    title: string
    icon: React.ElementType
    children: React.ReactNode
}) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-1"
        >
            <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4 text-muted-foreground" />
                <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                    {title}
                </h2>
            </div>
            <div className="rounded-xl bg-card border border-border divide-y divide-border px-4">
                {children}
            </div>
        </motion.div>
    )
}

function SettingsRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center justify-between py-3">
            <span className="font-medium">{label}</span>
            <span className="text-muted-foreground">{value}</span>
        </div>
    )
}

function SettingsToggle({
    label,
    description,
    checked,
    onCheckedChange,
}: {
    label: string
    description?: string
    checked: boolean
    onCheckedChange: (checked: boolean) => void
}) {
    return (
        <div className="flex items-center justify-between py-3">
            <div>
                <p className="font-medium">{label}</p>
                {description && <p className="text-sm text-muted-foreground">{description}</p>}
            </div>
            <Switch checked={checked} onCheckedChange={onCheckedChange} />
        </div>
    )
}

function SettingsLink({
    label,
    value,
    onClick,
}: {
    label: string
    value?: string
    onClick: () => void
}) {
    return (
        <button
            onClick={onClick}
            className="w-full flex items-center justify-between py-3 hover:opacity-80 transition-opacity"
        >
            <span className="font-medium">{label}</span>
            <div className="flex items-center gap-2 text-muted-foreground">
                {value && <span>{value}</span>}
                <ChevronRight className="w-4 h-4" />
            </div>
        </button>
    )
}
