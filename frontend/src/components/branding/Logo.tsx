"use client"

import { useId } from "react"
import { cn } from "@/lib/utils"

interface LogoMarkProps {
  size?: number
  className?: string
}

interface LogoLockupProps extends LogoMarkProps {
  textClassName?: string
}

export function LogoMark({ size = 32, className }: LogoMarkProps) {
  const gradientId = useId()

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={cn("text-white", className)}
      role="img"
      aria-label="Jamify"
    >
      <defs>
        <linearGradient id={`${gradientId}-jamify`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--gradient-start)" />
          <stop offset="100%" stopColor="var(--gradient-end)" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="28" fill={`url(#${gradientId}-jamify)`} opacity="0.95" />
      <circle cx="32" cy="32" r="14" fill="rgba(0, 0, 0, 0.25)" />
      <path
        d="M18 36c6 6 22 6 28 0"
        stroke="rgba(255, 255, 255, 0.75)"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M22 26c6-5 14-5 20 0"
        stroke="rgba(255, 255, 255, 0.5)"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="32" cy="32" r="3.5" fill="rgba(255, 255, 255, 0.9)" />
    </svg>
  )
}

export function LogoLockup({ size = 28, className, textClassName }: LogoLockupProps) {
  return (
    <div className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark size={size} />
      <span className={cn("text-base font-semibold tracking-tight", textClassName)}>Jamify</span>
    </div>
  )
}
