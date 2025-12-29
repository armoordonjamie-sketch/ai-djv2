import type React from "react"
import Link from "next/link"
import { ArrowLeft, Music2 } from "lucide-react"

interface LegalLayoutProps {
  children: React.ReactNode
  title: string
  lastUpdated: string
}

export function LegalLayout({ children, title, lastUpdated }: LegalLayoutProps) {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-border">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded-lg gradient-bg flex items-center justify-center">
              <Music2 className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg group-hover:text-primary transition-colors">Jamify</span>
          </Link>

          <Link
            href="/"
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to home
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">{title}</h1>
          <p className="text-muted-foreground">Last updated: {lastUpdated}</p>
        </div>

        <div className="prose prose-invert prose-purple max-w-none">{children}</div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-8">
        <div className="max-w-4xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
          <p>&copy; {new Date().getFullYear()} Jamify. All rights reserved.</p>
          <nav className="flex items-center gap-6">
            <Link href="/terms" className="hover:text-foreground transition-colors">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-foreground transition-colors">
              Privacy
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
