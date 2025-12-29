import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ThumbsUp, ThumbsDown, Clock, AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import * as api from '@/lib/jamifyApi'
import { cn } from '@/lib/utils'

export default function HistoryPage() {
    const [feedback, setFeedback] = useState<api.FeedbackListItem[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        loadHistory()
    }, [])

    async function loadHistory() {
        setIsLoading(true)
        setError(null)
        try {
            // The backend uses feedback endpoint for now
            // getHistory will return empty array if /history is not implemented
            const historyData = await api.getHistory()

            // If history endpoint works, great! Otherwise fall back to feedback
            if (historyData.length > 0) {
                // Map history data if available
                // For now, just show feedback as history
            }

            // Load feedback as fallback history view
            const feedbackData = await api.getFeedback(undefined, 50)
            setFeedback(feedbackData)
        } catch (err) {
            console.error('[HistoryPage] Failed to load history:', err)
            setError('Failed to load history')
        } finally {
            setIsLoading(false)
        }
    }

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

    async function handleFeedback(item: api.FeedbackListItem, type: 'like' | 'dislike') {
        try {
            await api.submitFeedback({
                song_uuid: item.song_uuid,
                track_title: item.track_title,
                track_artist: item.track_artist,
                mood_id: item.mood_id || undefined,
                value: type,
            })
            // Optimistically update the UI
            setFeedback(prev =>
                prev.map(f =>
                    f.id === item.id
                        ? { ...f, value: type }
                        : f
                )
            )
        } catch (err) {
            console.error('[HistoryPage] Failed to submit feedback:', err)
        }
    }

    if (isLoading) {
        return (
            <div className="min-h-full flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
        )
    }

    if (error) {
        return (
            <div className="min-h-full px-4 py-6 pt-safe-top">
                <div className="text-center py-12">
                    <AlertCircle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
                    <p className="text-muted-foreground">{error}</p>
                    <Button variant="outline" className="mt-4" onClick={loadHistory}>
                        Try Again
                    </Button>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-full px-4 py-6 pt-safe-top space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold">History</h1>
                <p className="text-muted-foreground text-sm">Your recent plays and feedback</p>
            </div>

            {/* History List */}
            {feedback.length === 0 ? (
                <div className="text-center py-12">
                    <Clock className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <p className="text-muted-foreground">No tracks played yet</p>
                    <p className="text-muted-foreground text-sm mt-1">
                        Start listening to see your history here
                    </p>
                </div>
            ) : (
                <div className="space-y-2">
                    {feedback.map((item, index) => (
                        <motion.div
                            key={item.id}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: index * 0.03 }}
                            className="flex items-center gap-3 p-3 rounded-xl bg-card border border-border hover:border-primary/30 transition-colors"
                        >
                            {/* Artwork placeholder */}
                            <div
                                className="w-14 h-14 rounded-lg flex-shrink-0"
                                style={{
                                    background: 'linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)',
                                }}
                            />

                            {/* Track info */}
                            <div className="flex-1 min-w-0">
                                <p className="font-medium truncate">{item.track_title}</p>
                                <p className="text-sm text-muted-foreground truncate">{item.track_artist}</p>
                                <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                                    <span>{formatTimeAgo(item.created_at)}</span>
                                    {item.value && (
                                        <span className={cn(
                                            "px-1.5 py-0.5 rounded",
                                            item.value === 'like' && "bg-green-500/20 text-green-500",
                                            item.value === 'dislike' && "bg-red-500/20 text-red-500",
                                            item.value === 'skip' && "bg-amber-500/20 text-amber-500"
                                        )}>
                                            {item.value}
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Actions */}
                            <div className="flex items-center gap-1">
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className={cn(
                                        "h-9 w-9",
                                        item.value === 'like' && "text-green-500 hover:text-green-500"
                                    )}
                                    onClick={() => handleFeedback(item, 'like')}
                                >
                                    <ThumbsUp className={cn("w-4 h-4", item.value === 'like' && "fill-current")} />
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className={cn(
                                        "h-9 w-9",
                                        item.value === 'dislike' && "text-red-500 hover:text-red-500"
                                    )}
                                    onClick={() => handleFeedback(item, 'dislike')}
                                >
                                    <ThumbsDown className={cn("w-4 h-4", item.value === 'dislike' && "fill-current")} />
                                </Button>
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}
        </div>
    )
}
