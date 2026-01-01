import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Plus, Copy, Trash2, Sparkles, Zap, Loader2, Star } from 'lucide-react'
import { LogoMark } from '@/components/branding/Logo'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from '@/components/ui/sheet'
import * as api from '@/lib/jamifyApi'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { usePlayer } from '@/providers/PlayerProvider'
import { HelperCard } from '@/components/ui/HelperCard'
import { useFirstRunHint } from '@/hooks/useFirstRunHint'

const DJ_PERSONALITIES = [
    { id: 'casual_funny', label: 'Casual', icon: '😌', description: 'Relaxed and fun commentary' },
    { id: 'hype_energetic', label: 'Hype', icon: '🔥', description: 'High energy and exciting' },
    { id: 'minimal_talk', label: 'Minimal', icon: '🤫', description: 'Just the music, almost no talk' },
]

const MOOD_COLORS = [
    '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#22c55e',
    '#14b8a6', '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#ec4899',
]

export default function MoodsPage() {
    const navigate = useNavigate()
    const player = usePlayer()
    const [moods, setMoods] = useState<api.Mood[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [isCreating, setIsCreating] = useState(false)
    const [isSaving, setIsSaving] = useState(false)
    const [isStartingStream, setIsStartingStream] = useState(false)
    const firstRunHint = useFirstRunHint('jamify_hint_moods')
    const [newMood, setNewMood] = useState({
        name: '',
        color: MOOD_COLORS[5],
        energy_target: 0.5,
        valence_target: 0.5,
        dj_personality: 'casual_funny',
    })

    // Load moods from API
    useEffect(() => {
        loadMoods()
    }, [])

    async function loadMoods() {
        try {
            setIsLoading(true)
            const data = await api.getMoods()
            setMoods(data)
        } catch (err) {
            console.error('[MoodsPage] Failed to load moods:', err)
            toast.error('Failed to load moods')
        } finally {
            setIsLoading(false)
        }
    }

    async function handleCreateMood() {
        if (!newMood.name.trim()) return

        try {
            setIsSaving(true)
            const created = await api.createMood({
                name: newMood.name.trim(),
                color: newMood.color,
                energy_target: newMood.energy_target,
                valence_target: newMood.valence_target,
                dj_personality: newMood.dj_personality,
                is_default: false,
            })
            setMoods(prev => [...prev, created])
            setNewMood({
                name: '',
                color: MOOD_COLORS[5],
                energy_target: 0.5,
                valence_target: 0.5,
                dj_personality: 'casual_funny',
            })
            setIsCreating(false)
            toast.success('Mood created!')
        } catch (err) {
            console.error('[MoodsPage] Failed to create mood:', err)
            toast.error('Failed to create mood')
        } finally {
            setIsSaving(false)
        }
    }

    async function handleSelectMood(moodId: string) {
        // When explicitly selecting a mood, start a fresh stream (not resume)
        setIsStartingStream(true)
        try {
            // Set as default
            await api.setDefaultMood(moodId)
            setMoods(prev => prev.map(m => ({ ...m, is_default: m.id === moodId })))

            // Clear resumable session flag to prevent ResumeDialog from interfering
            sessionStorage.removeItem('has_resumable_session')
            
            // Mark user interaction to enable autoplay and dismiss any dialogs
            player.setHasUserInteracted(true)
            
            // Start fresh stream with this mood (resume=false)
            await player.startStream(moodId, false)

            // Navigate to player with state to prevent duplicate stream/start
            navigate('/player', { state: { streamStarted: true } })
        } catch (err) {
            console.error('[MoodsPage] Failed to start stream:', err)
            toast.error('Failed to start stream')
        } finally {
            setIsStartingStream(false)
        }
    }

    async function handleDeleteMood(moodId: string) {
        try {
            await api.deleteMood(moodId)
            setMoods(prev => prev.filter(m => m.id !== moodId))
            toast.success('Mood deleted')
        } catch (err) {
            console.error('[MoodsPage] Failed to delete mood:', err)
            toast.error('Failed to delete mood')
        }
    }

    async function handleDuplicateMood(mood: api.Mood) {
        try {
            const created = await api.createMood({
                name: `${mood.name} (copy)`,
                color: mood.color,
                energy_target: mood.energy_target,
                valence_target: mood.valence_target,
                genres: mood.genres,
                dj_personality: mood.dj_personality,
                is_default: false,
            })
            setMoods(prev => [...prev, created])
            toast.success('Mood duplicated!')
        } catch (err) {
            console.error('[MoodsPage] Failed to duplicate mood:', err)
            toast.error('Failed to duplicate mood')
        }
    }

    if (isLoading) {
        return (
            <div className="h-full bg-background relative overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-24 right-[-10%] h-56 w-56 rounded-full bg-primary/20 blur-3xl" />
                    <div className="absolute bottom-[-20%] left-[10%] h-64 w-64 rounded-full bg-accent/20 blur-3xl" />
                </div>
                <div className="relative h-full flex items-center justify-center">
                    <div className="glass-subtle rounded-2xl border border-white/10 px-5 py-4 flex items-center gap-3">
                        <Loader2 className="w-5 h-5 animate-spin text-primary" />
                        <div className="text-left">
                            <p className="text-sm font-medium">Loading moods</p>
                            <p className="text-xs text-muted-foreground">Syncing your vibe presets</p>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

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
                            <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Moods</p>
                            <h1 className="text-base font-semibold">Your vibes</h1>
                        </div>
                    </div>

                    <Sheet open={isCreating} onOpenChange={setIsCreating}>
                        <SheetTrigger asChild>
                            <Button size="sm" className="gradient-bg">
                                <Plus className="w-4 h-4 mr-1" />
                                New
                            </Button>
                        </SheetTrigger>
                        <SheetContent side="bottom" className="pb-safe-bottom">
                            <SheetHeader>
                                <SheetTitle>Create a Mood</SheetTitle>
                                <SheetDescription>
                                    Design a new mood for your AI DJ to match.
                                </SheetDescription>
                            </SheetHeader>

                            <div className="space-y-6 py-4">
                                {/* Name */}
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Name</label>
                                    <Input
                                        placeholder="e.g., Late Night Coding"
                                        value={newMood.name}
                                        onChange={(e) => setNewMood(prev => ({ ...prev, name: e.target.value }))}
                                    />
                                </div>

                                {/* Color */}
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Color</label>
                                    <div className="flex flex-wrap gap-2">
                                        {MOOD_COLORS.map(color => (
                                            <button
                                                key={color}
                                                onClick={() => setNewMood(prev => ({ ...prev, color }))}
                                                className={cn(
                                                    "w-8 h-8 rounded-full transition-transform",
                                                    newMood.color === color && "ring-2 ring-white ring-offset-2 ring-offset-background scale-110"
                                                )}
                                                style={{ backgroundColor: color }}
                                            />
                                        ))}
                                    </div>
                                </div>

                                {/* Energy */}
                                <div className="space-y-3">
                                    <div className="flex justify-between">
                                        <label className="text-sm font-medium">Energy Level</label>
                                        <span className="text-sm text-muted-foreground">{Math.round(newMood.energy_target * 100)}%</span>
                                    </div>
                                    <Slider
                                        value={[newMood.energy_target * 100]}
                                        onValueChange={([v]) => setNewMood(prev => ({ ...prev, energy_target: v / 100 }))}
                                        max={100}
                                        step={1}
                                    />
                                </div>

                                {/* Valence/Mood */}
                                <div className="space-y-3">
                                    <div className="flex justify-between">
                                        <label className="text-sm font-medium">Mood (Sad ??" Happy)</label>
                                        <span className="text-sm text-muted-foreground">{Math.round(newMood.valence_target * 100)}%</span>
                                    </div>
                                    <Slider
                                        value={[newMood.valence_target * 100]}
                                        onValueChange={([v]) => setNewMood(prev => ({ ...prev, valence_target: v / 100 }))}
                                        max={100}
                                        step={1}
                                    />
                                </div>

                                {/* DJ Personality */}
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">DJ Personality</label>
                                    <div className="grid grid-cols-3 gap-2">
                                        {DJ_PERSONALITIES.map(p => (
                                            <button
                                                key={p.id}
                                                onClick={() => setNewMood(prev => ({ ...prev, dj_personality: p.id }))}
                                                className={cn(
                                                    "p-3 rounded-xl border text-center transition-all",
                                                    newMood.dj_personality === p.id
                                                        ? "border-primary bg-primary/10"
                                                        : "border-border hover:border-primary/50"
                                                )}
                                            >
                                                <div className="text-xl mb-1">{p.icon}</div>
                                                <div className="text-xs font-medium">{p.label}</div>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <Button
                                    onClick={handleCreateMood}
                                    className="w-full gradient-bg"
                                    disabled={!newMood.name.trim() || isSaving}
                                >
                                    {isSaving ? (
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    ) : (
                                        <Sparkles className="w-4 h-4 mr-2" />
                                    )}
                                    Create Mood
                                </Button>
                            </div>
                        </SheetContent>
                    </Sheet>
                </div>

                <div className="flex-1 min-h-0 flex flex-col">
                    <div className="flex-1 min-h-0 overflow-y-auto scroll-container scrollbar-hide pt-3 pb-2 space-y-4">
                        {firstRunHint.isVisible && (
                            <HelperCard
                                eyebrow="First session"
                                title="Build your first mood"
                                description="Moods set the vibe for your DJ. Create one or tap a vibe to start playing."
                                icon={<LogoMark size={20} />}
                                actionLabel="Create a mood"
                                onAction={() => setIsCreating(true)}
                                onDismiss={firstRunHint.dismiss}
                            >
                                <ul className="text-xs text-muted-foreground space-y-1">
                                    <li>Name it based on a moment or task.</li>
                                    <li>Pick energy and mood targets.</li>
                                    <li>Tap a mood to start listening.</li>
                                </ul>
                            </HelperCard>
                        )}

                        {/* Moods Grid */}
                        {moods.length === 0 ? (
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="text-center py-12 px-5 rounded-3xl border border-white/10 glass-subtle"
                            >
                                <div className="inline-flex p-4 rounded-2xl bg-primary/10 mb-4">
                                    <LogoMark size={32} />
                                </div>
                                <p className="text-base font-medium mb-1">No moods yet</p>
                                <p className="text-muted-foreground text-sm">Create your first mood to customize your AI DJ experience</p>
                            </motion.div>
                        ) : (
                            <div className="grid gap-3 pb-2">
                                {moods.map((mood, index) => {
                                    const isActive = mood.is_default
                                    return (
                                        <motion.div
                                            key={mood.id}
                                            initial={{ opacity: 0, y: 20, scale: 0.98 }}
                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                            transition={{
                                                delay: index * 0.05,
                                                type: "spring",
                                                stiffness: 300,
                                                damping: 25
                                            }}
                                            whileHover={{ scale: 1.01, y: -2 }}
                                            whileTap={{ scale: 0.99 }}
                                            onClick={() => !isStartingStream && handleSelectMood(mood.id)}
                                            className={cn(
                                                "relative group overflow-hidden rounded-2xl transition-all duration-300",
                                                isStartingStream
                                                    ? "cursor-not-allowed opacity-50"
                                                    : "cursor-pointer",
                                            )}
                                        >
                                            {/* Background with glass effect */}
                                            <div
                                                className="absolute inset-0 backdrop-blur-xl"
                                                style={{
                                                    background: `linear-gradient(135deg, ${mood.color}18 0%, ${mood.color}08 50%, transparent 100%)`,
                                                }}
                                            />

                                            {/* Border glow for active mood */}
                                            {isActive && (
                                                <motion.div
                                                    layoutId="activeMoodBorder"
                                                    className="absolute inset-0 rounded-2xl"
                                                    style={{
                                                        boxShadow: `inset 0 0 0 2px ${mood.color}, 0 0 30px ${mood.color}40`,
                                                    }}
                                                    transition={{ type: "spring", stiffness: 300, damping: 25 }}
                                                />
                                            )}

                                            {/* Inactive border */}
                                            {!isActive && (
                                                <div
                                                    className="absolute inset-0 rounded-2xl border border-white/10 group-hover:border-white/20 transition-colors"
                                                />
                                            )}

                                            {/* Content */}
                                            <div className="relative p-4 flex items-center gap-3">
                                                {/* Icon with gradient background */}
                                                <div
                                                    className="relative w-14 h-14 rounded-xl flex items-center justify-center text-xl shadow-lg"
                                                    style={{
                                                        background: `linear-gradient(135deg, ${mood.color}60 0%, ${mood.color}30 100%)`,
                                                    }}
                                                >
                                                    ?YZ?
                                                    {/* Shine effect */}
                                                    <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-white/20 to-transparent" />
                                                </div>

                                                {/* Info */}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <h3 className="font-semibold text-base truncate">{mood.name}</h3>
                                                        {isActive && (
                                                            <motion.span
                                                                initial={{ opacity: 0, scale: 0.8 }}
                                                                animate={{ opacity: 1, scale: 1 }}
                                                                className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium"
                                                                style={{
                                                                    backgroundColor: mood.color + '30',
                                                                    color: mood.color,
                                                                }}
                                                            >
                                                                <Star className="w-3 h-3 fill-current" />
                                                                Active
                                                            </motion.span>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                                        <span className="flex items-center gap-1.5">
                                                            <Zap className="w-3.5 h-3.5" style={{ color: mood.color }} />
                                                            {Math.round(mood.energy_target * 100)}% Energy
                                                        </span>
                                                        <span className="flex items-center gap-1.5">
                                                            <Sparkles className="w-3.5 h-3.5" style={{ color: mood.color }} />
                                                            {Math.round(mood.valence_target * 100)}% Mood
                                                        </span>
                                                    </div>
                                                    {mood.genres && mood.genres.length > 0 && (
                                                        <div className="flex flex-wrap gap-1.5 mt-2">
                                                            {mood.genres.slice(0, 3).map((genre, i) => (
                                                                <span
                                                                    key={i}
                                                                    className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-muted-foreground"
                                                                >
                                                                    {genre}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>

                                                {/* Actions with glass effect */}
                                                <div
                                                    className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
                                                    onClick={e => e.stopPropagation()}
                                                >
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 rounded-xl bg-white/5 hover:bg-white/10 backdrop-blur-sm"
                                                        onClick={() => handleDuplicateMood(mood)}
                                                    >
                                                        <Copy className="w-4 h-4" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 rounded-xl bg-white/5 hover:bg-destructive/20 backdrop-blur-sm text-destructive"
                                                        onClick={() => handleDeleteMood(mood.id)}
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </Button>
                                                </div>
                                            </div>

                                            {/* Hover gradient overlay */}
                                            <div
                                                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                                                style={{
                                                    background: `linear-gradient(90deg, transparent 0%, ${mood.color}10 100%)`,
                                                }}
                                            />
                                        </motion.div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )

}
