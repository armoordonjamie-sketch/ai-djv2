import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronLeft, ChevronRight, Sparkles, Music2, Palette } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const GENRES = [
  'Pop', 'Rock', 'Hip-Hop', 'R&B', 'Electronic', 'Dance',
  'Indie', 'Alternative', 'Jazz', 'Classical', 'Country', 'Folk',
  'Metal', 'Punk', 'Soul', 'Funk', 'Reggae', 'Latin',
]

const MOOD_PRESETS = [
  { name: 'Chill', emoji: '🌊', color: '#06b6d4' },
  { name: 'Focus', emoji: '🎯', color: '#8b5cf6' },
  { name: 'Hype', emoji: '⚡', color: '#f59e0b' },
  { name: 'Party', emoji: '🎉', color: '#ec4899' },
]

const MOOD_COLORS = [
  '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#22c55e',
  '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#ec4899',
]

interface MoodDraft {
  name: string
  emoji: string
  color: string
}

export default function OnboardingPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [selectedGenres, setSelectedGenres] = useState<string[]>([])
  const [vibes, setVibes] = useState({ energy: 50, mood: 50, discovery: 50 })
  const [moods, setMoods] = useState<MoodDraft[]>([
    { name: 'Chill', emoji: '🌊', color: '#06b6d4' },
  ])
  const [newMoodName, setNewMoodName] = useState('')

  const toggleGenre = (genre: string) => {
    setSelectedGenres(prev =>
      prev.includes(genre)
        ? prev.filter(g => g !== genre)
        : [...prev, genre]
    )
  }

  const addMood = (preset?: { name: string; emoji: string; color: string }) => {
    if (preset) {
      if (!moods.find(m => m.name === preset.name)) {
        setMoods(prev => [...prev, preset])
      }
    } else if (newMoodName.trim()) {
      setMoods(prev => [...prev, {
        name: newMoodName.trim(),
        emoji: '🎵',
        color: MOOD_COLORS[moods.length % MOOD_COLORS.length],
      }])
      setNewMoodName('')
    }
  }

  const removeMood = (name: string) => {
    setMoods(prev => prev.filter(m => m.name !== name))
  }

  const nextStep = () => {
    if (step < 3) {
      setStep(step + 1)
    } else {
      // Complete onboarding
      navigate('/player')
    }
  }

  const prevStep = () => {
    if (step > 1) {
      setStep(step - 1)
    }
  }

  const canProceed = () => {
    if (step === 1) return selectedGenres.length >= 3
    if (step === 2) return true
    if (step === 3) return moods.length >= 1
    return true
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="px-6 pt-safe-top py-4 flex items-center justify-between">
        <Button
          variant="ghost"
          size="icon"
          onClick={prevStep}
          className={cn(step === 1 && 'invisible')}
        >
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex gap-2">
          {[1, 2, 3].map(s => (
            <div
              key={s}
              className={cn(
                "w-8 h-1 rounded-full transition-colors",
                s <= step ? "gradient-bg" : "bg-muted"
              )}
            />
          ))}
        </div>
        <div className="w-10" />
      </header>

      {/* Content */}
      <main className="flex-1 px-6 pb-6 overflow-auto">
        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              <div className="text-center space-y-2">
                <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center mx-auto">
                  <Music2 className="w-8 h-8 text-white" />
                </div>
                <h1 className="text-2xl font-bold">What do you love?</h1>
                <p className="text-muted-foreground">
                  Pick at least 3 genres you enjoy. We'll use this to personalize your experience.
                </p>
              </div>

              <div className="flex flex-wrap gap-2 justify-center">
                {GENRES.map(genre => (
                  <button
                    key={genre}
                    onClick={() => toggleGenre(genre)}
                    className={cn(
                      "px-4 py-2 rounded-full text-sm font-medium transition-all",
                      "border border-border hover:border-primary/50",
                      selectedGenres.includes(genre)
                        ? "gradient-bg text-white border-transparent"
                        : "bg-card hover:bg-accent"
                    )}
                  >
                    {genre}
                  </button>
                ))}
              </div>

              <p className="text-center text-sm text-muted-foreground">
                {selectedGenres.length}/3 minimum selected
              </p>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-8"
            >
              <div className="text-center space-y-2">
                <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center mx-auto">
                  <Sparkles className="w-8 h-8 text-white" />
                </div>
                <h1 className="text-2xl font-bold">Set your vibe</h1>
                <p className="text-muted-foreground">
                  Adjust these sliders to match your default listening preferences.
                </p>
              </div>

              <div className="space-y-8 max-w-sm mx-auto">
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Low Energy</span>
                    <span className="font-medium">Energy</span>
                    <span className="text-muted-foreground">High Energy</span>
                  </div>
                  <Slider
                    value={[vibes.energy]}
                    onValueChange={([v]) => setVibes(prev => ({ ...prev, energy: v }))}
                    max={100}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Calm</span>
                    <span className="font-medium">Mood</span>
                    <span className="text-muted-foreground">Hype</span>
                  </div>
                  <Slider
                    value={[vibes.mood]}
                    onValueChange={([v]) => setVibes(prev => ({ ...prev, mood: v }))}
                    max={100}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Familiar</span>
                    <span className="font-medium">Discovery</span>
                    <span className="text-muted-foreground">Adventurous</span>
                  </div>
                  <Slider
                    value={[vibes.discovery]}
                    onValueChange={([v]) => setVibes(prev => ({ ...prev, discovery: v }))}
                    max={100}
                    step={1}
                    className="w-full"
                  />
                </div>
              </div>
            </motion.div>
          )}

          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              <div className="text-center space-y-2">
                <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center mx-auto">
                  <Palette className="w-8 h-8 text-white" />
                </div>
                <h1 className="text-2xl font-bold">Create your moods</h1>
                <p className="text-muted-foreground">
                  Moods help your AI DJ understand what you want to hear. Create at least one.
                </p>
              </div>

              {/* Quick add presets */}
              <div className="space-y-2">
                <p className="text-sm font-medium">Quick add:</p>
                <div className="flex flex-wrap gap-2">
                  {MOOD_PRESETS.map(preset => (
                    <button
                      key={preset.name}
                      onClick={() => addMood(preset)}
                      disabled={moods.some(m => m.name === preset.name)}
                      className={cn(
                        "px-3 py-1.5 rounded-full text-sm flex items-center gap-1.5",
                        "border border-border transition-all",
                        moods.some(m => m.name === preset.name)
                          ? "opacity-50 cursor-not-allowed"
                          : "hover:border-primary/50 hover:bg-accent"
                      )}
                    >
                      <span>{preset.emoji}</span>
                      <span>{preset.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom mood input */}
              <div className="flex gap-2">
                <Input
                  placeholder="Custom mood name..."
                  value={newMoodName}
                  onChange={(e) => setNewMoodName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addMood()}
                />
                <Button onClick={() => addMood()} disabled={!newMoodName.trim()}>
                  Add
                </Button>
              </div>

              {/* Created moods */}
              <div className="space-y-2">
                <p className="text-sm font-medium">Your moods:</p>
                <div className="space-y-2">
                  {moods.map(mood => (
                    <div
                      key={mood.name}
                      className="flex items-center justify-between p-3 rounded-xl bg-card border border-border"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className="w-10 h-10 rounded-lg flex items-center justify-center text-lg"
                          style={{ backgroundColor: mood.color + '20', color: mood.color }}
                        >
                          {mood.emoji}
                        </div>
                        <span className="font-medium">{mood.name}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeMood(mood.name)}
                        disabled={moods.length <= 1}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer */}
      <footer className="px-6 pb-safe-bottom py-4">
        <Button
          onClick={nextStep}
          disabled={!canProceed()}
          className="w-full h-12 text-base font-semibold gradient-bg hover:opacity-90"
        >
          {step === 3 ? (
            <>
              <Sparkles className="w-5 h-5 mr-2" />
              Start Listening
            </>
          ) : (
            <>
              Continue
              <ChevronRight className="w-5 h-5 ml-2" />
            </>
          )}
        </Button>
      </footer>
    </div>
  )
}
