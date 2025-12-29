import type React from "react"
import { cn } from "@/lib/utils"

interface SkeletonProps {
  className?: string
  variant?: "text" | "circular" | "rectangular" | "rounded"
  width?: string | number
  height?: string | number
  lines?: number
  style?: React.CSSProperties
}

export function Skeleton({ className, variant = "rectangular", width, height, lines = 1, style: customStyle }: SkeletonProps) {
  const baseStyles = "skeleton"

  const variantStyles = {
    text: "h-4 rounded",
    circular: "rounded-full",
    rectangular: "rounded-none",
    rounded: "rounded-lg",
  }

  const style: React.CSSProperties = {
    width: width ?? (variant === "circular" ? height : "100%"),
    height: height ?? (variant === "text" ? undefined : "100%"),
    ...customStyle,
  }

  if (variant === "text" && lines > 1) {
    return (
      <div className={cn("flex flex-col gap-2", className)}>
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className={cn(baseStyles, variantStyles.text)}
            style={{
              ...style,
              width: i === lines - 1 ? "75%" : style.width,
            }}
          />
        ))}
      </div>
    )
  }

  return <div className={cn(baseStyles, variantStyles[variant], className)} style={style} />
}

// Preset skeletons for common use cases
export function SkeletonTrack({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <Skeleton variant="rounded" width={48} height={48} />
      <div className="flex-1 space-y-2">
        <Skeleton variant="text" width="60%" height={16} />
        <Skeleton variant="text" width="40%" height={14} />
      </div>
    </div>
  )
}

export function SkeletonPlayer({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col items-center gap-6", className)}>
      <Skeleton variant="rounded" width={280} height={280} className="rounded-2xl" />
      <div className="w-full max-w-xs space-y-2 text-center">
        <Skeleton variant="text" width="70%" height={24} className="mx-auto" />
        <Skeleton variant="text" width="50%" height={18} className="mx-auto" />
      </div>
      <div className="flex items-center gap-8">
        <Skeleton variant="circular" width={40} height={40} />
        <Skeleton variant="circular" width={56} height={56} />
        <Skeleton variant="circular" width={40} height={40} />
      </div>
    </div>
  )
}

export function SkeletonMoodCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl overflow-hidden", className)}>
      <Skeleton variant="rectangular" height={120} />
      <div className="p-4 space-y-2 bg-surface-2">
        <Skeleton variant="text" width="60%" />
        <Skeleton variant="text" width="40%" />
      </div>
    </div>
  )
}
