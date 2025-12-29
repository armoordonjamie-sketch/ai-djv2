"use client"

import { useEffect, useState, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Check, X, AlertCircle, Sparkles, Info } from "lucide-react"
import { cn } from "@/lib/utils"

export interface ToastData {
  id: string
  type: "success" | "error" | "info" | "training"
  message: string
  description?: string
  duration?: number
}

interface StatusToastProps {
  toast: ToastData
  onDismiss: (id: string) => void
}

function StatusToastItem({ toast, onDismiss }: StatusToastProps) {
  const { id, type, message, description, duration = 3000 } = toast

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onDismiss(id)
      }, duration)
      return () => clearTimeout(timer)
    }
  }, [id, duration, onDismiss])

  const getIcon = () => {
    switch (type) {
      case "success":
        return <Check className="w-4 h-4 text-success" />
      case "error":
        return <AlertCircle className="w-4 h-4 text-destructive" />
      case "training":
        return <Sparkles className="w-4 h-4 text-warning" />
      default:
        return <Info className="w-4 h-4 text-info" />
    }
  }

  const getStyles = () => {
    switch (type) {
      case "success":
        return "bg-success/10 border-success/30"
      case "error":
        return "bg-destructive/10 border-destructive/30"
      case "training":
        return "bg-warning/10 border-warning/30"
      default:
        return "bg-info/10 border-info/30"
    }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.95 }}
      transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
      className={cn(
        "flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm",
        "pointer-events-auto",
        getStyles(),
      )}
    >
      <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">{message}</p>
        {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
      </div>
      <button
        onClick={() => onDismiss(id)}
        className="flex-shrink-0 p-1 rounded-md hover:bg-foreground/10 transition-colors"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5 text-muted-foreground" />
      </button>
    </motion.div>
  )
}

interface ToastContainerProps {
  toasts: ToastData[]
  onDismiss: (id: string) => void
  position?: "top" | "bottom"
}

export function ToastContainer({ toasts, onDismiss, position = "top" }: ToastContainerProps) {
  return (
    <div
      className={cn(
        "fixed left-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none",
        position === "top" ? "top-4 safe-area-inset-top" : "bottom-4 safe-area-inset-bottom",
      )}
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <StatusToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  )
}

// Hook for managing toasts
export function useToast() {
  const [toasts, setToasts] = useState<ToastData[]>([])

  const addToast = useCallback((toast: Omit<ToastData, "id">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToasts((prev) => [...prev, { ...toast, id }])
    return id
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const clearAll = useCallback(() => {
    setToasts([])
  }, [])

  // Convenience methods
  const success = useCallback(
    (message: string, description?: string) => {
      return addToast({ type: "success", message, description })
    },
    [addToast],
  )

  const error = useCallback(
    (message: string, description?: string) => {
      return addToast({ type: "error", message, description, duration: 5000 })
    },
    [addToast],
  )

  const info = useCallback(
    (message: string, description?: string) => {
      return addToast({ type: "info", message, description })
    },
    [addToast],
  )

  const training = useCallback(
    (message: string, description?: string) => {
      return addToast({ type: "training", message, description, duration: 2500 })
    },
    [addToast],
  )

  return {
    toasts,
    addToast,
    dismissToast,
    clearAll,
    success,
    error,
    info,
    training,
  }
}
