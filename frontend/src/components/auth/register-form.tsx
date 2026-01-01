import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { motion } from "framer-motion"
import { Eye, EyeOff, Loader2, Mail, Lock, User, CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { AuthField } from "@/components/auth/AuthField"
import { useAuth } from "@/providers/AuthProvider"
import { durations, easings } from "@/lib/motion"
import { cn } from "@/lib/utils"

const registerSchema = z
  .object({
    displayName: z.string().optional(),
    email: z.string().email("Please enter a valid email address"),
    password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
      .regex(/[a-z]/, "Password must contain at least one lowercase letter")
      .regex(/[0-9]/, "Password must contain at least one number"),
    confirmPassword: z.string(),
    acceptTerms: z.boolean().refine((val) => val === true, "You must accept the Terms and Privacy Policy"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  })

type RegisterFormData = z.infer<typeof registerSchema>

export function RegisterForm() {
  const navigate = useNavigate()
  const { register: registerUser } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    mode: "onBlur",
    defaultValues: {
      displayName: "",
      email: "",
      password: "",
      confirmPassword: "",
      acceptTerms: false,
    },
  })

  const password = watch("password")

  const onSubmit = async (data: RegisterFormData) => {
    setServerError(null)

    try {
      const result = await registerUser(data.email, data.password, data.displayName || undefined)

      if (result.success) {
        // Navigate to Spotify connect page first, then voice onboarding
        navigate("/connect-spotify")
      } else {
        setServerError(result.error || "Registration failed")
      }
    } catch {
      setServerError("Something went wrong. Please try again.")
    }
  }

  // Password strength indicator
  const getPasswordStrength = (pwd: string): { label: string; color: string; progress: number } => {
    if (!pwd) return { label: "", color: "", progress: 0 }
    let strength = 0
    if (pwd.length >= 8) strength++
    if (/[A-Z]/.test(pwd)) strength++
    if (/[a-z]/.test(pwd)) strength++
    if (/[0-9]/.test(pwd)) strength++
    if (/[^A-Za-z0-9]/.test(pwd)) strength++

    if (strength <= 2) return { label: "Weak", color: "bg-destructive", progress: 33 }
    if (strength <= 3) return { label: "Fair", color: "bg-warning", progress: 66 }
    return { label: "Strong", color: "bg-success", progress: 100 }
  }

  const passwordStrength = getPasswordStrength(password)

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {/* Server error message */}
      {serverError && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: durations.fast / 1000, ease: easings.out }}
          className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
        >
          {serverError}
        </motion.div>
      )}

      {/* Display name field (optional) */}
      <AuthField
        id="displayName"
        label="Display name"
        type="text"
        placeholder="How should we call you?"
        autoComplete="name"
        icon={<User className="w-5 h-5" />}
        error={errors.displayName?.message}
        disabled={isSubmitting}
        inputRef={register("displayName").ref}
        {...register("displayName")}
      />

      {/* Email field */}
      <AuthField
        id="email"
        label="Email"
        type="email"
        placeholder="you@example.com"
        autoComplete="email"
        inputMode="email"
        icon={<Mail className="w-5 h-5" />}
        error={errors.email?.message}
        disabled={isSubmitting}
        required
        inputRef={register("email").ref}
        {...register("email")}
      />

      {/* Password field */}
      <div className="space-y-2">
        <AuthField
          id="password"
          label="Password"
          type={showPassword ? "text" : "password"}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          icon={<Lock className="w-5 h-5" />}
          error={errors.password?.message}
          disabled={isSubmitting}
          required
          rightElement={
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="text-muted-foreground hover:text-foreground transition-colors p-1"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
            </button>
          }
          inputRef={register("password").ref}
          {...register("password")}
        />

        {/* Password strength indicator */}
        {password && (
          <div className="space-y-1">
            <div className="h-1 bg-muted rounded-full overflow-hidden">
              <motion.div
                className={cn("h-full", passwordStrength.color)}
                initial={{ width: 0 }}
                animate={{ width: `${passwordStrength.progress}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
            <p className="text-xs text-muted-foreground">Password strength: {passwordStrength.label}</p>
          </div>
        )}
      </div>

      {/* Confirm password field */}
      <AuthField
        id="confirmPassword"
        label="Confirm password"
        type={showPassword ? "text" : "password"}
        placeholder="Repeat your password"
        autoComplete="new-password"
        icon={<Lock className="w-5 h-5" />}
        error={errors.confirmPassword?.message}
        disabled={isSubmitting}
        required
        inputRef={register("confirmPassword").ref}
        {...register("confirmPassword")}
      />

      {/* Terms checkbox */}
      <div className="space-y-2">
        <div className="flex items-start gap-3">
          <Checkbox
            id="terms"
            disabled={isSubmitting}
            className="mt-1"
            onCheckedChange={(checked) => {
              register("acceptTerms").onChange({ target: { value: checked, name: "acceptTerms" } })
            }}
          />
          <Label htmlFor="terms" className="text-sm font-normal cursor-pointer leading-relaxed">
            I agree to the{" "}
            <Link to="/terms" className="text-primary hover:underline" target="_blank">
              Terms of Service
            </Link>{" "}
            and{" "}
            <Link to="/privacy" className="text-primary hover:underline" target="_blank">
              Privacy Policy
            </Link>
          </Label>
        </div>
        {/* Fixed-height error container */}
        <div className="min-h-[20px]">
          {errors.acceptTerms && <p className="text-sm text-destructive">{errors.acceptTerms.message}</p>}
        </div>
      </div>

      {/* Submit button */}
      <Button
        type="submit"
        className="w-full h-12 gradient-bg text-white hover:opacity-90 transition-opacity text-base font-medium"
        disabled={isSubmitting}
      >
        {isSubmitting ? (
          <>
            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
            Creating account...
          </>
        ) : (
          <>
            <CheckCircle2 className="w-5 h-5 mr-2" />
            Create account
          </>
        )}
      </Button>

      {/* Sign in link */}
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="text-primary hover:underline font-medium">
          Sign in
        </Link>
      </p>
    </form>
  )
}
