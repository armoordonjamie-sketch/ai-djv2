import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { ThumbsUp, ThumbsDown, Clock, AlertCircle, Loader2, Music2, Heart, TrendingUp, Calendar, Brain, Sparkles, PlusCircle, MinusCircle, SkipForward } from 'lucide-react'
import { LogoMark } from '@/components/branding/Logo'
import { Button } from '@/components/ui/button'
import * as api from '@/lib/jamifyApi'
import { cn } from '@/lib/utils'
import { HelperCard } from '@/components/ui/HelperCard'
import { useFirstRunHint } from '@/hooks/useFirstRunHint'

interface DateGroup {
    label: string
    items: api.PlayHistoryItem[]
}

export default function HistoryPage() {
    const [activeTab, setActiveTab] = useState<'history' | 'training'>('history')
    const [playHistory, setPlayHistory] = useState<api.PlayHistoryItem[]>([])
    const [trainingHistory, setTrainingHistory] = useState<api.TrainingLogEntry[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const firstRunHint = useFirstRunHint('jamify_hint_history')

    useEffect(() => {
        loadHistory()
    }, [])

    async function loadHistory() {
        setIsLoading(true)
        setError(null)
        try {
            const [playsData, trainingData] = await Promise.all([
                api.getPlayHistory(100),
                api.getTrainingHistory(50)
            ])
            setPlayHistory(playsData)
            setTrainingHistory(trainingData)
        } catch (err) {
            console.error('[HistoryPage] Failed to load history:', err)
            setError('Failed to load history')
        } finally {
            setIsLoading(false)
        }
    }

    // Group play history by date
    const groupedPlays = useMemo(() => {
        const groups: DateGroup[] = []
        const now = new Date()
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        const yesterday = new Date(today.getTime() - 86400000)
        const weekAgo = new Date(today.getTime() - 7 * 86400000)

        const todayItems: api.PlayHistoryItem[] = []
        const yesterdayItems: api.PlayHistoryItem[] = []
        const weekItems: api.PlayHistoryItem[] = []
        const olderItems: api.PlayHistoryItem[] = []

        playHistory.forEach(item => {
            const date = new Date(item.started_at)
            if (date >= today) {
                todayItems.push(item)
            } else if (date >= yesterday) {
                yesterdayItems.push(item)
            } else if (date >= weekAgo) {
                weekItems.push(item)
            } else {
                olderItems.push(item)
            }
        })

        if (todayItems.length > 0) groups.push({ label: 'Today', items: todayItems })
        if (yesterdayItems.length > 0) groups.push({ label: 'Yesterday', items: yesterdayItems })
        if (weekItems.length > 0) groups.push({ label: 'This Week', items: weekItems })
        if (olderItems.length > 0) groups.push({ label: 'Earlier', items: olderItems })

        return groups
    }, [playHistory])

    // Stats
    const stats = useMemo(() => {
        const total = playHistory.length
        const skipped = playHistory.filter(p => p.skipped).length
        const completed = total - skipped
        return { total, completed, skipped }
    }, [playHistory])

    function formatTimeAgo(dateString: string): string {
        const date = new Date(dateString)
        const now = new Date()
        const diffMs = now.getTime() - date.getTime()
        const diffMins = Math.floor(diffMs / 60000)
        const diffHours = Math.floor(diffMs / 3600000)
        const diffDays = Math.floor(diffMs / 86400000)

        if (diffMins < 1) return 'Just now'
        if (diffMins < 60) return `${diffMins}m ago`
        if (diffHours < 24) return `${diffHours}h ago`
        return `${diffDays}d ago`
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
                            <p className="text-sm font-medium">Loading history</p>
                            <p className="text-xs text-muted-foreground">Fetching your DJ sessions</p>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="h-full bg-background relative overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-24 right-[-10%] h-56 w-56 rounded-full bg-destructive/20 blur-3xl" />
                    <div className="absolute bottom-[-20%] left-[10%] h-64 w-64 rounded-full bg-warning/20 blur-3xl" />
                </div>
                <div className="relative h-full flex items-center justify-center px-6">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="text-center py-8 px-6 rounded-3xl border border-white/10 glass-subtle max-w-sm w-full"
                    >
                        <div className="inline-flex p-4 rounded-2xl bg-destructive/20 mb-4">
                            <AlertCircle className="w-8 h-8 text-destructive" />
                        </div>
                        <p className="text-lg font-medium mb-2">Something went wrong</p>
                        <p className="text-muted-foreground text-sm mb-4">{error}</p>
                        <Button variant="outline" onClick={loadHistory}>
                            Try Again
                        </Button>
                    </motion.div>
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
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="glass-subtle rounded-3xl border border-white/10 px-4 py-2.5 shadow-lg shadow-black/20 flex items-center justify-between gap-3"
                >
                    <div className="flex items-center gap-3">
                        <LogoMark size={28} />
                        <div>
                            <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">History</p>
                            <h1 className="text-base font-semibold">{activeTab === 'history' ? 'Listening' : 'Training'}</h1>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div className="flex p-1 rounded-full bg-white/5 border border-white/10">
                        <button
                            onClick={() => setActiveTab('history')}
                            className={cn(
                                "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                                activeTab === 'history'
                                    ? "bg-background text-primary shadow-sm"
                                    : "text-muted-foreground hover:text-primary"
                            )}
                        >
                            Listening
                        </button>
                        <button
                            onClick={() => setActiveTab('training')}
                            className={cn(
                                "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                                activeTab === 'training'
                                    ? "bg-background text-primary shadow-sm"
                                    : "text-muted-foreground hover:text-primary"
                            )}
                        >
                            Training
                        </button>
                    </div>
                </motion.div>

                <div className="flex-1 min-h-0 overflow-y-auto scroll-container scrollbar-hide pt-3 pb-2 space-y-4">
                    {firstRunHint.isVisible && (
                    <HelperCard
                        eyebrow="First session"
                        title="Teach your DJ"
                        description="Likes and skips are your training signals. The more you rate, the better the mix."
                        icon={<LogoMark size={20} />}
                        actionLabel="View training log"
                        onAction={() => setActiveTab('training')}
                        onDismiss={firstRunHint.dismiss}
                    >
                        <ul className="text-xs text-muted-foreground space-y-1">
                            <li>Tap like for tracks you want more of.</li>
                            <li>Tap dislike to steer away.</li>
                            <li>Review training updates here anytime.</li>
                        </ul>
                    </HelperCard>
                    )}

                    {activeTab === 'history' ? (
                <>
                    {/* Stats Hero */}
                    {playHistory.length > 0 && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 }}
                            className="grid grid-cols-3 gap-2"
                        >
                            <div className="relative overflow-hidden p-3 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20">
                                <div className="absolute top-2 right-2 opacity-20">
                                    <Music2 className="w-7 h-7" />
                                </div>
                                <p className="text-xl font-bold">{stats.total}</p>
                                <p className="text-xs text-muted-foreground">Tracks</p>
                            </div>
                            <div className="relative overflow-hidden p-3 rounded-2xl bg-gradient-to-br from-green-500/20 to-green-500/5 border border-green-500/20">
                                <div className="absolute top-2 right-2 opacity-20">
                                    <Heart className="w-7 h-7" />
                                </div>
                                <p className="text-xl font-bold text-green-500">{stats.completed}</p>
                                <p className="text-xs text-muted-foreground">Completed</p>
                            </div>
                            <div className="relative overflow-hidden p-3 rounded-2xl bg-gradient-to-br from-purple-500/20 to-purple-500/5 border border-purple-500/20">
                                <div className="absolute top-2 right-2 opacity-20">
                                    <TrendingUp className="w-7 h-7" />
                                </div>
                                <p className="text-xl font-bold text-purple-500">
                                    {stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0}%
                                </p>
                                <p className="text-xs text-muted-foreground">Completion</p>
                            </div>
                        </motion.div>
                    )}

                    {/* Timeline */}
                    {playHistory.length === 0 ? (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="text-center py-12 px-5 rounded-3xl border border-border/50 bg-gradient-to-br from-surface-2/50 to-transparent backdrop-blur-sm"
                        >
                            <div className="inline-flex p-4 rounded-2xl bg-primary/10 mb-4">
                                <Clock className="w-9 h-9 text-primary" />
                            </div>
                            <p className="text-base font-medium mb-1">No tracks played yet</p>
                            <p className="text-muted-foreground text-sm">Start listening to see your history here</p>
                        </motion.div>
                    ) : (
                        <div className="space-y-4 pb-2">
                            {groupedPlays.map((group: DateGroup, groupIndex: number) => (
                                <motion.div
                                    key={group.label}
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.1 + groupIndex * 0.1 }}
                                >
                                    {/* Date Header */}
                                    <div className="flex items-center gap-3 mb-3">
                                        <Calendar className="w-4 h-4 text-primary" />
                                        <span className="text-sm font-medium text-primary">{group.label}</span>
                                        <div className="flex-1 h-px bg-border/50" />
                                        <span className="text-xs text-muted-foreground">{group.items.length} tracks</span>
                                    </div>

                                    {/* Track List */}
                                    <div className="space-y-2 pl-2 border-l-2 border-border/30 ml-1.5">
                                        {group.items.map((item: api.PlayHistoryItem, index: number) => (
                                            <motion.div
                                                key={item.id}
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: 0.15 + groupIndex * 0.1 + index * 0.02 }}
                                                className={cn(
                                                    "group relative flex items-center gap-3 p-2.5 pl-4 rounded-xl",
                                                    "bg-gradient-to-r from-card/80 to-card/40 backdrop-blur-sm",
                                                    "border border-border/50 hover:border-primary/30 transition-all",
                                                    "hover:translate-x-1"
                                                )}
                                            >
                                                {/* Timeline dot */}
                                                <div className={cn(
                                                    "absolute -left-[9px] w-4 h-4 rounded-full bg-background border-2 transition-colors",
                                                    item.skipped ? "border-amber-500" : "border-green-500"
                                                )} />

                                                {/* Artwork placeholder with gradient */}
                                                <div
                                                    className="w-10 h-10 rounded-lg flex-shrink-0 shadow-md flex items-center justify-center"
                                                    style={{
                                                        background: item.skipped
                                                            ? 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'
                                                            : 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
                                                    }}
                                                >
                                                    <Music2 className="w-5 h-5 text-white/80" />
                                                </div>

                                                {/* Track info */}
                                                <div className="flex-1 min-w-0">
                                                    <p className="font-medium truncate text-sm">{item.track_title}</p>
                                                    <p className="text-xs text-muted-foreground truncate">{item.track_artist}</p>
                                                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-0.5">
                                                        <span>{formatTimeAgo(item.started_at)}</span>
                                                        {item.skipped && (
                                                            <span className="text-amber-500">• Skipped</span>
                                                        )}
                                                    </div>
                                                </div>
                                            </motion.div>
                                        ))}
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </>
            ) : (
                <div className="space-y-4 pb-2">
                    {trainingHistory.length === 0 ? (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="text-center py-12 px-5 rounded-3xl border border-dashed border-border/50 bg-secondary/20"
                        >
                            <Brain className="w-9 h-9 text-muted-foreground mb-4 mx-auto" />
                            <p className="text-base font-medium mb-2">No training insights yet</p>
                            <p className="text-muted-foreground text-sm">Rate songs to train your AI DJ</p>
                        </motion.div>
                    ) : (
                        <div className="space-y-3">
                            {trainingHistory.map((item, index) => (
                                <motion.div
                                    key={item.id}
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: index * 0.05 }}
                                    className="p-3 rounded-xl border border-border/50 bg-card/50 hover:bg-card hover:border-primary/20 transition-all"
                                >
                                    <div className="flex items-start gap-4">
                                        <div className={cn(
                                            "mt-1 p-2 rounded-lg",
                                            item.payload?.source === 'like' ? "bg-green-500/10 text-green-500" :
                                                item.payload?.source === 'dislike' ? "bg-red-500/10 text-red-500" :
                                                    item.payload?.source === 'skip' ? "bg-amber-500/10 text-amber-500" :
                                                        "bg-primary/10 text-primary"
                                        )}>
                                            {item.payload?.source === 'like' ? <ThumbsUp className="w-4 h-4" /> :
                                                item.payload?.source === 'dislike' ? <ThumbsDown className="w-4 h-4" /> :
                                                    item.payload?.source === 'skip' ? <SkipForward className="w-4 h-4" /> :
                                                        <Sparkles className="w-4 h-4" />}
                                        </div>

                                        <div className="flex-1 space-y-2">
                                            <div className="flex items-center justify-between">
                                                <h3 className="font-medium text-sm">
                                                    {item.payload?.track ? `Feedback on "${item.payload.track}"` : 'Session Training'}
                                                </h3>
                                                <span className="text-xs text-muted-foreground whitespace-nowrap">
                                                    {formatTimeAgo(item.timestamp)}
                                                </span>
                                            </div>

                                            {(item.payload?.reasoning || item.payload?.insights) && (
                                                <div className="p-3 rounded-lg bg-secondary/30 border border-border/30 text-xs text-foreground/90 italic">
                                                    "{item.payload.reasoning || item.payload.insights}"
                                                </div>
                                            )}

                                            <div className="flex flex-wrap gap-2">
                                                {item.payload?.added_artists?.map((artist, i) => (
                                                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/10 text-green-500 text-xs font-medium border border-green-500/20">
                                                        <PlusCircle className="w-3 h-3" />
                                                        {artist}
                                                    </span>
                                                ))}
                                                {item.payload?.demoted_artist && (
                                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/10 text-red-500 text-xs font-medium border border-red-500/20">
                                                        <MinusCircle className="w-3 h-3" />
                                                        {item.payload.demoted_artist}
                                                    </span>
                                                )}
                                            </div>

                                            {item.payload?.mood_name && (
                                                <p className="text-xs text-muted-foreground mt-1">
                                                    Updated <span className="text-primary font-medium">{item.payload.mood_name}</span> mood profile
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
                    )}
                </div>
        </div>
    </div>
    )
}
