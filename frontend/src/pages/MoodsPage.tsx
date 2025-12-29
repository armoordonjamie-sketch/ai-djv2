import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Plus, Copy, Trash2, Sparkles, Zap, Music, Loader2, Star } from 'lucide-react'
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
    const [moods, setMoods] = useState<api.Mood[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [isCreating, setIsCreating] = useState(false)
    const [isSaving, setIsSaving] = useState(false)
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
        // Set as default and navigate to player with mood ID
        try {
            await api.setDefaultMood(moodId)
            setMoods(prev => prev.map(m => ({ ...m, is_default: m.id === moodId })))
        } catch (err) {
            console.error('[MoodsPage] Failed to set default mood:', err)
        }
        // Always navigate, passing the mood ID for immediate stream start
        navigate('/player', { state: { moodId } })
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
            <div className="min-h-full flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="min-h-full px-4 py-6 pt-safe-top space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">Your Moods</h1>
                    <p className="text-muted-foreground text-sm">Customize your AI DJ experience</p>
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
                                    <label className="text-sm font-medium">Mood (Sad ↔ Happy)</label>
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

            {/* Moods Grid */}
            {moods.length === 0 ? (
                <div className="text-center py-12">
                    <Music className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <p className="text-muted-foreground">No moods yet. Create your first one!</p>
                </div>
            ) : (
                <div className="grid gap-4">
                    {moods.map((mood, index) => (
                        <motion.div
                            key={mood.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.05 }}
                            onClick={() => handleSelectMood(mood.id)}
                            className={cn(
                                "relative p-4 rounded-2xl border cursor-pointer transition-all",
                                "hover:border-primary/50",
                                mood.is_default && "ring-2 ring-primary"
                            )}
                            style={{
                                backgroundColor: mood.color + '15',
                                borderColor: mood.color + '40',
                            }}
                        >
                            <div className="flex items-center gap-4">
                                {/* Color indicator */}
                                <div
                                    className="w-14 h-14 rounded-xl flex items-center justify-center text-2xl"
                                    style={{ backgroundColor: mood.color + '30' }}
                                >
                                    🎵
                                </div>

                                {/* Info */}
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <h3 className="font-semibold truncate">{mood.name}</h3>
                                        {mood.is_default && (
                                            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary flex items-center gap-1">
                                                <Star className="w-3 h-3" />
                                                Default
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                                        <span className="flex items-center gap-1">
                                            <Zap className="w-3 h-3" />
                                            {Math.round(mood.energy_target * 100)}% Energy
                                        </span>
                                        {mood.genres && mood.genres.length > 0 && (
                                            <span className="flex items-center gap-1">
                                                <Music className="w-3 h-3" />
                                                {mood.genres.slice(0, 2).join(', ')}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* Actions */}
                                <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDuplicateMood(mood)}>
                                        <Copy className="w-4 h-4" />
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-destructive hover:text-destructive"
                                        onClick={() => handleDeleteMood(mood.id)}
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}
        </div>
    )
}
