"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuth } from "@/providers/AuthProvider"

const ONBOARDING_COMPLETE_KEY = "jamify_onboarding_complete"

export function useFirstRunHint(key: string) {
  const { isOnboarded } = useAuth()
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (!isOnboarded || typeof window === "undefined") return

    const hasCompletedOnboarding = window.localStorage.getItem(ONBOARDING_COMPLETE_KEY) === "true"
    if (!hasCompletedOnboarding) return

    const alreadySeen = window.localStorage.getItem(key) === "true"
    if (alreadySeen) return

    setIsVisible(true)
  }, [isOnboarded, key])

  const dismiss = useCallback(() => {
    setIsVisible(false)
    if (typeof window !== "undefined") {
      window.localStorage.setItem(key, "true")
    }
  }, [key])

  return { isVisible, dismiss }
}
