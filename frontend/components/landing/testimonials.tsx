"use client"

import { motion } from "framer-motion"
import { Star } from "lucide-react"

const testimonials = [
  {
    name: "Alex Chen",
    role: "Music Producer",
    content:
      "Jamify gets me. It's like having a friend who knows my entire music library and always picks the perfect track.",
    rating: 5,
  },
  {
    name: "Sarah Kim",
    role: "Remote Worker",
    content: "The Focus mood is a game-changer for deep work. I've never been more productive.",
    rating: 5,
  },
  {
    name: "Marcus Johnson",
    role: "Fitness Coach",
    content: "From warm-up to cool-down, Jamify adapts to every phase of my workout. Incredible AI.",
    rating: 5,
  },
]

export function Testimonials() {
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
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">
            Loved by <span className="gradient-text">music lovers</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-xl mx-auto">
            See what our community is saying about Jamify
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6">
          {testimonials.map((testimonial, index) => (
            <motion.div
              key={testimonial.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="glass rounded-2xl p-6 border border-border"
            >
              {/* Stars */}
              <div className="flex gap-1 mb-4">
                {Array.from({ length: testimonial.rating }).map((_, i) => (
                  <Star key={i} className="w-4 h-4 fill-primary text-primary" />
                ))}
              </div>

              {/* Content */}
              <p className="text-foreground mb-6 text-pretty">"{testimonial.content}"</p>

              {/* Author */}
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full gradient-bg" />
                <div>
                  <p className="font-medium text-sm">{testimonial.name}</p>
                  <p className="text-xs text-muted-foreground">{testimonial.role}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
