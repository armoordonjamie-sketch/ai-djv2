"use client"

import { motion } from "framer-motion"
import { mockMoods } from "@/lib/api"

export function MoodPersonalization() {
  return (
    <section className="py-24 px-4 overflow-hidden">
      <div className="max-w-6xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Text content */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <h2 className="text-3xl sm:text-4xl font-bold mb-6">
              Music that matches <span className="gradient-text">your vibe</span>
            </h2>
            <p className="text-lg text-muted-foreground mb-8">
              Create custom moods or choose from our presets. Your AI DJ adapts in real-time to deliver the perfect
              soundtrack for every moment of your day.
            </p>

            <div className="space-y-4">
              {["Unlimited custom moods", "Real-time adaptation", "Cross-session memory"].map((feature, index) => (
                <motion.div
                  key={feature}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.3, delay: 0.2 + index * 0.1 }}
                  className="flex items-center gap-3"
                >
                  <div className="w-5 h-5 rounded-full gradient-bg flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <span className="text-foreground">{feature}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Mood pills visualization */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="relative"
          >
            <div className="glass rounded-3xl p-8 border border-border">
              <p className="text-sm text-muted-foreground mb-6">Active moods</p>

              <div className="flex flex-wrap gap-3">
                {mockMoods.map((mood, index) => (
                  <motion.div
                    key={mood.id}
                    initial={{ opacity: 0, scale: 0.8 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.3, delay: 0.1 + index * 0.05 }}
                    whileHover={{ scale: 1.05 }}
                    className={`
                      flex items-center gap-2 px-4 py-2 rounded-full border cursor-pointer transition-all
                      ${
                        mood.isActive
                          ? "border-primary bg-primary/20 text-foreground"
                          : "border-border bg-card hover:border-primary/50"
                      }
                    `}
                  >
                    <span>{mood.emoji}</span>
                    <span className="text-sm font-medium">{mood.name}</span>
                  </motion.div>
                ))}
              </div>

              {/* Add mood button */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="mt-6 w-full py-3 rounded-xl border border-dashed border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors"
              >
                + Create custom mood
              </motion.button>
            </div>

            {/* Decorative glow */}
            <div className="absolute -inset-4 -z-10 bg-gradient-to-r from-[#8b5cf6]/20 to-[#ec4899]/20 blur-3xl rounded-3xl" />
          </motion.div>
        </div>
      </div>
    </section>
  )
}
