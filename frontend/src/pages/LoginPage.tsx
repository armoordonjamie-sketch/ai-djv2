import { AuthShell } from "@/components/auth/AuthShell"
import { LoginForm } from "@/components/auth/login-form"

export default function LoginPage() {
  return (
    <AuthShell title="Welcome back" subtitle="Sign in to continue your music journey">
      <LoginForm />
    </AuthShell>
  )
}
