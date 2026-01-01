import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { PlayCircle, RefreshCw, Music } from 'lucide-react'
import type { ResumableSession } from '@/lib/jamifyApi'
import { usePlayer } from '@/providers/PlayerProvider'

interface ResumeSessionDialogProps {
    resumableSession: ResumableSession | null
    onResume: () => void
    onStartFresh: () => void
}

export function ResumeSessionDialog({
    resumableSession,
    onResume,
    onStartFresh,
}: ResumeSessionDialogProps) {
    const [open, setOpen] = useState(false)
    const [dismissed, setDismissed] = useState(false)
    const player = usePlayer()

    useEffect(() => {
        // Only show dialog if we have a resumable session, haven't dismissed it,
        // AND no stream was already started by PlayerPage auto-start
        if (resumableSession?.resumable && !dismissed && !player.sessionId && !player.isLoading) {
            console.log('[ResumeDialog] Showing resume dialog')
            setOpen(true)
        } else if (resumableSession?.resumable && (player.sessionId || player.isLoading)) {
            console.log('[ResumeDialog] NOT showing - stream already started')
            // Auto-close if stream started while dialog was open
            setOpen(false)
            setDismissed(true)
        }
    }, [resumableSession, dismissed, player.sessionId, player.isLoading])

    const handleResume = () => {
        setOpen(false)
        setDismissed(true)
        onResume()
    }

    const handleStartFresh = () => {
        setOpen(false)
        setDismissed(true)
        onStartFresh()
    }

    if (!resumableSession?.resumable) {
        return null
    }

    const { track_info, mood_name, position_sec } = resumableSession

    // Format position as mm:ss
    const formatTime = (seconds?: number) => {
        if (!seconds) return '0:00'
        const mins = Math.floor(seconds / 60)
        const secs = Math.floor(seconds % 60)
        return `${mins}:${secs.toString().padStart(2, '0')}`
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Welcome back!</DialogTitle>
                    <DialogDescription>
                        You have an active session. Would you like to continue where you left off?
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-col gap-4 py-4">
                    {/* Track Info */}
                    <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50">
                        {track_info?.artwork_url ? (
                            <img
                                src={track_info.artwork_url}
                                alt={track_info.title}
                                className="w-16 h-16 rounded-md object-cover"
                            />
                        ) : (
                            <div className="w-16 h-16 rounded-md bg-muted flex items-center justify-center">
                                <Music className="w-8 h-8 text-muted-foreground" />
                            </div>
                        )}
                        <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">
                                {track_info?.title || 'Unknown Track'}
                            </div>
                            <div className="text-sm text-muted-foreground truncate">
                                {track_info?.artist || 'Unknown Artist'}
                            </div>
                            {mood_name && (
                                <div className="text-xs text-muted-foreground mt-1">
                                    {mood_name} mood
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Position Info */}
                    {position_sec !== undefined && position_sec > 0 && (
                        <div className="text-sm text-center text-muted-foreground">
                            Last position: {formatTime(position_sec)}
                        </div>
                    )}
                </div>

                <DialogFooter className="flex-col sm:flex-row gap-2">
                    <Button
                        variant="outline"
                        onClick={handleStartFresh}
                        className="w-full sm:w-auto"
                    >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Start Fresh
                    </Button>
                    <Button
                        onClick={handleResume}
                        className="w-full sm:w-auto gradient-bg"
                    >
                        <PlayCircle className="w-4 h-4 mr-2" />
                        Resume
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

