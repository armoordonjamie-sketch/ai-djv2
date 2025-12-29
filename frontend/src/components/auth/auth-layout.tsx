import type React from "react"
import { Link } from "react-router-dom"
import { motion } from "framer-motion"
import { Music2 } from "lucide-react"

interface AuthLayoutProps {
  children: React.ReactNode
  title: string
  subtitle: string
}

export function AuthLayout({ children, title, subtitle }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Animated background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-[#8b5cf6]/10 via-transparent to-[#ec4899]/10" />
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
      </div>

      {/* Header with logo */}
      <header className="p-6">
        <Link to="/" className="inline-flex items-center gap-2 group">
          <div className="w-10 h-10 rounded-xl gradient-bg flex items-center justify-center">
            <Music2 className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-xl group-hover:text-primary transition-colors">Jamify</span>
        </Link>
      </header>

      {/* Main content */}
      <main className="flex-1 flex items-center justify-center px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-md"
        >
          {/* Card */}
          <div className="glass rounded-3xl p-8 border border-border relative">
            {/* Decorative glow */}
            <div className="absolute -inset-1 -z-10 bg-gradient-to-r from-[#8b5cf6]/20 to-[#ec4899]/20 blur-xl rounded-3xl" />

            {/* Title */}
            <div className="text-center mb-8">
              <h1 className="text-2xl font-bold mb-2">{title}</h1>
              <p className="text-muted-foreground">{subtitle}</p>
            </div>

            {children}
          </div>
        </motion.div>
      </main>

      {/* Footer */}
      <footer className="p-6 text-center">
        <p className="text-sm text-muted-foreground">&copy; {new Date().getFullYear()} Jamify. All rights reserved.</p>
      </footer>
    </div>
  )
}
