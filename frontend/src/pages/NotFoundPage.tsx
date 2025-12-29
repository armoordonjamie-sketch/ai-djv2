import { Link } from "react-router-dom"
import { motion } from "framer-motion"
import { Music2, Home } from "lucide-react"
import { Button } from "@/components/ui/button"

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      {/* Background glow */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-96 h-96 bg-[#8b5cf6]/20 rounded-full blur-3xl" />
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center max-w-md">
        {/* Icon */}
        <div className="w-20 h-20 rounded-2xl gradient-bg flex items-center justify-center mx-auto mb-8 opacity-50">
          <Music2 className="w-10 h-10 text-white" />
        </div>

        {/* 404 text */}
        <h1 className="text-8xl font-bold gradient-text mb-4">404</h1>
        <h2 className="text-2xl font-semibold mb-4">Page not found</h2>
        <p className="text-muted-foreground mb-8">
          Looks like this track got lost in the mix. Let's get you back to the music.
        </p>

        {/* CTA */}
        <Button asChild className="gradient-bg text-white hover:opacity-90 transition-opacity">
          <Link to="/">
            <Home className="w-5 h-5 mr-2" />
            Back to home
          </Link>
        </Button>
      </motion.div>
    </div>
  )
}
