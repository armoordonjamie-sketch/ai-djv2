"use client"

import { motion } from "framer-motion"
import { Music2, SkipBack, SkipForward, Play, Heart } from "lucide-react"

export function DeviceMockup() {
  return (
    <section className="py-24 px-4">
      <div className="max-w-6xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mb-12"
        >
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">
            Take your music <span className="gradient-text">everywhere</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-xl mx-auto">
            Install Jamify on your phone for a native app experience with offline support.
          </p>
        </motion.div>

        {/* Phone mockup */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="relative inline-block"
        >
          {/* Phone frame */}
          <div className="relative w-[280px] h-[580px] bg-[#1a1a24] rounded-[3rem] p-3 border-4 border-[#2a2a3a] shadow-2xl">
            {/* Notch */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-6 bg-[#1a1a24] rounded-b-2xl" />

            {/* Screen content */}
            <div className="w-full h-full bg-background rounded-[2.5rem] overflow-hidden flex flex-col">
              {/* Status bar */}
              <div className="flex justify-between items-center px-6 pt-8 pb-2 text-xs text-muted-foreground">
                <span>9:41</span>
                <div className="flex gap-1">
                  <div className="w-4 h-2 bg-muted-foreground rounded-sm" />
                </div>
              </div>

              {/* App content */}
              <div className="flex-1 px-4 pb-4 flex flex-col">
                {/* Album art */}
                <div className="aspect-square rounded-2xl bg-gradient-to-br from-[#8b5cf6] via-[#a855f7] to-[#ec4899] mb-4 flex items-center justify-center glow">
                  <Music2 className="w-16 h-16 text-white/40" />
                </div>

                {/* Track info */}
                <div className="text-center mb-4">
                  <p className="font-semibold">Ocean Waves</p>
                  <p className="text-sm text-muted-foreground">Ambient Collective</p>
                </div>

                {/* Progress */}
                <div className="mb-4">
                  <div className="h-1 bg-muted rounded-full overflow-hidden">
                    <div className="h-full w-1/3 gradient-bg" />
                  </div>
                </div>

                {/* Controls */}
                <div className="flex items-center justify-center gap-6">
                  <SkipBack className="w-6 h-6 text-muted-foreground" />
                  <div className="w-14 h-14 rounded-full gradient-bg flex items-center justify-center">
                    <Play className="w-6 h-6 text-white fill-white ml-1" />
                  </div>
                  <SkipForward className="w-6 h-6 text-muted-foreground" />
                </div>

                {/* Bottom nav placeholder */}
                <div className="mt-auto pt-4 flex justify-around">
                  <Music2 className="w-5 h-5 text-primary" />
                  <Heart className="w-5 h-5 text-muted-foreground" />
                  <div className="w-5 h-5 rounded-full bg-muted-foreground" />
                </div>
              </div>
            </div>
          </div>

          {/* Glow effect behind phone */}
          <div className="absolute inset-0 -z-10 bg-gradient-to-b from-[#8b5cf6]/30 to-[#ec4899]/30 blur-3xl scale-150 opacity-50" />
        </motion.div>
      </div>
    </section>
  )
}
