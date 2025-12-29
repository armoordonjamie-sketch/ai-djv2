import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ThemeProvider } from '@/components/theme-provider'
import { AuthProvider } from '@/providers/AuthProvider'
import { PlayerProvider } from '@/providers/PlayerProvider'
import { AppShell } from '@/components/AppShell'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Toaster } from '@/components/ui/sonner'
import { durations, easings, prefersReducedMotion } from '@/lib/motion'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import VoiceOnboardingPage from './pages/VoiceOnboardingPage'
import MoodCreationPage from './pages/MoodCreationPage'
import PlayerPage from './pages/PlayerPage'
import MoodsPage from './pages/MoodsPage'
import HistoryPage from './pages/HistoryPage'
import SettingsPage from './pages/SettingsPage'
import PrivacyPage from './pages/PrivacyPage'
import TermsPage from './pages/TermsPage'
import NotFoundPage from './pages/NotFoundPage'

// Page transition wrapper
function PageTransition({ children }: { children: React.ReactNode }) {
  const reducedMotion = prefersReducedMotion()
  
  if (reducedMotion) {
    return <>{children}</>
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{
        duration: durations.fast / 1000,
        ease: easings.out,
      }}
    >
      {children}
    </motion.div>
  )
}

function AppContent() {
  const location = useLocation()
  
  // Only animate auth pages (/, /login, /register)
  const isAuthPage = ['/', '/login', '/register'].includes(location.pathname)

  return (
    <>
      <div className="font-sans antialiased min-h-screen">
        {isAuthPage ? (
          // Animated auth pages
          <AnimatePresence mode="wait" initial={false}>
            <Routes location={location} key={location.pathname}>
              <Route
                path="/"
                element={
                  <PageTransition>
                    <LandingPage />
                  </PageTransition>
                }
              />
              <Route
                path="/login"
                element={
                  <PageTransition>
                    <LoginPage />
                  </PageTransition>
                }
              />
              <Route
                path="/register"
                element={
                  <PageTransition>
                    <RegisterPage />
                  </PageTransition>
                }
              />
            </Routes>
          </AnimatePresence>
        ) : (
          // Non-animated app routes - PlayerProvider persists across navigation
          <Routes>
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />

            {/* Voice onboarding (protected) */}
            <Route
              path="/onboarding"
              element={
                <ProtectedRoute>
                  <VoiceOnboardingPage />
                </ProtectedRoute>
              }
            />

            {/* Mood creation animation (protected) */}
            <Route
              path="/creating-moods"
              element={
                <ProtectedRoute requireOnboarding>
                  <MoodCreationPage />
                </ProtectedRoute>
              }
            />

            {/* App routes with PlayerProvider - persists across /player, /moods, /history, /settings */}
            <Route
              element={
                <ProtectedRoute requireOnboarding>
                  <PlayerProvider>
                    <AppShell />
                  </PlayerProvider>
                </ProtectedRoute>
              }
            >
              <Route path="/player" element={<PlayerPage />} />
              <Route path="/moods" element={<MoodsPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        )}
      </div>
      <Toaster position="top-center" />
    </>
  )
}

function App() {
  return (
    <ThemeProvider defaultTheme="dark" attribute="class">
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
