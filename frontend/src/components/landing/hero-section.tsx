import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Play, Sparkles } from "lucide-react"
import { Link } from "react-router-dom"

export function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden px-4 py-20">
      {/* Animated gradient background */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-[#8b5cf6]/20 via-transparent to-transparent" />
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
      </div>

      <div className="max-w-4xl mx-auto text-center">
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-border bg-card/50 backdrop-blur-sm mb-8"
        >
          <Sparkles className="w-4 h-4 text-primary" />
          <span className="text-sm text-muted-foreground">AI-Powered Music Experience</span>
        </motion.div>

        {/* Main headline */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight mb-6 text-balance"
        >
          Your AI DJ, <span className="gradient-text">tuned to your mood</span>
        </motion.h1>

        {/* Subheadline */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 text-pretty"
        >
          Jamify learns what you love and creates the perfect soundtrack for every moment. Like having a personal DJ who
          knows exactly what you want to hear.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <Button
            asChild
            size="lg"
            className="gradient-bg text-white hover:opacity-90 transition-opacity min-w-[180px] h-12 text-base font-medium"
          >
            <Link to="/register">
              <Play className="w-5 h-5 mr-2" />
              Start listening
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            size="lg"
            className="min-w-[180px] h-12 text-base font-medium border-border hover:bg-card bg-transparent"
          >
            <Link to="/login">Log in</Link>
          </Button>
        </motion.div>

        {/* Social proof */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="mt-16 flex flex-col sm:flex-row items-center justify-center gap-6 text-sm text-muted-foreground"
        >
          <div className="flex -space-x-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="w-8 h-8 rounded-full border-2 border-background bg-gradient-to-br from-[#8b5cf6] to-[#ec4899]"
              />
            ))}
          </div>
          <span>Join 10,000+ listeners already vibing</span>
        </motion.div>
      </div>
    </section>
  )
}
