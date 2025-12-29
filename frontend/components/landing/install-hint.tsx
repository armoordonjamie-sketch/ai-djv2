"use client"

import { motion } from "framer-motion"
import { Share, PlusSquare, Smartphone } from "lucide-react"

export function InstallHint() {
  return (
    <section className="py-24 px-4 bg-card/50">
      <div className="max-w-3xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center mx-auto mb-6">
            <Smartphone className="w-8 h-8 text-white" />
          </div>

          <h2 className="text-3xl sm:text-4xl font-bold mb-4">Install on your device</h2>
          <p className="text-muted-foreground text-lg mb-10">
            Add Jamify to your home screen for a native app experience
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="glass rounded-2xl p-8 border border-border text-left max-w-md mx-auto"
        >
          <p className="text-sm font-medium text-muted-foreground mb-6">On iOS Safari:</p>

          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
                <Share className="w-5 h-5 text-primary" />
              </div>
              <p className="text-sm">
                Tap the <strong>Share</strong> button in the toolbar
              </p>
            </div>

            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
                <PlusSquare className="w-5 h-5 text-primary" />
              </div>
              <p className="text-sm">
                Scroll down and tap <strong>Add to Home Screen</strong>
              </p>
            </div>

            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
                <span className="text-primary font-bold">3</span>
              </div>
              <p className="text-sm">
                Tap <strong>Add</strong> to confirm
              </p>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
