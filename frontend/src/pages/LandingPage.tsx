import { useEffect } from "react"
import { useNavigate, Link } from "react-router-dom"
import { motion } from "framer-motion"
import { Play, Sparkles, Music2, Heart, TrendingUp, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/providers/AuthProvider"
import { InstallHint } from "@/components/InstallHint"
import { durations, easings, prefersReducedMotion } from "@/lib/motion"

export default function LandingPage() {
  const { isAuthenticated, isLoading } = useAuth()
  const navigate = useNavigate()
  const reducedMotion = prefersReducedMotion()

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/player", { replace: true })
    }
  }, [isAuthenticated, isLoading, navigate])

  return (
    <main className="min-h-dvh flex flex-col bg-background pt-safe-top pb-safe-bottom">
      {/* Animated background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-[#8b5cf6]/20 via-transparent to-[#ec4899]/20" />
        {!reducedMotion && (
          <>
            <motion.div
              className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#8b5cf6]/30 rounded-full blur-3xl"
              animate={{
                scale: [1, 1.2, 1],
                opacity: [0.3, 0.5, 0.3],
              }}
              transition={{
                duration: 8,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }}
            />
            <motion.div
              className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[#ec4899]/30 rounded-full blur-3xl"
              animate={{
                scale: [1.2, 1, 1.2],
                opacity: [0.3, 0.5, 0.3],
              }}
              transition={{
                duration: 8,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
                delay: 1,
              }}
            />
          </>
        )}
      </div>

      {/* Main content - centered */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="max-w-md w-full text-center">
          {/* Logo */}
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: durations.normal / 1000, ease: easings.spring }}
            className="mb-8 inline-flex"
          >
            <div className="w-20 h-20 rounded-3xl gradient-bg flex items-center justify-center shadow-xl glow">
              <Music2 className="w-10 h-10 text-white" />
            </div>
          </motion.div>

          {/* Badge */}
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: durations.normal / 1000, delay: 0.1 }}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-card/50 backdrop-blur-sm mb-6"
          >
            <Sparkles className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs text-muted-foreground font-medium">AI-Powered Music</span>
          </motion.div>

          {/* Main headline */}
          <motion.h1
            initial={reducedMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: durations.normal / 1000, delay: 0.2 }}
            className="text-4xl sm:text-5xl font-bold tracking-tight mb-4"
          >
            Your AI DJ, <span className="gradient-text">tuned to your mood</span>
          </motion.h1>

          {/* Subheadline */}
          <motion.p
            initial={reducedMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: durations.normal / 1000, delay: 0.3 }}
            className="text-base text-muted-foreground mb-10"
          >
            Music that adapts to you. Like having a personal DJ who knows exactly what you want to hear.
          </motion.p>

          {/* Feature bullets */}
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: durations.normal / 1000, delay: 0.4 }}
            className="grid gap-3 mb-10"
          >
            <div className="flex items-center gap-3 text-left p-3 rounded-xl bg-card/30 backdrop-blur-sm border border-border/50">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <Heart className="w-4 h-4 text-primary" />
              </div>
              <span className="text-sm">Learns your taste with every like</span>
            </div>
            <div className="flex items-center gap-3 text-left p-3 rounded-xl bg-card/30 backdrop-blur-sm border border-border/50">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <TrendingUp className="w-4 h-4 text-primary" />
              </div>
              <span className="text-sm">Mood-based playlists that evolve</span>
            </div>
            <div className="flex items-center gap-3 text-left p-3 rounded-xl bg-card/30 backdrop-blur-sm border border-border/50">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <Zap className="w-4 h-4 text-primary" />
              </div>
              <span className="text-sm">Instant playback, zero setup</span>
            </div>
          </motion.div>

          {/* CTAs */}
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: durations.normal / 1000, delay: 0.5 }}
            className="flex flex-col gap-3"
          >
            <Button
              asChild
              size="lg"
              className="gradient-bg text-white hover:opacity-90 transition-opacity h-12 text-base font-medium"
            >
              <Link to="/register">
                <Play className="w-5 h-5 mr-2" />
                Start listening
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="h-12 text-base font-medium border-border hover:bg-card">
              <Link to="/login">Log in</Link>
            </Button>
          </motion.div>

          {/* Social proof */}
          <motion.div
            initial={reducedMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: durations.normal / 1000, delay: 0.6 }}
            className="mt-8 flex items-center justify-center gap-3 text-xs text-muted-foreground"
          >
            <div className="flex -space-x-2">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="w-6 h-6 rounded-full border-2 border-background bg-gradient-to-br from-[#8b5cf6] to-[#ec4899]"
                />
              ))}
            </div>
            <span>10,000+ listeners</span>
          </motion.div>
        </div>
      </div>

      {/* Install hint (integrated) */}
      <InstallHint />

      {/* Footer */}
      <footer className="p-4 text-center space-y-2">
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <Link to="/privacy" className="hover:text-foreground transition-colors">
            Privacy
          </Link>
          <span>·</span>
          <Link to="/terms" className="hover:text-foreground transition-colors">
            Terms
          </Link>
        </div>
        <p className="text-xs text-muted-foreground">&copy; {new Date().getFullYear()} Jamify. All rights reserved.</p>
      </footer>
    </main>
  )
}
