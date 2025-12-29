import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Share2, X, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function InstallHint() {
  const [showHint, setShowHint] = useState(false)
  const [isIOS, setIsIOS] = useState(false)
  const [isStandalone, setIsStandalone] = useState(false)
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)

  useEffect(() => {
    // Check if running as standalone (already installed)
    const standalone = window.matchMedia('(display-mode: standalone)').matches
      || (window.navigator as Navigator & { standalone?: boolean }).standalone === true
    setIsStandalone(standalone)

    // Detect iOS
    const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as Window & { MSStream?: unknown }).MSStream
    setIsIOS(iOS)

    // Check if we've dismissed recently
    const dismissed = localStorage.getItem('jamify-install-dismissed')
    if (dismissed) {
      const dismissedAt = parseInt(dismissed, 10)
      const daysSince = (Date.now() - dismissedAt) / (1000 * 60 * 60 * 24)
      if (daysSince < 7) return
    }

    // Show hint after delay if not standalone
    if (!standalone) {
      const timer = setTimeout(() => setShowHint(true), 3000)
      return () => clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const handleDismiss = () => {
    setShowHint(false)
    localStorage.setItem('jamify-install-dismissed', Date.now().toString())
  }

  const handleInstall = async () => {
    if (deferredPrompt) {
      await deferredPrompt.prompt()
      const { outcome } = await deferredPrompt.userChoice
      if (outcome === 'accepted') setShowHint(false)
      setDeferredPrompt(null)
    }
  }

  if (isStandalone || !showHint) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 50 }}
        className="fixed bottom-20 left-4 right-4 z-50 max-w-md mx-auto"
      >
        <div className="p-4 rounded-2xl bg-card/95 backdrop-blur-xl border border-border shadow-lg">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl gradient-bg flex items-center justify-center flex-shrink-0">
              {isIOS ? <Share2 className="w-5 h-5 text-white" /> : <Download className="w-5 h-5 text-white" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm">Install Jamify</p>
              {isIOS ? (
                <p className="text-xs text-muted-foreground mt-1">
                  Tap <Share2 className="w-3 h-3 inline mx-0.5" /> then <strong>"Add to Home Screen"</strong>
                </p>
              ) : deferredPrompt ? (
                <Button size="sm" className="gradient-bg text-xs h-8 mt-2" onClick={handleInstall}>
                  <Download className="w-3 h-3 mr-1" /> Install App
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground mt-1">Add to home screen for the full experience.</p>
              )}
            </div>
            <button onClick={handleDismiss} className="p-1.5 rounded-lg hover:bg-accent" aria-label="Dismiss">
              <X className="w-4 h-4 text-muted-foreground" />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
