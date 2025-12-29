import { useState } from "react"
import { Link, useNavigate, useLocation } from "react-router-dom"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { motion } from "framer-motion"
import { Eye, EyeOff, Loader2, Mail, Lock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AuthField } from "@/components/auth/AuthField"
import { useAuth } from "@/providers/AuthProvider"
import { durations, easings } from "@/lib/motion"

const loginSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
  password: z.string().min(1, "Password is required"),
})

type LoginFormData = z.infer<typeof loginSchema>

export function LoginForm() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    mode: "onBlur",
  })

  // Get redirect path from location state
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/player"

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null)

    try {
      const result = await login(data.email, data.password)

      if (result.success) {
        navigate(from, { replace: true })
      } else {
        setServerError(result.error || "Login failed")
      }
    } catch {
      setServerError("Something went wrong. Please try again.")
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
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
        inputRef={register("email").ref}
        {...register("email")}
      />

      {/* Password field */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Password</span>
          <Link to="/forgot-password" className="text-xs text-primary hover:underline">
            Forgot password?
          </Link>
        </div>
        <AuthField
          id="password"
          label=""
          type={showPassword ? "text" : "password"}
          placeholder="Enter your password"
          autoComplete="current-password"
          icon={<Lock className="w-5 h-5" />}
          error={errors.password?.message}
          disabled={isSubmitting}
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
            Signing in...
          </>
        ) : (
          "Sign in"
        )}
      </Button>

      {/* Sign up link */}
      <p className="text-center text-sm text-muted-foreground">
        Don't have an account?{" "}
        <Link to="/register" className="text-primary hover:underline font-medium">
          Create account
        </Link>
      </p>

      {/* Demo credentials hint */}
      <p className="text-center text-xs text-muted-foreground/70">Demo: demo@jamify.app / demo123</p>
    </form>
  )
}
