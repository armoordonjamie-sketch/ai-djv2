import { Link } from "react-router-dom"
import { Music2 } from "lucide-react"

export function LandingFooter() {
  return (
    <footer className="py-12 px-4 border-t border-border">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg gradient-bg flex items-center justify-center">
              <Music2 className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg">Jamify</span>
          </Link>

          {/* Links */}
          <nav className="flex items-center gap-6 text-sm text-muted-foreground">
            <Link to="/terms" className="hover:text-foreground transition-colors">
              Terms of Service
            </Link>
            <Link to="/privacy" className="hover:text-foreground transition-colors">
              Privacy Policy
            </Link>
          </nav>

          {/* Copyright */}
          <p className="text-sm text-muted-foreground">
            &copy; {new Date().getFullYear()} Jamify. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  )
}
