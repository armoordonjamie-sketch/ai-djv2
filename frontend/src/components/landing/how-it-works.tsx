"use client"

import { motion } from "framer-motion"
import { Disc3, Sliders, Heart } from "lucide-react"

const steps = [
  {
    icon: Disc3,
    title: "Tell us your mood",
    description: "Select or create moods that match how you're feeling right now.",
  },
  {
    icon: Sliders,
    title: "AI generates your mix",
    description: "Our AI DJ crafts a personalized stream based on your preferences.",
  },
  {
    icon: Heart,
    title: "Train your taste",
    description: "Like or dislike tracks to make your experience even better.",
  },
]

export function HowItWorks() {
  return (
    <section className="py-24 px-4">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">How it works</h2>
          <p className="text-muted-foreground text-lg max-w-xl mx-auto">
            Three simple steps to your perfect soundtrack
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-8">
          {steps.map((step, index) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="relative"
            >
              <div className="glass rounded-2xl p-8 h-full border border-border">
                {/* Step number */}
                <div className="absolute -top-4 left-8 w-8 h-8 rounded-full gradient-bg flex items-center justify-center text-sm font-bold text-white">
                  {index + 1}
                </div>

                <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center mb-6 mt-2">
                  <step.icon className="w-7 h-7 text-primary" />
                </div>

                <h3 className="text-xl font-semibold mb-3">{step.title}</h3>
                <p className="text-muted-foreground">{step.description}</p>
              </div>

              {/* Connector line */}
              {index < steps.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-4 w-8 border-t border-dashed border-border" />
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
