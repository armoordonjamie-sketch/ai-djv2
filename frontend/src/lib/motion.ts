// Motion utilities for consistent animations across the app

export const durations = {
  fast: 150,
  normal: 250,
  slow: 400,
  slower: 600,
} as const

export const easings = {
  default: [0.4, 0, 0.2, 1] as const,
  in: [0.4, 0, 1, 1] as const,
  out: [0, 0, 0.2, 1] as const,
  spring: [0.175, 0.885, 0.32, 1.275] as const,
}

// Framer Motion variants for common animations
export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: durations.normal / 1000, ease: easings.out },
}

export const slideUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: durations.normal / 1000, ease: easings.out },
}

export const slideDown = {
  initial: { opacity: 0, y: -8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 8 },
  transition: { duration: durations.normal / 1000, ease: easings.out },
}

export const scaleIn = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.95 },
  transition: { duration: durations.normal / 1000, ease: easings.spring },
}

export const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.05,
    },
  },
}

export const staggerItem = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: durations.normal / 1000, ease: easings.out },
}

// Check if user prefers reduced motion
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

// Get animation duration respecting reduced motion preference
export function getAnimationDuration(duration: keyof typeof durations): number {
  if (prefersReducedMotion()) return 0
  return durations[duration]
}

// Haptic feedback for mobile (if supported)
export function triggerHaptic(style: "light" | "medium" | "heavy" = "light") {
  if (typeof navigator === "undefined") return

  if ("vibrate" in navigator) {
    const patterns = {
      light: [10],
      medium: [20],
      heavy: [30],
    }
    navigator.vibrate(patterns[style])
  }
}
