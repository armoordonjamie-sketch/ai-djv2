import type React from "react"
import { Link } from "react-router-dom"
import { motion } from "framer-motion"
import { ArrowLeft, Music2 } from "lucide-react"
import { durations, easings, prefersReducedMotion } from "@/lib/motion"

interface AuthShellProps {
  children: React.ReactNode
  title?: string
  subtitle?: string
  showBackButton?: boolean
  backTo?: string
}

export function AuthShell({ children, title, subtitle, showBackButton = true, backTo = "/" }: AuthShellProps) {
  const reducedMotion = prefersReducedMotion()

  return (
    <div className="min-h-dvh flex flex-col bg-background pt-safe-top pb-safe-bottom">
      {/* Animated background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-[#8b5cf6]/10 via-transparent to-[#ec4899]/10" />
        {!reducedMotion && (
          <>
            <motion.div
              className="absolute top-1/3 left-1/4 w-96 h-96 bg-[#8b5cf6]/20 rounded-full blur-3xl"
              animate={{
                scale: [1, 1.2, 1],
                opacity: [0.2, 0.3, 0.2],
              }}
              transition={{
                duration: 10,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }}
            />
            <motion.div
              className="absolute bottom-1/3 right-1/4 w-96 h-96 bg-[#ec4899]/20 rounded-full blur-3xl"
              animate={{
                scale: [1.2, 1, 1.2],
                opacity: [0.2, 0.3, 0.2],
              }}
              transition={{
                duration: 10,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
                delay: 2,
              }}
            />
          </>
        )}
      </div>

      {/* Header with logo and back button */}
      <header className="p-4 flex items-center justify-between">
        {showBackButton ? (
          <Link
            to={backTo}
            className="inline-flex items-center gap-2 p-2 -ml-2 rounded-lg hover:bg-accent/50 transition-colors"
            aria-label="Go back"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
        ) : (
          <div />
        )}
        <Link to="/" className="inline-flex items-center gap-2 group">
          <div className="w-10 h-10 rounded-xl gradient-bg flex items-center justify-center">
            <Music2 className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-xl group-hover:text-primary transition-colors">Jamify</span>
        </Link>
        <div className="w-10" /> {/* Spacer for centering */}
      </header>

      {/* Main content - centered vertically on mobile */}
      <main className="flex-1 flex items-center justify-center px-4 py-8">
        <motion.div
          initial={reducedMotion ? false : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: durations.normal / 1000, ease: easings.out }}
          className="w-full max-w-md"
        >
          {/* Card */}
          <div className="glass rounded-3xl p-6 sm:p-8 border border-border relative">
            {/* Decorative glow */}
            <div className="absolute -inset-1 -z-10 bg-gradient-to-r from-[#8b5cf6]/20 to-[#ec4899]/20 blur-xl rounded-3xl" />

            {/* Title */}
            {(title || subtitle) && (
              <div className="text-center mb-6">
                {title && <h1 className="text-2xl font-bold mb-2">{title}</h1>}
                {subtitle && <p className="text-muted-foreground text-sm">{subtitle}</p>}
              </div>
            )}

            {children}
          </div>
        </motion.div>
      </main>

      {/* Footer */}
      <footer className="p-4 text-center">
        <p className="text-xs text-muted-foreground">&copy; {new Date().getFullYear()} Jamify. All rights reserved.</p>
      </footer>
    </div>
  )
}

