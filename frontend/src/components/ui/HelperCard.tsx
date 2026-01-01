"use client"

import type React from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface HelperCardProps {
  title: string
  description?: string
  eyebrow?: string
  icon?: React.ReactNode
  actionLabel?: string
  onAction?: () => void
  onDismiss?: () => void
  className?: string
  children?: React.ReactNode
}

export function HelperCard({
  title,
  description,
  eyebrow,
  icon,
  actionLabel,
  onAction,
  onDismiss,
  className,
  children,
}: HelperCardProps) {
  return (
    <div className={cn("relative overflow-hidden rounded-3xl glass-subtle border border-white/10 px-4 py-4", className)}>
      <div className="absolute -top-10 right-0 h-36 w-36 rounded-full bg-primary/10 blur-2xl" />
      <div className="relative space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            {icon && (
              <div className="w-10 h-10 rounded-2xl bg-primary/15 flex items-center justify-center">
                {icon}
              </div>
            )}
            <div>
              {eyebrow && <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{eyebrow}</p>}
              <h3 className="text-sm font-semibold">{title}</h3>
            </div>
          </div>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="w-8 h-8 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
              aria-label="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {description && <p className="text-sm text-muted-foreground">{description}</p>}

        {children}

        {actionLabel && onAction && (
          <Button onClick={onAction} className="w-full gradient-bg touch-target">
            {actionLabel}
          </Button>
        )}
      </div>
    </div>
  )
}
