"use client"

import { motion } from "framer-motion"
import { ThumbsUp, ThumbsDown, Music } from "lucide-react"

export function TrainingSection() {
  return (
    <section className="py-24 px-4 bg-card/50">
      <div className="max-w-6xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Mock player UI */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="order-2 lg:order-1"
          >
            <div className="glass rounded-3xl p-6 border border-border max-w-sm mx-auto">
              {/* Album art placeholder */}
              <div className="aspect-square rounded-2xl bg-gradient-to-br from-[#8b5cf6] to-[#ec4899] mb-6 flex items-center justify-center">
                <Music className="w-24 h-24 text-white/30" />
              </div>

              {/* Track info */}
              <div className="text-center mb-6">
                <h4 className="font-semibold text-lg">Midnight Dreams</h4>
                <p className="text-muted-foreground">Neon Pulse</p>
              </div>

              {/* Progress bar */}
              <div className="mb-6">
                <div className="h-1 bg-muted rounded-full overflow-hidden">
                  <motion.div
                    className="h-full gradient-bg"
                    initial={{ width: "0%" }}
                    whileInView={{ width: "65%" }}
                    viewport={{ once: true }}
                    transition={{ duration: 1, delay: 0.3 }}
                  />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground mt-2">
                  <span>2:38</span>
                  <span>4:05</span>
                </div>
              </div>

              {/* Like/Dislike buttons */}
              <div className="flex items-center justify-center gap-6">
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="w-14 h-14 rounded-full border border-border flex items-center justify-center hover:border-destructive hover:text-destructive transition-colors"
                >
                  <ThumbsDown className="w-6 h-6" />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="w-14 h-14 rounded-full border border-primary bg-primary/20 flex items-center justify-center text-primary"
                >
                  <ThumbsUp className="w-6 h-6" />
                </motion.button>
              </div>
            </div>
          </motion.div>

          {/* Text content */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="order-1 lg:order-2"
          >
            <h2 className="text-3xl sm:text-4xl font-bold mb-6">
              Train your <span className="gradient-text">personal DJ</span>
            </h2>
            <p className="text-lg text-muted-foreground mb-8">
              Every like and dislike teaches your AI DJ more about your taste. The more you listen, the better your
              recommendations become.
            </p>

            <div className="space-y-6">
              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center shrink-0">
                  <ThumbsUp className="w-6 h-6 text-green-500" />
                </div>
                <div>
                  <h4 className="font-semibold mb-1">Like a track</h4>
                  <p className="text-muted-foreground text-sm">Get more similar vibes in your future streams</p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center shrink-0">
                  <ThumbsDown className="w-6 h-6 text-red-500" />
                </div>
                <div>
                  <h4 className="font-semibold mb-1">Dislike a track</h4>
                  <p className="text-muted-foreground text-sm">Skip to the next song and avoid similar sounds</p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
