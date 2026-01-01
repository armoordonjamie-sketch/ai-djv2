import { useEffect } from "react"
import { useNavigate, Link } from "react-router-dom"
import { motion } from "framer-motion"
import { Play, Sparkles, Heart, TrendingUp, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LogoMark } from "@/components/branding/Logo"
import { useAuth } from "@/providers/AuthProvider"
import { InstallHint } from "@/components/InstallHint"
import { durations, prefersReducedMotion } from "@/lib/motion"

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
    <main className="min-h-dvh bg-background relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-32 right-[-10%] h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute top-32 left-[-15%] h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <div className="absolute bottom-[-20%] right-[10%] h-72 w-72 rounded-full bg-success/15 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_55%)]" />
        {!reducedMotion && (
          <>
            <motion.div
              className="absolute top-1/4 left-1/4 w-80 h-80 bg-primary/20 rounded-full blur-3xl"
              animate={{
                scale: [1, 1.15, 1],
                opacity: [0.2, 0.4, 0.2],
              }}
              transition={{
                duration: 10,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }}
            />
            <motion.div
              className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-accent/20 rounded-full blur-3xl"
              animate={{
                scale: [1.1, 1, 1.1],
                opacity: [0.2, 0.4, 0.2],
              }}
              transition={{
                duration: 10,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
                delay: 1,
              }}
            />
          </>
        )}
      </div>

      {/* Header */}
      <header className="relative px-4 pt-safe-top">
        <div className="max-w-6xl mx-auto flex items-center justify-between py-4">
          <Link to="/" className="inline-flex items-center gap-2">
            <LogoMark size={32} />
            <span className="text-lg font-semibold tracking-tight">Jamify</span>
          </Link>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link to="/login">Log in</Link>
            </Button>
            <Button asChild size="sm" className="gradient-bg text-white">
              <Link to="/register">Get started</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative flex-1 px-4 pb-safe-bottom">
        <div className="max-w-6xl mx-auto grid gap-10 lg:grid-cols-[1.05fr_0.95fr] items-center py-8">
          <div className="text-center lg:text-left">
            <motion.div
              initial={reducedMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: durations.normal / 1000, delay: 0.05 }}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/5 backdrop-blur-sm mb-6"
            >
              <Sparkles className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs text-muted-foreground font-medium">Adaptive AI DJ</span>
            </motion.div>

            <motion.h1
              initial={reducedMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: durations.normal / 1000, delay: 0.15 }}
              className="text-4xl sm:text-5xl font-bold tracking-tight mb-4"
            >
              Your AI DJ, <span className="gradient-text">tuned to your mood</span>
            </motion.h1>

            <motion.p
              initial={reducedMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: durations.normal / 1000, delay: 0.25 }}
              className="text-base text-muted-foreground mb-8"
            >
              Build a living soundtrack that adapts in real time. Jamify listens to your feedback and curates the next track instantly.
            </motion.p>

            <motion.div
              initial={reducedMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: durations.normal / 1000, delay: 0.35 }}
              className="grid gap-3"
            >
              <div className="flex items-center gap-3 text-left p-3 rounded-2xl glass-subtle border border-white/10">
                <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                  <Heart className="w-4 h-4 text-primary" />
                </div>
                <span className="text-sm">Learns your taste with every like</span>
              </div>
              <div className="flex items-center gap-3 text-left p-3 rounded-2xl glass-subtle border border-white/10">
                <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                  <TrendingUp className="w-4 h-4 text-primary" />
                </div>
                <span className="text-sm">Mood-based mixes that evolve over time</span>
              </div>
              <div className="flex items-center gap-3 text-left p-3 rounded-2xl glass-subtle border border-white/10">
                <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                  <Zap className="w-4 h-4 text-primary" />
                </div>
                <span className="text-sm">Instant playback with zero setup</span>
              </div>
            </motion.div>

            <motion.div
              initial={reducedMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: durations.normal / 1000, delay: 0.45 }}
              className="mt-8 flex flex-col sm:flex-row gap-3 justify-center lg:justify-start"
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
              <Button asChild variant="outline" size="lg" className="h-12 text-base font-medium border-white/10 hover:bg-white/5">
                <Link to="/login">Log in</Link>
              </Button>
            </motion.div>

            <motion.div
              initial={reducedMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: durations.normal / 1000, delay: 0.55 }}
              className="mt-8 flex items-center justify-center lg:justify-start gap-3 text-xs text-muted-foreground"
            >
              <div className="flex -space-x-2">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="w-7 h-7 rounded-full border border-white/10 bg-gradient-to-br from-primary/60 to-accent/60"
                  />
                ))}
              </div>
              <span>10,000+ listeners</span>
            </motion.div>
          </div>

          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: durations.slow / 1000, delay: 0.2 }}
            className="relative mx-auto w-full max-w-sm"
          >
            <div className="glass rounded-[36px] border border-white/10 p-5 shadow-2xl shadow-black/40">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <LogoMark size={24} />
                  <span className="text-xs font-medium">Jamify Live</span>
                </div>
                <span className="px-2 py-1 rounded-full bg-success/15 text-success font-medium">Live</span>
              </div>

              <div className="mt-5 rounded-2xl bg-surface-2/80 border border-white/10 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Now playing</p>
                <h3 className="text-lg font-semibold">Midnight Drive</h3>
                <p className="text-sm text-muted-foreground">The Night Moves</p>
                <div className="mt-3 h-2 rounded-full bg-white/10 overflow-hidden">
                  <div className="h-full w-2/3 gradient-bg" />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                {['Focus', 'Late Night', 'Warm'].map((label) => (
                  <div
                    key={label}
                    className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-center"
                  >
                    {label}
                  </div>
                ))}
              </div>

              <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                <span>Energy 72%</span>
                <span>Mood calibrated</span>
                <span>Learning</span>
              </div>
            </div>
            <div className="absolute -bottom-6 -right-4 w-24 h-24 rounded-full bg-primary/30 blur-2xl" />
          </motion.div>
        </div>
      </section>

      {/* Install hint (integrated) */}
      <InstallHint />

      {/* Footer */}
      <footer className="relative p-4 text-center space-y-2">
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <Link to="/privacy" className="hover:text-foreground transition-colors">
            Privacy
          </Link>
          <span>|</span>
          <Link to="/terms" className="hover:text-foreground transition-colors">
            Terms
          </Link>
        </div>
        <p className="text-xs text-muted-foreground">&copy; {new Date().getFullYear()} Jamify. All rights reserved.</p>
      </footer>
    </main>
  )
}

