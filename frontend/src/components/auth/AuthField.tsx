import type React from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

interface AuthFieldProps {
  id: string
  label: string
  type?: "text" | "email" | "password" | "tel"
  placeholder?: string
  autoComplete?: string
  icon?: React.ReactNode
  error?: string
  disabled?: boolean
  required?: boolean
  inputMode?: "text" | "email" | "tel" | "url" | "numeric"
  rightElement?: React.ReactNode
  value?: string
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void
  name?: string
  inputRef?: React.Ref<HTMLInputElement>
}

export function AuthField({
  id,
  label,
  type = "text",
  placeholder,
  autoComplete,
  icon,
  error,
  disabled = false,
  required = false,
  inputMode,
  rightElement,
  value,
  onChange,
  onBlur,
  name,
  inputRef,
}: AuthFieldProps) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id} className={cn(required && "after:content-['*'] after:ml-0.5 after:text-destructive")}>
        {label}
      </Label>
      <div className="relative">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
            {icon}
          </div>
        )}
        <Input
          ref={inputRef}
          id={id}
          name={name || id}
          type={type}
          placeholder={placeholder}
          autoComplete={autoComplete}
          inputMode={inputMode}
          disabled={disabled}
          required={required}
          aria-invalid={error ? "true" : "false"}
          aria-describedby={error ? `${id}-error` : undefined}
          className={cn(
            "h-12 bg-input border-border text-base", // text-base = 16px to prevent iOS zoom
            icon && "pl-10",
            rightElement && "pr-10",
            error && "border-destructive focus-visible:border-destructive"
          )}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
        />
        {rightElement && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            {rightElement}
          </div>
        )}
      </div>
      {/* Fixed-height error container to prevent layout shift */}
      <div className="min-h-[20px]" aria-live="polite" aria-atomic="true">
        {error && (
          <p id={`${id}-error`} className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}

