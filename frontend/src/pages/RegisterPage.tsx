import { AuthShell } from "@/components/auth/AuthShell"
import { RegisterForm } from "@/components/auth/register-form"

export default function RegisterPage() {
  return (
    <AuthShell title="Create your account" subtitle="Start your personalized music experience">
      <RegisterForm />
    </AuthShell>
  )
}
