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
import { motion } from 'framer-motion'

export interface MoodSwitchInfo {
    moodId: string
    moodName: string
    moodColor: string
    currentTrack?: {
        title: string
        artist: string
        artworkUrl?: string
    }
    position: number
}

interface MoodSwitchDialogProps {
    open: boolean
    switchInfo: MoodSwitchInfo | null
    onResume: () => void
    onStartFresh: () => void
    onCancel: () => void
}

export function MoodSwitchDialog({
    open,
    switchInfo,
    onResume,
    onStartFresh,
    onCancel,
}: MoodSwitchDialogProps) {
    if (!switchInfo) return null

    const { moodName, moodColor, currentTrack, position } = switchInfo

    // Format position as mm:ss
    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60)
        const secs = Math.floor(seconds % 60)
        return `${mins}:${secs.toString().padStart(2, '0')}`
    }

    return (
        <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onCancel()}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <div
                            className="w-4 h-4 rounded-full"
                            style={{ backgroundColor: moodColor }}
                        />
                        Switch to {moodName}
                    </DialogTitle>
                    <DialogDescription>
                        You have a saved session in this mood. Would you like to continue where you left off?
                    </DialogDescription>
                </DialogHeader>

                {currentTrack && (
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex items-center gap-4 p-4 rounded-xl bg-gradient-to-br from-muted/50 to-muted/30 backdrop-blur-sm border border-border/30"
                    >
                        {currentTrack.artworkUrl ? (
                            <img
                                src={currentTrack.artworkUrl}
                                alt={currentTrack.title}
                                className="w-16 h-16 rounded-lg object-cover shadow-lg"
                            />
                        ) : (
                            <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center">
                                <Music className="w-8 h-8 text-muted-foreground" />
                            </div>
                        )}
                        <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">
                                {currentTrack.title}
                            </div>
                            <div className="text-sm text-muted-foreground truncate">
                                {currentTrack.artist}
                            </div>
                            <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                                <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse" />
                                Paused at {formatTime(position)}
                            </div>
                        </div>
                    </motion.div>
                )}

                <DialogFooter className="flex-col sm:flex-row gap-2 mt-2">
                    <Button
                        variant="outline"
                        onClick={onStartFresh}
                        className="w-full sm:w-auto"
                    >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Start Fresh
                    </Button>
                    <Button
                        onClick={onResume}
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
